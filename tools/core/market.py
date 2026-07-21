"""市场识别与代码转换纯函数 — 零外部依赖。

从 ashare_data.py 提取的纯业务逻辑，可被 CLI 入口和测试直接 import。

用法：
    from core.market import normalize_code, market, detect_market_type
    from core.market import qq_code, yf_ticker, tickflow_symbol
"""


def normalize_code(code: str) -> str:
    """去掉交易所后缀（.SH/.SZ/.BJ），返回纯数字股票代码。"""
    return code.strip().upper().replace(".SH", "").replace(".SZ", "").replace(".BJ", "")


def market(code: str) -> str:
    """根据代码首位数字推断交易所：沪 SH / 深 SZ / 北 BJ。"""
    code = normalize_code(code)
    if code.startswith(("6", "9", "5")):
        return "SH"
    if code.startswith(("0", "3", "2", "1")):
        return "SZ"
    if code.startswith(("4", "8")):
        return "BJ"
    return "SH"


def detect_market_type(code: str) -> str:
    """检测代码所属市场类型：'A' / 'HK' / 'US'。"""
    c = code.strip()
    cu = c.upper()
    if cu.endswith(".HK") or (cu.startswith("HK") and cu[2:].isdigit()):
        return "HK"
    if cu.startswith("US") and len(cu) > 2 and not cu[2:].isdigit():
        return "US"
    return "A"


def qq_code(code: str) -> str:
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
    code = normalize_code(c)
    return f"{market(code).lower()}{code}"


def yf_ticker(code: str) -> str:
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


def tickflow_symbol(code: str) -> str:
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
    code_clean = normalize_code(c)
    mkt = market(code_clean)
    return f"{code_clean}.{mkt}"


def market_label(qq_code_str: str) -> str:
    """根据腾讯行情代码前缀返回市场标签与币种提示。"""
    if qq_code_str.startswith("hk"):
        return "港股（币种：港元）"
    if qq_code_str.startswith("us"):
        return "美股（币种：美元）"
    return "A股（币种：人民币）"
