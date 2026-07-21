# 数据抽检准出协议

本文件是所有研报级流程**数据抽检（准出流程）** 的唯一定义。各子流程引用本文件，不再内联重复。

> 工具权威调用语法详见 [`skills/financial-data/references/verification-playbook.md`](../skills/financial-data/references/verification-playbook.md)。

## 适用范围

| 档位 | 流程类型 | 是否抽检 |
|------|---------|---------|
| **研报级（必须）** | 产出决策/研究/发布级报告的流程 | 抽检通过方可交付 |
| **快反/对话级（豁免）** | 时效优先或纯对话形态（dyp-ask / news-pulse） | 免抽检，标注「未经抽检」 |

## 三步流程

### Step 1 — 提取抽检清单（15% 随机抽样）

```bash
python3 tools/report_audit.py extract --report <报告文件路径>
```

输出 JSON 清单模板，每项含 `reported_value`（报告中的值）与 `fetched_value`（待填）。

推荐文件化闭环（避免 shell 引号转义问题）：

```bash
python3 tools/report_audit.py extract --report <报告文件路径> \
  --output reports/{公司名}/audit-checklist.json
```

### Step 2 — 取数核验

对清单中每个数据点，按 [`skills/financial-data/SKILL.md`](../skills/financial-data/SKILL.md) 规范从可靠信源取数：

- 美股：macrotrends + stockanalysis
- 港股：aastocks + macrotrends
- A股：东方财富 + 巨潮资讯

填入 `fetched_value` / `fetched_source`（必填），`fetched_value2` / `fetched_source2`（副源，选填）。

### Step 3 — 输出判决

```bash
python3 tools/report_audit.py verdict --results '<填好的JSON>' --report <报告文件名>
```

或文件方式：

```bash
python3 tools/report_audit.py verdict --results-file reports/{公司名}/audit-checklist.json --report <报告文件名>
```

## 判决标准

| 结果 | 条件 | 后续动作 |
|------|------|---------|
| **【准出】** | 所有抽检点偏差 ≤ 1% | 报告可发布 |
| **【打回】** | 任意点偏差 > 1% | 修正对应数据后重新抽检 |

## 死循环出口

同一数据点连续 2 次打回且确认为口径差异（GAAP/Non-GAAP、汇率、财年定义）时：
1. 在报告中显式标注口径与两源数值
2. 可人工放行，不得无限重试

## 配合要求

- 报告中的**关键数字应尽量放入 Markdown 表格**（抽检器对表格提取最可靠）
- 审计状态在抽检完成后回填报告元信息头，不得预填"通过"
