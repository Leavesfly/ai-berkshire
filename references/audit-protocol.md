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

## 逻辑链审计（可选增强档，数据抽检之外的第二道门）

数据抽检验证的是“数字对不对”，逻辑链审计验证的是“推理对不对”（数据对、结论错是更隐蔽的风险）：

```bash
python3 tools/report_audit.py logic-chain --report <报告文件路径>
```

适用范围与判决：

| 项 | 规则 |
|----|------|
| 适用流程 | 采用证据标注规范（`[E1]` `[E2]`，见 report-conventions.md）的研报级报告 |
| 检查内容 | 裸奔结论（无证据标注的判断句）、孤立证据（定义了未被引用）、证据覆盖率 |
| 退出码 | 0=覆盖率 ≥ 70% / 1=覆盖率 < 70%（建议补充证据链后重跑） |
| 定位 | 工具只能检查“结论是否标了证据”；“证据是否真支持该结论”需 LLM 逐条审查（见下） |

**LLM 语义审查（工具检查之后的人工智能环节）**：对工具输出的每条“有证据结论”，抽检 3-5 条逐条自问：
1. 该证据是否**真的支持**该结论（而非仅相关）？
2. 证据之间是否**互相矛盾**？
3. 是否存在“证据 A 支持小结论，小结论被偷换为大结论”的推理跳跃？

发现推理跳跃时在报告中修正或降级该结论的置信度，不得静默放行。

## 配合要求

- 报告中的**关键数字应尽量放入 Markdown 表格**（抽检器对表格提取最可靠）
- 审计状态在抽检完成后回填报告元信息头，不得预填"通过"
