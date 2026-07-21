"""数值格式化纯函数 — 零外部依赖。

从 ashare_data.py 提取的格式化逻辑，可被 CLI 入口和测试直接 import。

用法：
    from core.formatting import fmt_yi, fmt_pct, fmt_num
"""


def fmt_yi(value) -> str:
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


def fmt_pct(value) -> str:
    """将数值格式化为百分比字符串。"""
    if value is None or value == "-" or value == "":
        return "-"
    try:
        return f"{float(value):.2f}%"
    except (ValueError, TypeError):
        return str(value)


def fmt_num(value, unit="") -> str:
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
