# 金融数据验证 Playbook（工具调用唯一权威语法）

> 本文件是 `tools/financial_rigor.py`、`tools/report_audit.py` 与 `tools/chart_gen.py` 全部子命令的**权威调用语法**。
> 各子流程 SKILL.md 中的命令示例若与本文件冲突，**以本文件为准**。
> 修改工具 CLI 参数时必须同步更新本文件。

## 容差分档（全系统统一标准）

| 偏差 | 判定 | 处理方式 |
|------|------|---------|
| ≤ 1% | ✅ 一致 | 取主来源数值，标注两个来源 |
| 1% ~ 5% | ⚠️ 差异 | 标记"数据存在差异"，注明两个数值与可能原因（GAAP/Non-GAAP、汇率、财年口径） |
| > 5% | ❌ 重大差异 | 必须查原始财报核实，不得直接使用 |

数据抽检准出（report_audit）沿用 1% 容差：任意抽检点偏差 > 1% 即打回。

## 退出码语义（两个工具统一）

| 退出码 | 含义 | 调用方处理 |
|--------|------|-----------|
| 0 | 验证通过 / 准出（PASS） | 正常继续 |
| 1 | 验证不通过（重大偏差 / 打回 FAIL / Benford 异常） | 按容差分档处理：查原始财报或修正报告后重跑 |
| 2 | 参数错误（JSON 非法/来源不足/文件不存在） | 按错误提示修正命令后重试，不算验证失败 |

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
- **`--values` 必须是 JSON 对象 `{来源名: 数值}`**（不是空格分隔的数值列表，也没有 `--metric`/`--sources` 参数）；至少 2 个来源，值必须是纯数字（不带单位/逗号）。
- 默认容差 1%，与本文件容差分档一致；存在 >5% 重大差异时退出码为 1。

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

### 7. 复合年增长率（CAGR）

```bash
python3 tools/financial_rigor.py cagr --begin 2261 --end 6603 --years 5
```
- 期初/期末值必须均为正数（亏损转盈利等跨零场景 CAGR 无意义，退出码 2）；报告中的年均增速一律用本命令计算，禁止心算开方。

### 8. 股东盈余（Owner Earnings，巴菲特定义）

```bash
python3 tools/financial_rigor.py owner-earnings \
  --net-income 1941 --depreciation 380 --maintenance-capex 250 \
  --working-capital-change 45 --shares 45
```
- 公式：净利润 + 折旧摊销 − 维持性资本开支（− 营运资本增加，可选）；`--shares` 可选，传入时输出每股值。
- **维持性资本开支需从总 capex 中剔除扩张性部分**，该拆分是估计值，口径在报告中标注 `[估计]`。
- 工具会输出股东盈余/净利润比值：<0.7x 提示利润含金量存疑，>1.3x 提示核实折旧口径。

### 9. 反向 DCF（市场隐含增长率反解）

```bash
python3 tools/financial_rigor.py reverse-dcf \
  --market-cap 28000 --fcf 1600 --discount-rate 0.10 --terminal-growth 0.025 --years 10
```
- `--market-cap` 与 `--fcf` 单位必须一致（如都用亿）；贴现率/永续增长率为小数（0.10 = 10%），且贴现率必须大于永续增长率。
- 输出“当前价格隐含未来 N 年 FCF 年均增速 X%”，用于四大师“市场预期是否苛刻”判断；隐含增长 >100%/年时退出码 1（极端预期警告）。
- FCF 为负的公司不适用（退出码 2），改用 three-scenario 情景分析；贴现率/永续增长假设须在报告中明示。

### 10. 估值分位（当前 PE/PB 处于历史序列的百分位）

```bash
python3 tools/financial_rigor.py valuation-percentile \
  --metric PE --current 22 --history '[35,42,28,55,38,30,25,45,33,27]'
```
- `--history` 为 JSON 数组，建议 ≥5 个值覆盖完整估值周期（如近 5-10 年年度 PE）。
- 输出当前值在历史序列中的百分位（如“处于历史 30% 分位”），用于判断相对自身贵不贵。
- 样本 <5 个时退出码 2（数据不足，无法得出有意义的分位）。

### 11. 同业对标（目标公司 vs 可比公司估值溢价/折价）

```bash
python3 tools/financial_rigor.py peer-compare \
  --target '{"name":"腾讯","PE":18,"PB":3.4,"ROE":22}' \
  --peers '[{"name":"阿里","PE":12,"PB":1.8},{"name":"Meta","PE":24,"PB":7.5}]'
```
- `--target` 与 `--peers` 均为 JSON，字段名自定义（如 PE/PB/ROE/PS 等），工具自动计算同业中位数与溢价/折价率。
- 建议 3-5 家可比公司；指标不一致时只对比共有字段。

### 12. DCF 敏感性矩阵（增长率×贴现率二维内在价值）

```bash
python3 tools/financial_rigor.py dcf-matrix \
  --fcf 1600 --growth 0.05,0.10,0.15 --discount 0.08,0.10,0.12 \
  --terminal-growth 0.025 --market-cap 28000
```
- `--growth`/`--discount` 为逗号分隔的小数列表；`--market-cap` 可选，传入后额外输出当前市值相对各情景的溢价/折价。
- 贴现率必须大于永续增长率，否则退出码 2。
- 报告须注明基准情景（通常取中性增长+中性贴现）。

### 13. Beneish M-Score 盈余操纵初筛（需连续两年数据）

```bash
python3 tools/financial_rigor.py m-score \
  --current '{"revenue":6603,"receivables":800,"cogs":3100,"current_assets":5000,"ppe":4000,"total_assets":16000,"depreciation":380,"sga":600,"current_liabilities":3000,"long_term_debt":2000,"net_income":1941,"cfo":2200}' \
  --prior '{"revenue":6090,"receivables":750,"cogs":2900,"current_assets":4800,"ppe":3800,"total_assets":15000,"depreciation":350,"sga":550,"current_liabilities":2800,"long_term_debt":1800,"net_income":1750,"cfo":2000}'
```
- 需 12 个财务字段（两年同口径）；缺少字段时退出码 2 并提示缺少哪些。
- M-Score > -1.78 提示盈余操纵风险（退出码 1）；金融股不适用。
- 仅为概率初筛非定罪工具，高风险结果须回到报表科目逐项核查。

### 14. Altman Z-Score 财务困境风险

```bash
python3 tools/financial_rigor.py altman-z \
  --working-capital 3000 --retained-earnings 8000 --ebit 2300 \
  --equity-value 28000 --total-liabilities 6000 --total-assets 16000 \
  --revenue 6603 --model em
```
- `--model em`（默认）为新兴市场 Z'' 模型，适用 A股/港股/非制造业；`--model public` 为经典上市制造业模型（需 `--revenue`）。
- Z'' < 1.1 为困境区（退出码 1）；1.1-2.6 为灰色区；>2.6 为安全区。

### 15. 应计质量（Sloan 应计比率 + 利润含金量）

```bash
python3 tools/financial_rigor.py accruals \
  --net-income 1941 --cfo 2200 --total-assets 16000
```
- 应计比率 = (净利润 - 经营现金流) / 总资产；>10% 提示利润含金量存疑（退出码 1）。
- 同时输出 OCF/净利润 比值：<0.7 提示关注。

### 16. 凯利公式仓位参考（胜率/盈亏比→建议仓位上限）

```bash
python3 tools/financial_rigor.py kelly \
  --win-prob 0.6 --win 0.5 --loss 0.3 --cap 0.25
```
- `--win-prob`/`--win`/`--loss` 必须来自 `three-scenario` 推演，不得拍脑袋。
- `--cap` 为单一持仓上限（默认 0.25），凯利建议仓位不超过此值。
- 期望收益为负时退出码 1（不建议建仓）。

---

## report_audit.py 抽检准出三步（推荐文件化闭环）

```bash
# Step 1 — 提取数据点并随机抽样 15%，清单模板直接写入文件
python3 tools/report_audit.py extract --report reports/{公司名}/{报告文件}.md \
  --output reports/{公司名}/audit-checklist.json

# Step 2 — 对清单每项按 skills/financial-data/SKILL.md 规范从可靠信源取数，
#          直接编辑该 JSON 文件填入 fetched_value / fetched_source / fetched_value2 / fetched_source2

# Step 3 — 从文件读入核验结果，输出准出/打回判决（退出码 0=准出 1=打回 2=参数错误）
python3 tools/report_audit.py verdict --results-file reports/{公司名}/audit-checklist.json --report {报告文件名}
```

- 内联方式 `verdict --results '<JSON>'` 仍可用（向后兼容），但**优先用 `--results-file`**：大段 JSON 内联传参极易因 shell 引号转义失败。
- 不加 `--output` 时清单 JSON 打印到 stdout（旧行为不变）。

- **【准出】** 所有抽检点偏差 ≤ 1% → 可发布；**【打回】** 任意点 > 1% → 修正后重审。
- **死循环出口**：同一数据点连续 2 次打回且确认为口径差异（GAAP/Non-GAAP、汇率、财年）时，在报告中显式标注口径与两源数值后可人工放行，不得无限重试。
- 为配合抽检，报告中的**关键数字应尽量放入 Markdown 表格**（抽检器对表格提取最可靠）。

---

## chart_gen.py 报告图表生成（可视化首选方案）

四个子命令对应 `references/report-visuals.md` 的图表类型（三级方案与降级规则以该文件为准）：

```bash
# 类型1 趋势（多系列在 --series 传多个键；折线加 --kind line）
python3 tools/chart_gen.py trend --title "营业收入趋势（亿元）" \
  --x '[2021,2022,2023,2024,2025]' --series '{"营收":[5601,5546,6090,6603,7200]}' \
  --ylabel 亿元 --output reports/{公司名}/charts/revenue-trend-{日期}.png

# 类型2 结构（占比饼图）
python3 tools/chart_gen.py structure --title "收入结构（2025）" \
  --values '{"增值服务":48,"网络广告":19,"金融科技与企业服务":31,"其他":2}' \
  --output reports/{公司名}/charts/revenue-structure-{日期}.png

# 类型5 对比（分组柱状，支持 ≥3 家）
python3 tools/chart_gen.py compare --title "毛利率对比（%）" \
  --x '[2023,2024,2025]' --series '{"公司A":[42.1,43.5,45.0],"公司B":[35.2,34.8,33.9]}' \
  --ylabel "%" --output reports/{公司名}/charts/margin-compare-{日期}.png

# 类型7 象限（坐标 0-1；--labels 可选自定义四象限标签 [右上,左上,左下,右下]）
python3 tools/chart_gen.py quadrant --title "持仓质量×估值定位" \
  --points '{"腾讯":[0.45,0.9],"茅台":[0.55,0.85]}' \
  --output reports/{主题}/charts/quadrant-{日期}.png
```

- `--x`/`--series`/`--values`/`--points` 均为 JSON（shell 中单引号包裹，键名双引号）；系列长度必须与 x 轴一致，象限坐标取值 0-1。
- **退出码特例**：0=生成成功 / **1=matplotlib 不可用（按 report-visuals.md 降级 Mermaid，不算失败、不阻断流程）** / 2=参数错误。
- 图中数值必须与报告紧邻表格一致；修改数据后重跑命令重新生成。
- matplotlib 为可选依赖（`pip install matplotlib`），是全工具链唯一的可选外部库；缺失不影响其他工具。

---

## 通用规则

1. 涉及金额、市值、估值的计算**必须调用工具，禁止 LLM 心算**（CLAUDE.md 金融严谨性要求）。
2. 每个关键数据至少 2 个独立来源，来源优先级见 [`../SKILL.md`](../SKILL.md)（financial-data 数据源规范）。
3. 工具输出直接嵌入报告附录"关键数据交叉验证记录"，保证可审计。
4. 工具执行失败（网络/参数错误）时不得跳过验证：修正参数重试，或降级为"WebSearch 双源人工比对"并在报告中标注"未经工具验算"。
