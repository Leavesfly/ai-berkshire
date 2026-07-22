# 工具调用约定

本文件是 [`CLAUDE.md`](../CLAUDE.md) 的补充，定义工具层的使用规范。

## 金融严谨性

- 涉及金额、市值、估值的计算**必须调用 [`tools/financial_rigor.py`](../tools/financial_rigor.py)**，禁止心算。增长率用 `cagr`；利润含金量用 `owner-earnings`（股东盈余）；判断市场预期是否苛刻用 `reverse-dcf`（从当前市值反解隐含增长率，贴现率/永续增长假设须在报告中明示）；判断相对自身贵不贵用 `valuation-percentile`（历史分位）；同业比较用 `peer-compare`；估值假设敏感性用 `dcf-matrix`（增长率×贴现率矩阵，报告须注明基准情景）。
- **财务质量三件套**（去劣/财报精读场景按需叠加）：盈余操纵初筛用 `m-score`（需连续两年数据，金融股不适用）；财务困境风险用 `altman-z`（A股/港股/非制造业默认 `--model em`）；利润含金量与应计占比用 `accruals`；三者均为概率初筛非定罪工具，高风险结果须回到报表科目逐项核查。仓位上限参考用 `kelly`（胜率/盈亏比必须来自 `three-scenario` 推演）。
- 组合层计算（集中度/相关性矩阵/加权预期回报/历史回撤 `--drawdown`）走 [`tools/portfolio_calc.py`](../tools/portfolio_calc.py)；去劣硬指标初筛走 [`tools/quality_screen.py`](../tools/quality_screen.py)（豁免规则与银行保险特例仍由流程定性判断）。
- 财报精读/管理层研究优先取**官方披露原文**：[`tools/filings_fetch.py`](../tools/filings_fetch.py)（美股 SEC EDGAR / A股巨潮 / 港股披露易）下载，[`tools/filings_parse.py`](../tools/filings_parse.py) 抽取章节（风险因素/MD&A）与跨年措辞 diff；接口数据只能作为交叉验证而非 MD&A/附注类定性信息的替代。
- 大师/机构美股持仓事实一律出自 [`tools/masters_portfolio.py`](../tools/masters_portfolio.py)（SEC 13F），禁止凭记忆报持仓；解读时必须声明 13F 边界（仅美股多头、滞后最多45天）。
- 内部人/大股东买卖事实出自 [`tools/insider_trading.py`](../tools/insider_trading.py)（美股 SEC Form 4 / A股东财增减持 / 港股披露易股份变动文件索引），服务管理层本分度与论文红线核查；解读纪律：内部人**买入**信号通常强于卖出，**卖出**理由多样（缴税/行权/流动性），单笔减持≠看空，但多名高管同期非计划性大幅减持是强警告；美股 A(授予)/F(缴税)/M(行权)为非自主交易，不计入净买卖。
- 报告发布前执行数据抽检准出流程（唯一协议定义：[`references/audit-protocol.md`](audit-protocol.md)，工具：[`tools/report_audit.py`](../tools/report_audit.py)）。抽检分两档：
  - **研报级（必须抽检）**：产出决策/研究/发布级报告的流程，抽检通过方可交付；
  - **快反/对话级（可豁免）**：时效优先或纯对话形态，免抽检但须在产出物中标注「未经抽检」。
- 采用证据标注规范（`[E{n}]`，见 [`references/report-conventions.md`](report-conventions.md)）的报告，可追加逻辑链审计 `report_audit.py logic-chain`（退出码 0=证据覆盖率≥70% / 1=需补充证据链；协议见 audit-protocol.md「逻辑链审计」）。
- 工具调用语法与容差分档的唯一权威定义：[`skills/financial-data/references/verification-playbook.md`](../skills/financial-data/references/verification-playbook.md)。
- 工具退出码统一语义：0=验证通过 / 1=验证不通过（需排查后重跑） / 2=参数错误（修正命令重试，不算验证失败）。
- 启动研究流程前可运行 [`tools/doctor.py`](../tools/doctor.py) 一键自检取数与验算链路（退出码 0=全部就绪 / 1=存在降级项）。

## 决策日志约定（反馈闭环）

- 产出明确结论（买入/观望/回避/卖出/减仓/通过/不通过）的研报级流程，在报告交付后**必须**追加一条决策记录：
  `python3 tools/decision_log.py add --company {公司} --code {代码} --skill {子流程名} --verdict {结论} --price {当前价} --currency {币种} --reason "{一句话核心理由}" --report {报告路径} --probability {置信度0-100}`
  （`--probability` 为结论成立的主观概率，见 report-conventions.md「概率化结论规范」；校准统计用 `decision_log.py calibrate`）
- 历史判断的复盘由 `track-record` 子流程承接，系统性偏差诊断与规则修改建议由 `self-review` 承接；对话级产出（dyp-ask/news-pulse）不记录。
- 研究结论为「观望+理想买点」时，主动提议用户加入观察清单（`tools/watchlist.py add`，区间必须来自报告估值结论）。

## 数据复用约定

- 同一研究内已双源验证的数据点直接复用，禁止重复取数；下游技能优先读取上游报告附录的已验证数据，仅对时效性数据（股价/市值/最新财报）重新取数。
- **跨会话复用**：研报级流程取数前先查公司档案库 `python3 tools/company_facts.py get {代码}`；研究交付后把本次双源验证过的**稳定事实**（股本结构/历史财务关键值/商业模式要点/论文红线）用 `set` 归档；时效性数据（现价/市值/当前PE）禁止入库；引用档案数据时在报告中标注「档案数据（{验证日期}验证）」。
- 具体规则见 [`skills/financial-data/SKILL.md`](../skills/financial-data/SKILL.md) 的「数据复用规则」。

## 工具调用工作目录约定

- 所有 `tools/*.py` 脚本均以**技能根目录**（本仓库根）为基准的相对路径调用，例如 `python3 tools/financial_rigor.py ...`。
- 执行前必须确保当前工作目录为技能根目录；作为独立插件运行、无法保证 `cwd` 时，先定位到本仓库根目录再调用（例如 `cd <仓库根> && python3 tools/xxx.py ...`），避免相对路径失效。
