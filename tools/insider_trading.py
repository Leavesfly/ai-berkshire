#!/usr/bin/env python3
"""内部人交易与股东行为信号 — 三市场内部人买卖事实管道。

把"管理层/大股东在用真金白银投票"变成可引用的客观证据，直接服务
management-deep-dive（管理层本分吗）/ thesis-tracker（红线：大规模减持）/
investment-research（股东利益一致性）/ news-pulse（异动归因）等流程。

数据源（全部为免费官方/准官方渠道）：
  - 美股：SEC EDGAR Form 4（内部人持股变动声明，交易后 2 个工作日内强制披露）
  - A股：东方财富数据中心（股东增减持明细，源自巨潮公告）
  - 港股：披露易股份变动披露文件列表（翌日披露报表/证券变动月报表；≥5%权益明细以官网为准）

用法（由 Skills 自动调用）：
    python3 tools/insider_trading.py recent usAAPL --days 180     # 美股内部人近半年交易
    python3 tools/insider_trading.py recent 300750 --days 90      # A股股东增减持
    python3 tools/insider_trading.py recent hk00700               # 港股股份变动披露文件
    python3 tools/insider_trading.py recent usTSLA --only sell    # 只看卖出

解读纪律（必须随结论声明）：
  - 内部人**卖出**理由多样（缴税/行权/分散/个人流动性），单笔减持≠看空；
    但**多名高管同期、非计划性、大幅**减持是 thesis-tracker 的强警告信号。
  - 内部人**买入**信号通常更强——没人会为了打压股价而真金白银买自家股票。
  - 美股 Form 4 中 A（授予）/F（缴税代扣）非自主买卖，统计净买卖时已剔除。

依赖：零外部依赖（Python >= 3.9 标准库 + curl）。
退出码：0=成功 / 1=网络失败或无结果 / 2=参数错误。
"""

import argparse
import json
import os
import re
import sys
import time
from datetime import datetime, timedelta

from core.market import detect_market_type, normalize_code
from utils import EDGAR_UA as _EDGAR_UA
from utils import EXIT_BAD_ARGS, EXIT_FAIL, EXIT_OK
from utils import curl_get as _curl
from utils import curl_get_json as _curl_json

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_CACHE_DIR = os.path.join(_ROOT, "data", "cache")
_TTL = 86400  # 内部人交易列表缓存 1 天
_TIMEOUT = 20

# Form 4 交易代码 → 中文标签（SEC 官方 transactionCode 枚举）
_TXN_CODES = {
    "P": "买入",
    "S": "卖出",
    "A": "授予",
    "G": "赠与",
    "F": "缴税代扣",
    "D": "处置",
    "M": "行权",
    "E": "到期",
    "C": "转换",
    "X": "行权",
}
# 自主买卖（计入净买卖统计）；A/F/M/G/D 等为被动/非自主，单列不计入
_OPEN_MARKET = {"P": "买入", "S": "卖出"}


# ---------------------------------------------------------------------------
# 缓存（与 masters_portfolio 同风格，前缀 insider-）
# ---------------------------------------------------------------------------


def _cache_read(key):
    path = os.path.join(_CACHE_DIR, f"insider-{key}.json")
    try:
        with open(path, encoding="utf-8") as f:
            entry = json.load(f)
        if time.time() - entry["fetched_at"] <= _TTL:
            return entry["payload"]
    except (OSError, json.JSONDecodeError, KeyError):
        pass
    return None


def _cache_write(key, payload):
    try:
        os.makedirs(_CACHE_DIR, exist_ok=True)
        with open(os.path.join(_CACHE_DIR, f"insider-{key}.json"), "w", encoding="utf-8") as f:
            json.dump(
                {
                    "fetched_at": time.time(),
                    "fetched_date": time.strftime("%Y-%m-%d %H:%M"),
                    "payload": payload,
                },
                f,
                ensure_ascii=False,
            )
    except OSError:
        pass


def _safe_key(code: str) -> str:
    return "".join(ch for ch in code.lower() if ch.isalnum() or ch in "._-")


# ---------------------------------------------------------------------------
# 美股：SEC EDGAR Form 4
# ---------------------------------------------------------------------------


def _edgar_cik(ticker: str) -> str:
    """ticker → 10 位 CIK（公司清单缓存 1 天）。"""
    tickers = _cache_read("edgar-tickers")
    if tickers is None:
        data = _curl_json("https://www.sec.gov/files/company_tickers.json", ua=_EDGAR_UA)
        tickers = {v["ticker"].upper(): v["cik_str"] for v in data.values()}
        _cache_write("edgar-tickers", tickers)
    cik = tickers.get(ticker.upper()) or tickers.get(ticker.upper().replace(".", "-"))
    if cik is None:
        raise ValueError(f"EDGAR 未找到 ticker: {ticker}")
    return str(cik).zfill(10)


def _list_form4(cik: str, days: int, limit: int) -> list:
    """返回该公司 Form 4 列表（新→旧）：[{date, accession}]，限最近 days 天。

    大发行人（如 AAPL）申报量超过 EDGAR recent 窗口（约1000条），Form 4 会被
    分页到 filings.files 指向的历史文件，需逐个追加拉取直到越过时间窗口。
    """
    data = _curl_json(f"https://data.sec.gov/submissions/CIK{cik}.json", ua=_EDGAR_UA)
    filings_obj = data.get("filings", {})
    recent = filings_obj.get("recent", {})

    def _collect(src):
        hits, crossed = [], False
        forms = src.get("form", [])
        dates = src.get("filingDate", [])
        accs = src.get("accessionNumber", [])
        for i, f in enumerate(forms):
            # EDGAR submissions API 中 Form 4 的 form 字段为 "4"（修正版为 "4/A"）
            if f not in ("4", "4/A"):
                continue
            date = dates[i]
            if date < cutoff:
                crossed = True  # 各源按申报日降序，越过窗口即可停
                break
            hits.append({"date": date, "accession": accs[i].replace("-", "")})
            if len(hits) >= limit:
                crossed = True
                break
        return hits, crossed

    cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    out, crossed = _collect(recent)
    # 仅当 recent 未覆盖目标窗口时才惰性拉取分页历史文件（避免大发行人无谓下载）
    for meta in filings_obj.get("files", []):
        if crossed or len(out) >= limit:
            break
        name = meta.get("name")
        if not name:
            continue
        sub = _curl_json(f"https://data.sec.gov/submissions/{name}", ua=_EDGAR_UA)
        src = sub.get("recent", sub) if isinstance(sub, dict) else {}
        hits, crossed = _collect(src)
        out.extend(hits)
    return out[:limit]


def _parse_form4_xml(raw: str) -> dict:
    """解析 Form 4 ownership XML → {issuer, owner, title, period, transactions:[...]}。

    兼容带/不带命名空间前缀（<owner> 与 <ns:owner>）；衍生交易表不解析（期权行权
    多为被动，且 transactionCode 与现股表语义不同，避免污染净买卖统计）。
    """

    def _tag(block, name):
        """取 <name> 文本；兼容包装型（<name><value>x</value></name>）与平铺型（<name>x</name>）。"""
        m = re.search(rf"<(?:\w+:)?{name}[^>]*>([\s\S]*?)</(?:\w+:)?{name}>", block)
        if not m:
            return ""
        inner = m.group(1).strip()
        v = re.search(r"<(?:\w+:)?value[^>]*>([\s\S]*?)</(?:\w+:)?value>", inner)
        return (v.group(1).strip() if v else inner)

    issuer_m = re.search(r"<(?:\w+:)?issuer>([\s\S]*?)</(?:\w+:)?issuer>", raw)
    owner_m = re.search(r"<(?:\w+:)?reportingOwner>([\s\S]*?)</(?:\w+:)?reportingOwner>", raw)
    issuer = _tag(issuer_m.group(1), "issuerName") if issuer_m else ""
    owner = title = ""
    if owner_m:
        ob = owner_m.group(1)
        owner = _tag(ob, "rptOwnerName")
        title_m = re.search(r"<(?:\w+:)?officerTitle>([\s\S]*?)</(?:\w+:)?officerTitle>", ob)
        if title_m:
            title = title_m.group(1).strip()
        elif re.search(r"<(?:\w+:)?isDirector[^>]*>(?:true|1)", ob, re.I):
            title = "Director"

    period_m = re.search(r"<(?:\w+:)?periodOfReport>([\s\S]*?)</(?:\w+:)?periodOfReport>", raw)
    period = period_m.group(1).strip() if period_m else ""

    txns = []
    nd_m = re.search(
        r"<(?:\w+:)?nonDerivativeTable>([\s\S]*?)</(?:\w+:)?nonDerivativeTable>", raw
    )
    if nd_m:
        for tm in re.finditer(
            r"<(?:\w+:)?nonDerivativeTransaction>([\s\S]*?)"
            r"</(?:\w+:)?nonDerivativeTransaction>",
            nd_m.group(1),
        ):
            b = tm.group(1)

            def _f(name, block=b):
                return _tag(block, name)

            try:
                shares = float(_f("transactionShares") or 0)
            except ValueError:
                shares = 0.0
            try:
                price = float(_f("transactionPricePerShare") or 0)
            except ValueError:
                price = 0.0
            txns.append(
                {
                    "code": _f("transactionCode"),
                    "date": _f("transactionDate"),
                    "shares": shares,
                    "price": price,
                    "acquired_disposed": _f("transactionAcquiredDisposedCode"),
                    "owned_after": _f("sharesOwnedFollowingTransaction"),
                }
            )
    return {"issuer": issuer, "owner": owner, "title": title, "period": period, "transactions": txns}


def classify_txn(code: str) -> str:
    """交易代码 → 中文标签（未知代码归为「其他」）。"""
    return _TXN_CODES.get(code, "其他")


def aggregate_form4(txns: list) -> list:
    """按 (内部人, 交易类型) 聚合：返回 [{owner, title, code, label, shares, avg_price, dates}]。"""
    agg = {}
    for t in txns:
        key = (t["owner"], t["code"])
        a = agg.setdefault(
            key,
            {
                "owner": t["owner"],
                "title": t["title"],
                "code": t["code"],
                "label": classify_txn(t["code"]),
                "shares": 0.0,
                "_value": 0.0,
                "dates": [],
            },
        )
        a["title"] = a["title"] or t["title"]
        a["shares"] += t["shares"]
        a["_value"] += t["shares"] * t["price"]
        if t["date"]:
            a["dates"].append(t["date"])
    out = []
    for a in agg.values():
        a["avg_price"] = a["_value"] / a["shares"] if a["shares"] else 0.0
        a["date"] = min(a["dates"]) if a["dates"] else ""
        a.pop("_value", None)
        a.pop("dates", None)
        out.append(a)
    out.sort(key=lambda x: -x["shares"])
    return out


def net_summary(txns: list) -> dict:
    """净买卖统计（仅计 P/S 自主买卖）：{buy_shares, sell_shares, net, buy_n, sell_n}。"""
    buy_shares = sell_shares = 0.0
    buy_n = sell_n = 0
    for t in txns:
        if t["code"] == "P":
            buy_shares += t["shares"]
            buy_n += 1
        elif t["code"] == "S":
            sell_shares += t["shares"]
            sell_n += 1
    return {
        "buy_shares": buy_shares,
        "sell_shares": sell_shares,
        "net": buy_shares - sell_shares,
        "buy_n": buy_n,
        "sell_n": sell_n,
    }


def _fmt_shares(v: float) -> str:
    v = abs(v)
    if v >= 1e6:
        return f"{v / 1e6:.1f}M"
    if v >= 1e3:
        return f"{v / 1e3:.0f}K"
    return f"{v:,.0f}"


def _us_recent(code: str, days: int, limit: int, only: str):
    ticker = code.strip().upper()[2:]
    cik = _edgar_cik(ticker)
    filings = _list_form4(cik, days, limit)
    print("=" * 72)
    print(f"内部人交易（美股 Form 4）: {ticker} — 近 {days} 天，共 {len(filings)} 份申报")
    print("=" * 72)
    if not filings:
        print("  ⚠️ 该窗口内无 Form 4 申报（内部人未发生持股变动）")
        return

    all_txns, seen_owner = [], set()
    for f in filings:
        key = f"{cik}-{f['accession']}"
        cached = _cache_read(key)
        if cached is not None:
            parsed = cached
        else:
            raw = _curl(
                f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{f['accession']}/"
                f"{_primary_doc(cik, f['accession'])}",
                ua=_EDGAR_UA,
            )
            parsed = _parse_form4_xml(raw)
            parsed["filing_date"] = f["date"]
            if parsed["transactions"]:
                _cache_write(key, parsed)
        for t in parsed.get("transactions", []):
            t["owner"] = t.get("owner") or parsed.get("owner", "")
            t["title"] = t.get("title") or parsed.get("title", "")
            if not t["owner"]:
                t["owner"] = parsed.get("owner", "(未知)")
            all_txns.append(t)
        if parsed.get("owner"):
            seen_owner.add(parsed["owner"])

    if only in ("buy", "sell"):
        want = "P" if only == "buy" else "S"
        all_txns = [t for t in all_txns if t["code"] == want]

    summary = net_summary(all_txns)
    net = summary["net"]
    verdict = "净买入 🟢" if net > 0 else ("净卖出 🔴" if net < 0 else "无自主买卖")
    print(
        f"  自主买卖（P/S）: 买入 {_fmt_shares(summary['buy_shares'])} 股"
        f"（{summary['buy_n']} 笔） / 卖出 {_fmt_shares(summary['sell_shares'])} 股"
        f"（{summary['sell_n']} 笔） → {verdict}"
    )
    print(f"  涉及内部人: {len(seen_owner)} 位")
    print()

    rows = aggregate_form4(all_txns)
    if rows:
        print(f"  {'内部人':24s} {'职务':16s} {'类型':6s} {'股数':>9s} {'均价':>9s}")
        print("  " + "-" * 70)
        for a in rows[:20]:
            price = f"${a['avg_price']:.2f}" if a["avg_price"] else "-"
            print(
                f"  {a['owner'][:24]:24s} {(a['title'] or '-')[:16]:16s} "
                f"{a['label']:6s} {_fmt_shares(a['shares']):>9s} {price:>9s}"
            )
    else:
        print("  （该窗口内无匹配的内部人交易）")
    print()
    print("  解读: 买入信号通常强于卖出；A(授予)/F(缴税)/M(行权)为非自主，不计入净买卖。")
    print("  多名高管同期非计划性大幅减持 → thesis-tracker 强警告，须逐条核对论文红线。")


def _primary_doc(cik: str, accession: str) -> str:
    """定位 Form 4 申报的主文档（ownership XML，通常名为 *primary_doc.xml）。"""
    idx = _curl_json(
        f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{accession}/index.json",
        ua=_EDGAR_UA,
    )
    names = [it.get("name", "") for it in idx.get("directory", {}).get("item", [])]
    for n in names:
        if n.lower().endswith(".xml") and "primary_doc" in n.lower():
            return n
    for n in names:
        if n.lower().endswith(".xml"):
            return n
    raise ConnectionError("该 Form 4 申报未找到 XML 文档")


# ---------------------------------------------------------------------------
# A股：东方财富数据中心（股东增减持明细）
# ---------------------------------------------------------------------------


def parse_eastmoney_holder(rows: list) -> list:
    """东财 RPT_EXECUTIVE_HOLD_DETAILS 行 → 标准化增减持记录。

    返回 [{holder, position, date, shares, price, ratio, reason, direction}]，按日期降序。
    字段缺失时容错（价格/比例可能为空）；CHANGE_SHARES 正=增持 负=减持。
    """
    out = []
    for r in rows or []:
        try:
            shares = float(r.get("CHANGE_SHARES") or 0)
        except (TypeError, ValueError):
            continue
        if shares == 0:
            continue
        try:
            price = float(r.get("AVERAGE_PRICE") or 0)
        except (TypeError, ValueError):
            price = 0.0
        try:
            ratio = float(r.get("CHANGE_RATIO") or 0)
        except (TypeError, ValueError):
            ratio = 0.0
        out.append(
            {
                "holder": r.get("PERSON_NAME") or "(未知)",
                "position": r.get("POSITION_NAME") or "",
                "date": (r.get("CHANGE_DATE") or "")[:10],
                "shares": shares,
                "price": price,
                "ratio": ratio,  # 变动占持股比例（小数）
                "reason": r.get("CHANGE_REASON") or "",
                "direction": "增持" if shares > 0 else "减持",
            }
        )
    out.sort(key=lambda x: x["date"], reverse=True)
    return out


def _a_recent(code: str, days: int, limit: int, only: str):
    from urllib.parse import urlencode

    code_clean = normalize_code(code)
    params = {
        "sortColumns": "CHANGE_DATE",
        "sortTypes": "-1",
        "pageSize": "200",
        "pageNumber": "1",
        "reportName": "RPT_EXECUTIVE_HOLD_DETAILS",
        "columns": "ALL",
        "source": "WEB",
        "client": "WEB",
        "filter": f'(SECURITY_CODE="{code_clean}")',
    }
    data = _curl_json("https://datacenter-web.eastmoney.com/api/data/v1/get?" + urlencode(params))
    rows = parse_eastmoney_holder(((data or {}).get("result") or {}).get("data") or [])
    cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    rows = [r for r in rows if r["date"] >= cutoff]
    if only == "buy":
        rows = [r for r in rows if r["direction"] == "增持"]
    elif only == "sell":
        rows = [r for r in rows if r["direction"] == "减持"]

    print("=" * 72)
    print(f"股东增减持（A股）: {code_clean} — 近 {days} 天，共 {len(rows)} 笔")
    print("=" * 72)
    if not rows:
        print("  ⚠️ 该窗口内无董监高/股东增减持记录（或东财接口暂无数据）")
        print("  降级路径：WebSearch「{公司名} 股东增减持公告」或巨潮资讯股东变动公告")
        return
    inc = sum(r["shares"] for r in rows if r["direction"] == "增持")
    dec = sum(r["shares"] for r in rows if r["direction"] == "减持")
    print(f"  合计: 增持 {_fmt_shares(inc)} 股 / 减持 {_fmt_shares(dec)} 股")
    print()
    print(f"  {'日期':12s} {'股东/董监高':16s} {'职务':12s} {'方向':6s} {'变动股数':>12s} {'均价':>9s} {'途径':10s}")
    print("  " + "-" * 78)
    for r in rows[:limit]:
        price = f"{r['price']:.2f}" if r["price"] else "-"
        print(
            f"  {r['date']:12s} {r['holder'][:16]:16s} {(r['position'] or '-')[:12]:12s} "
            f"{r['direction']:6s} {r['shares']:>12,.0f} {price:>9s} {(r['reason'] or '-')[:10]:10s}"
        )
    print()
    print("  解读: 实控人/核心高管增持是较强正面信号；多名高管同期减持须回到论文红线核对。")


# ---------------------------------------------------------------------------
# 港股：披露易「披露权益」文件列表
# ---------------------------------------------------------------------------


def _hk_stock_id(code_num: str) -> str:
    from urllib.parse import urlencode

    raw = _curl(
        "https://www1.hkexnews.hk/search/prefix.do?"
        + urlencode(
            {
                "callback": "cb",
                "lang": "ZH",
                "type": "A",
                "name": code_num.zfill(5),
                "market": "SEHK",
            }
        )
    )
    m = re.search(r"\((.*)\)\s*;?\s*$", raw, re.S)
    if not m:
        raise ConnectionError("披露易 stockId 接口响应异常")
    info = json.loads(m.group(1)).get("stockInfo") or []
    if not info:
        raise ValueError(f"披露易未找到港股代码: {code_num}")
    return str(info[0]["stockId"])


def _hk_recent(code: str, days: int, limit: int):
    from urllib.parse import urlencode

    cu = code.strip().upper()
    code_num = cu[:-3] if cu.endswith(".HK") else cu[2:]
    stock_id = _hk_stock_id(code_num)
    params = {
        "sortDir": "0",
        "sortByOptions": "DateTime",
        "category": "0",
        "market": "SEHK",
        "stockId": stock_id,
        "documentType": "-1",
        "fromDate": (datetime.now() - timedelta(days=days)).strftime("%Y%m%d"),
        "toDate": datetime.now().strftime("%Y%m%d"),
        "title": "",
        "searchType": "1",
        "t1code": "40500",  # 股本变动披露类（翌日披露报表/证券变动月报表）
        "t2Gcode": "-2",
        "t2code": "-2",
        "rowRange": "30",
        "lang": "ZH",
    }
    data = _curl_json("https://www1.hkexnews.hk/search/titleSearchServlet.do?" + urlencode(params))
    results = data.get("result")
    rows = json.loads(results) if isinstance(results, str) else (results or [])

    print("=" * 72)
    print(f"股份变动披露文件（港股）: {code_num} — 近 {days} 天")
    print("=" * 72)
    # 披露易返回的股本变动类文件：翌日披露报表 / 证券变动月报表 / 权益披露
    _KW = ("披露", "證券變動", "证券变动", "股份變動", "股份变动", "權益", "权益")
    items = []
    for r in rows:
        link = (r.get("FILE_LINK") or "").strip()
        title = re.sub("<[^>]+>", " ", r.get("TITLE", "")).strip()
        if not link or not any(k in title for k in _KW):
            continue
        if not link.startswith("http"):
            link = "https://www1.hkexnews.hk" + ("" if link.startswith("/") else "/") + link
        date_raw = (r.get("DATE_TIME", "") or "").split(" ")[0]
        parts = date_raw.split("/")
        date = f"{parts[2]}-{parts[1]}-{parts[0]}" if len(parts) == 3 else date_raw
        items.append((date, title, link))
    if not items:
        print("  ⚠️ 该窗口内未检索到股份变动披露文件")
        print("  降级路径：披露易官网「披露权益」检索（www.hkexnews.hk）按公司逐条核对")
        return
    print(f"  共 {len(items)} 份股份变动披露文件（翌日披露报表/证券变动月报表）：")
    print()
    for i, (date, title, link) in enumerate(items[:limit], 1):
        print(f"  [{i}] {date}  {title[:56]}")
        print(f"      {link}")
    print()
    print("  解读: 港股以「翌日披露报表」与「证券变动月报表」披露已发行股份变动（回购/增发/")
    print("  董事持股）；大股东≥5%权益变动以披露易「披露权益」原文为准，本工具仅做文件索引。")


# ---------------------------------------------------------------------------
# 统一入口
# ---------------------------------------------------------------------------


def cmd_recent(code: str, days: int, limit: int, only: str):
    mkt = detect_market_type(code)
    if only not in ("all", "buy", "sell"):
        print("❌ --only 仅支持: all / buy / sell")
        sys.exit(EXIT_BAD_ARGS)
    if days <= 0:
        print("❌ --days 必须为正整数")
        sys.exit(EXIT_BAD_ARGS)
    if mkt == "US":
        _us_recent(code, days, limit, only)
    elif mkt == "A":
        _a_recent(code, days, limit, only)
    else:
        if only != "all":
            print("  提示: 港股仅索引权益披露文件，--only 过滤不适用，已忽略")
        _hk_recent(code, days, limit)


def main():
    parser = argparse.ArgumentParser(
        description="内部人交易与股东行为信号 — 美股Form4 / A股增减持 / 港股权益披露",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s recent usAAPL --days 180
  %(prog)s recent 300750 --days 90
  %(prog)s recent hk00700
  %(prog)s recent usTSLA --only sell --limit 30
        """,
    )
    sub = parser.add_subparsers(dest="command")

    p_r = sub.add_parser("recent", help="最近内部人/股东交易信号")
    p_r.add_argument("code", help="股票代码（600519 / hk00700 / usAAPL）")
    p_r.add_argument("--days", type=int, default=90, help="回溯天数（默认90）")
    p_r.add_argument("--limit", type=int, default=20, help="展示条数（默认20）")
    p_r.add_argument("--only", default="all", help="all / buy / sell（默认all）")

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        sys.exit(EXIT_BAD_ARGS)

    try:
        cmd_recent(args.code, args.days, args.limit, args.only)
        sys.exit(EXIT_OK)
    except ValueError as e:
        print(f"❌ {e}")
        sys.exit(EXIT_BAD_ARGS)
    except (ConnectionError, json.JSONDecodeError) as e:
        print(f"❌ 接口请求失败: {e}", file=sys.stderr)
        print(
            "   降级路径：WebSearch「{公司名} 内部人交易/股东增减持」（美股 openinsider、"
            "A股巨潮、港股披露易）",
            file=sys.stderr,
        )
        sys.exit(EXIT_FAIL)


if __name__ == "__main__":
    main()
