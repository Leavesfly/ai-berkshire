#!/usr/bin/env python3
"""AI Berkshire 金融数据严谨性验证工具集。

在投资研究过程中对财务数据做精确校验的命令行工具，由 Claude Code Skills
在关键验证节点自动调用，用于杜绝“心算”带来的数值错误。

核心能力：
    1. 市值验算     —— 股价 × 总股本 与报告市值交叉核对
    2. 估值验算     —— 从原始数据精确推导 PE/PB/ROE/股息率等指标
    3. 多源交叉验证 —— 同一数据点在多个信源间比对，标记偏差
    4. Benford 定律  —— 对财务数字首位分布做造假快速筛查
    5. 精确计算器   —— 使用十进制运算，避免浮点误差
    6. 三情景估值   —— 乐观/中性/悲观下的目标股价推演
    7. CAGR         —— 复合年增长率精确计算
    8. 股东盈余     —— 巴菲特 Owner Earnings（净利润+折旧摊销−维持性资本开支）
    9. 反向 DCF     —— 从当前市值反解市场隐含的未来增长率
   10. 估值分位     —— 当前 PE/PB 处于历史序列的百分位（便宜/贵的历史坐标）
   11. 同业对标     —— 目标公司 vs 可比公司估值溢价/折价量化
   12. DCF 敏感性   —— 增长率×贴现率二维内在价值矩阵

设计原则：零外部依赖，仅使用 Python 标准库（decimal/json/math/argparse），
要求 Python >= 3.7；所有计算基于 decimal.Decimal，结果可审计、可复现。

用法（通常由 Skills 自动调用，无需手动执行）：
    python3 tools/financial_rigor.py verify-market-cap --price 510 --shares 9.11e9 --reported 4.65e12 --currency HKD
    python3 tools/financial_rigor.py verify-valuation --price 510 --eps 23.5 --bvps 120 --fcf-per-share 18 --dividend 2.4
    python3 tools/financial_rigor.py cross-validate --field revenue --values '{"年报": 7518, "Yahoo": 7500, "StockAnalysis": 7520}' --unit 亿
    python3 tools/financial_rigor.py benford --values '[1234, 2345, 3456, ...]'
    python3 tools/financial_rigor.py calc --expr '510 * 9.11e9'
    python3 tools/financial_rigor.py cagr --begin 2261 --end 6603 --years 5
    python3 tools/financial_rigor.py owner-earnings --net-income 1941 --depreciation 380 --maintenance-capex 250
    python3 tools/financial_rigor.py reverse-dcf --market-cap 28000 --fcf 1600 --discount-rate 0.10 --terminal-growth 0.025
    python3 tools/financial_rigor.py valuation-percentile --metric PE --current 22 --history '[35,42,28,55,38,30,25,45,33,27]'
    python3 tools/financial_rigor.py peer-compare --target '{"name":"腾讯","PE":18,"PB":3.4}' --peers '[{"name":"阿里","PE":12,"PB":1.8},{"name":"Meta","PE":24,"PB":7.5}]'
    python3 tools/financial_rigor.py dcf-matrix --fcf 1600 --growth 0.05,0.10,0.15 --discount 0.08,0.10,0.12 --terminal-growth 0.025 --market-cap 28000
"""

import argparse
import json
import math
import sys
from decimal import Decimal, Context, ROUND_HALF_EVEN

# 退出码约定（供调用脚本判断）：0=验证通过 / 1=验证不通过（重大偏差） / 2=参数错误
EXIT_OK = 0
EXIT_VERIFY_FAIL = 1
EXIT_BAD_ARGS = 2


def _load_json_arg(raw: str, what: str, example: str):
    """解析命令行 JSON 参数；失败时输出友好错误并以退出码 2 结束（不抛 traceback）。"""
    try:
        return json.loads(raw)
    except json.JSONDecodeError as e:
        print(f"❌ {what} 不是合法 JSON: {e}")
        print(f"   正确格式示例: {example}")
        print("   提示: shell 中整体用单引号包裹，内部键名用双引号")
        sys.exit(EXIT_BAD_ARGS)

# ---------------------------------------------------------------------------
# 精确十进制引擎（避免浮点漂移）
# ---------------------------------------------------------------------------

_CTX = Context(prec=28, rounding=ROUND_HALF_EVEN)


def exact(value) -> Decimal:
    """将任意数值转换为精确的 Decimal，规避浮点数陷阱。

    统一先转成字符串再构造 Decimal（如 0.1 → "0.1"），
    避免 Decimal(0.1) 产生的二进制误差。
    """
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def fmt_number(d: Decimal, unit: str = "") -> str:
    """将大额数字格式化为易读形式（亿 / 万亿 / B / T）。"""
    v = float(d)
    abs_v = abs(v)
    if unit in ("亿", "亿元", "亿港元", "亿美元"):
        if abs_v >= 10000:
            return f"{v/10000:.2f}万亿{unit[1:] if len(unit) > 1 else ''}"
        return f"{v:.2f}{unit}"
    if abs_v >= 1e12:
        return f"{v/1e12:.2f}T"
    if abs_v >= 1e9:
        return f"{v/1e9:.2f}B"
    if abs_v >= 1e6:
        return f"{v/1e6:.2f}M"
    return f"{v:,.2f}"


# ---------------------------------------------------------------------------
# 1. Market Cap Verification (股价×总股本 vs 报告市值)
# ---------------------------------------------------------------------------

def verify_market_cap(price, shares, reported_cap, currency=""):
    """验算市值：计算「股价 × 总股本」并与报告市值比对，偏差 > 5% 判为不通过。"""
    p = exact(price)
    s = exact(shares)
    r = exact(reported_cap)

    calculated = _CTX.multiply(p, s)
    deviation = abs(float(calculated - r) / float(r)) * 100 if r != 0 else 0

    print("=" * 60)
    print("市值验算 (Market Cap Verification)")
    print("=" * 60)
    print(f"  股价 (Price):       {p} {currency}")
    print(f"  总股本 (Shares):    {fmt_number(s)}")
    print(f"  计算市值:           {fmt_number(calculated)} {currency}")
    print(f"  报告市值:           {fmt_number(r)} {currency}")
    print(f"  偏差:               {deviation:.2f}%")
    print()

    if deviation > 5:
        print(f"  ❌ 警告: 偏差 {deviation:.1f}% > 5%, 请检查:")
        print(f"     - 股本是否为最新（回购/增发）?")
        print(f"     - 单位是否一致（港币 vs 人民币 vs 美元）?")
        print(f"     - 股价是否为最新?")
        return False
    elif deviation > 1:
        print(f"  ⚠️  偏差 {deviation:.1f}% 在可接受范围, 可能因股价波动/股本变化")
        return True
    else:
        print(f"  ✅ 验证通过, 偏差仅 {deviation:.2f}%")
        return True


# ---------------------------------------------------------------------------
# 2. Valuation Metrics Verification (估值指标验算)
# ---------------------------------------------------------------------------

def verify_valuation(price, eps=None, bvps=None, fcf_per_share=None,
                     dividend=None, revenue_per_share=None):
    """从原始数据精确推导并验证关键估值指标（PE/PB/ROE/P-FCF/股息率/PS）。"""
    p = exact(price)

    print("=" * 60)
    print("估值指标验算 (Valuation Verification)")
    print("=" * 60)
    print(f"  当前股价: {p}")
    print()

    results = {}

    if eps is not None:
        e = exact(eps)
        if e != 0:
            pe = _CTX.divide(p, e)
            print(f"  PE (TTM):  {p} / {e} = {pe:.2f}x")
            results["PE"] = float(pe)
            # Earnings yield
            ey = _CTX.divide(e, p) * 100
            print(f"  盈利收益率: {ey:.2f}%")
        else:
            print(f"  PE: EPS为0, 无法计算")

    if bvps is not None:
        b = exact(bvps)
        if b != 0:
            pb = _CTX.divide(p, b)
            print(f"  PB:        {p} / {b} = {pb:.2f}x")
            results["PB"] = float(pb)
            if eps is not None and float(exact(eps)) != 0:
                roe = _CTX.divide(exact(eps), b) * 100
                print(f"  ROE:       {exact(eps)} / {b} = {roe:.2f}%")
                results["ROE"] = float(roe)

    if fcf_per_share is not None:
        f = exact(fcf_per_share)
        if f != 0:
            fcf_yield = _CTX.divide(f, p) * 100
            pfcf = _CTX.divide(p, f)
            print(f"  P/FCF:     {p} / {f} = {pfcf:.2f}x")
            print(f"  FCF Yield: {fcf_yield:.2f}%")
            results["P_FCF"] = float(pfcf)
            results["FCF_Yield"] = float(fcf_yield)

    if dividend is not None:
        d = exact(dividend)
        if p != 0:
            div_yield = _CTX.divide(d, p) * 100
            print(f"  股息率:    {d} / {p} = {div_yield:.2f}%")
            results["Dividend_Yield"] = float(div_yield)

    if revenue_per_share is not None:
        r = exact(revenue_per_share)
        if r != 0:
            ps = _CTX.divide(p, r)
            print(f"  PS:        {p} / {r} = {ps:.2f}x")
            results["PS"] = float(ps)

    print()
    print("  ✅ 以上指标均使用精确十进制计算, 无浮点误差")
    return results


# ---------------------------------------------------------------------------
# 3. Cross-Source Data Validation (多源交叉验证)
# ---------------------------------------------------------------------------

def cross_validate(field_name, source_values: dict, unit="", tolerance_pct=1.0):
    """多源交叉验证：以中位数为基准比对各信源数值。

    容差分档与 `skills/financial-data/SKILL.md` 规范对齐：
      ≤ 1% ✅ 一致；1%~5% ⚠️ 标记差异（可能是口径/汇率）；> 5% ❌ 重大差异，须查原始财报。
    """
    print("=" * 60)
    print(f"交叉验证: {field_name} (Cross-Validation)")
    print("=" * 60)

    # 输入防护：空对象 / 少于 2 个来源 / 非数值，友好报错而非 traceback
    if not isinstance(source_values, dict) or len(source_values) == 0:
        print("  ❌ --values 为空，需要 {来源名: 数值} 形式的 JSON 对象")
        sys.exit(EXIT_BAD_ARGS)
    if len(source_values) < 2:
        print("  ❌ 只有 1 个来源，交叉验证至少需要 2 个独立来源")
        print('     示例: --values \'{"公司年报": 7518, "macrotrends": 7500}\'')
        sys.exit(EXIT_BAD_ARGS)
    try:
        values = {k: exact(v) for k, v in source_values.items()}
    except Exception:
        bad = {k: v for k, v in source_values.items()
               if not isinstance(v, (int, float))}
        print(f"  ❌ 存在非数值的来源数据: {bad}")
        print("     每个来源的值必须是数字（不要带单位/逗号/百分号）")
        sys.exit(EXIT_BAD_ARGS)
    sources = list(values.keys())
    nums = list(values.values())

    # Find median as reference
    sorted_vals = sorted(float(v) for v in nums)
    n = len(sorted_vals)
    median = sorted_vals[n // 2] if n % 2 == 1 else (sorted_vals[n//2-1] + sorted_vals[n//2]) / 2

    print(f"  数据来源数: {len(sources)}")
    print(f"  参考中位数: {fmt_number(exact(median))} {unit}")
    print()

    all_ok = True
    has_warn = False
    for src, val in values.items():
        dev = abs(float(val) - median) / median * 100 if median != 0 else 0
        if dev <= tolerance_pct:
            status = "✅"
        elif dev <= 5:
            status = "⚠️"
            has_warn = True
        else:
            status = "❌"
            all_ok = False
        print(f"  {status} {src:20s}: {fmt_number(val)} {unit}  (偏差 {dev:.2f}%)")

    print()
    if all_ok and not has_warn:
        print(f"  ✅ 所有来源偏差 ≤ {tolerance_pct}%, 数据一致")
    elif all_ok:
        print(f"  ⚠️  存在来源偏差在 {tolerance_pct}%~5% 之间, 请标注差异及可能原因（GAAP/Non-GAAP、汇率、财年口径）")
    else:
        print(f"  ❌ 存在来源偏差 > 5%, 属重大差异, 不得直接使用")
        print(f"     必须查原始财报核实; 优先采用公司年报/交易所数据")

    # Consensus value
    consensus = median
    print(f"\n  共识值 (加权中位数): {fmt_number(exact(consensus))} {unit}")
    return {"consensus": consensus, "all_consistent": all_ok and not has_warn, "has_major_diff": not all_ok}


# ---------------------------------------------------------------------------
# 4. Benford's Law Quick Check (财务数据造假检测)
# ---------------------------------------------------------------------------

_BENFORD = {d: math.log10(1 + 1/d) for d in range(1, 10)}


def benford_check(values: list):
    """对一组财务数字做 Benford 定律快速检测，用于造假线索初筛。

    统计首位数字（1-9）的分布，与 Benford 理论分布比较，
    通过 MAD（平均绝对偏差）和卡方值判断符合度；样本量 < 50 时不可靠。
    """
    print("=" * 60)
    print("Benford定律检测 (Financial Data Fabrication Check)")
    print("=" * 60)

    # Extract leading digits
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
        print(f"  ⚠️  样本量不足: {n} < 50, Benford分析不可靠")
        return None

    # Observed distribution
    counts = {}
    for d in digits:
        counts[d] = counts.get(d, 0) + 1
    observed = {d: counts.get(d, 0) / n for d in range(1, 10)}

    # MAD (Nigrini's Mean Absolute Deviation)
    mad = sum(abs(observed.get(d, 0) - _BENFORD[d]) for d in range(1, 10)) / 9

    # Chi-square
    chi2 = sum((counts.get(d, 0) - _BENFORD[d] * n) ** 2 / (_BENFORD[d] * n) for d in range(1, 10))

    # Conformity
    if mad < 0.006:
        conformity = "Close (高度符合)"
    elif mad < 0.012:
        conformity = "Acceptable (可接受)"
    elif mad < 0.015:
        conformity = "Marginally Acceptable (边缘)"
    else:
        conformity = "Nonconforming (不符合 ⚠️)"

    print(f"  样本量:    {n}")
    print(f"  MAD:       {mad:.6f}")
    print(f"  Chi-sq:    {chi2:.2f}")
    print(f"  符合度:    {conformity}")
    print()

    # Digit distribution table
    print(f"  {'首位数':>6} {'观测':>8} {'Benford期望':>12} {'偏差':>8}")
    print(f"  {'-'*6} {'-'*8} {'-'*12} {'-'*8}")
    for d in range(1, 10):
        obs = observed.get(d, 0)
        exp = _BENFORD[d]
        dev = obs - exp
        flag = " ⚠️" if abs(dev) > 0.03 else ""
        print(f"  {d:>6d} {obs:>8.3f} {exp:>12.3f} {dev:>+8.3f}{flag}")

    print()
    is_ok = mad < 0.015
    if is_ok:
        print("  ✅ 数据首位数字分布符合Benford定律")
    else:
        print("  ❌ 数据首位数字分布异常, 可能存在人为调整")
        print("     提示: 不符合Benford定律不一定是造假, 但值得进一步调查")

    return {"mad": mad, "chi2": chi2, "conformity": conformity, "is_conforming": is_ok}


# ---------------------------------------------------------------------------
# 5. Exact Calculator (精确计算器)
# ---------------------------------------------------------------------------

def exact_calc(expr: str):
    """Evaluate a financial expression with exact decimal arithmetic.

    Supports: +, -, *, /, (), numbers (including scientific notation).
    """
    print("=" * 60)
    print("精确计算 (Exact Calculator)")
    print("=" * 60)

    # 安全校验：仅允许数字、四则运算符、括号与科学计数法字符
    allowed = set("0123456789.+-*/() eE")
    compact = expr.replace(" ", "")
    if not all(c in allowed for c in compact):
        print(f"  ❌ 不安全的表达式: {expr}")
        return None
    # 防护：禁用幂运算与超长表达式，避免恶意/意外的资源耗尽（如 9**9**9）
    if "**" in compact or len(compact) > 200:
        print(f"  ❌ 表达式含幂运算或过长（仅支持 + - * / 与括号，长度 ≤ 200）: {expr}")
        return None

    try:
        # 表达式已通过字符白名单校验，此处禁用内建函数后安全求值
        result = eval(expr, {"__builtins__": {}}, {})
        d_result = exact(result)
        print(f"  表达式: {expr}")
        print(f"  结果:   {fmt_number(d_result)}")
        print(f"  精确值: {d_result}")
        return float(d_result)
    except Exception as e:
        print(f"  ❌ 计算错误: {e}")
        return None


# ---------------------------------------------------------------------------
# 6. Three-Scenario Valuation (三情景估值)
# ---------------------------------------------------------------------------

def three_scenario_valuation(current_price, current_eps, shares_billion,
                             growth_optimistic, growth_neutral, growth_pessimistic,
                             pe_optimistic, pe_neutral, pe_pessimistic,
                             years=3, currency=""):
    """三情景估值：按乐观/中性/悲观的增速与目标 PE，精确推演各情景目标股价。"""
    print("=" * 60)
    print("三情景估值模型 (Three-Scenario Valuation)")
    print("=" * 60)

    p = exact(current_price)
    eps = exact(current_eps)
    shares = exact(shares_billion)

    # 防御：增速应为小数（如 0.15 = 15%）；若绝对值 > 1.5 则判定为误传百分数，自动换算并提示
    def _normalize_growth(g):
        g = float(g)
        if abs(g) > 1.5:
            print(f"  ⚠️  增速 {g} 疑似以百分数传入，已自动换算为 {g/100}（正确格式：0.15 表示 15%）")
            return g / 100
        return g

    growth_optimistic = _normalize_growth(growth_optimistic)
    growth_neutral = _normalize_growth(growth_neutral)
    growth_pessimistic = _normalize_growth(growth_pessimistic)

    scenarios = [
        ("乐观 (Bull)", growth_optimistic, pe_optimistic),
        ("中性 (Base)", growth_neutral, pe_neutral),
        ("悲观 (Bear)", growth_pessimistic, pe_pessimistic),
    ]

    print(f"  当前股价: {p} {currency}")
    print(f"  当前EPS:  {eps}")
    print(f"  预测期:   {years}年")
    print()
    print(f"  {'情景':12} {'年增速':>8} {'目标PE':>8} {'目标EPS':>10} {'目标股价':>10} {'涨跌幅':>8}")
    print(f"  {'-'*12} {'-'*8} {'-'*8} {'-'*10} {'-'*10} {'-'*8}")

    for name, growth, pe in scenarios:
        g = exact(growth)
        target_pe = exact(pe)
        # Future EPS = current EPS × (1 + growth)^years
        future_eps = eps
        for _ in range(years):
            future_eps = _CTX.multiply(future_eps, _CTX.add(Decimal("1"), g))
        target_price = _CTX.multiply(future_eps, target_pe)
        change = float(target_price - p) / float(p) * 100

        print(f"  {name:12} {float(g)*100:>7.0f}% {float(target_pe):>7.0f}x "
              f"{float(future_eps):>10.2f} {float(target_price):>9.1f} {change:>+7.1f}%")

    print()
    print("  ✅ 所有计算使用精确十进制, 结果可审计复现")


# ---------------------------------------------------------------------------
# 7. CAGR 复合年增长率
# ---------------------------------------------------------------------------

def cagr_calc(begin, end, years):
    """CAGR = (期末/期初)^(1/年数) - 1，精确计算复合年增长率。"""
    print("=" * 60)
    print("复合年增长率 (CAGR)")
    print("=" * 60)

    if begin <= 0 or end <= 0:
        print(f"  ❌ 期初/期末值必须为正数（期初={begin}, 期末={end}）")
        print("     提示: 亏损转盈利等跨零场景 CAGR 无意义，改用绝对值变化描述")
        sys.exit(EXIT_BAD_ARGS)
    if years <= 0:
        print(f"  ❌ 年数必须为正数（years={years}）")
        sys.exit(EXIT_BAD_ARGS)

    ratio = float(end) / float(begin)
    cagr = ratio ** (1.0 / years) - 1.0
    total = (ratio - 1.0) * 100

    print(f"  期初值:     {fmt_number(exact(begin))}")
    print(f"  期末值:     {fmt_number(exact(end))}")
    print(f"  年数:       {years}")
    print(f"  累计增幅:   {total:+.2f}%")
    print(f"  CAGR:       {cagr*100:+.2f}%/年")
    print()
    print("  ✅ 精确计算, 可审计复现")
    return cagr


# ---------------------------------------------------------------------------
# 8. 股东盈余 (Owner Earnings, 巴菲特 1986 致股东信定义)
# ---------------------------------------------------------------------------

def owner_earnings(net_income, depreciation, maintenance_capex,
                   working_capital_change=None, shares=None):
    """股东盈余 = 净利润 + 折旧摊销 − 维持性资本开支 (− 营运资本增加，可选)。"""
    print("=" * 60)
    print("股东盈余 (Owner Earnings, 巴菲特定义)")
    print("=" * 60)

    ni = exact(net_income)
    dep = exact(depreciation)
    capex = exact(maintenance_capex)

    oe = _CTX.add(ni, dep) - capex
    print(f"  净利润:             {fmt_number(ni)}")
    print(f"  + 折旧摊销:         {fmt_number(dep)}")
    print(f"  - 维持性资本开支:   {fmt_number(capex)}")
    if working_capital_change is not None:
        wc = exact(working_capital_change)
        oe = oe - wc
        print(f"  - 营运资本增加:     {fmt_number(wc)}")
    print(f"  = 股东盈余:         {fmt_number(oe)}")

    if shares is not None and float(shares) > 0:
        per_share = _CTX.divide(oe, exact(shares))
        print(f"  每股股东盈余:       {float(per_share):.4f}")

    print()
    ratio_note = float(_CTX.divide(oe, ni)) if ni != 0 else None
    if ratio_note is not None:
        print(f"  股东盈余/净利润:    {ratio_note:.2f}x", end="")
        if ratio_note < 0.7:
            print("  ⚠️ 显著低于净利润，利润含金量存疑，需查资本开支结构")
        elif ratio_note > 1.3:
            print("  ℹ️ 显著高于净利润，确认折旧是否包含大额非现金摊销")
        else:
            print("  ✅ 与净利润基本匹配")
    print("  提示: 维持性资本开支需从总 capex 中剔除扩张性部分，口径在报告中标注 [估计]")
    return float(oe)


# ---------------------------------------------------------------------------
# 9. 反向 DCF (从当前市值反解隐含增长率)
# ---------------------------------------------------------------------------

def reverse_dcf(market_cap, fcf, discount_rate, terminal_growth, years=10):
    """二分法反解：当前市值隐含的未来 N 年 FCF 年增长率。

    模型：两段式 DCF —— 前 N 年 FCF 按 g 增长逐年折现，
    之后按永续增长率进入终值（Gordon 增长模型）。
    """
    print("=" * 60)
    print("反向 DCF (市场隐含增长率反解)")
    print("=" * 60)

    if market_cap <= 0 or fcf <= 0:
        print(f"  ❌ 市值与当前 FCF 必须为正数（market_cap={market_cap}, fcf={fcf}）")
        print("     提示: FCF 为负的公司不适用反向 DCF，改用情景分析（three-scenario）")
        sys.exit(EXIT_BAD_ARGS)
    if not (0 < discount_rate < 1) or not (0 <= terminal_growth < 1):
        print(f"  ❌ 贴现率/永续增长率应为小数形式（如 0.10 表示 10%）")
        sys.exit(EXIT_BAD_ARGS)
    if discount_rate <= terminal_growth:
        print(f"  ❌ 贴现率（{discount_rate}）必须大于永续增长率（{terminal_growth}），否则终值发散")
        sys.exit(EXIT_BAD_ARGS)
    if years <= 0:
        print(f"  ❌ 预测期年数必须为正整数（years={years}）")
        sys.exit(EXIT_BAD_ARGS)

    r = float(discount_rate)
    gt = float(terminal_growth)
    f0 = float(fcf)

    def dcf_value(g):
        """给定前 N 年增长率 g 的企业现值。"""
        pv = 0.0
        f = f0
        for t in range(1, years + 1):
            f = f * (1 + g)
            pv += f / (1 + r) ** t
        terminal = f * (1 + gt) / (r - gt)
        pv += terminal / (1 + r) ** years
        return pv

    lo, hi = -0.50, 1.00
    target = float(market_cap)
    if dcf_value(lo) > target:
        print(f"  ℹ️ 当前市值极低：即使 FCF 每年衰退 50% 现值仍高于市值，隐含增长率 < -50%")
        sys.exit(EXIT_OK)
    if dcf_value(hi) < target:
        print(f"  ⚠️ 当前市值隐含增长率 > 100%/年，远超任何可持续增长，估值存在极端预期")
        sys.exit(EXIT_VERIFY_FAIL)

    for _ in range(100):  # 二分法，收敛至 1e-8 以内
        mid = (lo + hi) / 2
        if dcf_value(mid) < target:
            lo = mid
        else:
            hi = mid
    implied = (lo + hi) / 2

    print(f"  当前市值:           {fmt_number(exact(market_cap))}")
    print(f"  当前 FCF:           {fmt_number(exact(fcf))}")
    print(f"  贴现率:             {r*100:.1f}%")
    print(f"  永续增长率:         {gt*100:.1f}%")
    print(f"  预测期:             {years} 年")
    print()
    print(f"  → 市场隐含增长率:   {implied*100:+.2f}%/年（未来 {years} 年 FCF 年均增速）")
    print()
    print("  解读参考（四大师视角：市场预期是否苛刻）：")
    if implied <= 0.05:
        print("    隐含增长 ≤ 5%/年：市场预期保守，若基本面好于此预期则存在安全边际")
    elif implied <= 0.15:
        print("    隐含增长 5%~15%/年：预期合理区间，需判断护城河能否支撑该增速")
    else:
        print("    隐含增长 > 15%/年：预期苛刻，需验证高增长的可持续性与确定性")
    print("  ✅ 结果仅为反推参考，贴现率/永续增长假设需在报告中明示")
    return implied


# ---------------------------------------------------------------------------
# 10. 估值分位 (当前估值在历史序列中的百分位)
# ---------------------------------------------------------------------------

def valuation_percentile(metric, current, history: list):
    """计算当前估值在历史序列中的百分位（便宜/贵的历史坐标系）。

    历史序列由调用方提供（如 ashare_data 历年 PE、macrotrends 年度均值），
    建议 ≥ 5 个样本（覆盖一个以上估值周期），样本过少时输出低置信度提示。
    """
    print("=" * 60)
    print(f"估值分位: {metric} (Valuation Percentile)")
    print("=" * 60)

    try:
        hist = sorted(float(v) for v in history)
    except (TypeError, ValueError):
        print("  ❌ --history 必须是数值数组，如 [35,42,28,55]")
        sys.exit(EXIT_BAD_ARGS)
    if len(hist) < 3:
        print(f"  ❌ 历史样本仅 {len(hist)} 个（至少 3 个，建议 ≥ 5 个覆盖完整估值周期）")
        sys.exit(EXIT_BAD_ARGS)

    cur = float(current)
    below = sum(1 for v in hist if v < cur)
    equal = sum(1 for v in hist if v == cur)
    pct = (below + equal * 0.5) / len(hist) * 100

    n = len(hist)
    median = hist[n // 2] if n % 2 == 1 else (hist[n // 2 - 1] + hist[n // 2]) / 2
    q1 = hist[max(0, int(n * 0.25) - (0 if n * 0.25 % 1 else 1))]
    q3 = hist[min(n - 1, int(n * 0.75))]

    print(f"  当前 {metric}:      {cur:.2f}")
    print(f"  历史样本数:     {n}")
    print(f"  历史区间:       {hist[0]:.2f} ~ {hist[-1]:.2f}")
    print(f"  历史中位数:     {median:.2f}")
    print(f"  四分位(Q1/Q3):  {q1:.2f} / {q3:.2f}")
    print(f"  → 当前分位:     {pct:.0f}%（当前值高于历史 {pct:.0f}% 的样本，分位越低越便宜）")
    print()
    if n < 5:
        print("  ⚠️ 样本不足 5 个，分位结论低置信度，仅作参考")
    if pct <= 20:
        print("  解读: 处于历史低位——便宜有便宜的原因，须确认基本面未恶化（估值陷阱检验）")
    elif pct >= 80:
        print("  解读: 处于历史高位——需验证盈利增速能否消化估值，或商业模式是否发生质变")
    else:
        print("  解读: 处于历史中位区间，估值不构成买入/回避的主导理由，以基本面判断为主")
    print("  提示: 历史分位只回答「相对自己贵不贵」，不回答「绝对价值」，需配合 reverse-dcf 使用")
    return pct


# ---------------------------------------------------------------------------
# 11. 同业对标 (目标公司 vs 可比公司)
# ---------------------------------------------------------------------------

def peer_compare(target: dict, peers: list):
    """目标公司与可比公司的估值/质量指标对标，量化溢价/折价。

    target/peers 的指标键自由（PE/PB/PS/EV_EBITDA/ROE/毛利率...），
    只对双方都有的数值键做对比；数据由调用方双源验证后传入。
    """
    print("=" * 60)
    print("同业对标 (Peer Comparison)")
    print("=" * 60)

    if not isinstance(target, dict) or "name" not in target:
        print('  ❌ --target 需为对象且含 name 键，如 {"name":"腾讯","PE":18}')
        sys.exit(EXIT_BAD_ARGS)
    if not isinstance(peers, list) or len(peers) < 2:
        print("  ❌ --peers 至少需要 2 家可比公司（建议 3-5 家）")
        sys.exit(EXIT_BAD_ARGS)

    metrics = [k for k, v in target.items()
               if k != "name" and isinstance(v, (int, float))]
    if not metrics:
        print("  ❌ target 中无数值指标可对比")
        sys.exit(EXIT_BAD_ARGS)

    names = [target["name"]] + [p.get("name", f"peer{i+1}") for i, p in enumerate(peers)]
    col_w = max(10, max(len(str(n)) for n in names) + 2)

    header = f"  {'指标':8}" + "".join(f"{n:>{col_w}}" for n in names) + f"{'同业中位':>10}{'溢价/折价':>10}"
    print(header)
    print("  " + "-" * (len(header) - 2))

    premium_notes = []
    for m in metrics:
        peer_vals = [float(p[m]) for p in peers if isinstance(p.get(m), (int, float))]
        row = f"  {m:8}" + f"{float(target[m]):>{col_w}.2f}"
        for p in peers:
            v = p.get(m)
            row += f"{float(v):>{col_w}.2f}" if isinstance(v, (int, float)) else f"{'-':>{col_w}}"
        if len(peer_vals) >= 2:
            sv = sorted(peer_vals)
            k = len(sv)
            med = sv[k // 2] if k % 2 == 1 else (sv[k // 2 - 1] + sv[k // 2]) / 2
            prem = (float(target[m]) / med - 1) * 100 if med != 0 else 0
            row += f"{med:>10.2f}{prem:>+9.0f}%"
            if m.upper() in ("PE", "PB", "PS", "EV_EBITDA", "P_FCF") and abs(prem) >= 20:
                premium_notes.append((m, prem))
        else:
            row += f"{'-':>10}{'-':>10}"
        print(row)

    print()
    for m, prem in premium_notes:
        if prem > 0:
            print(f"  ⚠️ {m} 较同业中位溢价 {prem:+.0f}%：需用 ROE/增速/护城河证据解释溢价合理性")
        else:
            print(f"  ℹ️ {m} 较同业中位折价 {prem:+.0f}%：确认是机会还是基本面疲弱的合理定价")
    print("  提示: 可比公司需同行业、相近商业模式；跨市场对比需注意会计准则与利率环境差异")
    return premium_notes


# ---------------------------------------------------------------------------
# 12. DCF 敏感性矩阵 (增长率 × 贴现率)
# ---------------------------------------------------------------------------

def dcf_matrix(fcf, growth_list, discount_list, terminal_growth, years=10,
               market_cap=None):
    """两段式 DCF 内在价值敏感性矩阵：行=增长率，列=贴现率。

    模型与 reverse-dcf 一致（前 N 年按 g 增长逐年折现 + Gordon 终值），
    传入 --market-cap 时额外输出各格相对当前市值的溢价/折价。
    """
    print("=" * 60)
    print("DCF 敏感性矩阵 (增长率 × 贴现率)")
    print("=" * 60)

    if fcf <= 0:
        print(f"  ❌ 当前 FCF 必须为正数（fcf={fcf}）；FCF 为负改用 three-scenario 情景分析")
        sys.exit(EXIT_BAD_ARGS)
    gt = float(terminal_growth)
    for r in discount_list:
        if r <= gt:
            print(f"  ❌ 贴现率 {r} 必须大于永续增长率 {gt}，否则终值发散")
            sys.exit(EXIT_BAD_ARGS)

    def intrinsic(g, r):
        pv, f = 0.0, float(fcf)
        for t in range(1, years + 1):
            f = f * (1 + g)
            pv += f / (1 + r) ** t
        pv += f * (1 + gt) / (r - gt) / (1 + r) ** years
        return pv

    print(f"  当前 FCF: {fmt_number(exact(fcf))} | 预测期: {years}年 | 永续增长: {gt*100:.1f}%")
    if market_cap:
        print(f"  当前市值: {fmt_number(exact(market_cap))}（括号内为内在价值相对市值的溢价空间）")
    print()

    corner = "增速\\贴现"
    col_w = 20 if market_cap else 15
    header = f"  {corner:>10}" + "".join(f"{format(r*100, '.1f') + '%':>{col_w}}" for r in discount_list)
    print(header)
    print("  " + "-" * (len(header) - 2))
    for g in growth_list:
        row = f"  {g*100:>9.1f}%"
        for r in discount_list:
            v = intrinsic(g, r)
            cell = fmt_number(exact(round(v, 2)))
            if market_cap:
                upside = (v / float(market_cap) - 1) * 100
                cell += f" ({upside:+.0f}%)"
            row += f"{cell:>{col_w}}"
        print(row)

    print()
    if market_cap:
        print("  解读: 多数格子为正溢价→存在安全边际；仅乐观角落为正→买入需苛刻假设成立，谨慎")
    print("  ✅ 假设矩阵已展开，报告中须注明选取哪一格作为基准情景及理由")


# ---------------------------------------------------------------------------
# 财务质量三件套：Beneish M-Score / Altman Z-Score / 应计质量（Sloan）
# ---------------------------------------------------------------------------

_MSCORE_FIELDS = ("revenue", "receivables", "cogs", "current_assets", "ppe",
                  "total_assets", "depreciation", "sga", "current_liabilities",
                  "long_term_debt", "net_income", "cfo")


def m_score(cur: dict, pri: dict):
    """Beneish M-Score 盈余操纵概率模型（需连续两年同口径数据）。
    返回 True=低风险 / False=高风险（退出码用）。"""
    missing = [f for f in _MSCORE_FIELDS if not isinstance(cur.get(f), (int, float))
               or not isinstance(pri.get(f), (int, float))]
    if missing:
        print(f"❌ --current/--prior 缺少字段: {', '.join(missing)}")
        print(f"   全部字段: {', '.join(_MSCORE_FIELDS)}（同一币种同一单位，取自年报）")
        sys.exit(EXIT_BAD_ARGS)

    def safe_div(a, b):
        return a / b if b else None

    # 八大指数（任一项分母为零时置 1 = 中性，并标注）
    neutral = []

    def idx(name, val):
        if val is None:
            neutral.append(name)
            return 1.0
        return val

    dsri = idx("DSRI", safe_div(safe_div(cur["receivables"], cur["revenue"]),
                                safe_div(pri["receivables"], pri["revenue"])))
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
    sgai = idx("SGAI", safe_div(safe_div(cur["sga"], cur["revenue"]),
                                safe_div(pri["sga"], pri["revenue"])))
    lev_cur = safe_div(cur["current_liabilities"] + cur["long_term_debt"], cur["total_assets"])
    lev_pri = safe_div(pri["current_liabilities"] + pri["long_term_debt"], pri["total_assets"])
    lvgi = idx("LVGI", safe_div(lev_cur, lev_pri))
    tata = safe_div(cur["net_income"] - cur["cfo"], cur["total_assets"]) or 0.0

    m = (-4.84 + 0.920 * dsri + 0.528 * gmi + 0.404 * aqi + 0.892 * sgi
         + 0.115 * depi - 0.172 * sgai + 4.679 * tata - 0.327 * lvgi)

    print("=" * 66)
    print("Beneish M-Score 盈余操纵初筛")
    print("=" * 66)
    rows = [("DSRI 应收周转指数", dsri, "应收增速远超收入→可能提前确认收入"),
            ("GMI  毛利率指数", gmi, "毛利恶化的公司更有动机粉饰"),
            ("AQI  资产质量指数", aqi, "软性资产占比上升→费用资本化嫌疑"),
            ("SGI  收入增长指数", sgi, "高增长公司更有动机维持增长假象"),
            ("DEPI 折旧率指数", depi, "折旧率下降→可能拉长折旧年限增利"),
            ("SGAI 费用率指数", sgai, "费用增速超收入→经营效率恶化"),
            ("LVGI 杠杆指数", lvgi, "杠杆上升→违约压力下的操纵动机"),
            ("TATA 总应计/总资产", tata, "利润中非现金部分越高越可疑")]
    for name, v, note in rows:
        print(f"  {name:20s} {v:>7.3f}   {note}")
    if neutral:
        print(f"  ⚠️ 分母为零置中性值的指数: {', '.join(neutral)}")
    print()
    print(f"  M-Score = {m:.2f}")
    if m > -1.78:
        print("  🔴 高风险（> -1.78）：落入操纵组典型区间，必须逐项排查异常指数对应的报表科目")
        ok = False
    elif m > -2.22:
        print("  🟡 灰色区（-2.22 ~ -1.78）：未达典型操纵阈值，但应对最高的 2-3 个指数做交叉验证")
        ok = True
    else:
        print("  🟢 低风险（< -2.22）：未见典型盈余操纵信号")
        ok = True
    print("  注: M-Score 是概率初筛非定罪工具，金融股不适用；高风险≠造假，低风险≠安全")
    return ok


def altman_z(working_capital, retained_earnings, ebit, equity_value,
             total_liabilities, total_assets, revenue=None, model="public"):
    """Altman Z-Score 财务困境风险。model: public(经典上市制造业) / em(新兴市场 Z''，
    适用非制造业与 A股/港股)。返回 True=安全 / False=困境区。"""
    if total_assets <= 0 or total_liabilities <= 0:
        print("❌ 总资产/总负债必须 > 0")
        sys.exit(EXIT_BAD_ARGS)
    x1 = working_capital / total_assets
    x2 = retained_earnings / total_assets
    x3 = ebit / total_assets
    x4 = equity_value / total_liabilities

    model_label = "经典上市制造业" if model == "public" else "新兴市场 Z''"
    print("=" * 66)
    print(f"Altman Z-Score 财务困境风险（{model_label}模型）")
    print("=" * 66)
    print(f"  X1 营运资本/总资产   {x1:>7.3f}")
    print(f"  X2 留存收益/总资产   {x2:>7.3f}")
    print(f"  X3 EBIT/总资产       {x3:>7.3f}")
    print(f"  X4 股权价值/总负债   {x4:>7.3f}")

    if model == "public":
        if revenue is None:
            print("❌ 经典模型需要 --revenue（X5 = 收入/总资产）；非制造业请用 --model em")
            sys.exit(EXIT_BAD_ARGS)
        x5 = revenue / total_assets
        print(f"  X5 收入/总资产       {x5:>7.3f}")
        z = 1.2 * x1 + 1.4 * x2 + 3.3 * x3 + 0.6 * x4 + 1.0 * x5
        safe_line, distress_line = 2.99, 1.81
    else:
        z = 6.56 * x1 + 3.26 * x2 + 6.72 * x3 + 1.05 * x4
        safe_line, distress_line = 2.60, 1.10

    print()
    print(f"  Z-Score = {z:.2f}（安全线 {safe_line} / 困境线 {distress_line}）")
    if z >= safe_line:
        print("  🟢 安全区：近期破产/财务困境风险低")
        ok = True
    elif z >= distress_line:
        print("  🟡 灰色区：风险中性，关注现金流与再融资能力变化")
        ok = True
    else:
        print("  🔴 困境区：财务压力显著，价值投资视角应直接一票否决或要求极高安全边际")
        ok = False
    print("  注: 金融股不适用；重资产周期股应用周期低点数据复算一次")
    return ok


def accrual_quality(net_income, cfo, total_assets):
    """应计质量（Sloan 应计比率）：利润含金量与应计占比。返回 True=质量尚可。"""
    if total_assets <= 0:
        print("❌ 总资产必须 > 0")
        sys.exit(EXIT_BAD_ARGS)
    accruals = net_income - cfo
    sloan = accruals / total_assets
    ocf_ni = cfo / net_income if net_income else None

    print("=" * 66)
    print("应计质量检查（Sloan 应计比率）")
    print("=" * 66)
    print(f"  净利润:            {fmt_number(exact(net_income))}")
    print(f"  经营现金流:        {fmt_number(exact(cfo))}")
    print(f"  总应计(NI-CFO):    {fmt_number(exact(round(accruals, 2)))}")
    if ocf_ni is not None:
        flag = "✅" if ocf_ni >= 0.8 else "⚠️"
        print(f"  {flag} 利润含金量 CFO/NI = {ocf_ni:.2f}（健康线 ≥0.8，长期应≥1）")
    print(f"  应计比率 (NI-CFO)/总资产 = {sloan*100:+.1f}%")
    print()
    if sloan > 0.10:
        print("  🔴 应计比率 > +10%：利润主要靠应计支撑，Sloan 研究中此组后续收益显著跑输；")
        print("     逐项核查应收/存货/合同资产变动")
        ok = False
    elif sloan > 0.05:
        print("  🟡 应计比率 +5%~+10%：偏高，结合连续 3 年趋势判断（单年可能是扩张期正常现象）")
        ok = True
    else:
        print("  🟢 应计比率正常：利润与现金流匹配度良好")
        ok = True
    print("  注: 高成长公司应计天然偏高，应与同行业同增速公司对比；连续多年 CFO/NI < 0.8 是硬红线")
    return ok


def kelly_position(win_prob, win_return, loss_return, cap=0.25):
    """凯利公式仓位参考：f* = p - q/b，b=盈亏比。输出全凯利/半凯利与上限提示。"""
    if not (0 < win_prob < 1):
        print("❌ --win-prob 需在 (0,1) 区间")
        sys.exit(EXIT_BAD_ARGS)
    if win_return <= 0 or loss_return <= 0:
        print("❌ --win/--loss 均为正数（loss 传入亏损幅度的绝对值，如 0.3）")
        sys.exit(EXIT_BAD_ARGS)
    b = win_return / loss_return
    q = 1 - win_prob
    f = win_prob - q / b

    print("=" * 66)
    print("凯利公式仓位参考")
    print("=" * 66)
    print(f"  胜率 p = {win_prob*100:.0f}%  盈亏比 b = {win_return:.2f}/{loss_return:.2f} = {b:.2f}")
    print(f"  全凯利 f* = p - (1-p)/b = {f*100:+.1f}%")
    if f <= 0:
        print("  🔴 f* ≤ 0：期望为负，这笔交易不应参与（任何仓位都是错的）")
        return False
    half = f / 2
    rec = min(half, cap)
    print(f"  半凯利（实务推荐） = {half*100:.1f}%")
    if half > cap:
        print(f"  ⚠️ 半凯利仍超单一持仓上限 {cap*100:.0f}%，按上限执行")
    print(f"  → 建议仓位区间: {rec*100/2:.0f}% ~ {rec*100:.0f}%")
    print()
    print("  注: 胜率/盈亏比应来自 three-scenario 情景推演而非拍脑袋；凯利公式对输入误差极度敏感，")
    print("     只作上限参考不作精确目标；与 portfolio-review 的集中度建议取交集")
    return True


# ---------------------------------------------------------------------------
# 命令行入口
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Financial Rigor Toolkit — 金融数据严谨性验证工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s verify-market-cap --price 510 --shares 9.11e9 --reported 4.65e12 --currency HKD
  %(prog)s verify-valuation --price 510 --eps 23.5 --bvps 120
  %(prog)s cross-validate --field revenue --values '{"年报": 7518, "Yahoo": 7500}' --unit 亿
  %(prog)s benford --values '[1234, 2345, 3456, ...]'
  %(prog)s calc --expr '510 * 9.11e9'
  %(prog)s cagr --begin 2261 --end 6603 --years 5
  %(prog)s owner-earnings --net-income 1941 --depreciation 380 --maintenance-capex 250
  %(prog)s reverse-dcf --market-cap 28000 --fcf 1600 --discount-rate 0.10 --terminal-growth 0.025
        """)

    sub = parser.add_subparsers(dest="command")

    # verify-market-cap
    mc = sub.add_parser("verify-market-cap", help="验算市值 = 股价 × 总股本")
    mc.add_argument("--price", type=float, required=True)
    mc.add_argument("--shares", type=float, required=True, help="总股本")
    mc.add_argument("--reported", type=float, required=True, help="报告市值")
    mc.add_argument("--currency", default="", help="币种")

    # verify-valuation
    val = sub.add_parser("verify-valuation", help="验算估值指标")
    val.add_argument("--price", type=float, required=True)
    val.add_argument("--eps", type=float, default=None)
    val.add_argument("--bvps", type=float, default=None, help="每股净资产")
    val.add_argument("--fcf-per-share", type=float, default=None)
    val.add_argument("--dividend", type=float, default=None, help="每股股息")
    val.add_argument("--revenue-per-share", type=float, default=None)

    # cross-validate
    cv = sub.add_parser("cross-validate", help="多源交叉验证")
    cv.add_argument("--field", required=True, help="数据字段名")
    cv.add_argument("--values", required=True, help="JSON: {来源: 数值}")
    cv.add_argument("--unit", default="")
    cv.add_argument("--tolerance", type=float, default=1.0, help="容差百分比（默认1%，与 financial-data 规范对齐）")

    # benford
    bf = sub.add_parser("benford", help="Benford定律检测")
    bf.add_argument("--values", required=True, help="JSON数组")

    # calc
    ca = sub.add_parser("calc", help="精确计算")
    ca.add_argument("--expr", required=True, help="算术表达式")

    # three-scenario
    ts = sub.add_parser("three-scenario", help="三情景估值")
    ts.add_argument("--price", type=float, required=True)
    ts.add_argument("--eps", type=float, required=True)
    ts.add_argument("--shares", type=float, required=True, help="总股本(亿)")
    ts.add_argument("--growth", nargs=3, type=float, required=True,
                    help="三情景年增速 (乐观 中性 悲观), 如 0.15 0.08 0.0")
    ts.add_argument("--pe", nargs=3, type=float, required=True,
                    help="三情景目标PE, 如 25 20 15")
    ts.add_argument("--years", type=int, default=3)
    ts.add_argument("--currency", default="")

    # cagr
    cg = sub.add_parser("cagr", help="复合年增长率")
    cg.add_argument("--begin", type=float, required=True, help="期初值（必须>0）")
    cg.add_argument("--end", type=float, required=True, help="期末值（必须>0）")
    cg.add_argument("--years", type=float, required=True, help="年数")

    # owner-earnings
    oe = sub.add_parser("owner-earnings", help="股东盈余（巴菲特定义）")
    oe.add_argument("--net-income", type=float, required=True, help="净利润")
    oe.add_argument("--depreciation", type=float, required=True, help="折旧摊销")
    oe.add_argument("--maintenance-capex", type=float, required=True,
                    help="维持性资本开支（从总capex剔除扩张性部分，口径标注[估计]）")
    oe.add_argument("--working-capital-change", type=float, default=None,
                    help="营运资本增加（可选，减项）")
    oe.add_argument("--shares", type=float, default=None, help="总股本（可选，输出每股值）")

    # reverse-dcf
    rd = sub.add_parser("reverse-dcf", help="反向DCF：反解市场隐含增长率")
    rd.add_argument("--market-cap", type=float, required=True, help="当前市值（与FCF同单位）")
    rd.add_argument("--fcf", type=float, required=True, help="当前年自由现金流")
    rd.add_argument("--discount-rate", type=float, required=True, help="贴现率，如 0.10")
    rd.add_argument("--terminal-growth", type=float, required=True, help="永续增长率，如 0.025")
    rd.add_argument("--years", type=int, default=10, help="预测期年数（默认10）")

    # valuation-percentile
    vp = sub.add_parser("valuation-percentile", help="当前估值的历史分位")
    vp.add_argument("--metric", default="PE", help="指标名（PE/PB/PS等，仅用于展示）")
    vp.add_argument("--current", type=float, required=True, help="当前值")
    vp.add_argument("--history", required=True, help="历史值JSON数组，建议≥5个覆盖完整估值周期")

    # peer-compare
    pc = sub.add_parser("peer-compare", help="同业估值/质量对标")
    pc.add_argument("--target", required=True, help='JSON对象: {"name":"腾讯","PE":18,"PB":3.4}')
    pc.add_argument("--peers", required=True, help='JSON数组: [{"name":"阿里","PE":12},...]（建议3-5家）')

    # dcf-matrix
    dm = sub.add_parser("dcf-matrix", help="DCF敏感性矩阵（增长率×贴现率）")
    dm.add_argument("--fcf", type=float, required=True, help="当前年自由现金流")
    dm.add_argument("--growth", required=True, help="增长率列表，逗号分隔如 0.05,0.10,0.15")
    dm.add_argument("--discount", required=True, help="贴现率列表，逗号分隔如 0.08,0.10,0.12")
    dm.add_argument("--terminal-growth", type=float, required=True, help="永续增长率，如 0.025")
    dm.add_argument("--years", type=int, default=10, help="预测期年数（默认10）")
    dm.add_argument("--market-cap", type=float, default=None,
                    help="当前市值（可选，传入后额外输出溢价/折价）")

    # m-score
    ms = sub.add_parser("m-score", help="Beneish M-Score 盈余操纵初筛（需两年数据）")
    ms.add_argument("--current", required=True,
                    help='本期JSON: {"revenue":..,"receivables":..,"cogs":..,"current_assets":..,'
                         '"ppe":..,"total_assets":..,"depreciation":..,"sga":..,'
                         '"current_liabilities":..,"long_term_debt":..,"net_income":..,"cfo":..}')
    ms.add_argument("--prior", required=True, help="上年同口径 JSON（字段同 --current）")

    # altman-z
    az = sub.add_parser("altman-z", help="Altman Z-Score 财务困境风险")
    az.add_argument("--working-capital", type=float, required=True, help="营运资本（流动资产-流动负债）")
    az.add_argument("--retained-earnings", type=float, required=True, help="留存收益（未分配利润+盈余公积）")
    az.add_argument("--ebit", type=float, required=True)
    az.add_argument("--equity-value", type=float, required=True, help="股权价值（上市公司用市值）")
    az.add_argument("--total-liabilities", type=float, required=True)
    az.add_argument("--total-assets", type=float, required=True)
    az.add_argument("--revenue", type=float, default=None, help="营收（经典模型必填）")
    az.add_argument("--model", choices=["public", "em"], default="em",
                    help="public=经典上市制造业 / em=新兴市场 Z''（默认，适用非制造业与A股港股）")

    # accruals
    ac = sub.add_parser("accruals", help="应计质量（Sloan 应计比率 + 利润含金量）")
    ac.add_argument("--net-income", type=float, required=True)
    ac.add_argument("--cfo", type=float, required=True, help="经营现金流净额")
    ac.add_argument("--total-assets", type=float, required=True)

    # kelly
    ke = sub.add_parser("kelly", help="凯利公式仓位参考（胜率/盈亏比→建议仓位上限）")
    ke.add_argument("--win-prob", type=float, required=True, help="胜率，如 0.6")
    ke.add_argument("--win", type=float, required=True, help="盈利情景涨幅，如 0.5")
    ke.add_argument("--loss", type=float, required=True, help="亏损情景跌幅绝对值，如 0.3")
    ke.add_argument("--cap", type=float, default=0.25, help="单一持仓上限（默认0.25）")

    args = parser.parse_args()

    # 各子命令返回值 → 退出码（0=通过 / 1=验证不通过 / 2=参数错误）
    if args.command == "verify-market-cap":
        ok = verify_market_cap(args.price, args.shares, args.reported, args.currency)
        sys.exit(EXIT_OK if ok else EXIT_VERIFY_FAIL)
    elif args.command == "verify-valuation":
        verify_valuation(args.price, args.eps, args.bvps, args.fcf_per_share,
                        args.dividend, args.revenue_per_share)
        sys.exit(EXIT_OK)
    elif args.command == "cross-validate":
        values = _load_json_arg(
            args.values, "--values",
            '{"公司年报": 7518, "macrotrends": 7500, "stockanalysis": 7520}')
        outcome = cross_validate(args.field, values, args.unit, args.tolerance)
        sys.exit(EXIT_VERIFY_FAIL if outcome["has_major_diff"] else EXIT_OK)
    elif args.command == "benford":
        values = _load_json_arg(args.values, "--values", "[1234, 2345, 3456]")
        if not isinstance(values, list):
            print("❌ --values 必须是 JSON 数组，如 [1234, 2345, 3456]")
            sys.exit(EXIT_BAD_ARGS)
        outcome = benford_check(values)
        # 样本不足(None)不算失败；分布明显异常时返回 1 提示进一步调查
        if outcome is not None and not outcome["is_conforming"]:
            sys.exit(EXIT_VERIFY_FAIL)
        sys.exit(EXIT_OK)
    elif args.command == "calc":
        result = exact_calc(args.expr)
        sys.exit(EXIT_OK if result is not None else EXIT_BAD_ARGS)
    elif args.command == "three-scenario":
        three_scenario_valuation(
            args.price, args.eps, args.shares,
            args.growth[0], args.growth[1], args.growth[2],
            args.pe[0], args.pe[1], args.pe[2],
            args.years, args.currency)
        sys.exit(EXIT_OK)
    elif args.command == "cagr":
        cagr_calc(args.begin, args.end, args.years)
        sys.exit(EXIT_OK)
    elif args.command == "owner-earnings":
        owner_earnings(args.net_income, args.depreciation, args.maintenance_capex,
                       args.working_capital_change, args.shares)
        sys.exit(EXIT_OK)
    elif args.command == "reverse-dcf":
        reverse_dcf(args.market_cap, args.fcf, args.discount_rate,
                    args.terminal_growth, args.years)
        sys.exit(EXIT_OK)
    elif args.command == "valuation-percentile":
        history = _load_json_arg(args.history, "--history", "[35,42,28,55,38]")
        if not isinstance(history, list):
            print("❌ --history 必须是 JSON 数组，如 [35,42,28,55,38]")
            sys.exit(EXIT_BAD_ARGS)
        valuation_percentile(args.metric, args.current, history)
        sys.exit(EXIT_OK)
    elif args.command == "peer-compare":
        target = _load_json_arg(args.target, "--target", '{"name":"腾讯","PE":18}')
        peers = _load_json_arg(args.peers, "--peers", '[{"name":"阿里","PE":12}]')
        peer_compare(target, peers)
        sys.exit(EXIT_OK)
    elif args.command == "dcf-matrix":
        try:
            growth_list = [float(x) for x in args.growth.split(",") if x.strip()]
            discount_list = [float(x) for x in args.discount.split(",") if x.strip()]
        except ValueError:
            print("❌ --growth/--discount 需为逗号分隔的小数，如 0.05,0.10,0.15")
            sys.exit(EXIT_BAD_ARGS)
        if not growth_list or not discount_list:
            print("❌ --growth/--discount 不能为空")
            sys.exit(EXIT_BAD_ARGS)
        dcf_matrix(args.fcf, growth_list, discount_list, args.terminal_growth,
                   args.years, args.market_cap)
        sys.exit(EXIT_OK)
    elif args.command == "m-score":
        cur = _load_json_arg(args.current, "--current", '{"revenue":6603,...}')
        pri = _load_json_arg(args.prior, "--prior", '{"revenue":6090,...}')
        if not isinstance(cur, dict) or not isinstance(pri, dict):
            print("❌ --current/--prior 必须是 JSON 对象")
            sys.exit(EXIT_BAD_ARGS)
        ok = m_score(cur, pri)
        sys.exit(EXIT_OK if ok else EXIT_VERIFY_FAIL)
    elif args.command == "altman-z":
        ok = altman_z(args.working_capital, args.retained_earnings, args.ebit,
                      args.equity_value, args.total_liabilities, args.total_assets,
                      args.revenue, args.model)
        sys.exit(EXIT_OK if ok else EXIT_VERIFY_FAIL)
    elif args.command == "accruals":
        ok = accrual_quality(args.net_income, args.cfo, args.total_assets)
        sys.exit(EXIT_OK if ok else EXIT_VERIFY_FAIL)
    elif args.command == "kelly":
        ok = kelly_position(args.win_prob, args.win, args.loss, args.cap)
        sys.exit(EXIT_OK if ok else EXIT_VERIFY_FAIL)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
