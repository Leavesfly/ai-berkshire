#!/usr/bin/env python3
"""去劣筛选硬指标程序化 — quality-screen 七条指标的自动取数与打分。

对应 skills/quality-screen/SKILL.md 的 7 条去劣指标，自动拉取财务数据逐条检验，
替代逐家手工取数（更快、更准、可批量）。工具只做**硬指标初筛**：
豁免规则（战略投入期/主动低利润率/高周转薄利）与银行保险特例仍由流程结合定性判断。

数据通道：
  - A股：ashare_data 财务通道（akshare 同花顺源，近5年）——可自动检验 5/7 条
  - 港股/美股：yfinance（利润表+现金流+资产负债表，近4-5个财年）——可自动检验 7/7 条
  - 自动取不到的指标输出「需人工补充」，绝不臆测填充

用法（由 Skills 自动调用）：
    python3 tools/quality_screen.py 600519                    # 单家
    python3 tools/quality_screen.py 600519 hk00700 usAAPL     # 批量
    python3 tools/quality_screen.py usCOST --json             # 机器可读输出

依赖：A股需 akshare（缺失时走东财降级源）；港美股需 yfinance。
退出码：0=完成（无论通过与否）/ 1=全部标的取数失败 / 2=参数错误。
"""

import argparse
import json
import sys

from core.metrics import RULES as _RULES  # noqa: F401 — 保持外部可访问
from core.metrics import grade_indicators as _grade_core
from utils import EXIT_FAIL, EXIT_OK


def _avg(values):
    vals = [v for v in values if v is not None]
    return sum(vals) / len(vals) if vals else None


# ---------------------------------------------------------------------------
# A股指标提取（基于 ashare_data 财务摘要，近5年）
# ---------------------------------------------------------------------------


def _metrics_a(code: str) -> dict:
    """从 A 股财务摘要计算可得指标；FCF/利息覆盖无原始数据，标记人工补充。"""
    import ashare_data  # 延迟导入：仅取数时需要

    code_clean = ashare_data._normalize_code(code)
    if ashare_data._HAS_AKSHARE:
        try:
            reports = ashare_data._fetch_financials_a_akshare(code_clean)
        except Exception:
            reports = ashare_data._fetch_financials_a_eastmoney(code_clean)
    else:
        reports = ashare_data._fetch_financials_a_eastmoney(code_clean)
    if not reports:
        raise ConnectionError(f"未获取到 {code} 的财务数据")

    roe_avg = _avg([r.get("roe") for r in reports])
    gm_avg = _avg([r.get("gross_margin") for r in reports])
    nm_avg = _avg([r.get("net_margin") for r in reports])

    # OCF/NI：用每股口径近似（每股经营现金流 / EPS），无需总股本
    ocf_ni = _avg(
        [
            r["ocf_per_share"] / r["eps"]
            for r in reports
            if r.get("ocf_per_share") is not None and r.get("eps") not in (None, 0)
        ]
    )

    # 股本膨胀：用 净利润/EPS 估算各年股本（近似值，标注 [估计]）
    dilution = None
    est_shares = [
        r["net_profit"] / r["eps"]
        for r in reports
        if r.get("net_profit") is not None and r.get("eps") not in (None, 0)
    ]
    if len(est_shares) >= 2 and est_shares[-1] > 0:
        dilution = (est_shares[0] / est_shares[-1] - 1) * 100  # 最新在前

    return {
        "years": len(reports),
        "roe_avg": roe_avg,
        "fcf_5y": None,  # 摘要无 capex，需人工补充
        "interest_cover": None,  # 摘要无利息支出，需人工补充
        "gross_margin": gm_avg,
        "ocf_ni": ocf_ni,
        "net_margin": nm_avg,
        "dilution_pct": dilution,
        "dilution_note": "[估计] 股本由净利润/EPS反推",
        "source": "akshare/同花顺" if ashare_data._HAS_AKSHARE else "东方财富API",
    }


# ---------------------------------------------------------------------------
# 港股/美股指标提取（yfinance 三表，近4-5个财年）
# ---------------------------------------------------------------------------


def _yf_row(df, names, col):
    """按候选行名取值（不同公司行名有差异），无则 None。"""
    for name in names:
        if name in df.index:
            v = df.loc[name, col]
            if v == v:  # not NaN
                return float(v)
    return None


def _metrics_yf(code: str) -> dict:
    import ashare_data  # 延迟导入：仅取数时需要
    import yfinance as yf

    t = yf.Ticker(ashare_data._yf_ticker(code))
    inc, cf, bs = t.income_stmt, t.cashflow, t.balance_sheet
    if inc is None or inc.empty:
        raise ConnectionError(f"yfinance 无 {code} 利润表数据")

    cols = list(inc.columns)[:5]
    roes, gms, nms, ocf_nis, fcfs = [], [], [], [], []
    interest_cover = None
    shares_series = []

    for col in cols:
        rev = _yf_row(inc, ["Total Revenue"], col)
        ni = _yf_row(inc, ["Net Income"], col)
        gp = _yf_row(inc, ["Gross Profit"], col)
        if rev and gp is not None:
            gms.append(gp / rev * 100)
        if rev and ni is not None:
            nms.append(ni / rev * 100)
        if bs is not None and not bs.empty and col in bs.columns:
            eq = _yf_row(bs, ["Stockholders Equity", "Total Equity Gross Minority Interest"], col)
            if eq and ni is not None:
                roes.append(ni / eq * 100)
            sh = _yf_row(bs, ["Share Issued", "Ordinary Shares Number"], col)
            if sh:
                shares_series.append(sh)
        if cf is not None and not cf.empty and col in cf.columns:
            fcf = _yf_row(cf, ["Free Cash Flow"], col)
            if fcf is None:
                ocf_ = _yf_row(cf, ["Operating Cash Flow"], col)
                capex = _yf_row(cf, ["Capital Expenditure"], col)
                if ocf_ is not None and capex is not None:
                    fcf = ocf_ + capex  # capex 为负数
            if fcf is not None:
                fcfs.append(fcf)
            ocf = _yf_row(cf, ["Operating Cash Flow"], col)
            if ocf is not None and ni not in (None, 0):
                ocf_nis.append(ocf / ni)
        if interest_cover is None:
            ebit = _yf_row(inc, ["EBIT", "Operating Income"], col)
            interest = _yf_row(inc, ["Interest Expense"], col)
            if ebit is not None and interest not in (None, 0):
                interest_cover = ebit / abs(interest)

    dilution = None
    if len(shares_series) >= 2 and shares_series[-1] > 0:
        dilution = (shares_series[0] / shares_series[-1] - 1) * 100  # 最新在前

    return {
        "years": len(cols),
        "roe_avg": _avg(roes),
        "fcf_5y": sum(fcfs) if fcfs else None,
        "interest_cover": interest_cover,
        "gross_margin": _avg(gms),
        "ocf_ni": _avg(ocf_nis),
        "net_margin": _avg(nms),
        "dilution_pct": dilution,
        "dilution_note": "",
        "source": "yfinance/Yahoo Finance",
    }


# ---------------------------------------------------------------------------
# 打分（委托 core.metrics，保持原有 _grade 接口兼容）
# ---------------------------------------------------------------------------


def _grade(m: dict) -> list:
    """返回 [(编号, 名称, 状态, 说明)]；状态: pass/fail/edge/na。"""
    return _grade_core(m)


_STATUS_ICON = {"pass": "✅", "fail": "❌", "edge": "⚠️", "na": "❓"}


def screen_one(code: str) -> dict:
    """单标的筛选，返回结构化结果。"""
    import ashare_data  # 延迟导入：仅市场检测需要

    mkt = ashare_data._detect_market_type(code)
    metrics = _metrics_a(code) if mkt == "A" else _metrics_yf(code)
    grades = _grade(metrics)
    fails = [g for g in grades if g[2] == "fail"]
    nas = [g for g in grades if g[2] == "na"]
    if fails:
        verdict = "排除（触犯硬指标，豁免规则见 quality-screen SKILL.md 第{}条）".format(
            "/".join(g[0] for g in fails)
        )
    elif nas:
        verdict = f"初步通过（{len(nas)} 项需人工补充后终判）"
    else:
        verdict = "通过硬指标初筛"
    return {
        "code": code,
        "market": mkt,
        "metrics": metrics,
        "grades": grades,
        "verdict": verdict,
        "fail_rules": [g[0] for g in fails],
        "na_rules": [g[0] for g in nas],
    }


def main():
    parser = argparse.ArgumentParser(
        description="去劣筛选硬指标程序化 — 7条指标自动取数打分",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("codes", nargs="+", help="股票代码，如 600519 hk00700 usAAPL")
    parser.add_argument("--json", action="store_true", help="输出JSON（供批量汇总）")
    args = parser.parse_args()

    results, errors = [], []
    for code in args.codes:
        try:
            results.append(screen_one(code))
        except Exception as e:
            errors.append((code, str(e)))

    if args.json:
        print(
            json.dumps(
                {"results": results, "errors": [{"code": c, "error": e} for c, e in errors]},
                ensure_ascii=False,
                default=str,
            )
        )
        sys.exit(EXIT_OK if results else EXIT_FAIL)

    for r in results:
        m = r["metrics"]
        print("=" * 66)
        print(f"去劣筛选: {r['code']} — 数据源: {m['source']}（{m['years']} 个财年窗口）")
        print("=" * 66)
        for no, name, status, note in r["grades"]:
            print(f"  {_STATUS_ICON[status]} 第{no}条 {name:12s} {note}")
        print(f"\n  → 初筛结论: {r['verdict']}")
        if m["years"] < 5:
            print(f"  ⚠️ 数据窗口仅 {m['years']} 年（标准要求5-10年），结论标注「数据窗口不足」")
        if r["market"] == "A" and r["na_rules"]:
            print(
                "  提示: A股 FCF/利息覆盖需从年报现金流量表与利润表人工补充（可用 filings_fetch.py 取年报）"
            )
        print("  提示: 触犯指标的公司先查豁免规则（豁免A/B/C），银行保险不适用第3条")
        print()

    for code, err in errors:
        print(f"❌ {code} 取数失败: {err}")
        print("   降级路径：按 skills/quality-screen/SKILL.md 走 WebSearch 手工取数")

    sys.exit(EXIT_OK if results else EXIT_FAIL)


if __name__ == "__main__":
    main()
