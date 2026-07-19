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

- 涉及金额、市值、估值的计算**必须调用 [`tools/financial_rigor.py`](tools/financial_rigor.py)**，禁止心算。
- 报告发布前执行数据抽检准出流程（[`tools/report_audit.py`](tools/report_audit.py)）。
- 工具调用语法与容差分档的唯一权威定义：[`skills/financial-data/references/verification-playbook.md`](skills/financial-data/references/verification-playbook.md)。

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

## 语言与风格

- 默认输出语言：中文。
- 风格：直接、犀利、不说废话；用 Markdown 表格呈现关键数据。
