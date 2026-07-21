"""财务质量分析纯计算函数 — 零外部依赖（仅标准库 + core 内部）。

从 financial_rigor.py 提取的核心数学逻辑，可被 CLI 入口和测试直接 import。
所有函数无 print / sys.exit，仅返回结构化结果。

用法：
    from core.analysis import compute_m_score, compute_altman_z, compute_accruals
    from core.analysis import compute_kelly, compute_owner_earnings, benford_analysis

    result = compute_kelly(win_prob=0.6, win_return=0.5, loss_return=0.3)
"""

import math
from decimal import Decimal

from core.exceptions import ValidationError
from core.valuation import CTX, exact

# ---------------------------------------------------------------------------
# Beneish M-Score（盈余操纵概率模型）
# ---------------------------------------------------------------------------

MSCORE_FIELDS = (
    "revenue",
    "receivables",
    "cogs",
    "current_assets",
    "ppe",
    "total_assets",
    "depreciation",
    "sga",
    "current_liabilities",
    "long_term_debt",
    "net_income",
    "cfo",
)


def compute_m_score(cur: dict, pri: dict) -> dict:
    """Beneish M-Score 盈余操纵概率模型（需连续两年同口径数据）。

    Args:
        cur: 当年财务数据字典（须含 MSCORE_FIELDS 全部字段）
        pri: 上年财务数据字典

    Returns:
        {"m_score": float, "ok": bool, "indices": dict, "neutral": list}

    Raises:
        ValidationError: 缺少必要字段
    """
    missing = [
        f
        for f in MSCORE_FIELDS
        if not isinstance(cur.get(f), (int, float)) or not isinstance(pri.get(f), (int, float))
    ]
    if missing:
        raise ValidationError(
            f"--current/--prior 缺少字段: {', '.join(missing)}\n"
            f"   全部字段: {', '.join(MSCORE_FIELDS)}（同一币种同一单位，取自年报）"
        )

    def safe_div(a, b):
        return a / b if b else None

    neutral = []

    def idx(name, val):
        if val is None:
            neutral.append(name)
            return 1.0
        return val

    dsri = idx(
        "DSRI",
        safe_div(
            safe_div(cur["receivables"], cur["revenue"]),
            safe_div(pri["receivables"], pri["revenue"]),
        ),
    )
    gm_cur = safe_div(cur["revenue"] - cur["cogs"], cur["revenue"])
    gm_pri = safe_div(pri["revenue"] - pri["cogs"], pri["revenue"])
    gmi = idx("GMI", safe_div(gm_pri, gm_cur))
    aq_cur = safe_div(cur["total_assets"] - cur["current_assets"] - cur["ppe"], cur["total_assets"])
    aq_pri = safe_div(pri["total_assets"] - pri["current_assets"] - pri["ppe"], pri["total_assets"])
    aqi = idx("AQI", safe_div(aq_cur, aq_pri))
    sgi = idx("SGI", safe_div(cur["revenue"], pri["revenue"]))
    dep_cur = safe_div(cur["depreciation"], cur["depreciation"] + cur["ppe"])
    dep_pri = safe_div(pri["depreciation"], pri["depreciation"] + pri["ppe"])
    depi = idx("DEPI", safe_div(dep_pri, dep_cur))
    sgai = idx(
        "SGAI", safe_div(safe_div(cur["sga"], cur["revenue"]), safe_div(pri["sga"], pri["revenue"]))
    )
    lev_cur = safe_div(cur["current_liabilities"] + cur["long_term_debt"], cur["total_assets"])
    lev_pri = safe_div(pri["current_liabilities"] + pri["long_term_debt"], pri["total_assets"])
    lvgi = idx("LVGI", safe_div(lev_cur, lev_pri))
    tata = safe_div(cur["net_income"] - cur["cfo"], cur["total_assets"]) or 0.0

    m = (
        -4.84
        + 0.920 * dsri
        + 0.528 * gmi
        + 0.404 * aqi
        + 0.892 * sgi
        + 0.115 * depi
        - 0.172 * sgai
        + 4.679 * tata
        - 0.327 * lvgi
    )

    indices = {
        "DSRI": dsri, "GMI": gmi, "AQI": aqi, "SGI": sgi,
        "DEPI": depi, "SGAI": sgai, "LVGI": lvgi, "TATA": tata,
    }
    # M > -1.78 高风险；-2.22 ~ -1.78 灰色区；< -2.22 低风险
    ok = m <= -1.78  # 灰色区和低风险都算 ok（不触发退出码 1）

    return {"m_score": m, "ok": ok, "indices": indices, "neutral": neutral}


# ---------------------------------------------------------------------------
# Altman Z-Score（财务困境风险）
# ---------------------------------------------------------------------------


def compute_altman_z(
    working_capital,
    retained_earnings,
    ebit,
    equity_value,
    total_liabilities,
    total_assets,
    revenue=None,
    model="public",
) -> dict:
    """Altman Z-Score 财务困境风险模型。

    Args:
        model: "public"（经典上市制造业）或 "em"（新兴市场 Z''）

    Returns:
        {"z": float, "ok": bool, "x": dict, "safe_line": float, "distress_line": float}

    Raises:
        ValidationError: 参数不合法
    """
    if total_assets <= 0 or total_liabilities <= 0:
        raise ValidationError("总资产/总负债必须 > 0")

    x1 = working_capital / total_assets
    x2 = retained_earnings / total_assets
    x3 = ebit / total_assets
    x4 = equity_value / total_liabilities
    x = {"x1": x1, "x2": x2, "x3": x3, "x4": x4}

    if model == "public":
        if revenue is None:
            raise ValidationError(
                "经典模型需要 --revenue（X5 = 收入/总资产）；非制造业请用 --model em"
            )
        x5 = revenue / total_assets
        x["x5"] = x5
        z = 1.2 * x1 + 1.4 * x2 + 3.3 * x3 + 0.6 * x4 + 1.0 * x5
        safe_line, distress_line = 2.99, 1.81
    else:
        z = 6.56 * x1 + 3.26 * x2 + 6.72 * x3 + 1.05 * x4
        safe_line, distress_line = 2.60, 1.10

    ok = z >= distress_line  # 灰色区和安全区都算 ok
    return {"z": z, "ok": ok, "x": x, "safe_line": safe_line, "distress_line": distress_line}


# ---------------------------------------------------------------------------
# 应计质量（Sloan 应计比率）
# ---------------------------------------------------------------------------


def compute_accruals(net_income, cfo, total_assets) -> dict:
    """应计质量（Sloan 应计比率）：利润含金量与应计占比。

    Returns:
        {"sloan": float, "ocf_ni": float|None, "accruals": float, "ok": bool}

    Raises:
        ValidationError: 总资产 <= 0
    """
    if total_assets <= 0:
        raise ValidationError("总资产必须 > 0")
    accruals = net_income - cfo
    sloan = accruals / total_assets
    ocf_ni = cfo / net_income if net_income else None
    ok = sloan <= 0.10  # > 10% 为高风险
    return {"sloan": sloan, "ocf_ni": ocf_ni, "accruals": accruals, "ok": ok}


# ---------------------------------------------------------------------------
# 凯利公式仓位参考
# ---------------------------------------------------------------------------


def compute_kelly(win_prob, win_return, loss_return, cap=0.25) -> dict:
    """凯利公式仓位参考：f* = p - q/b。

    Returns:
        {"f": float, "half": float, "recommended": float, "b": float, "ok": bool}

    Raises:
        ValidationError: 参数不合法
    """
    if not (0 < win_prob < 1):
        raise ValidationError("--win-prob 需在 (0,1) 区间")
    if win_return <= 0 or loss_return <= 0:
        raise ValidationError("--win/--loss 均为正数（loss 传入亏损幅度的绝对值，如 0.3）")
    b = win_return / loss_return
    q = 1 - win_prob
    f = win_prob - q / b
    if f <= 0:
        return {"f": f, "half": 0, "recommended": 0, "b": b, "ok": False}
    half = f / 2
    rec = min(half, cap)
    return {"f": f, "half": half, "recommended": rec, "b": b, "ok": True}


# ---------------------------------------------------------------------------
# 股东盈余（Owner Earnings, 巴菲特 1986 定义）
# ---------------------------------------------------------------------------


def compute_owner_earnings(
    net_income, depreciation, maintenance_capex, working_capital_change=None
) -> Decimal:
    """股东盈余 = 净利润 + 折旧摊销 − 维持性资本开支 (− 营运资本增加，可选)。

    Returns:
        股东盈余（Decimal，与输入同单位）
    """
    ni = exact(net_income)
    dep = exact(depreciation)
    capex = exact(maintenance_capex)
    oe = CTX.add(ni, dep) - capex
    if working_capital_change is not None:
        oe = oe - exact(working_capital_change)
    return oe


# ---------------------------------------------------------------------------
# Benford 定律检测
# ---------------------------------------------------------------------------

_BENFORD_EXPECTED = {d: math.log10(1 + 1 / d) for d in range(1, 10)}


def benford_analysis(values: list) -> dict | None:
    """对一组财务数字做 Benford 定律检测。

    Returns:
        {"mad": float, "chi2": float, "conformity": str, "is_conforming": bool,
         "n": int, "observed": dict} 或 None（样本不足）
    """
    digits = []
    for v in values:
        v = abs(float(v))
        if v > 0:
            sig = 10 ** (math.log10(v) - math.floor(math.log10(v)))
            d = int(sig)
            if 1 <= d <= 9:
                digits.append(d)

    n = len(digits)
    if n < 50:
        return None

    counts = {}
    for d in digits:
        counts[d] = counts.get(d, 0) + 1
    observed = {d: counts.get(d, 0) / n for d in range(1, 10)}

    mad = sum(abs(observed.get(d, 0) - _BENFORD_EXPECTED[d]) for d in range(1, 10)) / 9
    chi2 = sum(
        (counts.get(d, 0) - _BENFORD_EXPECTED[d] * n) ** 2 / (_BENFORD_EXPECTED[d] * n)
        for d in range(1, 10)
    )

    if mad < 0.006:
        conformity = "Close (高度符合)"
    elif mad < 0.012:
        conformity = "Acceptable (可接受)"
    elif mad < 0.015:
        conformity = "Marginally Acceptable (边缘)"
    else:
        conformity = "Nonconforming (不符合 ⚠️)"

    return {
        "mad": mad,
        "chi2": chi2,
        "conformity": conformity,
        "is_conforming": mad < 0.015,
        "n": n,
        "observed": observed,
    }
