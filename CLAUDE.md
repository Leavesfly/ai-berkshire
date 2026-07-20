# AI Berkshire — 项目级指令与客观性原则

本文件是 AI Berkshire 投研技能包的项目级约束。**所有子技能在执行时都必须遵循以下原则**，尤其是被各技能反复引用的"客观性原则"。

## 客观性原则（最高优先级）

1. **先数据，后结论** — 不预设看多或看空，先摆事实、再推逻辑、最后给结论。
2. **区分事实与推测** — 明确标注哪些是已证实的事实、哪些是推断/估计。估计值一律标注 `[估计]`。
3. **数据必须标注来源** — 每个关键数据附来源；财务数据遵循 [`skills/financial-data/SKILL.md`](skills/financial-data/SKILL.md) 的双源交叉验证规范（两源误差 >1% 须标记）。
4. **诚实面对不确定性** — 找不到数据就写"数据不足"，绝不用推测填满框架伪装确定性。
5. **正反两面** — 每个核心判断都要附反面论据（芒格式逆向检验）。
6. **结论要明确** — 不回避给出"通过 / 不通过 / 灰色地带"或"买入 / 观望 / 回避"的判断。

## 反偏见机制

- **信息丰富度评级（A/B/C）**：资料多 ≠ 确定性高。A 级信息充裕的公司重点做反面检验与非共识视角，避免输出"正确的废话"；C 级信息稀缺的公司转入第一性原理模式，聚焦商业本质。
- **AI 研究局限性声明**：报告需说明结论受资料充裕度影响的程度，以及是否与市场共识过度趋同。
- **8 条红线否决**：触及任一红线（如财务造假嫌疑、管理层诚信问题等）直接否决，不被叙事吸引力覆盖。

## 金融严谨性

- 涉及金额、市值、估值的计算**必须调用 [`tools/financial_rigor.py`](tools/financial_rigor.py)**，禁止心算。增长率用 `cagr`；利润含金量用 `owner-earnings`（股东盈余）；判断市场预期是否苛刻用 `reverse-dcf`（从当前市值反解隐含增长率，贴现率/永续增长假设须在报告中明示）；判断相对自身贵不贵用 `valuation-percentile`（历史分位）；同业比较用 `peer-compare`；估值假设敏感性用 `dcf-matrix`（增长率×贴现率矩阵，报告须注明基准情景）。
- **财务质量三件套**（去劣/财报精读场景按需叠加）：盈余操纵初筛用 `m-score`（需连续两年数据，金融股不适用）；财务困境风险用 `altman-z`（A股/港股/非制造业默认 `--model em`）；利润含金量与应计占比用 `accruals`；三者均为概率初筛非定罪工具，高风险结果须回到报表科目逐项核查。仓位上限参考用 `kelly`（胜率/盈亏比必须来自 `three-scenario` 推演）。
- 组合层计算（集中度/相关性矩阵/加权预期回报/历史回撤 `--drawdown`）走 [`tools/portfolio_calc.py`](tools/portfolio_calc.py)；去劣硬指标初筛走 [`tools/quality_screen.py`](tools/quality_screen.py)（豁免规则与银行保险特例仍由流程定性判断）。
- 财报精读/管理层研究优先取**官方披露原文**：[`tools/filings_fetch.py`](tools/filings_fetch.py)（美股 SEC EDGAR / A股巨潮 / 港股披露易）下载，[`tools/filings_parse.py`](tools/filings_parse.py) 抽取章节（风险因素/MD&A）与跨年措辞 diff；接口数据只能作为交叉验证而非 MD&A/附注类定性信息的替代。
- 大师/机构美股持仓事实一律出自 [`tools/masters_portfolio.py`](tools/masters_portfolio.py)（SEC 13F），禁止凭记忆报持仓；解读时必须声明 13F 边界（仅美股多头、滞后最多45天）。
- 报告发布前执行数据抽检准出流程（[`tools/report_audit.py`](tools/report_audit.py)）。抽检分两档：
  - **研报级（必须抽检）**：产出决策/研究/发布级报告的流程（investment-research、investment-team、investment-checklist、earnings-review、earnings-team、industry-research、industry-funnel、quality-screen、management-deep-dive、portfolio-review、bottleneck-hunter、private-company-research，及投资主题的内容创作），抽检通过方可交付；
  - **快反/对话级（可豁免）**：时效优先或纯对话形态（news-pulse 异动归因、dyp-ask 问答等），免抽检但须在产出物中标注「未经抽检」；各技能内的抽检章节或豁免声明以本档位划分为准。
- 工具调用语法与容差分档的唯一权威定义：[`skills/financial-data/references/verification-playbook.md`](skills/financial-data/references/verification-playbook.md)。
- 工具退出码统一语义：0=验证通过 / 1=验证不通过（需排查后重跑） / 2=参数错误（修正命令重试，不算验证失败）。
- 启动研究流程前可运行 [`tools/doctor.py`](tools/doctor.py) 一键自检取数与验算链路（退出码 0=全部就绪 / 1=存在降级项）。

## 决策日志约定（反馈闭环）

- 产出明确结论（买入/观望/回避/卖出/减仓/通过/不通过）的研报级流程，在报告交付后**必须**追加一条决策记录：
  `python3 tools/decision_log.py add --company {公司} --code {代码} --skill {子流程名} --verdict {结论} --price {当前价} --currency {币种} --reason "{一句话核心理由}" --report {报告路径}`
- 历史判断的复盘由 `track-record` 子流程承接；对话级产出（dyp-ask/news-pulse）不记录。
- 研究结论为「观望+理想买点」时，主动提议用户加入观察清单（`tools/watchlist.py add`，区间必须来自报告估值结论）。

## 数据复用约定

- 同一研究内已双源验证的数据点直接复用，禁止重复取数；下游技能优先读取上游报告附录的已验证数据，仅对时效性数据（股价/市值/最新财报）重新取数。
- **跨会话复用**：研报级流程取数前先查公司档案库 `python3 tools/company_facts.py get {代码}`；研究交付后把本次双源验证过的**稳定事实**（股本结构/历史财务关键值/商业模式要点/论文红线）用 `set` 归档；时效性数据（现价/市值/当前PE）禁止入库；引用档案数据时在报告中标注「档案数据（{验证日期}验证）」。
- 具体规则见 [`skills/financial-data/SKILL.md`](skills/financial-data/SKILL.md) 的「数据复用规则」。

## 四大师视角一致性

- 模拟巴菲特/芒格/段永平/李录视角、分配角色分工、撰写大师点评时，以 [`references/masters-profiles.md`](references/masters-profiles.md) 的画像定义为准，不得越出各自视角边界，不得虚构大师未说过的具体表述。

## 工具调用工作目录约定

- 所有 `tools/*.py` 脚本均以**技能根目录**（本仓库根）为基准的相对路径调用，例如 `python3 tools/financial_rigor.py ...`。
- 执行前必须确保当前工作目录为技能根目录；作为独立插件运行、无法保证 `cwd` 时，先定位到本 `CLAUDE.md` 所在的技能根目录再调用（例如 `cd <本CLAUDE.md所在目录> && python3 tools/xxx.py ...`），避免相对路径失效。

## 报告输出路径约定（所有子流程必须遵守）

- **公司级报告**：统一写入 `reports/{公司名}/{公司名}-{技能名}-{YYYYMMDD}.md`（如 `reports/腾讯/腾讯-research-20260719.md`）。
- **行业/主题级报告**：写入 `reports/{行业名}-{技能名}-{YYYYMMDD}.md`。
- **投资论文快照**：固定为 `reports/{公司名}-thesis.md`（`thesis-tracker` / `thesis-drift` 依赖此路径）。
- **组合文件**：固定为 `reports/portfolio-latest.md`。
- **禁止**将报告写入用户家目录（`~/`）或仓库外路径；目录不存在时先创建。
- 上游技能的报告是下游技能的输入（如 `thesis-tracker` 读取 `investment-research`/`investment-team` 报告），路径一致性是数据链路成立的前提。

## 报告元信息头（所有报告开头必填）

每份报告正文前统一放置元信息块，供版本追踪与下游流程读取：

```
> **研究对象**：{公司/行业} | **执行技能**：{子流程名} | **报告日期**：{YYYY-MM-DD}
> **数据截止**：{最新财报期或取数日} | **信息丰富度**：{A/B/C} | **审计状态**：{抽检通过 / 未经工具验算+原因}
> **上一版**：{同对象历史报告相对路径，无则写“首次研究”}
```

- 同一对象存在历史报告时（按上方路径约定在 `reports/{公司名}/` 下查找），「上一版」必填，且报告正文首节需含一行「**与上一版结论差异**」摘要（结论变/不变 + 一句原因）；首次研究免填。
- 审计状态在 `report_audit.py` 抽检完成后回填，不得预填“通过”。

## 语言与风格

- 默认输出语言：中文。
- 风格：直接、犀利、不说废话；用 Markdown 表格呈现关键数据。
- 报告图表遵循 [`references/report-visuals.md`](references/report-visuals.md)（图为辅、表为准）：首选 `tools/chart_gen.py` 生成 PNG，matplotlib 不可用（退出码 1）时降级 Mermaid，再降级符号/表格。
