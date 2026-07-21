"""精确十进制估值计算引擎 — 零外部依赖的核心数学函数。

从 financial_rigor.py 提取的纯计算逻辑，可被 CLI 入口和测试直接 import。

用法：
    from core.valuation import exact, fmt_number, cagr, dcf_intrinsic_value

    result = cagr(begin=2261, end=6603, years=5)  # → 0.2391...
"""

from decimal import ROUND_HALF_EVEN, Context, Decimal

from core.exceptions import CalculationError

# 精确十进制上下文（28位有效数字，银行家舍入）
CTX = Context(prec=28, rounding=ROUND_HALF_EVEN)


def exact(value) -> Decimal:
    """将任意数值转换为精确的 Decimal，规避浮点数陷阱。

    统一先转成字符串再构造 Decimal（如 0.1 → "0.1"），
    避免 Decimal(0.1) 产生的二进制误差。
    """
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def fmt_number(d, unit: str = "") -> str:
    """将大额数字格式化为易读形式（亿 / 万亿 / B / T）。"""
    if isinstance(d, Decimal):
        v = float(d)
    else:
        v = float(d)
    abs_v = abs(v)
    if unit in ("亿", "亿元", "亿港元", "亿美元"):
        if abs_v >= 10000:
            return f"{v / 10000:.2f}万亿{unit[1:] if len(unit) > 1 else ''}"
        return f"{v:.2f}{unit}"
    if abs_v >= 1e12:
        return f"{v / 1e12:.2f}T"
    if abs_v >= 1e9:
        return f"{v / 1e9:.2f}B"
    if abs_v >= 1e6:
        return f"{v / 1e6:.2f}M"
    return f"{v:,.2f}"


def cagr(begin, end, years) -> float:
    """复合年增长率精确计算。

    Args:
        begin: 起始值（必须 > 0）
        end: 终止值（必须 > 0）
        years: 年数（必须 > 0）

    Returns:
        CAGR 小数形式（如 0.2391 表示 23.91%）

    Raises:
        ValueError: 参数不合法
    """
    b, e, y = float(begin), float(end), float(years)
    if b <= 0 or e <= 0 or y <= 0:
        raise CalculationError(f"参数必须均为正数: begin={b}, end={e}, years={y}")
    return (e / b) ** (1 / y) - 1


def dcf_intrinsic_value(
    fcf: float,
    growth_rate: float,
    discount_rate: float,
    terminal_growth: float,
    years: int = 10,
) -> float:
    """简化 DCF 内在价值计算（两阶段模型）。

    Args:
        fcf: 当前自由现金流
        growth_rate: 前 N 年增长率
        discount_rate: 贴现率（必须 > terminal_growth）
        terminal_growth: 永续增长率
        years: 高增长阶段年数

    Returns:
        内在价值（与 fcf 同单位）

    Raises:
        ValueError: 贴现率 <= 永续增长率
    """
    if discount_rate <= terminal_growth:
        raise CalculationError(
            f"贴现率({discount_rate})必须大于永续增长率({terminal_growth})"
        )

    total_pv = 0.0
    projected_fcf = fcf
    for yr in range(1, years + 1):
        projected_fcf *= (1 + growth_rate)
        total_pv += projected_fcf / (1 + discount_rate) ** yr

    # 终值
    terminal_value = projected_fcf * (1 + terminal_growth) / (discount_rate - terminal_growth)
    total_pv += terminal_value / (1 + discount_rate) ** years

    return total_pv


def reverse_dcf_implied_growth(
    market_cap: float,
    fcf: float,
    discount_rate: float,
    terminal_growth: float,
    years: int = 10,
) -> float:
    """从当前市值反解隐含增长率（二分法求解）。

    Args:
        market_cap: 当前市值
        fcf: 当前自由现金流（必须 > 0）
        discount_rate: 贴现率
        terminal_growth: 永续增长率
        years: 高增长阶段年数

    Returns:
        隐含增长率（小数形式）

    Raises:
        ValueError: 参数不合法
    """
    if fcf <= 0:
        raise CalculationError(f"FCF 必须为正: {fcf}")
    if market_cap <= 0:
        raise CalculationError(f"市值必须为正: {market_cap}")
    if discount_rate <= terminal_growth:
        raise CalculationError("贴现率必须大于永续增长率")

    lo, hi = -0.5, 1.0
    for _ in range(100):  # 二分迭代
        mid = (lo + hi) / 2
        iv = dcf_intrinsic_value(fcf, mid, discount_rate, terminal_growth, years)
        if iv < market_cap:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def valuation_percentile(current: float, history: list) -> float:
    """计算当前值在历史序列中的百分位。

    Args:
        current: 当前值（如当前 PE）
        history: 历史值列表（至少 5 个数据点）

    Returns:
        百分位（0-100），表示当前值低于历史中多少比例的数据点

    Raises:
        ValueError: 历史数据不足
    """
    if len(history) < 5:
        raise CalculationError(f"历史数据至少需要 5 个数据点，当前仅 {len(history)} 个")
    below = sum(1 for h in history if h < current)
    return below / len(history) * 100
