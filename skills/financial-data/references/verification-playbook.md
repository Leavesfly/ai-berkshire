# 金融数据验证 Playbook（工具调用唯一权威语法）

> 本文件是 `tools/financial_rigor.py` 与 `tools/report_audit.py` 全部子命令的**权威调用语法**。
> 各子流程 SKILL.md 中的命令示例若与本文件冲突，**以本文件为准**。
> 修改工具 CLI 参数时必须同步更新本文件。

## 容差分档（全系统统一标准）

| 偏差 | 判定 | 处理方式 |
|------|------|---------|
| ≤ 1% | ✅ 一致 | 取主来源数值，标注两个来源 |
| 1% ~ 5% | ⚠️ 差异 | 标记"数据存在差异"，注明两个数值与可能原因（GAAP/Non-GAAP、汇率、财年口径） |
| > 5% | ❌ 重大差异 | 必须查原始财报核实，不得直接使用 |

数据抽检准出（report_audit）沿用 1% 容差：任意抽检点偏差 > 1% 即打回。

---

## financial_rigor.py 子命令

### 1. 市值验算（股价 × 总股本 vs 报告市值）

```bash
python3 tools/financial_rigor.py verify-market-cap \
  --price 510 --shares 9.11e9 --reported 4.65e12 --currency HKD
```
- `--shares` 为总股本（股数，支持科学计数法）；偏差 >1% 警告，>5% 不通过。
- 总股本必须来自交易所/F10 等独立来源，不得由市值÷股价倒推（循环论证）。

### 2. 估值指标验算（PE/PB/ROE/P-FCF/股息率/PS）

```bash
python3 tools/financial_rigor.py verify-valuation \
  --price 510 --eps 23.5 --bvps 120 --fcf-per-share 18 --dividend 2.4 --revenue-per-share 85
```
- 除 `--price` 外均可选，只算传入的指标。

### 3. 多源交叉验证

```bash
python3 tools/financial_rigor.py cross-validate \
  --field revenue --values '{"公司年报": 7518, "macrotrends": 7500, "stockanalysis": 7520}' --unit 亿
```
- **`--values` 必须是 JSON 对象 `{来源名: 数值}`**（不是空格分隔的数值列表，也没有 `--metric`/`--sources` 参数）。
- 默认容差 1%，与本文件容差分档一致。

### 4. 三情景估值

```bash
python3 tools/financial_rigor.py three-scenario \
  --price 100 --eps 5.2 --shares 12.5 \
  --growth 0.15 0.08 0.00 --pe 25 20 15 --years 3 --currency CNY
```
- `--shares` 单位为**亿股**；`--growth` 为**小数**（0.15 = 15%，传入 >1.5 的值会被判定为百分数并自动换算）。

### 5. 精确计算器（代替一切心算）

```bash
python3 tools/financial_rigor.py calc --expr '510 * 9.11e9'
```
- 仅支持 `+ - * /` 与括号，不支持幂运算，长度 ≤ 200 字符。

### 6. Benford 定律造假初筛

```bash
python3 tools/financial_rigor.py benford --values '[1234, 2345, 3456, ...]'
```
- 需 ≥ 50 个财务数字样本（取财报附注/分部数据中的大量金额）；不符合 ≠ 造假，但值得深入调查。

---

## report_audit.py 抽检准出三步

```bash
# Step 1 — 提取数据点并随机抽样 15%（输出 JSON 模板）
python3 tools/report_audit.py extract --report reports/{公司名}/{报告文件}.md

# Step 2 — 对清单每项按 skills/financial-data/SKILL.md 规范从可靠信源取数，
#          填入 fetched_value / fetched_source / fetched_value2 / fetched_source2

# Step 3 — 输出准出/打回判决（退出码 0=准出 1=打回）
python3 tools/report_audit.py verdict --results '<填好的JSON>' --report {报告文件名}
```

- **【准出】** 所有抽检点偏差 ≤ 1% → 可发布；**【打回】** 任意点 > 1% → 修正后重审。
- **死循环出口**：同一数据点连续 2 次打回且确认为口径差异（GAAP/Non-GAAP、汇率、财年）时，在报告中显式标注口径与两源数值后可人工放行，不得无限重试。
- 为配合抽检，报告中的**关键数字应尽量放入 Markdown 表格**（抽检器对表格提取最可靠）。

---

## 通用规则

1. 涉及金额、市值、估值的计算**必须调用工具，禁止 LLM 心算**（CLAUDE.md 金融严谨性要求）。
2. 每个关键数据至少 2 个独立来源，来源优先级见 [`../SKILL.md`](../SKILL.md)（financial-data 数据源规范）。
3. 工具输出直接嵌入报告附录"关键数据交叉验证记录"，保证可审计。
4. 工具执行失败（网络/参数错误）时不得跳过验证：修正参数重试，或降级为"WebSearch 双源人工比对"并在报告中标注"未经工具验算"。
