"""去劣筛选核心评分逻辑 — 7 条硬指标的阈值定义与打分函数。

零外部依赖，可被 quality_screen.py CLI 入口和测试直接 import。

用法：
    from core.metrics import RULES, grade_indicators

    grades = grade_indicators({
        "roe_avg": 25, "fcf_5y": 1000, "interest_cover": 20,
        "gross_margin": 50, "ocf_ni": 1.1, "net_margin": 30,
        "dilution_pct": -2, "dilution_note": "",
    })
"""

from core.formatting import fmt_num as _fmt_num

# (编号, 名称, 排除条件描述)
RULES = [
    ("1", "平均ROE", "< 8%"),
    ("2", "5年累计FCF", "为负"),
    ("3", "利息覆盖倍数", "< 2倍"),
    ("4", "毛利率", "< 15%"),
    ("5", "OCF/净利润", "< 0.7"),
    ("6", "净利率", "< 5%"),
    ("7", "股本膨胀", "> 20%"),
]

# 阈值常量（供外部引用或测试断言）
THRESHOLDS = {
    "roe_fail": 8,
    "roe_edge": 10,
    "fcf_fail": 0,
    "interest_cover_fail": 2,
    "interest_cover_edge": 3,
    "gross_margin_fail": 15,
    "gross_margin_edge": 18,
    "ocf_ni_fail": 0.7,
    "ocf_ni_edge": 0.8,
    "net_margin_fail": 5,
    "net_margin_edge": 6,
    "dilution_fail": 20,
    "dilution_edge": 15,
}


def grade_indicators(m: dict) -> list:
    """对 7 条去劣指标逐条打分。

    Args:
        m: 指标字典，含 roe_avg / fcf_5y / interest_cover / gross_margin /
           ocf_ni / net_margin / dilution_pct / dilution_note 字段。

    Returns:
        [(编号, 名称, 状态, 说明)]；状态: pass / fail / edge / na。
    """
    out = []

    def _judge(no, name, value, fail_cond, edge_cond, fmt):
        if value is None:
            out.append((no, name, "na", "需人工补充（工具无原始数据）"))
        elif fail_cond(value):
            out.append((no, name, "fail", fmt(value)))
        elif edge_cond(value):
            out.append((no, name, "edge", fmt(value) + "（边界，需复核）"))
        else:
            out.append((no, name, "pass", fmt(value)))

    t = THRESHOLDS
    _judge("1", "平均ROE", m["roe_avg"],
           lambda v: v < t["roe_fail"], lambda v: v < t["roe_edge"],
           lambda v: f"{v:.1f}%")
    _judge("2", "5年累计FCF", m["fcf_5y"],
           lambda v: v < t["fcf_fail"], lambda v: False,
           lambda v: _fmt_num(v))
    _judge("3", "利息覆盖倍数", m["interest_cover"],
           lambda v: v < t["interest_cover_fail"], lambda v: v < t["interest_cover_edge"],
           lambda v: f"{v:.1f}x")
    _judge("4", "毛利率", m["gross_margin"],
           lambda v: v < t["gross_margin_fail"], lambda v: v < t["gross_margin_edge"],
           lambda v: f"{v:.1f}%")
    _judge("5", "OCF/净利润", m["ocf_ni"],
           lambda v: v < t["ocf_ni_fail"], lambda v: v < t["ocf_ni_edge"],
           lambda v: f"{v:.2f}")
    _judge("6", "净利率", m["net_margin"],
           lambda v: v < t["net_margin_fail"], lambda v: v < t["net_margin_edge"],
           lambda v: f"{v:.1f}%")
    _judge("7", "股本膨胀", m["dilution_pct"],
           lambda v: v > t["dilution_fail"], lambda v: v > t["dilution_edge"],
           lambda v: f"{v:+.1f}%" + (f" {m['dilution_note']}" if m.get("dilution_note") else ""))
    return out
