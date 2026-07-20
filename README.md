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
│   ├── masters-profiles.md          # 四大师画像卡（跨流程视角一致性的唯一定义）
│   └── report-visuals.md            # 报告可视化规范（四类图表标准与降级方案）
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
    ├── financial_rigor.py           # 市值/估值/情景计算 + Benford 初筛 + CAGR/股东盈余/反向DCF + 估值分位/同业对标/DCF矩阵 + M-Score/Altman-Z/应计质量/凯利仓位（禁止心算）
    ├── report_audit.py              # 报告数据抽检准出
    ├── report_export.py             # ★ 报告导出自包含 HTML（图表 base64 内嵌，单文件可分享）
    ├── chart_gen.py                 # 报告图表 PNG 生成（matplotlib 可选依赖，缺失时自动降级 Mermaid）
    ├── doctor.py                    # 环境一键自检（取数/验算链路就绪度）
    ├── ashare_data.py               # A 股行情/财务 + 港美股行情 + 日K历史与指数通道（腾讯行情+东财接口，带 data/cache/ 本地缓存）
    ├── filings_fetch.py             # 一手财报原文管道（美股 SEC EDGAR / A股巨潮 / 港股披露易，零依赖）
    ├── filings_parse.py             # ★ 财报原文语义管道：章节抽取（风险因素/MD&A）+ 跨年措辞 diff（PDF 需可选 pypdf）
    ├── masters_portfolio.py         # ★ SEC 13F 大师持仓解析（伯克希尔/喜马拉雅季度持仓与变动，零依赖）
    ├── quality_screen.py            # 去劣 7 条硬指标自动取数打分（三市场批量）
    ├── portfolio_calc.py            # 组合集中度/相关性矩阵/加权预期回报 + 历史回撤模拟（--drawdown）
    ├── decision_log.py              # 决策日志：结论落盘 data/decisions.jsonl + 现价复盘 + 同期基准对比（--benchmark）
    ├── watchlist.py                 # 观察清单：买卖区间维护 + 批量信号扫描 + webhook 推送（--notify）+ 定时配置生成（schedule）
    ├── company_facts.py             # ★ 公司档案库：已验证稳定事实跨会话沉淀 data/companies/
    ├── xueqiu_scraper.py            # 雪球大 V 观点抓取（需 Playwright + 登录态）
    ├── morningstar_fair_value.py    # 晨星公允价值（第三方接口，可能失效，失效时降级 WebSearch）
    ├── log-command.sh
    └── experimental/                # ⚠️ 动量实验工具，不属于四大师价值投资体系，不被任何流程调用
        ├── data/                    # 实验工具私有数据（fundamentals.json / watchlist.json，手工维护）
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

> **渐进式披露**：当子流程正文过长（建议 SKILL.md 正文控制在 ~500 行内）时，把大块模板/清单拆到该目录下的 `references/` 子目录按需引用，例如 [`skills/private-company-research/`](skills/private-company-research/)（6 个任务模板 + 报告结构外置）、[`skills/earnings-team/`](skills/earnings-team/)（6 个 Agent 任务书外置到 `references/agent-briefs.md`）、[`skills/bottleneck-hunter/`](skills/bottleneck-hunter/)（每小时扫描模式外置到 `references/hourly-scan-mode.md`），主 `SKILL.md` 仅保留执行骨架。

## 能力清单（1 个入口 + 23 个子流程）

统一入口是根目录的 [`SKILL.md`](SKILL.md)（技能名 `ai-berkshire`），负责识别意图并调度下列子流程；作为插件使用时，下列子流程也可被独立调用。报告统一输出到 `reports/` 目录（路径约定见 [`CLAUDE.md`](CLAUDE.md)）。

| 分类（按投资生命周期） | 子流程 | 一句话 |
|------|--------|--------|
| **① 发现与筛选** | `industry-research` | 产业链全景 + 四大师个股框架 |
| | `industry-funnel` | 行业漏斗筛选，全市场到 3 家 |
| | `quality-screen` | 7 条硬指标去劣初筛 |
| | `bottleneck-hunter` | 供应链瓶颈套利 |
| **② 深度研究** | `investment-research` | 四大师综合分析（单 Agent），出明确结论 |
| | `investment-team` | 4 角色多 Agent 并行团队研究 |
| | `management-deep-dive` | 管理层纵深研究：买股票就是买人 |
| | `private-company-research` | 一级市场未上市公司研究（信息稀缺对象的深研变体） |
| **③ 买卖决策** | `investment-checklist` | 巴菲特买入前 Checklist |
| | `exit-review` | 卖出决策审查（段永平“卖出三理由”+退出纪律） |
| **④ 持有与监控** | `thesis-tracker` | 投资论文追踪 |
| | `thesis-drift` | 投资论文漂移检测 |
| | `earnings-review` | 财报精读（单人） |
| | `news-pulse` | 股价异动快速归因（快反级，免抽检） |
| | `portfolio-review` | 组合管理（跨标的） |
| | `watchlist-monitor` | 观察清单：买卖区间维护 + 批量信号扫描 |
| | `track-record` | 决策复盘：历史结论准确率与错误模式归纳 |
| | `masters-portfolio` | 大师持仓跟踪：伯克希尔/喜马拉雅 13F 季度持仓与变动 |
| **⑤ 内容创作** | `wechat-article` | 公众号文章（三 Agent 协作，投资主题强制严谨性管线） |
| | `deep-company-series` | 8 篇深度长文系列 |
| | `earnings-team` | 财报团队精读 + 公众号发布（监控×创作双归属） |
| **⑥ 视角问答** | `dyp-ask` | 以段永平视角问答（对话级，免抽检） |
| **⑦ 共享规范** | `financial-data` | 财务数据获取与交叉验证规范（被其他流程引用，不单独触发） |

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

| 你想做什么 | 直接对 agent 说 | 会发生什么 | 耗时 |
|-----------|----------------|-----------|------|
| 研究一家公司 | “帮我研究一下贵州茅台，判断现在能不能买” | 确认后执行 `investment-research`，产出四大师视角研报 + 明确结论，写入 `reports/贵州茅台/` | ⚡ 几分钟 |
| 深度团队研究 | “用团队方式深度研究拼多多” | 4 角色并行研究，阶段性更新进度，最终合并报告 | 🕐 多Agent并行，较久更深 |
| 读财报 | “读一下腾讯 2025Q4 财报” | 一手财报解读 + 双源数据交叉验证 + Benford 初筛 | ⚡ 几分钟 |
| 行业选股 | “新能源车行业帮我选出最值得研究的 3 家” | `industry-funnel` 逐层筛选到 3 家，含淘汰理由 | ⚡ 几分钟 |
| 持仓检视 | “帮我审视组合：腾讯 30%、茅台 25%、…” | 组合集中度/相关性/预期回报分析 + 调仓建议 | ⚡ 几分钟 |
| 要不要卖 | “英伟达涨了很多，要不要卖点” | `exit-review` 按段永平“卖出三理由”审查，出去留方案 | ⚡ 几分钟 |
| 不知道从哪开始 | “AI Berkshire 能做什么？” | 展示能力菜单与新手引导 | — |

其他调用形式：
- **显式指定子流程**（跳过确认）：`用 earnings-review 精读英伟达最新财报`
- **意图不明时**：agent 会最多问 2 个带编号选项的问题，回复数字即可

## 最佳实践

1. **一句话给足两个要素**：研究对象 + 目的（“研究拼多多，判断能不能买”优于“看看拼多多”），可显著减少反问。
2. **按生命周期使用**：筛选 → 深研 → 买前 Checklist → 买后 thesis-tracker 建论文 → 持有期每季 earnings-review / 异动 news-pulse → 想卖时 exit-review。报告链路互通，上游产出会被下游自动读取。
3. **已持仓先声明**：说“我持有腾讯，…”会优先路由到跟踪/退出类流程，而不是从头研究。
4. **报告都在 `reports/`**：公司级 `reports/{公司名}/{公司名}-{技能名}-{日期}.md`，论文快照 `reports/{公司名}-thesis.md`。不要手动移动，否则下游流程读不到。
5. **多 Agent 流程耗时更长**：追求速度选单 Agent 版（investment-research / earnings-review），追求深度选团队版（investment-team / earnings-team）。
6. **已验证数据会自动复用**：同一研究内及上下游流程间，已双源验证的历史数据直接复用不重复取数，仅股价/市值等时效性数据会刷新，因此链式使用（研究→跟踪→退出）更快。
7. **结论只是研究参考**：所有输出均为方法论推演，不构成投资建议。

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

# 内在价值类计算：年均增速 / 股东盈余 / 市场隐含增长率反解
python3 tools/financial_rigor.py cagr --begin 2261 --end 6603 --years 5
python3 tools/financial_rigor.py owner-earnings --net-income 1941 --depreciation 380 --maintenance-capex 250
python3 tools/financial_rigor.py reverse-dcf --market-cap 28000 --fcf 1600 --discount-rate 0.10 --terminal-growth 0.025

# 估值深化：历史分位 / 同业对标 / DCF 敏感性矩阵
python3 tools/financial_rigor.py valuation-percentile --metric PE --current 22 --history '[35,42,28,55,38,30,25,45,33,27]'
python3 tools/financial_rigor.py peer-compare --target '{"name":"腾讯","PE":18,"PB":3.4}' --peers '[{"name":"阿里","PE":12},{"name":"Meta","PE":24}]'
python3 tools/financial_rigor.py dcf-matrix --fcf 1600 --growth 0.05,0.10,0.15 --discount 0.08,0.10,0.12 --terminal-growth 0.025 --market-cap 28000

# 行情取数（A股/港股/美股，命中本地缓存时秒回；加 --no-cache 强制直连）
python3 tools/ashare_data.py quote 600519
python3 tools/ashare_data.py quote hk00700
python3 tools/ashare_data.py quote usAAPL
python3 tools/ashare_data.py history 600519 --days 250      # 日K收盘价序列（前复权）

# 一手财报原文（美股 SEC EDGAR / A股巨潮 / 港股披露易）
python3 tools/filings_fetch.py list usAAPL --type 10-K --limit 5
python3 tools/filings_fetch.py fetch hk00700 --type annual --latest   # 下载到 data/filings/

# 财报原文语义管道：章节抽取 + 跨年措辞对比
python3 tools/filings_parse.py sections data/filings/usaapl/2025-10-K.htm
python3 tools/filings_parse.py extract data/filings/usaapl/2025-10-K.htm --section mda
python3 tools/filings_parse.py diff data/filings/usaapl/2024-10-K.htm data/filings/usaapl/2025-10-K.htm --section risk

# 大师持仓跟踪（SEC 13F：伯克希尔/喜马拉雅，或任意机构 CIK）
python3 tools/masters_portfolio.py holdings berkshire
python3 tools/masters_portfolio.py diff berkshire                    # 最近两季新建仓/清仓/加减仓

# 财务质量三件套 + 凯利仓位
python3 tools/financial_rigor.py m-score --current '{...}' --prior '{...}'   # 盈余操纵初筛（两年数据）
python3 tools/financial_rigor.py altman-z --working-capital 3000 --retained-earnings 8000 --ebit 2300 --equity-value 28000 --total-liabilities 6000 --total-assets 16000
python3 tools/financial_rigor.py accruals --net-income 1941 --cfo 2200 --total-assets 16000
python3 tools/financial_rigor.py kelly --win-prob 0.6 --win 0.5 --loss 0.3

# 去劣 7 条硬指标一键打分（三市场批量）
python3 tools/quality_screen.py 600519 hk00700 usAAPL

# 组合层计算：集中度 / 相关性矩阵 / 加权预期回报 / 历史回撤模拟
python3 tools/portfolio_calc.py --holdings '[{"name":"腾讯","code":"hk00700","weight":0.3,"expected_return":0.12},{"name":"现金","code":"cash","weight":0.7,"expected_return":0.04}]' --drawdown

# 决策日志与复盘（研报级流程交付结论后自动追加；--benchmark 对比同期指数）
python3 tools/decision_log.py add --company 腾讯 --code hk00700 --skill investment-research --verdict 买入 --price 480 --currency HKD --reason "核心理由"
python3 tools/decision_log.py review --benchmark

# 观察清单：买卖区间维护 + 批量信号扫描 + 推送/定时
python3 tools/watchlist.py add --code hk00700 --name 腾讯 --buy-below 400
python3 tools/watchlist.py scan --notify        # 需 export WATCHLIST_WEBHOOK=<钉钉/飞书 webhook>
python3 tools/watchlist.py schedule --every 60  # 生成 launchd/cron 定时扫描配置（不自动安装）

# 公司档案库：已验证稳定事实跨会话复用（取数前先 get，研究后 set 归档）
python3 tools/company_facts.py get hk00700
python3 tools/company_facts.py set hk00700 --name 腾讯 --category financial --key "2025年营收" --value "6603亿CNY" --source "年报+东财双源验证"

# 环境一键自检（启动研究前可选）
python3 tools/doctor.py

# 报告图表 PNG 生成（可视化首选；matplotlib 缺失时退出码 1，自动降级 Mermaid）
python3 tools/chart_gen.py trend --title "营业收入趋势（亿元）" \
  --x '[2021,2022,2023,2024,2025]' --series '{"营收":[5601,5546,6090,6603,7200]}' \
  --ylabel 亿元 --output reports/腾讯/charts/revenue-trend.png

# 报告数据抽检（推荐文件化闭环：清单写入文件 → 填入核验值 → 从文件读入判决）
python3 tools/report_audit.py extract --report <报告路径> --output <报告目录>/audit-checklist.json
python3 tools/report_audit.py verdict --results-file <报告目录>/audit-checklist.json

# 报告导出单文件 HTML（图表内嵌，微信/邮件直接分享；浏览器打印可存 PDF）
python3 tools/report_export.py reports/腾讯/腾讯-investment-research-20260720.md
```

工具路径以**技能根目录**为基准（`tools/xxx.py`）。退出码统一语义：0=验证通过/准出，1=验证不通过/打回，2=参数错误。

**依赖安装**（通过根目录 `pyproject.toml` 统一管理）：
```bash
pip install .            # 核心依赖（akshare + yfinance）
pip install .[viz]       # + 图表生成（matplotlib）
pip install .[filings]   # + 财报 PDF 解析（pypdf，A股/港股年报章节抽取需要）
pip install .[scraper]   # + 雪球爬虫（playwright）
pip install .[all]       # 全部依赖
```

**各工具依赖明细**：
- `financial_rigor.py` / `report_audit.py` / `report_export.py` / `doctor.py` / `morningstar_fair_value.py` / `filings_fetch.py` / `masters_portfolio.py` / `decision_log.py` / `watchlist.py` / `portfolio_calc.py` / `company_facts.py`：零外部依赖（仅 Python ≥ 3.8 标准库；取数/探测类需网络与 `curl`）
- `filings_parse.py`：美股 HTML/TXT 零依赖；A股/港股 PDF 需可选 `pypdf`（`pip install .[filings]`），缺失时退出码 1 并提示降级路径
- `ashare_data.py` / `quality_screen.py`：推荐依赖 `akshare`（A股财务主源）+ `yfinance`（港美股财务主源），安装：`pip install akshare yfinance`；缺失时自动降级（A股→东财datacenter API，港美股→提示走网页双源）；行情/日K始终走腾讯接口（curl 直连）
- `chart_gen.py`：可选依赖 matplotlib（`pip install matplotlib`），缺失或损坏时退出码 1，图表整体降级为 Mermaid/表格方案，不影响其他功能
- `xueqiu_scraper.py`：需 `pip install playwright && playwright install chromium`，首次使用需交互式登录雪球（登录态缓存后可 headless 复用）；不适合在无交互环境首次运行
- `tests/`：工具层冒烟测试（全离线，`pip install .[dev] && python3 -m pytest tests/ -q`）
- `tools/experimental/`：动量实验工具，与四大师价值投资方法论无关，不被任何流程调用；其依赖的 `tools/experimental/data/fundamentals.json` 需手工维护，过期时工具会提示

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
A股/港股/美股及未上市公司。行情/市值三市场均有程序化通道（`ashare_data.py quote 600519 / hk00700 / usAAPL`）；财务数据 A股有接口通道，港美股走 WebSearch 双源验证；每个市场均有三级备用源轮换（见 `skills/financial-data/SKILL.md`）。

**Q: 数据是实时的吗？**
行情类数据带 15 分钟本地缓存、财务类 7 天（命中缓存时输出会标注抓取时间）；网络失败时自动回退过期缓存并标注 `[缓存数据]`。卖出决策等需强制实时场景会加 `--no-cache` 直连。

**Q: 报告里的图表是怎么生成的？**
三级方案：首选 `tools/chart_gen.py`（matplotlib）生成**出版级 PNG**（趋势/结构/对比/象限图，中文字体与数值标注完整）；matplotlib 缺失时自动降级为 Mermaid 代码块；渲染器不支持时再降级为符号/表格。链路图与时间线固定用 Mermaid（其强项）。图仅辅助阅读，数据以表格为准（规范见 `references/report-visuals.md`）。

**Q: 不做什么？**
不做短线择时、技术分析、加密货币预测、期权策略——与价值投资定位不符，会如实告知并建议替代。

## 核心原则

所有流程执行时都遵循 [`CLAUDE.md`](CLAUDE.md) 的客观性原则：先数据后结论、区分事实与推测、数据标注来源、诚实面对不确定性、正反两面、结论明确。
