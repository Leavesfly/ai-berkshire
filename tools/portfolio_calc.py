#!/usr/bin/env python3
"""组合层计算工具 — 集中度、相关性矩阵、加权预期回报（禁止心算的组合版）。

对应 skills/portfolio-review/SKILL.md 第四步「组合层面分析」的可计算部分：
  1. 集中度 —— 第一/前三大持仓占比、持仓数量、现金占比 vs 建议区间
  2. 相关性 —— 基于近一年日收益率的皮尔逊相关系数矩阵（识别隐性风险共振）
  3. 预期回报 —— 各持仓预期年化的加权汇总，与无风险利率对照

用法（由 Skills 自动调用）：
    python3 tools/portfolio_calc.py --holdings '[
        {"name":"腾讯","code":"hk00700","weight":0.30,"expected_return":0.12},
        {"name":"茅台","code":"600519","weight":0.25,"expected_return":0.10},
        {"name":"英伟达","code":"usNVDA","weight":0.15},
        {"name":"现金","code":"cash","weight":0.30,"expected_return":0.04}]'
    python3 tools/portfolio_calc.py --holdings '...' --days 250 --risk-free 0.04
    python3 tools/portfolio_calc.py --holdings '...' --no-corr     # 跳过取数，只算结构

说明：weight 为小数占比（合计应≈1）；现金用 code="cash"；expected_return 可选
（来自 three-scenario/reverse-dcf 推演，缺省则不计入加权回报）。
相关性走 ashare_data 日K通道（1天缓存）；定性关联（同行业/供应链）仍由流程判断。

依赖：零外部依赖（相关性需网络取日K）。
退出码：0=完成 / 1=取数全部失败 / 2=参数错误。
"""

import argparse
import json
import math
import sys

from utils import EXIT_BAD_ARGS, EXIT_OK


def _pearson(xs, ys):
    n = len(xs)
    if n < 2:
        return None
    mx, my = sum(xs) / n, sum(ys) / n
    cov = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    vx = sum((x - mx) ** 2 for x in xs)
    vy = sum((y - my) ** 2 for y in ys)
    if vx == 0 or vy == 0:
        return None
    return cov / math.sqrt(vx * vy)


def _daily_returns(series):
    """[{date, close}] → {date: 日收益率}。"""
    rets = {}
    for prev, cur in zip(series, series[1:]):
        if prev["close"] > 0:
            rets[cur["date"]] = cur["close"] / prev["close"] - 1
    return rets


def analyze_concentration(holdings):
    print("─" * 66)
    print("1. 集中度分析")
    print("─" * 66)
    stocks = sorted(
        [h for h in holdings if h["code"].lower() != "cash"], key=lambda h: -h["weight"]
    )
    cash_w = sum(h["weight"] for h in holdings if h["code"].lower() == "cash")
    total_w = sum(h["weight"] for h in holdings)
    if abs(total_w - 1) > 0.02:
        print(f"  ⚠️ 权重合计 {total_w:.2f} ≠ 1，请核对输入（下方比例按原值计算）")

    top1 = stocks[0]["weight"] if stocks else 0
    top3 = sum(h["weight"] for h in stocks[:3])

    rows = [
        (
            "第一大持仓占比",
            f"{top1 * 100:.1f}%" + (f"（{stocks[0]['name']}）" if stocks else ""),
            "<40%",
            top1 < 0.40,
        ),
        ("前三大持仓占比", f"{top3 * 100:.1f}%", "50-80%", 0.50 <= top3 <= 0.80),
        ("持仓数量（非现金）", str(len(stocks)), "5-15只", 5 <= len(stocks) <= 15),
        ("现金占比", f"{cash_w * 100:.1f}%", "10-30%（视市场环境）", 0.10 <= cash_w <= 0.30),
    ]
    for name, val, ref, ok in rows:
        print(f"  {'✅' if ok else '⚠️'} {name:16s} {val:24s} 建议 {ref}")
    print("  提示: 建议区间来自 portfolio-review 规范；李录式集中（3-5只前3占80%+）")
    print("        要求每只都研究透彻，偏离区间本身不是错误，须说明理由")


def analyze_correlation(holdings, days):
    import ashare_data  # 延迟导入：仅相关性分析需要网络取数

    print()
    print("─" * 66)
    print(f"2. 相关性矩阵（近 {days} 个交易日日收益率，Pearson）")
    print("─" * 66)
    stocks = [h for h in holdings if h["code"].lower() != "cash"]
    if len(stocks) < 2:
        print("  （非现金持仓不足 2 只，跳过）")
        return

    returns, failed = {}, []
    for h in stocks:
        try:
            series, _note = ashare_data.get_close_series(h["code"], days)
        except Exception:
            series = []
        if series and len(series) > 20:
            returns[h["name"]] = _daily_returns(series)
        else:
            failed.append(h["name"])
    if failed:
        print(f"  ⚠️ 取数失败（不计入矩阵）: {', '.join(failed)}")
    names = list(returns.keys())
    if len(names) < 2:
        print("  ❌ 可用序列不足 2 只，相关性分析降级为定性判断（同行业/同主题人工识别）")
        return

    col_w = max(8, max(len(n) for n in names) + 2)
    print("  " + " " * col_w + "".join(f"{n:>{col_w}}" for n in names))
    high_pairs = []
    for i, a in enumerate(names):
        row = f"  {a:{col_w}}"
        for j, b in enumerate(names):
            if j < i:
                row += " " * col_w
                continue
            if a == b:
                row += f"{'1.00':>{col_w}}"
                continue
            common = sorted(set(returns[a]) & set(returns[b]))
            corr = (
                _pearson([returns[a][d] for d in common], [returns[b][d] for d in common])
                if len(common) > 20
                else None
            )
            cell = f"{corr:.2f}" if corr is not None else "-"
            row += f"{cell:>{col_w}}"
            if corr is not None and j > i and corr >= 0.7:
                high_pairs.append((a, b, corr))
        print(row)

    print()
    if high_pairs:
        for a, b, c in high_pairs:
            print(f"  ⚠️ {a} × {b} 相关系数 {c:.2f} ≥ 0.7：存在风险共振，合并视为一个风险敞口评估")
    else:
        print("  ✅ 无高相关（≥0.7）持仓对")
    print("  提示: 价格相关性只捕捉历史共振；供应链/监管等隐性关联仍需定性识别")


def analyze_expected_return(holdings, risk_free):
    print()
    print("─" * 66)
    print(f"3. 加权预期回报（无风险利率 {risk_free * 100:.1f}% 对照）")
    print("─" * 66)
    known = [h for h in holdings if isinstance(h.get("expected_return"), (int, float))]
    missing = [h["name"] for h in holdings if h not in known]

    if not known:
        print(
            "  （所有持仓均未提供 expected_return，跳过——预期回报应来自 three-scenario/reverse-dcf 推演）"
        )
        return
    print(f"  {'标的':10s} {'占比':>8s} {'预期年化':>10s} {'贡献':>8s}  对照")
    print("  " + "-" * 52)
    weighted = 0.0
    for h in sorted(known, key=lambda x: -x["expected_return"]):
        er, w = h["expected_return"], h["weight"]
        weighted += er * w
        if h["code"].lower() == "cash":
            flag = "— 现金底仓（机会成本基准）"
        elif er > risk_free:
            flag = "✅"
        else:
            flag = "❌ 不高于无风险利率，检视是否换成现金"
        print(f"  {h['name']:10s} {w * 100:>7.1f}% {er * 100:>9.1f}% {er * w * 100:>7.2f}%  {flag}")
    covered = sum(h["weight"] for h in known)
    print()
    print(f"  → 加权预期回报: {weighted * 100:.2f}%/年（覆盖 {covered * 100:.0f}% 仓位）")
    if missing:
        print(f"  ⚠️ 未提供预期回报: {', '.join(missing)}——需先用 three-scenario 推演后重算")
    if covered > 0 and weighted / covered < risk_free:
        print(f"  ❌ 覆盖仓位的加权回报低于无风险利率 {risk_free * 100:.1f}%，组合结构需要检视")


def analyze_drawdown(holdings, days):
    """历史回撤模拟：用当前权重回测近 N 日组合净值，输出最大回撤与年化波动。"""
    import ashare_data  # 延迟导入：仅回撤模拟需要网络取数

    print()
    print("─" * 66)
    print(f"4. 历史回撤模拟（当前权重 × 近 {days} 日日收益，现金计 0 收益）")
    print("─" * 66)
    stocks = [h for h in holdings if h["code"].lower() != "cash"]
    cash_w = sum(h["weight"] for h in holdings if h["code"].lower() == "cash")
    returns, failed = {}, []
    for h in stocks:
        try:
            series, _note = ashare_data.get_close_series(h["code"], days)
        except Exception:
            series = []
        if series and len(series) > 20:
            returns[h["code"]] = (_daily_returns(series), h["weight"])
        else:
            failed.append(h["name"])
    if failed:
        print(f"  ⚠️ 取数失败（按 0 收益计入，回撤会被低估）: {', '.join(failed)}")
    if not returns:
        print("  ❌ 无可用序列，跳过回撤模拟")
        return

    # 交易日并集（不同市场休市日不同，缺失日按 0 收益处理）
    all_dates = sorted(set().union(*[set(r) for r, _w in returns.values()]))
    nav, peak, max_dd, dd_date = 1.0, 1.0, 0.0, ""
    daily = []
    for d in all_dates:
        day_ret = sum(r.get(d, 0.0) * w for r, w in returns.values())
        daily.append(day_ret)
        nav *= 1 + day_ret
        peak = max(peak, nav)
        dd = nav / peak - 1
        if dd < max_dd:
            max_dd, dd_date = dd, d
    n = len(daily)
    mean = sum(daily) / n
    vol = (sum((x - mean) ** 2 for x in daily) / (n - 1)) ** 0.5 * (250**0.5) if n > 1 else 0

    print(
        f"  区间组合收益:   {(nav - 1) * 100:+.1f}%（{all_dates[0]} ~ {all_dates[-1]}，股票仓 {sum(w for _r, w in returns.values()) * 100:.0f}% + 现金 {cash_w * 100:.0f}%）"
    )
    print(f"  最大回撤:       {max_dd * 100:.1f}%（低点 {dd_date}）")
    print(f"  年化波动率:     {vol * 100:.1f}%")
    if abs(max_dd) > 0.30:
        print("  ⚠️ 历史最大回撤超 30%：自问能否扛住同等跌幅不割肉；扛不住就降集中度或加现金")
    print("  提示: 回撤是历史重演非预测；价值投资者真正的风险是永久性损失，不是波动本身")


def main():
    parser = argparse.ArgumentParser(
        description="组合层计算 — 集中度/相关性/加权预期回报",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--holdings",
        required=True,
        help='JSON数组: [{"name","code","weight","expected_return"?},...]，现金 code="cash"',
    )
    parser.add_argument("--days", type=int, default=250, help="相关性计算窗口（默认250交易日）")
    parser.add_argument("--risk-free", type=float, default=0.04, help="无风险利率（默认0.04）")
    parser.add_argument("--no-corr", action="store_true", help="跳过相关性取数（离线模式）")
    parser.add_argument(
        "--drawdown", action="store_true", help="额外输出历史回撤模拟（需网络取日K）"
    )
    args = parser.parse_args()

    try:
        holdings = json.loads(args.holdings)
        assert isinstance(holdings, list) and holdings
        for h in holdings:
            assert "name" in h and "code" in h and isinstance(h.get("weight"), (int, float))
    except (json.JSONDecodeError, AssertionError):
        print('❌ --holdings 格式错误。示例: [{"name":"腾讯","code":"hk00700","weight":0.3}]')
        print('   weight 为小数占比；现金用 code="cash"')
        sys.exit(EXIT_BAD_ARGS)

    print("=" * 66)
    print(f"组合层计算（{len(holdings)} 个持仓，含现金）")
    print("=" * 66)
    analyze_concentration(holdings)
    if not args.no_corr:
        analyze_correlation(holdings, args.days)
    analyze_expected_return(holdings, args.risk_free)
    if args.drawdown:
        analyze_drawdown(holdings, args.days)
    print()
    print("  ✅ 以上为可计算部分；机会成本排序/压力测试/调仓建议由 portfolio-review 流程完成")
    sys.exit(EXIT_OK)


if __name__ == "__main__":
    main()
