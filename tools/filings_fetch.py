#!/usr/bin/env python3
"""一手财报原文管道 — SEC EDGAR(美股) + 巨潮资讯(A股) + 披露易(港股)。

为 Claude Code Skills 提供上市公司**官方披露原文**的检索与下载能力，
让 earnings-review / management-deep-dive 等流程可以直读一手资料
（MD&A、附注、股权激励、关联交易等接口数据看不到的信息）。

数据源（全部为免费官方/准官方渠道）：
  - 美股：SEC EDGAR（data.sec.gov，10-K/10-Q/8-K/DEF 14A 结构化索引）
  - A股：巨潮资讯（cninfo.com.cn，年报/半年报/季报 PDF）
  - 港股：披露易（hkexnews.hk，年报/中期报告 PDF）

用法（由 Skills 自动调用）：
    python3 tools/filings_fetch.py list usAAPL --type 10-K --limit 5    # 列出美股最近披露
    python3 tools/filings_fetch.py list 600519 --type annual            # A股年报列表
    python3 tools/filings_fetch.py list hk00700 --type annual           # 港股年报列表
    python3 tools/filings_fetch.py fetch usAAPL --type 10-K --latest    # 下载最新一份
    python3 tools/filings_fetch.py fetch --url <list输出的链接> --output data/filings/x.pdf

下载文件默认保存到 data/filings/{代码}/，PDF 可交给 pdf 解析能力提取正文。
列表结果带本地缓存（TTL 1 天）；加 --no-cache 强制直连。

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
from urllib.parse import urlencode

from utils import EDGAR_UA as _EDGAR_UA
from utils import EXIT_BAD_ARGS, EXIT_FAIL, EXIT_OK
from utils import curl_get as _curl_base
from utils import curl_get_json as _curl_json_base

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_CACHE_DIR = os.path.join(_ROOT, "data", "cache")
_FILINGS_DIR = os.path.join(_ROOT, "data", "filings")
_TTL_LIST = 86400  # 披露列表缓存 1 天
_TIMEOUT = 20  # 财报文件下载超时（比默认 15s 稍宽）


# ---------------------------------------------------------------------------
# curl 直连（委托 utils 统一实现，本模块默认超时 20s）
# ---------------------------------------------------------------------------


def _curl(url, post_data=None, ua=None, binary=False):
    """curl 取数；post_data 非空时发 POST 表单；binary=True 返回 bytes。"""
    return _curl_base(url, post_data=post_data, ua=ua, binary=binary, timeout=_TIMEOUT, retries=0)


def _curl_json(url, post_data=None, ua=None):
    return _curl_json_base(url, post_data=post_data, ua=ua, timeout=_TIMEOUT, retries=0)


# ---------------------------------------------------------------------------
# 轻量缓存（列表类结果，TTL 1 天）
# ---------------------------------------------------------------------------


def _cache_read(key):
    path = os.path.join(_CACHE_DIR, f"filings-{key}.json")
    try:
        with open(path, encoding="utf-8") as f:
            entry = json.load(f)
        if time.time() - entry["fetched_at"] <= _TTL_LIST:
            return entry["payload"]
    except (OSError, json.JSONDecodeError, KeyError):
        pass
    return None


def _cache_write(key, payload):
    try:
        os.makedirs(_CACHE_DIR, exist_ok=True)
        path = os.path.join(_CACHE_DIR, f"filings-{key}.json")
        with open(path, "w", encoding="utf-8") as f:
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


# ---------------------------------------------------------------------------
# 市场识别（与 ashare_data.py 代码格式约定一致）
# ---------------------------------------------------------------------------


def _detect_market(code: str) -> str:
    c = code.strip().upper()
    if c.endswith(".HK") or (c.startswith("HK") and c[2:].isdigit()):
        return "HK"
    if c.startswith("US") and len(c) > 2 and not c[2:].isdigit():
        return "US"
    return "A"


def _safe_key(code: str) -> str:
    return "".join(ch for ch in code.lower() if ch.isalnum() or ch in "._-")


# ---------------------------------------------------------------------------
# 美股：SEC EDGAR
# ---------------------------------------------------------------------------

_US_TYPE_MAP = {
    "annual": "10-K",
    "quarterly": "10-Q",
    "current": "8-K",
    "proxy": "DEF 14A",
}


def _edgar_cik(ticker: str) -> str:
    """ticker → 10 位 CIK。公司清单较大，缓存 1 天。"""
    tickers = _cache_read("edgar-tickers")
    if tickers is None:
        data = _curl_json("https://www.sec.gov/files/company_tickers.json", ua=_EDGAR_UA)
        tickers = {v["ticker"].upper(): v["cik_str"] for v in data.values()}
        _cache_write("edgar-tickers", tickers)
    cik = tickers.get(ticker.upper())
    if cik is None:
        # BRK.A 等带点的代码在 EDGAR 里用 - 表示
        cik = tickers.get(ticker.upper().replace(".", "-"))
    if cik is None:
        raise ValueError(f"EDGAR 未找到 ticker: {ticker}")
    return str(cik).zfill(10)


def _list_us(code: str, form_type: str, limit: int, no_cache=False) -> list:
    """列出美股披露：返回 [{date, form, title, url}]。"""
    ticker = code.strip().upper()[2:]  # 去掉 us 前缀
    form = _US_TYPE_MAP.get(form_type, form_type.upper() if form_type != "all" else "")
    key = _safe_key(f"us-{ticker}-{form or 'all'}")
    if not no_cache:
        cached = _cache_read(key)
        if cached is not None:
            return cached[:limit]

    cik = _edgar_cik(ticker)
    data = _curl_json(f"https://data.sec.gov/submissions/CIK{cik}.json", ua=_EDGAR_UA)
    recent = data.get("filings", {}).get("recent", {})
    forms = recent.get("form", [])
    items = []
    for i, f in enumerate(forms):
        if form and f != form:
            continue
        accession = recent["accessionNumber"][i].replace("-", "")
        primary = recent["primaryDocument"][i]
        items.append(
            {
                "date": recent["filingDate"][i],
                "form": f,
                "title": recent.get("primaryDocDescription", [""] * len(forms))[i] or primary,
                "url": f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{accession}/{primary}",
            }
        )
        if len(items) >= 40:
            break
    if not no_cache:
        _cache_write(key, items)
    return items[:limit]


# ---------------------------------------------------------------------------
# A股：巨潮资讯
# ---------------------------------------------------------------------------

_CN_TYPE_MAP = {
    "annual": "category_ndbg_szsh",  # 年报
    "interim": "category_bndbg_szsh",  # 半年报
    "q1": "category_yjdbg_szsh",  # 一季报
    "q3": "category_sjdbg_szsh",  # 三季报
    "all": "",
}


def _cninfo_org_id(code_clean: str) -> str:
    data = _curl_json(
        "http://www.cninfo.com.cn/new/information/topSearch/query",
        post_data=urlencode({"keyWord": code_clean, "maxNum": "10"}),
    )
    for item in data if isinstance(data, list) else []:
        if item.get("code") == code_clean:
            return item.get("orgId", "")
    raise ValueError(f"巨潮未找到股票代码: {code_clean}")


def _list_a_cninfo(code_clean: str, form_type: str) -> list:
    """巨潮主源：列出 A 股定期报告。"""
    category = _CN_TYPE_MAP[form_type]
    org_id = _cninfo_org_id(code_clean)
    to_date = datetime.now().strftime("%Y-%m-%d")
    from_date = (datetime.now() - timedelta(days=6 * 365)).strftime("%Y-%m-%d")
    payload = {
        "pageNum": "1",
        "pageSize": "30",
        "column": "szse",
        "tabName": "fulltext",
        "plate": "",
        "stock": f"{code_clean},{org_id}",
        "searchkey": "",
        "secid": "",
        "category": category,
        "trade": "",
        "seDate": f"{from_date}~{to_date}",
        "sortName": "",
        "sortType": "",
        "isHLtitle": "true",
    }
    data = _curl_json(
        "http://www.cninfo.com.cn/new/hisAnnouncement/query", post_data=urlencode(payload)
    )
    items = []
    for ann in data.get("announcements") or []:
        title = re.sub(r"</?em>", "", ann.get("announcementTitle", ""))
        # 过滤摘要/英文版/更正公告的干扰项
        if any(k in title for k in ("摘要", "英文", "已取消")):
            continue
        ts = ann.get("announcementTime", 0) / 1000
        items.append(
            {
                "date": time.strftime("%Y-%m-%d", time.localtime(ts)) if ts else "",
                "form": form_type,
                "title": f"{ann.get('secName', '')} {title}",
                "url": "http://static.cninfo.com.cn/" + ann.get("adjunctUrl", ""),
            }
        )
    return items


# 东财公告接口降级源：按标题关键词筛选定期报告
_EM_TITLE_FILTER = {
    "annual": ("年度报告",),
    "interim": ("半年度报告",),
    "q1": ("一季度报告",),
    "q3": ("三季度报告",),
    "all": (),
}


def _list_a_eastmoney(code_clean: str, form_type: str) -> list:
    """降级源：东财公告接口（巨潮不可达时回退）。PDF 走 pdf.dfcfw.com。"""
    params = {
        "sr": "-1",
        "page_size": "50",
        "page_index": "1",
        "ann_type": "A",
        "client_source": "web",
        "stock_list": code_clean,
        "f_node": "1",
        "s_node": "0",
    }
    data = _curl_json(
        "https://np-anotice-stock.eastmoney.com/api/security/ann?" + urlencode(params)
    )
    keywords = _EM_TITLE_FILTER[form_type]
    items = []
    for ann in (data.get("data") or {}).get("list") or []:
        title = ann.get("title", "")
        if any(k in title for k in ("摘要", "英文", "已取消", "正式披露提示")):
            continue
        if keywords and not any(k in title for k in keywords):
            continue
        if form_type == "annual" and "半年度" in title:
            continue
        codes = ann.get("codes") or [{}]
        sec_name = codes[0].get("short_name", "") if codes else ""
        items.append(
            {
                "date": (ann.get("notice_date", "") or "")[:10],
                "form": form_type,
                "title": f"{sec_name} {title}".strip(),
                "url": f"https://pdf.dfcfw.com/pdf/H2_{ann.get('art_code', '')}_1.pdf",
            }
        )
    return items


def _list_a(code: str, form_type: str, limit: int, no_cache=False) -> list:
    """列出 A 股定期报告：巨潮主源 → 东财公告接口降级。"""
    code_clean = code.strip().upper().replace(".SH", "").replace(".SZ", "").replace(".BJ", "")
    if form_type not in _CN_TYPE_MAP:
        raise ValueError(f"A股 --type 仅支持: {', '.join(_CN_TYPE_MAP)}")
    key = _safe_key(f"a-{code_clean}-{form_type}")
    if not no_cache:
        cached = _cache_read(key)
        if cached is not None:
            return cached[:limit]

    try:
        items = _list_a_cninfo(code_clean, form_type)
    except (ConnectionError, json.JSONDecodeError, ValueError):
        items = _list_a_eastmoney(code_clean, form_type)
    if items and not no_cache:
        _cache_write(key, items)
    return items[:limit]


# ---------------------------------------------------------------------------
# 港股：披露易
# ---------------------------------------------------------------------------

_HK_TYPE_MAP = {
    "annual": ("40000", "40100"),  # 年报
    "interim": ("40000", "40200"),  # 中期/半年度报告
    "quarterly": ("40000", "40300"),  # 季度报告
    "all": ("-2", "-2"),
}


def _hkex_stock_id(code_num: str) -> str:
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


def _list_hk(code: str, form_type: str, limit: int, no_cache=False) -> list:
    """列出港股披露易文件：返回 [{date, form, title, url}]。"""
    cu = code.strip().upper()
    code_num = cu[:-3] if cu.endswith(".HK") else cu[2:]
    codes = _HK_TYPE_MAP.get(form_type)
    if codes is None:
        raise ValueError(f"港股 --type 仅支持: {', '.join(_HK_TYPE_MAP)}")
    key = _safe_key(f"hk-{code_num}-{form_type}")
    if not no_cache:
        cached = _cache_read(key)
        if cached is not None:
            return cached[:limit]

    stock_id = _hkex_stock_id(code_num)
    t1, t2 = codes
    params = {
        "sortDir": "0",
        "sortByOptions": "DateTime",
        "category": "0",
        "market": "SEHK",
        "stockId": stock_id,
        "documentType": "-1",
        "fromDate": (datetime.now() - timedelta(days=6 * 365)).strftime("%Y%m%d"),
        "toDate": datetime.now().strftime("%Y%m%d"),
        "title": "",
        "searchType": "1",
        "t1code": t1,
        "t2Gcode": "-2",
        "t2code": t2,
        "rowRange": "30",
        "lang": "ZH",
    }
    data = _curl_json("https://www1.hkexnews.hk/search/titleSearchServlet.do?" + urlencode(params))
    results = data.get("result")
    rows = json.loads(results) if isinstance(results, str) else (results or [])
    items = []
    for r in rows:
        link = r.get("FILE_LINK", "").strip()
        if not link:
            continue
        if not link.startswith("http"):
            link = "https://www1.hkexnews.hk" + ("" if link.startswith("/") else "/") + link
        # 日期 DD/MM/YYYY → YYYY-MM-DD；名称/标题去除 HTML 标签
        date_raw = (r.get("DATE_TIME", "") or "").split(" ")[0]
        parts = date_raw.split("/")
        date = f"{parts[2]}-{parts[1]}-{parts[0]}" if len(parts) == 3 else date_raw
        name = re.sub("<[^>]+>", " ", r.get("STOCK_NAME", "")).split()
        title = re.sub("<[^>]+>", " ", r.get("TITLE", "")).strip()
        items.append(
            {
                "date": date,
                "form": form_type,
                "title": f"{name[0] if name else ''} {title}".strip(),
                "url": link,
            }
        )
    if not no_cache:
        _cache_write(key, items)
    return items[:limit]


# ---------------------------------------------------------------------------
# list / fetch 命令
# ---------------------------------------------------------------------------


def _dispatch_list(code: str, form_type: str, limit: int, no_cache=False) -> list:
    market = _detect_market(code)
    if market == "US":
        return _list_us(code, form_type if form_type != "default" else "10-K", limit, no_cache)
    if market == "HK":
        return _list_hk(code, form_type if form_type != "default" else "annual", limit, no_cache)
    return _list_a(code, form_type if form_type != "default" else "annual", limit, no_cache)


def cmd_list(code: str, form_type: str, limit: int, no_cache=False):
    market = _detect_market(code)
    market_label = {"US": "美股/SEC EDGAR", "HK": "港股/披露易", "A": "A股/巨潮资讯"}[market]
    items = _dispatch_list(code, form_type, limit, no_cache)

    print("=" * 66)
    print(f"披露文件列表: {code} — {market_label}")
    print("=" * 66)
    if not items:
        print("  ⚠️ 未找到匹配的披露文件（检查代码/类型，或该期间无披露）")
        sys.exit(EXIT_FAIL)
    for i, it in enumerate(items, 1):
        print(f"  [{i}] {it['date']}  {it['form']:10s} {it['title'][:60]}")
        print(f"      {it['url']}")
    print()
    print("  下载: python3 tools/filings_fetch.py fetch --url <上方链接>")
    print(f"  或最新一份: python3 tools/filings_fetch.py fetch {code} --type {form_type} --latest")


def _guess_ext(url: str) -> str:
    for ext in (".pdf", ".htm", ".html", ".txt"):
        if url.lower().split("?")[0].endswith(ext):
            return ext
    return ".pdf"


def cmd_fetch(code=None, form_type="default", latest=False, url=None, output=None, no_cache=False):
    """下载披露原文到 data/filings/{代码}/（或 --output 指定路径）。"""
    if url is None:
        if not (code and latest):
            print("❌ fetch 需要 --url，或 <code> --type <类型> --latest 组合")
            sys.exit(EXIT_BAD_ARGS)
        items = _dispatch_list(code, form_type, 1, no_cache)
        if not items:
            print("❌ 未找到可下载的披露文件")
            sys.exit(EXIT_FAIL)
        url = items[0]["url"]
        if output is None:
            safe_date = items[0]["date"].replace("-", "")
            form = items[0]["form"].replace(" ", "").replace("/", "-")
            sub = _safe_key(code)
            output = os.path.join(_FILINGS_DIR, sub, f"{safe_date}-{form}{_guess_ext(url)}")
    if output is None:
        name = os.path.basename(url.split("?")[0]) or f"filing{_guess_ext(url)}"
        output = os.path.join(_FILINGS_DIR, name)

    ua = _EDGAR_UA if "sec.gov" in url else None
    print(f"  下载中: {url}")
    content = _curl(url, ua=ua, binary=True)
    if len(content) < 500:
        print(f"❌ 下载内容过小（{len(content)} 字节），可能是错误页，请核对链接")
        sys.exit(EXIT_FAIL)
    os.makedirs(os.path.dirname(os.path.abspath(output)), exist_ok=True)
    with open(output, "wb") as f:
        f.write(content)
    size_mb = len(content) / 1e6
    print(f"  ✅ 已保存: {output}（{size_mb:.1f} MB）")
    if output.lower().endswith(".pdf"):
        print("  提示: PDF 可用 pdf 解析能力提取正文后再做精读")
    return output


# ---------------------------------------------------------------------------
# CLI 入口
# ---------------------------------------------------------------------------


def main():
    parser = argparse.ArgumentParser(
        description="一手财报原文管道 — SEC EDGAR(美股) + 巨潮(A股) + 披露易(港股)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s list usAAPL --type 10-K --limit 5
  %(prog)s list 600519 --type annual
  %(prog)s list hk00700 --type interim
  %(prog)s fetch usAAPL --type 10-K --latest
  %(prog)s fetch --url http://static.cninfo.com.cn/... --output data/filings/mt-2025.pdf

--type 取值：
  美股: 10-K / 10-Q / 8-K / "DEF 14A" / annual / quarterly / all
  A股:  annual(年报) / interim(半年报) / q1(一季报) / q3(三季报) / all
  港股: annual(年报) / interim(中期) / quarterly(季报) / all
        """,
    )
    sub = parser.add_subparsers(dest="command")

    common = argparse.ArgumentParser(add_help=False)
    common.add_argument(
        "--type",
        default="default",
        dest="form_type",
        help="披露类型（默认：美股 10-K / A股港股年报）",
    )
    common.add_argument("--no-cache", action="store_true", help="跳过列表缓存")

    p_list = sub.add_parser("list", help="列出披露文件", parents=[common])
    p_list.add_argument("code", help="股票代码，如 600519 / hk00700 / usAAPL")
    p_list.add_argument("--limit", type=int, default=8, help="最多列出条数（默认8）")

    p_fetch = sub.add_parser("fetch", help="下载披露原文", parents=[common])
    p_fetch.add_argument("code", nargs="?", default=None, help="股票代码（配合 --latest）")
    p_fetch.add_argument("--latest", action="store_true", help="下载最新一份匹配文件")
    p_fetch.add_argument("--url", default=None, help="直接指定下载链接（来自 list 输出）")
    p_fetch.add_argument("--output", default=None, help="保存路径（默认 data/filings/{代码}/）")

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        sys.exit(EXIT_BAD_ARGS)

    try:
        if args.command == "list":
            cmd_list(args.code, args.form_type, args.limit, args.no_cache)
        else:
            cmd_fetch(args.code, args.form_type, args.latest, args.url, args.output, args.no_cache)
        sys.exit(EXIT_OK)
    except ValueError as e:
        print(f"❌ {e}")
        sys.exit(EXIT_BAD_ARGS)
    except (ConnectionError, json.JSONDecodeError) as e:
        print(f"❌ 接口请求失败: {e}", file=sys.stderr)
        print(
            "   降级路径：WebSearch「{公司名} 年报 PDF」或按 skills/financial-data/SKILL.md 网页源",
            file=sys.stderr,
        )
        sys.exit(EXIT_FAIL)


if __name__ == "__main__":
    main()
