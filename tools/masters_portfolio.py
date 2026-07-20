#!/usr/bin/env python3
"""大师持仓跟踪 — SEC EDGAR 13F 机构持仓解析（巴菲特/李录等季度持仓与变动）。

与"四大师"定位天然契合：13F 是美股机构每季度向 SEC 强制披露的持仓快照，
本工具把它变成两类可直接引用的证据：
  1. holdings — 最新持仓清单（按市值权重排序，含前十集中度）
  2. diff     — 相邻两季对比（新建仓 / 清仓 / 显著加减仓）

内置大师（别名直接用）：
  berkshire  伯克希尔（巴菲特）
  himalaya   喜马拉雅资本（李录）
其他机构先用 search 找 CIK，再用 CIK 调 holdings/diff。

用法（由 Skills 自动调用）：
    python3 tools/masters_portfolio.py search 高瓴                 # 按名称找机构 CIK
    python3 tools/masters_portfolio.py holdings berkshire          # 最新一季持仓
    python3 tools/masters_portfolio.py holdings 0001061768 --top 30
    python3 tools/masters_portfolio.py diff berkshire              # 最近两季持仓变动

注意：13F 只覆盖美股多头（不含 A股/港股/债券/空头），披露滞后季末最多 45 天，
只能当"聪明钱方向参考"，不能当抄作业清单——大师买入成本与你不同。

依赖：零外部依赖（Python >= 3.8 标准库 + curl）。
退出码：0=成功 / 1=网络失败或无结果 / 2=参数错误。
"""

import argparse
import json
import os
import re
import sys
import time
from urllib.parse import quote

EXIT_OK = 0
EXIT_FAIL = 1
EXIT_BAD_ARGS = 2

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_CACHE_DIR = os.path.join(_ROOT, "data", "cache")
_TTL = 86400  # 13F 季度更新，列表/持仓缓存 1 天足够

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from filings_fetch import _curl, _curl_json, _EDGAR_UA  # noqa: E402  复用 curl 与 UA

# 内置大师别名 → CIK（EDGAR 官方编号）
_MASTERS = {
    "berkshire": ("0001067983", "Berkshire Hathaway（巴菲特）"),
    "himalaya": ("0001709323", "Himalaya Capital（李录）"),
}


# ---------------------------------------------------------------------------
# 缓存（与 filings_fetch 同风格，前缀区分）
# ---------------------------------------------------------------------------

def _cache_read(key):
    path = os.path.join(_CACHE_DIR, f"13f-{key}.json")
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
        with open(os.path.join(_CACHE_DIR, f"13f-{key}.json"), "w",
                  encoding="utf-8") as f:
            json.dump({"fetched_at": time.time(),
                       "fetched_date": time.strftime("%Y-%m-%d %H:%M"),
                       "payload": payload}, f, ensure_ascii=False)
    except OSError:
        pass


# ---------------------------------------------------------------------------
# CIK 解析与 13F 抓取
# ---------------------------------------------------------------------------

def _resolve_cik(who: str) -> tuple:
    """别名/CIK → (10位CIK, 展示名)。"""
    w = who.strip().lower()
    if w in _MASTERS:
        return _MASTERS[w]
    digits = re.sub(r"\D", "", who)
    if digits and len(digits) <= 10:
        return digits.zfill(10), f"CIK {digits.zfill(10)}"
    raise ValueError(f"无法识别机构: {who}（用别名 {'/'.join(_MASTERS)}，或先 search 拿 CIK）")


def cmd_search(name: str):
    """EDGAR 机构名称搜索（限定 13F 申报人）。"""
    url = ("https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&company="
           + quote(name) + "&type=13F&dateb=&owner=include&count=20&output=atom")
    raw = _curl(url, ua=_EDGAR_UA)
    hits = re.findall(r"<title>(.*?)</title>[\s\S]*?CIK=(\d{10})", raw)
    print("=" * 66)
    print(f"EDGAR 13F 申报机构搜索: {name}")
    print("=" * 66)
    seen = set()
    shown = 0
    for title, cik in hits:
        if cik in seen or "13F" in title:
            continue
        seen.add(cik)
        shown += 1
        print(f"  [{shown}] {title.strip()[:52]}  CIK={cik}")
    if not shown:
        print("  ⚠️ 未找到匹配机构（换英文注册名试试，如 Hillhouse / HHLR）")
        sys.exit(EXIT_FAIL)
    print()
    print("  查看持仓: python3 tools/masters_portfolio.py holdings <CIK>")


def _list_13f_filings(cik: str) -> list:
    """返回该 CIK 的 13F-HR 列表：[{date, period, accession}]（新→旧）。"""
    data = _curl_json(f"https://data.sec.gov/submissions/CIK{cik}.json", ua=_EDGAR_UA)
    recent = data.get("filings", {}).get("recent", {})
    out = []
    for i, form in enumerate(recent.get("form", [])):
        if form != "13F-HR":  # 只要原始申报，不要修正版 13F-HR/A 以免期次错位
            continue
        out.append({
            "date": recent["filingDate"][i],
            "period": recent.get("reportDate", [""] * 10 ** 6)[i],
            "accession": recent["accessionNumber"][i].replace("-", ""),
        })
    return out


def _fetch_infotable(cik: str, accession: str) -> list:
    """下载并解析 13F information table XML → [{issuer, class, cusip, value, shares, putcall}]。"""
    key = f"{cik}-{accession}-v2"
    cached = _cache_read(key)
    if cached is not None:
        return cached

    idx = _curl_json(
        f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{accession}/index.json",
        ua=_EDGAR_UA)
    xml_name = None
    for item in idx.get("directory", {}).get("item", []):
        n = item.get("name", "")
        # 信息表命名不统一（infotable/form13fInfoTable/...），排除首要文档 primary_doc
        if n.lower().endswith(".xml") and "primary_doc" not in n.lower():
            xml_name = n
            break
    if not xml_name:
        raise ConnectionError("该 13F 申报未找到 information table XML")
    raw = _curl(
        f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{accession}/{xml_name}",
        ua=_EDGAR_UA)

    rows = []
    for block in re.findall(r"<(?:\w+:)?infoTable>([\s\S]*?)</(?:\w+:)?infoTable>", raw):
        def _tag(name):
            m = re.search(rf"<(?:\w+:)?{name}>([\s\S]*?)</(?:\w+:)?{name}>", block)
            return m.group(1).strip() if m else ""
        try:
            value = float(_tag("value"))
            shares = float(_tag("sshPrnamt") or 0)
        except ValueError:
            continue
        rows.append({
            "issuer": re.sub(r"\s+", " ", _tag("nameOfIssuer")),
            "class": _tag("titleOfClass"),
            "cusip": _tag("cusip").upper(),
            "value": value,
            "shares": shares,
            "putcall": _tag("putCall"),
        })
    if rows:
        _cache_write(key, rows)
    return rows


def _aggregate(rows: list) -> dict:
    """按发行人聚合：键用 CUSIP 前6位（发行人唯一码，免受名称写法波动影响）；
    期权单独成键不并入多头。返回 {键: {name, value, shares}}。"""
    agg = {}
    for r in rows:
        base = (r.get("cusip") or "")[:6] or r["issuer"]
        key = f"{base}|{r['putcall']}" if r["putcall"] else base
        name = f"{r['issuer']} [{r['putcall']}]" if r["putcall"] else r["issuer"]
        a = agg.setdefault(key, {"name": name, "value": 0.0, "shares": 0.0})
        a["name"] = name  # 同一发行人多行时保留最后见到的名称
        a["value"] += r["value"]
        a["shares"] += r["shares"]
    return agg


def _fmt_value(v: float) -> str:
    """13F value 2023 起为美元全额（更早年份为千美元，本工具主用近期数据）。"""
    if v >= 1e9:
        return f"{v/1e9:.1f}B"
    if v >= 1e6:
        return f"{v/1e6:.0f}M"
    return f"{v:,.0f}"


def cmd_holdings(who: str, top: int, quarter=None):
    cik, label = _resolve_cik(who)
    filings = _list_13f_filings(cik)
    if not filings:
        print(f"❌ {label} 无 13F-HR 申报记录（可能非 13F 义务机构）")
        sys.exit(EXIT_FAIL)
    target = filings[0]
    if quarter:  # YYYYQn → 匹配 reportDate 所在季度
        m = re.match(r"(\d{4})Q([1-4])", quarter.upper())
        if not m:
            print("❌ --quarter 格式: 2026Q1")
            sys.exit(EXIT_BAD_ARGS)
        month_end = {"1": "03", "2": "06", "3": "09", "4": "12"}[m.group(2)]
        prefix = f"{m.group(1)}-{month_end}"
        match = [f for f in filings if f["period"].startswith(prefix)]
        if not match:
            print(f"❌ 未找到 {quarter} 期 13F（可用期次: {', '.join(f['period'] for f in filings[:8])}）")
            sys.exit(EXIT_FAIL)
        target = match[0]

    rows = _fetch_infotable(cik, target["accession"])
    agg = _aggregate(rows)
    total = sum(a["value"] for a in agg.values())
    ranked = sorted(agg.items(), key=lambda kv: -kv[1]["value"])

    print("=" * 72)
    print(f"13F 持仓: {label} — 报告期 {target['period']}（申报日 {target['date']}）")
    print("=" * 72)
    print(f"  组合市值: ${_fmt_value(total)}，共 {len(ranked)} 个头寸")
    print()
    print(f"  {'#':>3s} {'发行人':32s} {'市值':>10s} {'权重':>7s}")
    print("  " + "-" * 58)
    for i, (_key, a) in enumerate(ranked[:top], 1):
        w = a["value"] / total * 100 if total else 0
        print(f"  {i:>3d} {a['name'][:32]:32s} {_fmt_value(a['value']):>10s} {w:>6.1f}%")
    top10 = sum(a["value"] for _n, a in ranked[:10]) / total * 100 if total else 0
    print()
    print(f"  前十集中度: {top10:.0f}%")
    print("  ⚠️ 13F 只含美股多头，滞后最多45天；参考方向，不可直接抄作业")


def cmd_diff(who: str, threshold: float):
    cik, label = _resolve_cik(who)
    filings = _list_13f_filings(cik)
    if len(filings) < 2:
        print(f"❌ {label} 13F 申报不足两期，无法对比")
        sys.exit(EXIT_FAIL)
    new_f, old_f = filings[0], filings[1]
    new_agg = _aggregate(_fetch_infotable(cik, new_f["accession"]))
    old_agg = _aggregate(_fetch_infotable(cik, old_f["accession"]))
    new_total = sum(a["value"] for a in new_agg.values()) or 1
    old_total = sum(a["value"] for a in old_agg.values()) or 1

    opened = sorted([(n, a) for n, a in new_agg.items() if n not in old_agg],
                    key=lambda kv: -kv[1]["value"])
    closed = sorted([(n, a) for n, a in old_agg.items() if n not in new_agg],
                    key=lambda kv: -kv[1]["value"])
    changed = []
    for n, a in new_agg.items():
        o = old_agg.get(n)
        if not o or not o["shares"] or not a["shares"]:
            continue
        chg = a["shares"] / o["shares"] - 1
        if abs(chg) >= threshold:
            changed.append((a["name"], chg, a["value"] / new_total * 100))
    changed.sort(key=lambda x: -abs(x[1]))

    print("=" * 72)
    print(f"13F 持仓变动: {label} — {old_f['period']} → {new_f['period']}")
    print("=" * 72)
    print(f"  组合市值: ${_fmt_value(old_total)} → ${_fmt_value(new_total)}")
    print()
    if opened:
        print(f"  🆕 新建仓（{len(opened)} 个）：")
        for _n, a in opened[:10]:
            print(f"     + {a['name'][:40]:40s} ${_fmt_value(a['value'])}（权重 {a['value']/new_total*100:.1f}%）")
    if closed:
        print(f"  🚪 清仓（{len(closed)} 个）：")
        for _n, a in closed[:10]:
            print(f"     - {a['name'][:40]:40s} 原持 ${_fmt_value(a['value'])}")
    if changed:
        print(f"  🔁 加减仓（股数变动 ≥{threshold*100:.0f}%）：")
        for n, chg, w in changed[:12]:
            arrow = "加仓" if chg > 0 else "减仓"
            print(f"     {arrow} {n[:38]:38s} 股数 {chg*100:+.0f}%（现权重 {w:.1f}%）")
    if not (opened or closed or changed):
        print("  ✅ 两季持仓无显著变动（按股数阈值）")
    print()
    print("  解读: 新建仓/大幅加仓标的可作为研究线索（说\"研究 XX\"），清仓需区分")
    print("  估值兑现与逻辑变化——大师卖出理由不会写在 13F 里")


# ---------------------------------------------------------------------------
# CLI 入口
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="大师持仓跟踪 — SEC EDGAR 13F 解析",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s holdings berkshire
  %(prog)s holdings himalaya --top 15
  %(prog)s holdings 0001061768 --quarter 2026Q1
  %(prog)s diff berkshire
  %(prog)s search Hillhouse
        """)
    sub = parser.add_subparsers(dest="command")

    p_h = sub.add_parser("holdings", help="最新一季持仓清单")
    p_h.add_argument("who", help=f"别名（{'/'.join(_MASTERS)}）或 CIK")
    p_h.add_argument("--top", type=int, default=20, help="展示前 N 大持仓（默认20）")
    p_h.add_argument("--quarter", default=None, help="指定报告期，如 2026Q1（默认最新）")

    p_d = sub.add_parser("diff", help="最近两季持仓变动")
    p_d.add_argument("who", help=f"别名（{'/'.join(_MASTERS)}）或 CIK")
    p_d.add_argument("--threshold", type=float, default=0.10,
                     help="加减仓股数变动阈值（默认0.10=10%%）")

    p_s = sub.add_parser("search", help="按名称搜索 13F 申报机构")
    p_s.add_argument("name", help="机构名称（英文注册名命中率更高）")

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        sys.exit(EXIT_BAD_ARGS)

    try:
        if args.command == "holdings":
            cmd_holdings(args.who, args.top, args.quarter)
        elif args.command == "diff":
            cmd_diff(args.who, args.threshold)
        else:
            cmd_search(args.name)
        sys.exit(EXIT_OK)
    except ValueError as e:
        print(f"❌ {e}")
        sys.exit(EXIT_BAD_ARGS)
    except (ConnectionError, json.JSONDecodeError) as e:
        print(f"❌ 接口请求失败: {e}", file=sys.stderr)
        print("   降级路径：WebSearch「{机构名} 13F latest quarter」（whalewisdom/dataroma 等聚合站）",
              file=sys.stderr)
        sys.exit(EXIT_FAIL)


if __name__ == "__main__":
    main()
