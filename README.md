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
├── CLAUDE.md                        # 项目级指令与客观性原则（被各流程引用）
├── skills/                          # 全部子流程，每个一个目录
│   ├── investment-research/
│   │   └── SKILL.md
│   ├── investment-team/
│   │   └── SKILL.md
│   ├── ...                          # 其余子流程同构
│   └── financial-data/              # 共享数据规范（被其他流程引用）
│       └── SKILL.md
└── tools/                           # 共享 Python 工具，供流程通过 Bash 调用
    ├── financial_rigor.py           # 市值/估值/情景计算（禁止心算）
    ├── report_audit.py              # 报告数据抽检准出
    ├── stock_screener.py            # 选股筛选
    ├── ashare_data.py               # A 股数据
    ├── xueqiu_scraper.py            # 雪球大 V 观点抓取
    ├── morningstar_fair_value.py    # 晨星公允价值
    ├── momentum_backtest.py / _v2.py# 动量回测
    └── log-command.sh
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

## 能力清单（1 个入口 + 19 个子流程）

统一入口是根目录的 [`SKILL.md`](SKILL.md)（技能名 `ai-berkshire`），负责识别意图并调度下列子流程；作为插件使用时，下列子流程也可被独立调用。

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

### 调用示例

- **自然语言**：`帮我用团队方式深度研究一下拼多多` → 执行 `skills/investment-team/SKILL.md`
- **显式指定**：`用 earnings-review 精读英伟达最新财报`
- **查看能力**：`AI Berkshire 能做什么？` → 根 `SKILL.md` 展示能力菜单

## 工具集成

流程通过 `Bash` 调用 `tools/` 下的 Python 脚本以保证数据精确性，例如：

```bash
# 市值验算（禁止心算）
python3 tools/financial_rigor.py verify-market-cap --price 100 --shares 12.5 --reported 1250 --currency USD

# 报告数据抽检
python3 tools/report_audit.py extract --report <报告路径>
```

工具路径以**技能根目录**为基准（`tools/xxx.py`）。

## 扩展新子流程

1. 在 `skills/` 下新建目录 `skills/<new-skill>/`。
2. 创建 `SKILL.md`，填写 `name`（与目录同名）与 `description`（含触发关键词）。
3. 在正文中编写执行流程；如需数据精确性，调用 `tools/` 工具并遵循 [`skills/financial-data/SKILL.md`](skills/financial-data/SKILL.md) 数据规范。
4. 在根 [`SKILL.md`](SKILL.md) 的意图路由表中补充一行，使其可被统一入口调度。

作为插件使用时无需改动任何配置文件——Claude Code 会自动发现新技能。

## 核心原则

所有流程执行时都遵循 [`CLAUDE.md`](CLAUDE.md) 的客观性原则：先数据后结论、区分事实与推测、数据标注来源、诚实面对不确定性、正反两面、结论明确。
