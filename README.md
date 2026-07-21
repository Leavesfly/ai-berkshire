<div align="center">

# 🏛️ AI Berkshire

### 四位价值投资大师的方法论，一个 AI 投研系统

**巴菲特** 看护城河 · **芒格** 找死法 · **段永平** 看生意本质 · **李录** 看文明趋势

[![Python](https://img.shields.io/badge/Python-≥3.9-blue?logo=python&logoColor=white)](pyproject.toml)
[![Version](https://img.shields.io/badge/version-1.2.0-green)](pyproject.toml)
[![Markets](https://img.shields.io/badge/markets-A股_·_港股_·_美股_·_未上市-orange)](#支持市场)
[![License](https://img.shields.io/badge/license-MIT-lightgrey)]()

</div>

---

> *"投资的第一条规则是不要亏损，第二条规则是记住第一条。"* — Warren Buffett

**AI Berkshire** 将巴菲特、芒格、段永平、李录四位价值投资大师数十年验证的方法论系统化、结构化，通过 **多 Agent 并行协作**、**结构化反偏见机制** 与 **金融严谨性工具链**，让每个人都能获得专业级投资研究能力。

不是聊天机器人式的"分析"——是一套完整的、有纪律的投研工作流。

---

## ✨ 为什么不一样

| | 普通 AI 分析 | AI Berkshire |
|:--|:--|:--|
| **视角** | 单一视角，容易确认偏误 | 四大师独立视角 + 强制反面检验 |
| **数据** | 可能编造数字 | 双源交叉验证，差异 >5% 不采用 |
| **计算** | 心算，不可靠 | 全部走 Python 工具，禁止心算 |
| **结论** | 模棱两可 | 必须给出"买入/观望/回避"明确判断 |
| **纪律** | 无 | 8 条红线一票否决，决策日志可复盘 |
| **覆盖** | 单次对话 | 完整投资生命周期：筛选→深研→买入→持有→退出 |

---

## 🚀 30 秒上手

```bash
# 1. 安装依赖
pip install .

# 2. 环境自检（可选）
python3 tools/doctor.py

# 3. 开始研究 — 对 Agent 说：
"帮我研究一下贵州茅台，判断现在能不能买"
```

就这么简单。不需要记任何命令或子流程名称——用大白话描述需求即可。

---

## 🎯 快速开始：照着说就行

| 你想做什么 | 直接说 | 耗时 |
|:--|:--|:--|
| 研究一家公司 | "帮我研究一下贵州茅台" | ⚡ 几分钟 |
| 多标的对比 | "腾讯、美团、比亚迪哪个好" | ⚡ 几分钟 |
| 深度团队研究 | "用团队方式深度研究拼多多" | 🕐 多Agent并行 |
| 读财报 | "读一下腾讯 2025Q4 财报" | ⚡ 几分钟 |
| 行业选股 | "新能源车行业选出最值得研究的 3 家" | ⚡ 几分钟 |
| 股价异动 | "拼多多跌了 8%，发生了什么" | ⚡ 快反级 |
| 要不要卖 | "英伟达涨了很多，要不要卖点" | ⚡ 几分钟 |
| 持仓检视 | "帮我审视组合：腾讯 30%、茅台 25%…" | ⚡ 几分钟 |
| 大师持仓 | "巴菲特最近买了什么" | ⚡ 几分钟 |
| 写深度文章 | "写一篇拼多多的公众号深度稿" | 🕐 多Agent协作 |
| 段永平视角 | "段永平会怎么看拼多多" | 💬 对话级 |

**快捷用法**（熟练后更简短）：

```
研究 茅台          → 完整投研报告
财报 腾讯          → 最新财报精读
卖不卖 英伟达      → 退出决策审查
段永平 拼多多      → 段永平视角问答
对比 腾讯 阿里 美团 → 多标的去劣对比
```

---

## 🧠 四大师各看什么

每份研报都包含四位大师的**独立视角**，不是拼凑，是真正的方法论分工：

<div align="center">

| 大师 | 核心问题 | 否决条件 |
|:--|:--|:--|
| 🎩 **巴菲特** | 10 年后护城河还在吗？赚的是真钱还是假钱？ | 看不懂 / 无护城河 / 无安全边际 |
| 🔄 **芒格** | 这家公司最可能怎么死？聪明人为什么做空它？ | 故事太完美 / 靠接盘者赚钱 |
| 🏭 **段永平** | 这是好生意吗？管理层本分吗？股市关 5 年你拿不拿？ | 不在能力圈 / 无差异化 / 不本分 |
| 🌏 **李录** | 20 年后是"标准石油"还是"昙花一现的 3Com"？ | 永久性资本损失风险 / 管理层隐瞒 |

</div>

> 画像定义见 [`references/masters-profiles.md`](references/masters-profiles.md)，跨全部 23 个子流程保持一致。

---

## 📐 投资生命周期全覆盖

AI Berkshire 不是一次性分析工具，而是覆盖**完整投资生命周期**的研究系统：

```
┌─────────────────────────────────────────────────────────────────────┐
│                                                                     │
│   ① 发现筛选          ② 深度研究           ③ 买卖决策              │
│   ┌──────────┐       ┌──────────┐        ┌──────────┐             │
│   │行业研究   │──→    │单Agent研究│──→     │买前清单   │             │
│   │漏斗筛选   │       │团队并行   │        │退出审查   │             │
│   │去劣初筛   │       │管理层深研 │        └────┬─────┘             │
│   │瓶颈套利   │       │未上市公司 │             │                   │
│   └──────────┘       └──────────┘             ▼                   │
│                                                                     │
│   ⑥ 视角问答          ⑤ 内容创作           ④ 持有监控              │
│   ┌──────────┐       ┌──────────┐        ┌──────────┐             │
│   │段永平问答 │       │公众号文章 │        │论文跟踪   │             │
│   └──────────┘       │深度长文系列│        │财报精读   │             │
│                      │财报团队   │        │异动归因   │             │
│                      └──────────┘        │组合检视   │             │
│                                          │观察清单   │             │
│                                          │决策复盘   │             │
│                                          │大师持仓   │             │
│                                          └──────────┘             │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

**推荐链路**（长期使用收益最大化）：

> 筛选 → 深研 → 买前 Checklist → 建论文 → 每季财报精读 / 异动归因 → 想卖时退出审查

上游产出自动成为下游输入，已验证数据跨流程复用，不重复取数。

---

## 🗂️ 能力全景（1 入口 + 23 子流程）

### ① 发现与筛选

| 子流程 | 能力 |
|:--|:--|
| `industry-research` | 产业链全景 + 四大师个股分析框架 |
| `industry-funnel` | 全市场逐层漏斗筛选到 3 家，含淘汰理由 |
| `quality-screen` | 7 条硬指标去劣初筛（ROE/负债率/现金流等） |
| `bottleneck-hunter` | 从供应链物理瓶颈找第二/三层套利标的 |

### ② 深度研究

| 子流程 | 能力 |
|:--|:--|
| `investment-research` | 四大师综合分析（单 Agent），出明确结论 |
| `investment-team` | 4 角色多 Agent 并行团队研究 |
| `management-deep-dive` | 管理层纵深：能力/诚信/资本配置 |
| `private-company-research` | 一级市场未上市公司深度研究 |

### ③ 买卖决策

| 子流程 | 能力 |
|:--|:--|
| `investment-checklist` | 巴菲特买入前逐项核对清单 |
| `exit-review` | 段永平"卖出三理由" + 退出纪律审查 |

### ④ 持有与监控

| 子流程 | 能力 |
|:--|:--|
| `thesis-tracker` | 投资论文纪律性复查 |
| `thesis-drift` | 论文漂移检测：事实变化 vs 措辞变化 |
| `earnings-review` | 一手财报深度解读 + 数据校验 |
| `news-pulse` | 4 Agent 侦察 + 股价异动快速归因 |
| `portfolio-review` | 组合集中度/相关性/预期回报优化 |
| `watchlist-monitor` | 买卖区间维护 + 批量信号扫描 + 推送 |
| `track-record` | 历史决策准确率复盘 + 错误模式归纳 |
| `masters-portfolio` | SEC 13F 大师持仓跟踪（伯克希尔/喜马拉雅） |

### ⑤ 内容创作

| 子流程 | 能力 |
|:--|:--|
| `wechat-article` | 作者-编辑-读者三 Agent 协作公众号深度稿 |
| `deep-company-series` | 8 篇成体系深度长文系列 |
| `earnings-team` | 财报团队精读 + 公众号发布 |

### ⑥ 视角问答

| 子流程 | 能力 |
|:--|:--|
| `dyp-ask` | 以段永平视角即时问答 |

---

## 🔧 工具链

所有涉及金额、估值、增长率的计算**必须走 Python 工具**，禁止心算——这是铁律。

### 核心工具一览

| 工具 | 职责 | 依赖 |
|:--|:--|:--|
| `financial_rigor.py` | 市值验算 / CAGR / 股东盈余 / 反向DCF / 估值分位 / 同业对标 / DCF矩阵 / M-Score / Altman-Z / 凯利仓位 | 零依赖 |
| `ashare_data.py` | A股/港股/美股行情 + 日K历史 + 指数通道 | akshare + yfinance |
| `filings_fetch.py` | 一手财报原文（SEC EDGAR / 巨潮 / 披露易） | 零依赖 |
| `chart_gen.py` | 出版级图表 PNG 生成 | matplotlib |
| `report_audit.py` | 报告数据抽检准出 | 零依赖 |
| `doctor.py` | 环境一键自检 | 零依赖 |

> 完整工具清单与调用语法见 [`references/tool-conventions.md`](references/tool-conventions.md)。

### 工具调用示例

```bash
# 市值验算（禁止心算）
python3 tools/financial_rigor.py verify-market-cap \
  --price 100 --shares 12.5 --reported 1250 --currency USD

# 内在价值：股东盈余 / 反向DCF / CAGR
python3 tools/financial_rigor.py owner-earnings \
  --net-income 1941 --depreciation 380 --maintenance-capex 250
python3 tools/financial_rigor.py reverse-dcf \
  --market-cap 28000 --fcf 1600 --discount-rate 0.10 --terminal-growth 0.025

# DCF 敏感性矩阵（增长率 × 贴现率）
python3 tools/financial_rigor.py dcf-matrix \
  --fcf 1600 --growth 0.05,0.10,0.15 \
  --discount 0.08,0.10,0.12 --terminal-growth 0.025 --market-cap 28000

# 行情取数（三市场，带本地缓存）
python3 tools/ashare_data.py quote 600519       # A股
python3 tools/ashare_data.py quote hk00700      # 港股
python3 tools/ashare_data.py quote usAAPL       # 美股

# 一手财报原文
python3 tools/filings_fetch.py fetch hk00700 --type annual --latest

# 大师持仓（SEC 13F）
python3 tools/masters_portfolio.py holdings berkshire
python3 tools/masters_portfolio.py diff berkshire   # 最近两季变动

# 去劣初筛（三市场批量）
python3 tools/quality_screen.py 600519 hk00700 usAAPL

# 组合分析 + 历史回撤模拟
python3 tools/portfolio_calc.py --holdings '[...]' --drawdown

# 观察清单 + 信号扫描
python3 tools/watchlist.py add --code hk00700 --name 腾讯 --buy-below 400
python3 tools/watchlist.py scan --notify

# 报告导出单文件 HTML（图表内嵌，微信/邮件直接分享）
python3 tools/report_export.py reports/腾讯/腾讯-investment-research-20260720.md
```

---

## 📦 安装

### 依赖安装

```bash
pip install .            # 核心依赖（akshare + yfinance + tickflow）
pip install .[viz]       # + 图表生成（matplotlib）
pip install .[filings]   # + 财报 PDF 解析（pypdf）
pip install .[all]       # 全部依赖
pip install .[dev]       # + 开发测试（pytest + ruff）
```

### 作为技能安装（推荐）

整个目录即一个技能，入口是根 [`SKILL.md`](SKILL.md)：

```bash
# 项目级
mkdir -p .claude/skills && ln -s "$(pwd)" .claude/skills/ai-berkshire

# 或个人级
ln -s "$(pwd)" ~/.claude/skills/ai-berkshire
```

### 作为插件安装

保留 [`.claude-plugin/plugin.json`](.claude-plugin/plugin.json)，将本仓库作为插件源安装；`skills/` 下每个子技能都会被独立发现。

---

## 🛡️ 金融严谨性保障

这不是"AI 随便说说"——每一步都有纪律：

```
┌─────────────────────────────────────────────────────┐
│              金融严谨性五道防线                        │
├─────────────────────────────────────────────────────┤
│                                                     │
│  ① 双源交叉验证                                     │
│     关键财务数据必须两个独立来源验证                    │
│     差异 >5% → 不采用，标注数据分歧                   │
│                                                     │
│  ② 禁止心算                                        │
│     所有金额/估值/增长率计算走 financial_rigor.py     │
│     退出码 0=通过 / 1=不通过 / 2=参数错误            │
│                                                     │
│  ③ 反偏见机制                                       │
│     信息丰富度评级（A/B/C）                          │
│     强制反面检验（芒格式逆向）                        │
│     8 条红线一票否决                                 │
│                                                     │
│  ④ 报告抽检准出                                     │
│     report_audit.py 数据抽检                         │
│     研报级流程：抽检通过方可交付                      │
│                                                     │
│  ⑤ 决策日志闭环                                     │
│     每个结论落盘 → 现价复盘 → 错误模式归纳           │
│     支持同期基准对比                                 │
│                                                     │
└─────────────────────────────────────────────────────┘
```

---

## 📊 支持市场

| 市场 | 行情 | 财务数据 | 一手财报 |
|:--|:--|:--|:--|
| 🇨🇳 A股 | ✅ 腾讯行情接口 | ✅ akshare + 东财 | ✅ 巨潮资讯 |
| 🇭🇰 港股 | ✅ 腾讯行情接口 | ✅ yfinance + WebSearch | ✅ 披露易 |
| 🇺🇸 美股 | ✅ 腾讯行情接口 | ✅ yfinance + WebSearch | ✅ SEC EDGAR |
| 🏢 未上市 | — | WebSearch 多源 | 公开披露 |

- 行情数据 15 分钟本地缓存，财务数据 7 天缓存
- 网络失败自动回退缓存并标注 `[缓存数据]`
- 每个市场三级备用源轮换

---

## 🏗️ 项目结构

```
ai-berkshire/
├── SKILL.md                    # ★ 统一入口：意图识别 → 子流程调度
├── CLAUDE.md                   # 项目级指令：客观性原则 / 金融严谨性
├── .claude-plugin/plugin.json  # 插件清单
│
├── references/                 # 跨流程共享定义
│   ├── masters-profiles.md     #   四大师画像卡（唯一权威）
│   ├── report-visuals.md       #   报告可视化规范
│   ├── report-conventions.md   #   报告输出规范
│   ├── routing-guide.md        #   路由消歧规则
│   └── tool-conventions.md     #   工具调用规范
│
├── skills/                     # 23 个子流程（每个一个目录）
│   ├── investment-research/    #   四大师综合分析
│   ├── investment-team/        #   多Agent团队研究
│   ├── earnings-review/        #   财报精读
│   ├── quality-screen/         #   去劣初筛
│   ├── exit-review/            #   卖出决策
│   ├── financial-data/         #   共享数据规范
│   └── ...                     #   其余子流程同构
│
├── tools/                      # Python 工具链
│   ├── financial_rigor.py      #   估值计算引擎（禁止心算）
│   ├── ashare_data.py          #   三市场行情/财务取数
│   ├── filings_fetch.py        #   一手财报原文管道
│   ├── filings_parse.py        #   财报语义解析
│   ├── masters_portfolio.py    #   SEC 13F 持仓解析
│   ├── chart_gen.py            #   出版级图表生成
│   ├── report_audit.py         #   报告数据抽检
│   ├── report_export.py        #   单文件HTML导出
│   └── ...                     #   更多工具
│
├── data/                       # 运行时数据
│   ├── cache/                  #   行情/财务本地缓存
│   ├── companies/              #   公司档案库（跨会话沉淀）
│   ├── filings/                #   下载的财报原文
│   └── watchlist.json          #   观察清单
│
├── reports/                    # 报告输出（按公司分目录）
└── tests/                      # 工具层冒烟测试
```

---

## 🔄 兼容性与优雅降级

在任何 Agent 环境下都能运行，自动检测能力并降级：

| 环境能力 | 执行方式 |
|:--|:--|
| ✅ Team 协作工具 | 多 Agent 真正并行 |
| ✅ 并行子代理 | 同一消息并行启动各角色 |
| ⚠️ 仅单 Agent | 顺序扮演各角色，标注"非真正并行" |
| ⚠️ 无 Python/网络 | 双源人工比对，标注"未经工具验算" |

降级无需用户配置，启动前自动告知影响。

---

## 💡 最佳实践

1. **一句话给足两要素**：研究对象 + 目的。"研究拼多多，判断能不能买" 远优于 "看看拼多多"。

2. **按生命周期使用**：筛选 → 深研 → Checklist → 建论文 → 每季精读 → 想卖时退出审查。报告链路互通。

3. **已持仓先声明**：说"我持有腾讯，…"会优先路由到跟踪/退出类流程。

4. **追求速度 vs 深度**：单 Agent 版（`investment-research`）快，团队版（`investment-team`）深。

5. **数据自动复用**：已验证数据跨流程复用不重复取数，链式使用越来越快。

6. **报告在 `reports/`**：按公司分目录，不要手动移动——下游流程依赖路径。

---

## 🧪 测试

```bash
pip install .[dev]
python3 -m pytest tests/ -q
```

全离线冒烟测试，验证工具链基本功能。

---

## 🚫 不做什么

AI Berkshire 有明确的能力边界——与价值投资定位不符的事，不做：

- ❌ 短线择时 / 技术分析
- ❌ 加密货币预测
- ❌ 期权策略 / 衍生品
- ❌ 虚构大师未说过的具体表述
- ❌ 用推测填满框架伪装确定性

> 所有输出均为方法论推演，**不构成投资建议**。

---

## 📜 核心原则

> 先数据后结论 · 区分事实与推测 · 数据标注来源 · 诚实面对不确定性 · 正反两面 · 结论明确

详见 [`CLAUDE.md`](CLAUDE.md) — 全部 23 个子流程执行时的最高优先级约束。

---

## 🧩 扩展新子流程

```bash
# 1. 创建目录
mkdir skills/my-new-skill

# 2. 编写 SKILL.md（name 与目录同名，description 含触发关键词）
vim skills/my-new-skill/SKILL.md

# 3. 在根 SKILL.md 路由表补充一行

# 4. 完成 — 插件模式下自动发现，无需改配置
```

---

<div align="center">

**用大师的纪律，做自己的研究。**

*AI Berkshire — 让价值投资方法论真正可执行。*

</div>
