#!/usr/bin/env python3
"""股票数据工具 — 腾讯行情 + akshare(A股财务) + yfinance(港美股财务) + TickFlow(交叉验证)。

为 Claude Code Skills 提供 A 股/港股/美股实时行情与财务数据。
数据源分层：
  - 实时行情：腾讯行情 qt.gtimg.cn（curl 直连，A股/港股/美股）
  - A股财务：akshare 同花顺源（stock_financial_abstract_ths）
  - 港股/美股财务：yfinance（Yahoo Finance 结构化数据）
  - 交叉验证：TickFlow（设置 TICKFLOW_API_KEY 后启用，财务指标第二源）
  - 股票搜索：东方财富 searchadapter（curl 直连）
  - 降级兖底：东方财富 datacenter API（curl，akshare 不可用时回退）

用法（由 Skills 自动调用）：
    python3 tools/ashare_data.py quote 600519                    # A股实时行情
    python3 tools/ashare_data.py quote hk00700                   # 港股行情
    python3 tools/ashare_data.py quote usAAPL                    # 美股行情
    python3 tools/ashare_data.py financials 600519               # A股核心财务（近5年）
    python3 tools/ashare_data.py financials usAAPL               # 美股核心财务（近4年）
    python3 tools/ashare_data.py financials hk00700              # 港股核心财务（近4年）
    python3 tools/ashare_data.py valuation 600519                # 估值指标
    python3 tools/ashare_data.py history 600519 --days 250       # 日K收盘价序列（前复权）
    python3 tools/ashare_data.py search 茅台                      # 搜索股票代码

缓存：取数成功后写入 data/cache/（行情 TTL 15 分钟、财务 TTL 7 天），
网络全部失败时回退过期缓存并标注 [缓存数据]；加 --no-cache 可强制直连。

依赖：akshare, yfinance, tickflow（pip install akshare yfinance tickflow）
"""

import argparse
import json
import os
import subprocess
import sys
import time
from decimal import Decimal
from urllib.parse import urlencode, urlparse

# ---------------------------------------------------------------------------
# 可选依赖导入（缺失时优雅降级）
# ---------------------------------------------------------------------------

_HAS_AKSHARE = False
_HAS_YFINANCE = False
_HAS_TICKFLOW = False
_TICKFLOW_API_KEY = os.environ.get("TICKFLOW_API_KEY", "")

try:
    os.environ.setdefault("NO_PROXY", "*")
    os.environ.setdefault("no_proxy", "*")
    import akshare as ak
    _HAS_AKSHARE = True
except (ImportError, Exception):
    pass

try:
    import yfinance as yf
    _HAS_YFINANCE = True
except (ImportError, Exception):
    pass

try:
    from tickflow import TickFlow
    _HAS_TICKFLOW = True
except (ImportError, Exception):
    pass

_TIMEOUT = 15
_RETRIES = 1          # 失败/超时后重试次数
_RETRY_WAIT = 2       # 重试间隔（秒）


def _curl(url):
    """用 curl --noproxy 直连，绕过系统代理；失败/超时后自动重试 1 次。"""
    last_err = None
    for attempt in range(_RETRIES + 1):
        try:
            result = subprocess.run(
                ["/usr/bin/curl", "-s", "--noproxy", "*",
                 "-H", "User-Agent: Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)",
                 url],
                capture_output=True, timeout=_TIMEOUT,
            )
            if result.returncode == 0 and result.stdout.strip():
                try:
                    return result.stdout.decode("utf-8")
                except UnicodeDecodeError:
                    return result.stdout.decode("gbk")
            last_err = ConnectionError(f"请求失败 (curl 退出码 {result.returncode}): {url}")
        except subprocess.TimeoutExpired:
            last_err = ConnectionError(f"请求超时 (>{_TIMEOUT}s): {url}")
        if attempt < _RETRIES:
            time.sleep(_RETRY_WAIT)
    raise last_err


def _curl_json(url, params=None):
    """用 curl 获取并解析 JSON；params 会编码为查询字符串附加到 url。"""
    if params:
        url = f"{url}?{urlencode(params)}"
    return json.loads(_curl(url))


# ---------------------------------------------------------------------------
# 本地缓存层（data/cache/，行情 TTL 15 分钟 / 财务 TTL 7 天）
# ---------------------------------------------------------------------------

_CACHE_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "cache"
)
_TTL_QUOTE = 15 * 60          # 行情类：15 分钟
_TTL_FINANCIALS = 7 * 86400   # 财务类：7 天
_TTL_KLINE = 86400            # 日K线：1 天


def _cache_path(kind: str, code: str) -> str:
    safe = "".join(ch for ch in code if ch.isalnum() or ch in "._-")
    return os.path.join(_CACHE_DIR, f"{kind}-{safe}.json")


def _cache_read(kind: str, code: str):
    """读缓存条目，失败/不存在返回 None。"""
    try:
        with open(_cache_path(kind, code), encoding="utf-8") as f:
            entry = json.load(f)
        if "fetched_at" in entry and "payload" in entry:
            return entry
    except (OSError, json.JSONDecodeError):
        pass
    return None


def _cache_write(kind: str, code: str, payload):
    """写缓存条目；缓存不可写不影响主流程。"""
    try:
        os.makedirs(_CACHE_DIR, exist_ok=True)
        entry = {
            "fetched_at": time.time(),
            "fetched_date": time.strftime("%Y-%m-%d %H:%M"),
            "payload": payload,
        }
        with open(_cache_path(kind, code), "w", encoding="utf-8") as f:
            json.dump(entry, f, ensure_ascii=False)
    except OSError:
        pass


def _cached_fetch(kind: str, code: str, ttl: int, fetch_fn, no_cache=False):
    """三级取数：TTL 内缓存 → 网络（成功回写缓存）→ 过期缓存兜底。

    返回 (payload, note)：note 非空时须在输出中展示缓存来源标注。
    """
    entry = None if no_cache else _cache_read(kind, code)
    if entry and time.time() - entry["fetched_at"] <= ttl:
        return entry["payload"], f"[缓存数据 抓取于{entry['fetched_date']}]（TTL内复用）"
    try:
        payload = fetch_fn()
        if not no_cache:
            _cache_write(kind, code, payload)
        return payload, None
    except (ConnectionError, json.JSONDecodeError, Exception) as e:
        if entry:
            return entry["payload"], (
                f"[缓存数据 抓取于{entry['fetched_date']}]（网络失败回退，可能过期）"
            )
        raise


# ---------------------------------------------------------------------------
# 腾讯行情 API（稳定可靠，无需鉴权）
# ---------------------------------------------------------------------------

def _normalize_code(code: str) -> str:
    """去掉交易所后缀（.SH/.SZ/.BJ），返回纯数字股票代码。"""
    return code.strip().upper().replace(".SH", "").replace(".SZ", "").replace(".BJ", "")


def _market(code: str) -> str:
    """根据代码首位数字推断交易所：沪 SH / 深 SZ / 北 BJ。"""
    code = _normalize_code(code)
    if code.startswith(("6", "9", "5")):
        return "SH"
    if code.startswith(("0", "3", "2", "1")):
        return "SZ"
    if code.startswith(("4", "8")):
        return "BJ"
    return "SH"


def _detect_market_type(code: str) -> str:
    """检测代码所属市场类型：'A' / 'HK' / 'US'。"""
    c = code.strip()
    cu = c.upper()
    if cu.endswith(".HK") or (cu.startswith("HK") and cu[2:].isdigit()):
        return "HK"
    if cu.startswith("US") and len(cu) > 2 and not cu[2:].isdigit():
        return "US"
    return "A"


def _qq_code(code: str) -> str:
    """将股票代码转为腾讯行情格式。

    支持三个市场：
    - A股：600519 / 600519.SH → sh600519
    - 港股：hk00700 / 0700.HK / 00700.HK → hk00700
    - 美股：usAAPL / usBRK.A → usAAPL
    """
    c = code.strip()
    cu = c.upper()
    # 已带交易所前缀的代码（含指数，如 sh000300 沪深300）直接透传
    if len(cu) == 8 and cu[:2] in ("SH", "SZ", "BJ") and cu[2:].isdigit():
        return cu.lower()
    if cu.endswith(".HK"):
        num = cu[:-3]
        if num.isdigit():
            return "hk" + num.zfill(5)
    if cu.startswith("HK") and cu[2:].isdigit():
        return "hk" + cu[2:].zfill(5)
    if cu.startswith("HK") and len(cu) > 2:
        return "hk" + c[2:]  # 港股指数字母代码（hkHSI 恒指等）保留原大小写透传
    if cu.startswith("US") and len(cu) > 2 and not cu[2:].isdigit():
        return "us" + cu[2:]
    code = _normalize_code(c)
    return f"{_market(code).lower()}{code}"


def _yf_ticker(code: str) -> str:
    """将用户输入的代码转为 yfinance ticker 格式。

    - 港股：hk00700 / 0700.HK / 00700.HK → 0700.HK（Yahoo 用 4 位）
    - 美股：usAAPL → AAPL
    """
    c = code.strip()
    cu = c.upper()
    if cu.endswith(".HK"):
        num = cu[:-3].lstrip("0") or "0"
        return num.zfill(4) + ".HK"
    if cu.startswith("HK") and cu[2:].isdigit():
        num = cu[2:].lstrip("0") or "0"
        return num.zfill(4) + ".HK"
    if cu.startswith("US") and len(cu) > 2:
        return cu[2:]
    return c


def _market_label(qq_code: str) -> str:
    """根据腾讯行情代码前缀返回市场标签与币种提示。"""
    if qq_code.startswith("hk"):
        return "港股（币种：港元）"
    if qq_code.startswith("us"):
        return "美股（币种：美元）"
    return "A股（币种：人民币）"


def _parse_qq_quote(raw: str) -> dict:
    """解析腾讯行情数据。格式：v_shXXXXXX="字段1~字段2~..."; """
    start = raw.find('"')
    end = raw.rfind('"')
    if start < 0 or end <= start:
        return {}
    fields = raw[start + 1:end].split("~")
    if len(fields) < 50:
        return {}
    return {
        "name": fields[1],
        "code": fields[2],
        "price": fields[3],
        "prev_close": fields[4],
        "open": fields[5],
        "volume": fields[6],
        "buy_vol": fields[7],
        "sell_vol": fields[8],
        "high": fields[33] if len(fields) > 33 else fields[3],
        "low": fields[34] if len(fields) > 34 else fields[3],
        "change_pct": fields[32],
        "change_amt": fields[31],
        "turnover_amt": fields[37] if len(fields) > 37 else "-",
        "turnover_rate": fields[38] if len(fields) > 38 else "-",
        "pe": fields[39] if len(fields) > 39 else "-",
        "market_cap": fields[45] if len(fields) > 45 else "-",
        "float_cap": fields[44] if len(fields) > 44 else "-",
        "pb": fields[46] if len(fields) > 46 else "-",
        "high_52w": fields[47] if len(fields) > 47 else "-",
        "low_52w": fields[48] if len(fields) > 48 else "-",
    }


def _fmt_yi(value) -> str:
    """将数值按量级格式化为「亿 / 万」单位。"""
    if value is None or value == "-" or value == "":
        return "-"
    try:
        v = float(value)
    except (ValueError, TypeError):
        return str(value)
    if abs(v) >= 1e8:
        return f"{v / 1e8:.2f}亿"
    if abs(v) >= 1e4:
        return f"{v / 1e4:.2f}万"
    return f"{v:.2f}"


def _fmt_pct(value) -> str:
    """将数值格式化为百分比字符串。"""
    if value is None or value == "-" or value == "":
        return "-"
    try:
        return f"{float(value):.2f}%"
    except (ValueError, TypeError):
        return str(value)


def _fmt_num(value, unit="") -> str:
    """格式化大数字（自动转换为亿/万）。"""
    if value is None or value != value:  # NaN check
        return "-"
    try:
        v = float(value)
    except (ValueError, TypeError):
        return str(value)
    if abs(v) >= 1e12:
        return f"{v / 1e12:.2f}万亿{unit}"
    if abs(v) >= 1e8:
        return f"{v / 1e8:.2f}亿{unit}"
    if abs(v) >= 1e4:
        return f"{v / 1e4:.2f}万{unit}"
    return f"{v:.2f}{unit}"


# ---------------------------------------------------------------------------
# 行情命令
# ---------------------------------------------------------------------------

def _fetch_quote_dict(qq_code: str) -> dict:
    """从腾讯行情拉取并解析单只股票；美股无结果时自动补交易所后缀重试。"""
    candidates = [qq_code]
    if qq_code.startswith("us") and "." not in qq_code:
        candidates += [f"{qq_code}.OQ", f"{qq_code}.N"]
    for cand in candidates:
        raw = _curl(f"https://qt.gtimg.cn/q={cand}")
        d = _parse_qq_quote(raw)
        if d:
            return d
    return {}


def _get_quote(code: str, no_cache=False):
    """带缓存的行情获取，返回 (dict, 缓存标注)。"""
    qq_code = _qq_code(code)
    payload, note = _cached_fetch(
        "quote", qq_code, _TTL_QUOTE,
        lambda: _fetch_quote_dict(qq_code), no_cache=no_cache,
    )
    return payload, note


def cmd_quote(code: str, no_cache=False):
    """实时行情快照（A股/港股/美股）。"""
    qq_code = _qq_code(code)
    d, note = _get_quote(code, no_cache=no_cache)
    if not d:
        print(f"❌ 未找到股票 {code}")
        return

    print("=" * 60)
    print(f"实时行情: {d['name']} ({d['code']}) — {_market_label(qq_code)}")
    if note:
        print(f"⚠️ {note}")
    print("=" * 60)
    print(f"  当前价:     {d['price']}")
    print(f"  涨跌幅:     {d['change_pct']}%")
    print(f"  涨跌额:     {d['change_amt']}")
    print(f"  今开:       {d['open']}")
    print(f"  最高:       {d['high']}")
    print(f"  最低:       {d['low']}")
    print(f"  昨收:       {d['prev_close']}")
    print(f"  成交量:     {d['volume']} 手")
    print(f"  成交额:     {d['turnover_amt']}万")
    print(f"  总市值:     {d['market_cap']}亿")
    print(f"  流通市值:   {d['float_cap']}亿")
    print(f"  PE(动):     {d['pe']}")
    print(f"  PB:         {d['pb']}")
    print(f"  换手率:     {d['turnover_rate']}%")
    print(f"  52周最高:   {d['high_52w']}")
    print(f"  52周最低:   {d['low_52w']}")


def cmd_valuation(code: str, no_cache=False):
    """估值指标汇总（A股/港股/美股）。"""
    qq_code = _qq_code(code)
    d, note = _get_quote(code, no_cache=no_cache)
    if not d:
        print(f"❌ 未找到股票 {code}")
        return

    price = d["price"]
    market_cap_yi = d["market_cap"]

    print("=" * 60)
    print(f"估值指标: {d['name']} ({d['code']}) — {_market_label(qq_code)}")
    if note:
        print(f"⚠️ {note}")
    print("=" * 60)
    print(f"  当前价:     {price}")
    print(f"  总市值:     {market_cap_yi}亿")
    print(f"  流通市值:   {d['float_cap']}亿")
    print(f"  PE(动):     {d['pe']}")
    print(f"  PB:         {d['pb']}")
    print(f"  52周最高:   {d['high_52w']}")
    print(f"  52周最低:   {d['low_52w']}")

    try:
        p = Decimal(price)
        cap = Decimal(market_cap_yi) * Decimal("1e8")
        shares = cap / p
        print(f"\n  推算总股本: {_fmt_yi(float(shares))}股 [仅供参考，非独立验证]")
        print(f"  提示: 独立市值验算请取交易所/F10总股本后调用 financial_rigor.py verify-market-cap")
    except Exception:
        pass


# ---------------------------------------------------------------------------
# A股财务数据（akshare 同花顺源，降级→东财 datacenter API）
# ---------------------------------------------------------------------------

def _fetch_financials_a_akshare(code_clean: str) -> list:
    """通过 akshare 同花顺源获取 A 股年度财务摘要，返回标准化 list[dict]。"""
    df = ak.stock_financial_abstract_ths(symbol=code_clean, indicator="按年度")
    if df is None or df.empty:
        return []
    # 取最近 5 年
    df = df.tail(5).iloc[::-1]  # 倒序，最新在前
    reports = []
    for _, row in df.iterrows():
        def _parse_val(v):
            """解析 '747.34亿' / '34.19%' / 'False' 等格式。"""
            if v is None or v == "False" or v == "" or (isinstance(v, float) and v != v):
                return None
            s = str(v).strip()
            if s.endswith("亿"):
                try:
                    return float(s[:-1]) * 1e8
                except ValueError:
                    return None
            if s.endswith("万"):
                try:
                    return float(s[:-1]) * 1e4
                except ValueError:
                    return None
            if s.endswith("%"):
                try:
                    return float(s[:-1])
                except ValueError:
                    return None
            try:
                return float(s)
            except ValueError:
                return None

        reports.append({
            "REPORT_DATE": str(row.get("报告期", "")),
            "revenue": _parse_val(row.get("营业总收入")),
            "revenue_growth": _parse_val(row.get("营业总收入同比增长率")),
            "net_profit": _parse_val(row.get("净利润")),
            "profit_growth": _parse_val(row.get("净利润同比增长率")),
            "eps": _parse_val(row.get("基本每股收益")),
            "bps": _parse_val(row.get("每股净资产")),
            "roe": _parse_val(row.get("净资产收益率")),
            "gross_margin": _parse_val(row.get("销售毛利率")),
            "net_margin": _parse_val(row.get("销售净利率")),
            "debt_ratio": _parse_val(row.get("资产负债率")),
            "ocf_per_share": _parse_val(row.get("每股经营现金流")),
        })
    return reports


def _fetch_financials_a_eastmoney(code_clean: str) -> list:
    """降级方案：通过东财 datacenter API 获取 A 股财务数据（curl 直连）。"""
    market = _market(code_clean)
    fin_url = "https://datacenter.eastmoney.com/securities/api/data/get"
    params = {
        "type": "RPT_F10_FINANCE_MAINFINADATA",
        "sty": "ALL",
        "filter": f'(SECUCODE="{code_clean}.{market}")(REPORT_TYPE="年报")',
        "p": "1",
        "ps": "5",
        "sr": "-1",
        "st": "REPORT_DATE",
        "source": "HSF10",
        "client": "PC",
    }
    reports = []
    try:
        data = _curl_json(fin_url, params)
        raw_reports = data.get("result", {}).get("data", []) or []
    except Exception:
        raw_reports = []
    if not raw_reports:
        params["filter"] = f'(SECUCODE="{code_clean}.{market}")'
        try:
            data = _curl_json(fin_url, params)
            raw_reports = data.get("result", {}).get("data", []) or []
        except Exception:
            raw_reports = []
    for r in raw_reports[:5]:
        reports.append({
            "REPORT_DATE": (r.get("REPORT_DATE", "") or "")[:10],
            "revenue": r.get("TOTALOPERATEREVE"),
            "revenue_growth": r.get("TOTALOPERATEREVETZ"),
            "net_profit": r.get("PARENTNETPROFIT"),
            "profit_growth": r.get("PARENTNETPROFITTZ"),
            "eps": r.get("EPSJB"),
            "bps": r.get("BPS"),
            "roe": r.get("ROEJQ"),
            "gross_margin": None,
            "net_margin": None,
            "debt_ratio": None,
            "ocf_per_share": None,
        })
    return reports


# ---------------------------------------------------------------------------
# 港股/美股财务数据（yfinance）
# ---------------------------------------------------------------------------

def _fetch_financials_yf(code: str) -> list:
    """通过 yfinance 获取港股/美股年度财务数据，返回标准化 list[dict]。"""
    ticker_sym = _yf_ticker(code)
    t = yf.Ticker(ticker_sym)
    inc = t.income_stmt
    if inc is None or inc.empty:
        return []

    reports = []
    for col in inc.columns[:5]:  # 最近 5 个财年
        def _get(row_name):
            if row_name in inc.index:
                v = inc.loc[row_name, col]
                if v == v:  # not NaN
                    return float(v)
            return None

        revenue = _get("Total Revenue")
        net_profit = _get("Net Income")
        gross_profit = _get("Gross Profit")
        operating_income = _get("Operating Income")

        # 计算增长率（需要上一期数据）
        rev_growth = None
        profit_growth = None

        gross_margin = None
        if revenue and gross_profit:
            gross_margin = (gross_profit / revenue) * 100

        net_margin = None
        if revenue and net_profit:
            net_margin = (net_profit / revenue) * 100

        reports.append({
            "REPORT_DATE": str(col.date()),
            "revenue": revenue,
            "revenue_growth": rev_growth,
            "net_profit": net_profit,
            "profit_growth": profit_growth,
            "eps": _get("Diluted EPS") or _get("Basic EPS"),
            "bps": None,
            "roe": None,
            "gross_margin": gross_margin,
            "net_margin": net_margin,
            "debt_ratio": None,
            "ocf_per_share": None,
            "operating_income": operating_income,
        })

    # 补充增长率（用相邻年份计算）
    for i in range(len(reports) - 1):
        curr = reports[i]
        prev = reports[i + 1]
        if curr["revenue"] and prev["revenue"] and prev["revenue"] != 0:
            curr["revenue_growth"] = ((curr["revenue"] - prev["revenue"]) / abs(prev["revenue"])) * 100
        if curr["net_profit"] and prev["net_profit"] and prev["net_profit"] != 0:
            curr["profit_growth"] = ((curr["net_profit"] - prev["net_profit"]) / abs(prev["net_profit"])) * 100

    # 补充 ROE / BPS / 资产负债率（从 balance_sheet 和 info）
    try:
        info = t.info
        if info.get("returnOnEquity"):
            reports[0]["roe"] = info["returnOnEquity"] * 100
        if info.get("bookValue"):
            reports[0]["bps"] = info["bookValue"]
        if info.get("debtToEquity"):
            reports[0]["debt_ratio"] = info["debtToEquity"]
    except Exception:
        pass

    return reports


# ---------------------------------------------------------------------------
# TickFlow 交叉验证（需 TICKFLOW_API_KEY 环境变量）
# ---------------------------------------------------------------------------

def _tickflow_symbol(code: str) -> str:
    """将用户输入的代码转为 TickFlow 格式（600519.SH / AAPL.US / 00700.HK）。"""
    c = code.strip()
    cu = c.upper()
    # 港股
    if cu.endswith(".HK"):
        num = cu[:-3]
        return num.zfill(5) + ".HK"
    if cu.startswith("HK") and cu[2:].isdigit():
        return cu[2:].zfill(5) + ".HK"
    # 美股
    if cu.startswith("US") and len(cu) > 2 and not cu[2:].isdigit():
        return cu[2:] + ".US"
    # A股
    code_clean = _normalize_code(c)
    market = _market(code_clean)
    return f"{code_clean}.{market}"


def _fetch_tickflow_metrics(code: str) -> dict:
    """从 TickFlow 获取最新一期核心财务指标（作为交叉验证第二源）。

    返回 dict，失败返回 {}。需要 TICKFLOW_API_KEY 环境变量。
    """
    if not _HAS_TICKFLOW or not _TICKFLOW_API_KEY:
        return {}
    try:
        tf = TickFlow(api_key=_TICKFLOW_API_KEY)
        symbol = _tickflow_symbol(code)
        result = tf.financials.metrics(symbol, latest=True)
        if not result:
            return {}
        # result 可能是 dict {symbol: [records]} 或 list
        records = None
        if isinstance(result, dict):
            records = result.get(symbol, [])
        elif isinstance(result, list):
            records = result
        if not records:
            return {}
        r = records[0] if isinstance(records, list) else records
        return {
            "period_end": r.get("period_end", ""),
            "revenue_yoy": r.get("revenue_yoy"),
            "net_income_yoy": r.get("net_income_yoy"),
            "gross_margin": r.get("gross_margin"),
            "net_margin": r.get("net_margin"),
            "roe": r.get("roe"),
            "eps_basic": r.get("eps_basic"),
            "bps": r.get("bps"),
            "debt_to_asset_ratio": r.get("debt_to_asset_ratio"),
            "ocfps": r.get("ocfps"),
        }
    except Exception:
        return {}


def _print_tickflow_crossval(code: str, primary_reports: list):
    """输出 TickFlow 交叉验证结果（仅当有 API Key 且主源数据存在时）。"""
    tf_data = _fetch_tickflow_metrics(code)
    if not tf_data:
        return

    print(f"\n  ─── TickFlow 交叉验证（{tf_data.get('period_end', '')}）───")

    # 对比主源最新一期
    if primary_reports:
        p = primary_reports[0]
        comparisons = []
        # ROE
        if tf_data.get("roe") is not None and p.get("roe") is not None:
            tf_v = tf_data["roe"]
            p_v = p["roe"]
            diff = abs(tf_v - p_v)
            flag = "✅" if diff <= 1 else ("⚠️" if diff <= 5 else "❌")
            comparisons.append(f"  ROE:        主源 {p_v:.2f}% | TickFlow {tf_v:.2f}% | 差异 {diff:.2f}% {flag}")
        # 毛利率
        if tf_data.get("gross_margin") is not None and p.get("gross_margin") is not None:
            tf_v = tf_data["gross_margin"]
            p_v = p["gross_margin"]
            diff = abs(tf_v - p_v)
            flag = "✅" if diff <= 1 else ("⚠️" if diff <= 5 else "❌")
            comparisons.append(f"  毛利率:      主源 {p_v:.2f}% | TickFlow {tf_v:.2f}% | 差异 {diff:.2f}% {flag}")
        # 净利率
        if tf_data.get("net_margin") is not None and p.get("net_margin") is not None:
            tf_v = tf_data["net_margin"]
            p_v = p["net_margin"]
            diff = abs(tf_v - p_v)
            flag = "✅" if diff <= 1 else ("⚠️" if diff <= 5 else "❌")
            comparisons.append(f"  净利率:      主源 {p_v:.2f}% | TickFlow {tf_v:.2f}% | 差异 {diff:.2f}% {flag}")
        # EPS
        if tf_data.get("eps_basic") is not None and p.get("eps") is not None:
            tf_v = tf_data["eps_basic"]
            p_v = p["eps"]
            diff_pct = abs(tf_v - p_v) / max(abs(p_v), 0.01) * 100
            flag = "✅" if diff_pct <= 1 else ("⚠️" if diff_pct <= 5 else "❌")
            comparisons.append(f"  EPS:        主源 {p_v:.2f} | TickFlow {tf_v:.2f} | 差异 {diff_pct:.1f}% {flag}")
        # 资产负债率
        if tf_data.get("debt_to_asset_ratio") is not None and p.get("debt_ratio") is not None:
            tf_v = tf_data["debt_to_asset_ratio"]
            p_v = p["debt_ratio"]
            diff = abs(tf_v - p_v)
            flag = "✅" if diff <= 1 else ("⚠️" if diff <= 5 else "❌")
            comparisons.append(f"  资产负债率:  主源 {p_v:.2f}% | TickFlow {tf_v:.2f}% | 差异 {diff:.2f}% {flag}")

        if comparisons:
            for line in comparisons:
                print(line)
        else:
            print("  （无可对比字段）")
    else:
        # 主源无数据，直接输出 TickFlow 数据
        if tf_data.get("roe") is not None:
            print(f"  ROE:        {_fmt_pct(tf_data['roe'])}")
        if tf_data.get("gross_margin") is not None:
            print(f"  毛利率:      {_fmt_pct(tf_data['gross_margin'])}")
        if tf_data.get("net_margin") is not None:
            print(f"  净利率:      {_fmt_pct(tf_data['net_margin'])}")
        if tf_data.get("eps_basic") is not None:
            print(f"  EPS:        {tf_data['eps_basic']:.2f}")
        if tf_data.get("bps") is not None:
            print(f"  每股净资产:  {tf_data['bps']:.2f}")
        if tf_data.get("debt_to_asset_ratio") is not None:
            print(f"  资产负债率:  {_fmt_pct(tf_data['debt_to_asset_ratio'])}")


# ---------------------------------------------------------------------------
# financials 命令（统一入口）
# ---------------------------------------------------------------------------

def cmd_financials(code: str, no_cache=False):
    """核心财务数据（A股/港股/美股）。"""
    mkt_type = _detect_market_type(code)
    code_clean = _normalize_code(code) if mkt_type == "A" else code

    # 获取股票名称（从行情）
    try:
        d, _ = _get_quote(code, no_cache=no_cache)
    except (ConnectionError, json.JSONDecodeError):
        d = {}
    name = d.get("name", code) if d else code

    # 选择数据源
    cache_key = f"financials-{_qq_code(code)}"

    def _fetch():
        if mkt_type == "A":
            # A股：优先 akshare THS，降级→东财 API
            if _HAS_AKSHARE:
                try:
                    result = _fetch_financials_a_akshare(code_clean)
                    if result:
                        return result
                except Exception:
                    pass
            return _fetch_financials_a_eastmoney(code_clean)
        else:
            # 港股/美股：yfinance
            if _HAS_YFINANCE:
                result = _fetch_financials_yf(code)
                if result:
                    return result
            raise ConnectionError(
                f"yfinance 不可用或无数据（{code}）。"
                "请按 skills/financial-data/SKILL.md 走网页双源验证。"
            )

    try:
        reports, note = _cached_fetch(
            "financials", _qq_code(code), _TTL_FINANCIALS, _fetch,
            no_cache=no_cache,
        )
    except (ConnectionError, json.JSONDecodeError, Exception) as e:
        print(f"❌ 财务数据获取失败: {e}")
        if mkt_type != "A":
            print("   降级路径：按 skills/financial-data/SKILL.md 走网页双源验证")
            print("   美股: macrotrends → stockanalysis → wsj → SEC EDGAR")
            print("   港股: aastocks → macrotrends(ADR) → 富途牛牛 → 披露易")
        else:
            print("   降级路径：东财网页 → 巨潮资讯 → 新浪财经")
        return

    # 数据源标注
    if mkt_type == "A":
        source_label = "akshare/同花顺" if _HAS_AKSHARE else "东方财富API"
    else:
        source_label = "yfinance/Yahoo Finance"

    print("=" * 60)
    print(f"核心财务数据: {name} ({code_clean}) — 数据源: {source_label}")
    if note:
        print(f"⚠️ {note}")
    print("=" * 60)

    if not reports:
        print("  ⚠️ 未能获取财务数据，建议通过 WebSearch 补充")
        return

    for r in reports[:5]:
        date = r.get("REPORT_DATE", "")
        print(f"\n  --- {date} ---")
        if r.get("revenue") is not None:
            print(f"  营收:           {_fmt_num(r['revenue'])}")
        if r.get("revenue_growth") is not None:
            print(f"  营收增速:       {_fmt_pct(r['revenue_growth'])}")
        if r.get("net_profit") is not None:
            print(f"  净利润:         {_fmt_num(r['net_profit'])}")
        if r.get("profit_growth") is not None:
            print(f"  净利润增速:     {_fmt_pct(r['profit_growth'])}")
        if r.get("operating_income") is not None:
            print(f"  营业利润:       {_fmt_num(r['operating_income'])}")
        if r.get("gross_margin") is not None:
            print(f"  毛利率:         {_fmt_pct(r['gross_margin'])}")
        if r.get("net_margin") is not None:
            print(f"  净利率:         {_fmt_pct(r['net_margin'])}")
        if r.get("eps") is not None:
            print(f"  每股收益:       {r['eps']:.2f}")
        if r.get("bps") is not None:
            print(f"  每股净资产:     {r['bps']:.2f}")
        if r.get("roe") is not None:
            print(f"  ROE:            {_fmt_pct(r['roe'])}")
        if r.get("debt_ratio") is not None:
            print(f"  资产负债率:     {_fmt_pct(r['debt_ratio'])}")
        if r.get("ocf_per_share") is not None:
            print(f"  每股经营现金流: {r['ocf_per_share']:.2f}")

    # TickFlow 交叉验证（有 API Key 时自动执行）
    _print_tickflow_crossval(code, reports)


# ---------------------------------------------------------------------------
# 日K线历史（腾讯 ifzq 接口，前复权收盘价；供估值分位/组合相关性计算使用）
# ---------------------------------------------------------------------------

def _fetch_kline(code: str, days: int = 250) -> list:
    """拉取日K收盘价序列，返回 [{date, close}]（旧→新）。

    美股不带交易所后缀时接口可能返回脱节的零星数据，故按行数阈值校验，
    不达标则轮换 .OQ/.N 候选代码，取行数最多的结果。
    """
    qq_code = _qq_code(code)
    candidates = [qq_code]
    if qq_code.startswith("us") and "." not in qq_code:
        candidates += [f"{qq_code}.OQ", f"{qq_code}.N"]
    min_rows = max(5, min(days, 30) // 2)
    best = []
    for cand in candidates:
        url = (f"https://web.ifzq.gtimg.cn/appstock/app/fqkline/get"
               f"?param={cand},day,,,{days},qfq")
        try:
            data = _curl_json(url)
        except (ConnectionError, json.JSONDecodeError):
            continue
        node = (data.get("data") or {}).get(cand) or {}
        rows = node.get("qfqday") or node.get("day") or []
        if len(rows) > len(best):
            best = rows
        if len(rows) >= min_rows:
            break
    return [{"date": r[0], "close": float(r[2])} for r in best]


def get_close_series(code: str, days: int = 250, no_cache=False):
    """带缓存的收盘价序列（供本工具 history 命令与 portfolio_calc 导入复用）。"""
    payload, note = _cached_fetch(
        "kline", f"{_qq_code(code)}-{days}", _TTL_KLINE,
        lambda: _fetch_kline(code, days), no_cache=no_cache,
    )
    return payload, note


def cmd_history(code: str, days: int = 250, as_json=False, no_cache=False):
    """日K收盘价序列（前复权）。--json 输出机器可读格式供下游计算。"""
    series, note = get_close_series(code, days, no_cache=no_cache)
    if not series:
        print(f"❌ 未获取到 {code} 的日K数据（检查代码格式：600519 / hk00700 / usAAPL）")
        sys.exit(1)
    if as_json:
        print(json.dumps({"code": code, "days": len(series),
                          "note": note or "", "series": series},
                         ensure_ascii=False))
        return
    closes = [s["close"] for s in series]
    print("=" * 60)
    print(f"日K收盘价序列: {code}（前复权，{series[0]['date']} ~ {series[-1]['date']}，共 {len(series)} 个交易日）")
    if note:
        print(f"⚠️ {note}")
    print("=" * 60)
    print(f"  区间最低/最高:  {min(closes):.2f} / {max(closes):.2f}")
    print(f"  区间涨跌幅:     {(closes[-1]/closes[0]-1)*100:+.2f}%")
    print(f"  最新收盘:       {closes[-1]:.2f}（{series[-1]['date']}）")
    print()
    print("  提示: 加 --json 可输出完整序列，供估值分位/相关性等下游计算使用")


# ---------------------------------------------------------------------------
# 搜索命令
# ---------------------------------------------------------------------------

def cmd_search(keyword: str):
    """搜索股票代码（东方财富搜索接口）。"""
    url = "https://searchadapter.eastmoney.com/api/suggest/get"
    token = os.environ.get("EASTMONEY_SEARCH_TOKEN") or "D43BF722C8E33BDC906FB84D85E326E8"
    params = {
        "input": keyword,
        "type": "14",
        "token": token,
        "count": "10",
    }
    data = _curl_json(url, params)
    results = data.get("QuotationCodeTable", {}).get("Data", [])

    if not results:
        print(f"❌ 未找到匹配 '{keyword}' 的股票")
        return

    print("=" * 60)
    print(f"搜索结果: '{keyword}'")
    print("=" * 60)
    for r in results:
        code = r.get("Code", "")
        name = r.get("Name", "")
        market = r.get("MktNum", "")
        mkt_label = {"1": "沪", "2": "深", "3": "北"}.get(str(market), "")
        print(f"  {code} {name} [{mkt_label}]")


# ---------------------------------------------------------------------------
# CLI 入口
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="股票数据工具 — 腾讯行情 + akshare(A股财务) + yfinance(港美股财务)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = parser.add_subparsers(dest="command")

    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--no-cache", action="store_true",
                        help="跳过本地缓存，强制从接口直连取数")

    p_quote = sub.add_parser("quote", help="实时行情（A股/港股/美股）", parents=[common])
    p_quote.add_argument("code", help="股票代码，如 600519 / hk00700 / usAAPL")

    p_fin = sub.add_parser("financials", help="核心财务数据（A股/港股/美股）", parents=[common])
    p_fin.add_argument("code", help="股票代码，如 600519 / hk00700 / usAAPL")

    p_val = sub.add_parser("valuation", help="估值指标（A股/港股/美股）", parents=[common])
    p_val.add_argument("code", help="股票代码")

    p_hist = sub.add_parser("history", help="日K收盘价序列（前复权）", parents=[common])
    p_hist.add_argument("code", help="股票代码，如 600519 / hk00700 / usAAPL")
    p_hist.add_argument("--days", type=int, default=250, help="交易日数（默认250≈1年）")
    p_hist.add_argument("--json", action="store_true", help="输出JSON（供下游计算）")

    p_search = sub.add_parser("search", help="搜索股票代码", parents=[common])
    p_search.add_argument("keyword", help="公司名或关键词")

    args = parser.parse_args()

    if not args.command:
        # 打印依赖状态
        print("股票数据工具 — 依赖状态：")
        print(f"  akshare:  {'✅ ' + ak.__version__ if _HAS_AKSHARE else '❌ 未安装 (pip install akshare)'}")
        print(f"  yfinance: {'✅ ' + yf.__version__ if _HAS_YFINANCE else '❌ 未安装 (pip install yfinance)'}")
        tf_status = "✅ 已安装" if _HAS_TICKFLOW else "❌ 未安装 (pip install tickflow)"
        if _HAS_TICKFLOW:
            tf_status += " | API Key: " + ("✅ 已配置" if _TICKFLOW_API_KEY else "⚠️ 未设置 TICKFLOW_API_KEY（财务交叉验证不可用）")
        print(f"  tickflow: {tf_status}")
        print()
        parser.print_help()
        sys.exit(1)

    no_cache = getattr(args, "no_cache", False)
    cmds = {
        "quote": lambda: cmd_quote(args.code, no_cache=no_cache),
        "financials": lambda: cmd_financials(args.code, no_cache=no_cache),
        "valuation": lambda: cmd_valuation(args.code, no_cache=no_cache),
        "history": lambda: cmd_history(args.code, args.days, args.json, no_cache=no_cache),
        "search": lambda: cmd_search(args.keyword),
    }
    try:
        cmds[args.command]()
    except (ConnectionError, json.JSONDecodeError) as e:
        domain = ""
        msg = str(e)
        for token in msg.split():
            if token.startswith("http"):
                domain = urlparse(token).netloc
                break
        print(f"❌ 接口请求失败（已重试 {_RETRIES} 次）: {msg}", file=sys.stderr)
        if domain:
            print(f"   失败域名: {domain}", file=sys.stderr)
        print("   降级路径（按 skills/financial-data/SKILL.md 回退顺序）：", file=sys.stderr)
        print("   A股: akshare/THS → 东方财富 → 巨潮资讯 → 新浪财经", file=sys.stderr)
        print("   美股: yfinance → macrotrends → stockanalysis → wsj → SEC EDGAR", file=sys.stderr)
        print("   港股: yfinance → aastocks → macrotrends(ADR) → 富途 → 披露易", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
