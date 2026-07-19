# AI Berkshire 投研技能

一套符合 **Claude Code 技能规范**的投资研究技能。将巴菲特、芒格、段永平、李录四位价值投资大师的方法论系统化、结构化，通过多 Agent 并行、结构化反偏见机制与金融严谨性工具，实现专业级投资研究。

支持**两种使用形态**（可共存）：
- **单个技能**（推荐）：整个目录即一个技能，入口是根 [`SKILL.md`](SKILL.md)（`name: ai-berkshire`），由它识别意图并调度 `skills/` 下的子流程。
- **插件（Plugin）**：保留 [`.claude-plugin/plugin.json`](.claude-plugin/plugin.json)，`skills/` 下每个子技能都可被独立发现与调用。

## 目录结构

```
ai-berkshire/                        # 技能根目录（= 仓库根）
├── SKILL.md                         # ★ 单技能入口（name: ai-berkshire）：意图识别与子流程调度
├── .claude-plugin/
│   └── plugin.json                  # 插件清单（name / version / description ...）
├── CLAUDE.md                        # 项目级指令：客观性原则/报告路径约定/金融严谨性（被各流程引用）
├── references/
│   └── masters-profiles.md          # 四大师画像卡（跨流程视角一致性的唯一定义）
├── skills/                          # 全部子流程，每个一个目录
│   ├── investment-research/
│   │   └── SKILL.md
│   ├── investment-team/
│   │   └── SKILL.md
│   ├── ...                          # 其余子流程同构
│   └── financial-data/              # 共享数据规范（被其他流程引用）
│       ├── SKILL.md
│       └── references/
│           └── verification-playbook.md  # 验证工具权威调用语法与容差分档
└── tools/                           # 共享 Python 工具，供流程通过 Bash 调用
    ├── financial_rigor.py           # 市值/估值/情景计算 + Benford 造假初筛（禁止心算）
    ├── report_audit.py              # 报告数据抽检准出
    ├── ashare_data.py               # A 股行情/财务（腾讯行情+东财接口）
    ├── xueqiu_scraper.py            # 雪球大 V 观点抓取（需 Playwright + 登录态）
    ├── morningstar_fair_value.py    # 晨星公允价值（第三方接口，可能失效，失效时降级 WebSearch）
    ├── log-command.sh
    └── experimental/                # ⚠️ 动量实验工具，不属于四大师价值投资体系，不被任何流程调用
        ├── stock_screener.py        # 动量发现+价值验证选股筛（独立实验）
        └── momentum_backtest.py / _v2.py  # 动量回测
```

每个子流程是一个独立目录，内含一个 `SKILL.md`，遵循 Claude Code 技能规范：

```markdown
---
name: <kebab-case，与目录名一致>
description: <做什么 + 何时使用，含触发关键词，用于自动匹配>
---

# 正文（执行流程、模板、规则……）
```

> **渐进式披露**：当子流程正文过长（建议 SKILL.md 正文控制在 ~500 行内）时，把大块模板/清单拆到该目录下的 `references/` 子目录按需引用，例如 [`skills/private-company-research/`](skills/private-company-research/) 将 6 个任务模板与最终报告结构分别外置到 `references/task-briefs.md`、`references/report-template.md`，主 `SKILL.md` 仅保留执行骨架。

## 能力清单（1 个入口 + 20 个子流程）

统一入口是根目录的 [`SKILL.md`](SKILL.md)（技能名 `ai-berkshire`），负责识别意图并调度下列子流程；作为插件使用时，下列子流程也可被独立调用。报告统一输出到 `reports/` 目录（路径约定见 [`CLAUDE.md`](CLAUDE.md)）。

| 分类 | 子流程 | 一句话 |
|------|--------|--------|
| **个股研究** | `investment-research` | 四大师综合分析（单 Agent），出明确结论 |
| | `investment-team` | 4 角色多 Agent 并行团队研究 |
| | `investment-checklist` | 巴菲特买入前 Checklist |
| | `management-deep-dive` | 管理层纵深研究：买股票就是买人 |
| | `dyp-ask` | 以段永平视角问答 |
| **行业/筛选** | `industry-research` | 产业链全景 + 四大师个股框架 |
| | `industry-funnel` | 行业漏斗筛选，全市场到 3 家 |
| | `quality-screen` | 7 条硬指标去劣初筛 |
| | `bottleneck-hunter` | 供应链瓶颈套利 |
| **财报** | `earnings-review` | 财报精读（单人） |
| | `earnings-team` | 财报团队精读 + 公众号发布 |
| **决策/监控** | `portfolio-review` | 组合管理 |
| | `thesis-tracker` | 投资论文追踪 |
| | `thesis-drift` | 投资论文漂移检测 |
| | `news-pulse` | 股价异动快速归因 |
| | `exit-review` | 卖出决策审查（段永平“卖出三理由”+退出纪律） |
| **未上市** | `private-company-research` | 一级市场未上市公司研究 |
| **内容创作** | `deep-company-series` | 8 篇深度长文系列 |
| | `wechat-article` | 公众号文章（三 Agent 协作） |
| **规范** | `financial-data` | 财务数据获取与交叉验证规范 |

## 使用方式

### 形态一：作为单个技能（推荐）

整个 `ai-berkshire/` 目录就是一个技能，入口是根 [`SKILL.md`](SKILL.md)。把整个目录放到 agent 会扫描的技能目录下即可：

```bash
# 项目级
mkdir -p .claude/skills && ln -s "$(pwd)" .claude/skills/ai-berkshire
# 或个人级
ln -s "$(pwd)" ~/.claude/skills/ai-berkshire
```

agent 读取根 `SKILL.md` 的 `description` 后，在用户提出投研需求时自动触发；触发后按其路由表打开并执行对应的 `skills/<名称>/SKILL.md`。

### 形态二：作为 Claude Code 插件

保留 `.claude-plugin/plugin.json`，将本仓库作为插件源加入市场（marketplace）或通过 `/plugin` 安装；安装后 `skills/` 下的每个子技能都会被独立发现。

### 快速开始（复制即用）

| 你想做什么 | 直接对 agent 说 | 会发生什么 |
|-----------|----------------|-----------|
| 研究一家公司 | “帮我研究一下贵州茅台，判断现在能不能买” | 确认后执行 `investment-research`，产出四大师视角研报 + 明确结论，写入 `reports/贵州茅台/` |
| 深度团队研究 | “用团队方式深度研究拼多多” | 4 角色并行研究，阶段性更新进度，最终合并报告（耗时更长） |
| 读财报 | “读一下腾讯 2025Q4 财报” | 一手财报解读 + 双源数据交叉验证 + Benford 初筛 |
| 行业选股 | “新能源车行业帮我选出最值得研究的 3 家” | `industry-funnel` 逐层筛选到 3 家，含淘汰理由 |
| 持仓检视 | “帮我审视组合：腾讯 30%、茅台 25%、…” | 组合集中度/相关性/预期回报分析 + 调仓建议 |
| 要不要卖 | “英伟达涨了很多，要不要卖点” | `exit-review` 按段永平“卖出三理由”审查，出去留方案 |
| 不知道从哪开始 | “AI Berkshire 能做什么？” | 展示能力菜单与新手引导 |

其他调用形式：
- **显式指定子流程**（跳过确认）：`用 earnings-review 精读英伟达最新财报`
- **意图不明时**：agent 会最多问 2 个带编号选项的问题，回复数字即可

## 最佳实践

1. **一句话给足两个要素**：研究对象 + 目的（“研究拼多多，判断能不能买”优于“看看拼多多”），可显著减少反问。
2. **按生命周期使用**：筛选 → 深研 → 买前 Checklist → 买后 thesis-tracker 建论文 → 持有期每季 earnings-review / 异动 news-pulse → 想卖时 exit-review。报告链路互通，上游产出会被下游自动读取。
3. **已持仓先声明**：说“我持有腾讯，…”会优先路由到跟踪/退出类流程，而不是从头研究。
4. **报告都在 `reports/`**：公司级 `reports/{公司名}/{公司名}-{技能名}-{日期}.md`，论文快照 `reports/{公司名}-thesis.md`。不要手动移动，否则下游流程读不到。
5. **多 Agent 流程耗时更长**：追求速度选单 Agent 版（investment-research / earnings-review），追求深度选团队版（investment-team / earnings-team）。
6. **结论只是研究参考**：所有输出均为方法论推演，不构成投资建议。

## 兼容性与降级

本技能在不同 agent 环境下均可运行，多 Agent 类流程启动前会自检工具能力并自动降级（详见根 `SKILL.md`「执行环境自检」节）：

- **有 Team 协作工具**（Claude Code）：按原文多 Agent 协作执行；
- **仅有并行子代理**：同一消息并行启动各角色，直接汇总报告；
- **单 Agent 环境**：顺序扮演各角色后汇总，报告标注“非真正并行”；
- **无 Python/网络**：验算降级为双源人工比对，报告标注“未经工具验算”。

降级不需要用户配置，agent 会在启动前告知降级方式与影响。

## 工具集成

流程通过 `Bash` 调用 `tools/` 下的 Python 脚本以保证数据精确性，**权威调用语法与容差分档见 [`skills/financial-data/references/verification-playbook.md`](skills/financial-data/references/verification-playbook.md)**，例如：

```bash
# 市值验算（禁止心算）
python3 tools/financial_rigor.py verify-market-cap --price 100 --shares 12.5 --reported 1250 --currency USD

# 报告数据抽检
python3 tools/report_audit.py extract --report <报告路径>
```

工具路径以**技能根目录**为基准（`tools/xxx.py`）。

**依赖说明**：
- `financial_rigor.py` / `report_audit.py` / `ashare_data.py` / `morningstar_fair_value.py`：零外部依赖（仅 Python ≥ 3.8 标准库；后两者需网络与 `curl`）
- `xueqiu_scraper.py`：需 `pip install playwright && playwright install chromium`，首次使用需交互式登录雪球（登录态缓存后可 headless 复用）；不适合在无交互环境首次运行
- `tools/experimental/`：动量实验工具，与四大师价值投资方法论无关，不被任何流程调用；其依赖的 `data/fundamentals.json` 需手工维护，过期时工具会提示

## 扩展新子流程

1. 在 `skills/` 下新建目录 `skills/<new-skill>/`。
2. 创建 `SKILL.md`，填写 `name`（与目录同名）与 `description`（含触发关键词）。
3. 在正文中编写执行流程；如需数据精确性，调用 `tools/` 工具并遵循 [`skills/financial-data/SKILL.md`](skills/financial-data/SKILL.md) 数据规范。
4. 在根 [`SKILL.md`](SKILL.md) 的意图路由表中补充一行，使其可被统一入口调度。

作为插件使用时无需改动任何配置文件——Claude Code 会自动发现新技能。

## FAQ

**Q: 说了需求但技能没被触发？**
确认软链/插件安装正确（`ls .claude/skills/ai-berkshire/SKILL.md` 应存在）；或直接显式说“用 AI Berkshire 研究 XX”。

**Q: 报告生成在哪？**
统一在技能根目录的 `reports/` 下，按公司名分文件夹；执行完成时 agent 会告知具体路径。

**Q: 没有 Claude Code 的 Team 工具，多 Agent 流程能用吗？**
能。会自动降级为并行子代理或单 Agent 顺序执行，见上方「兼容性与降级」。

**Q: 数据可靠吗？**
关键财务数据强制双源交叉验证（差异 >5% 不采用），计算一律走 `financial_rigor.py` 禁止心算，报告交付前经 `report_audit.py` 抽检。但结论仍为研究参考，非投资建议。

**Q: 支持哪些市场？**
A股/港股/美股及未上市公司。A股有程序化取数通道（`ashare_data.py`），其他市场走 WebSearch 双源验证。

**Q: 不做什么？**
不做短线择时、技术分析、加密货币预测、期权策略——与价值投资定位不符，会如实告知并建议替代。

## 核心原则

所有流程执行时都遵循 [`CLAUDE.md`](CLAUDE.md) 的客观性原则：先数据后结论、区分事实与推测、数据标注来源、诚实面对不确定性、正反两面、结论明确。
