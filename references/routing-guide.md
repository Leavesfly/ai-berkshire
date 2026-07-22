# 路由消歧指南（供入口路由参考）

本文件是根 `SKILL.md` 路由表的补充参考。当用户意图落在多个子流程之间时，按以下规则处理。

## 消歧规则

1. **研究深度**：想要"快速判断" → `investment-research`；想要"深度并行团队" → `investment-team`。不确定时反问一句。
2. **单公司 vs 行业**：明确了公司名 → 个股类；只给了赛道/方向 → 行业类。
3. **上市 vs 未上市**：目标是蚂蚁、SpaceX 等未上市公司 → 强制走 `private-company-research`。
4. **研究 vs 内容**：目标是"做投资决策" → 研究类；目标是"发文章" → 内容创作类。
5. **持仓 vs 新标的**：用户已持有并问"要不要继续拿" → 决策监控类（`thesis-tracker` / `thesis-drift` / `news-pulse`）；问"要不要卖/卖多少" → `exit-review`。
6. **三种"筛选"的区分**：已有候选名单要过滤去劣 → `quality-screen`；给定行业要选出最优几家 → `industry-funnel`；从超级趋势找被忽视的供应链标的 → `bottleneck-hunter`。
7. **对比 vs 筛选**：用户给出 2-4 家要"哪个好/对比" → `quality-screen`（对比模式）；给出行业要"选出最好的" → `industry-funnel`。
8. **估值疑问 vs 完整研究**：用户只问"贵不贵/是不是泡沫/值多少" → `investment-research`（侧重估值模块）；问"值不值得买/全面研究" → `investment-research`（完整流程）。
9. **看空 vs 异动归因**：想要"做空理由/反驳论点/压力测试" → `red-team`（对论点的攻击性研究）；问"为什么跌了" → `news-pulse`（对已发生异动的归因）。
10. **两种"值得关注"**：用户已有观察清单/持仓，问"今天有什么值得关注/晨报" → `morning-brief`（关注面信号扫描）；无任何关注标的，问"最近有什么机会/研究什么好" → 引导式转 `industry-funnel`（找新标的）。
11. **两种"复盘"**：问"之前的判断对了吗/胜率" → `track-record`（逐条决策复盘）；问"系统有什么偏差/校准一下/优化原则" → `self-review`（系统性诊断 + 规则修改建议）。

## 易混淆案例对照（路由前先过一遍）

| 用户说 | 容易误判为 | 应路由到 | 判据 |
|--------|-----------|----------|------|
| "腾讯这季财报怎么样，能买吗" | `earnings-review` | 先反问：只读财报还是要买入结论？ | 同时命中财报+买入两个意图 |
| "帮我看看新能源车哪家好" | `industry-research` | `industry-funnel` | 目标是"选出好公司"不是"看懂行业" |
| "比亚迪跌了很多，要不要抓住机会" | `news-pulse` | 先问是否已持仓：未持仓→`investment-research`；已持仓想加仓→`thesis-tracker` | "跌"只是背景，真意图是买入判断 |
| "巴菲特为什么买西方石油" | `investment-research` | `masters-portfolio`（持仓事实）+ 可衔接研究 | 先用 13F 确认持仓事实，动机只能推测不能编造 |
| "给我分析一下宁德时代的管理层" | `investment-research` | `management-deep-dive` | 明确限定了管理层维度 |
| "写一篇分析英伟达的文章发公众号" | `investment-research` | `wechat-article` | 产出物是文章不是决策 |
| "帮我看看小红书" | `investment-research` | `private-company-research` | 未上市公司强制路由 |
| "段永平会买拼多多吗" | `investment-research` | `dyp-ask` | 要的是段式视角回答，不是完整研报 |
| "腾讯和阿里哪个好" | `investment-research` | `quality-screen`（对比模式） | 多标的对比，不是单标的深研 |
| "茅台是不是泡沫" | `news-pulse` | `investment-research`（估值侧重） | 问的是估值判断，不是异动归因 |
| "英伟达有什么致命弱点" | `investment-research` | `red-team` | 要的是攻击性做空研究，不是平衡分析 |
| "今天有什么值得关注的" | 引导到行业筛选 | 先查观察清单/决策日志：有关注标的→`morning-brief`；皆空→引导式 | 晨报需要关注面，无标的时才找新机会 |
| "我们的判断是不是总是太乐观" | `track-record` | `self-review` | 问的是系统性偏差，不是单次决策对错 |
| "这只票能拿多久" | `exit-review` | `thesis-tracker` | 问持有期跟踪，不是卖出决策 |
| "我手上有 10 万块买什么好" | 无法路由 | 引导：先问行业偏好 → `industry-funnel` | 缺少标的，需先缩窄范围 |
| "帮我对比一下腾讯美团比亚迪" | `investment-research` | `quality-screen`（对比模式） | 多标的横向对比 |

## 口语化触发词映射（扩展）

以下口语表达在路由时等价于对应意图关键词：

| 口语表达 | 等价意图 | 路由到 |
|---------|---------|--------|
| 能不能抄底 / 能不能买 / 现在能入吗 | 买入判断 | `investment-research` |
| 要不要割肉 / 该不该跑 / 止损吗 | 卖出决策 | `exit-review` |
| 有没有雷 / 会不会暴雷 / 财务有没有问题 | 风险排查 | `quality-screen` 或 `earnings-review` |
| 帮我盯一下 / 盯着点 / 有异动告诉我 | 持有监控 | 已建论文→`thesis-tracker`；只要价格提醒→`watchlist-monitor` |
| 跌到多少提醒我 / 到价告诉我 / 自选股怎么样 | 观察清单 | `watchlist-monitor` |
| 之前的判断对了吗 / 复盘一下 / 胜率如何 | 决策复盘 | `track-record` |
| 是不是泡沫 / 贵不贵 / 值多少 | 估值判断 | `investment-research`（估值侧重） |
| 能拿多久 / 拿得住吗 / 长期持有行不行 | 持有期跟踪 | `thesis-tracker` |
| 哪个好 / 对比一下 / PK 一下 | 多标的对比 | `quality-screen`（对比模式） |
| 最近发生了什么 / 出什么事了 | 异动归因 | `news-pulse` |
| 巴菲特买了什么 / 伯克希尔调仓 / 李录持仓 / 看看大师在买什么 | 大师持仓跟踪 | `masters-portfolio` |
| 某机构 13F / 机构持仓 | 大师持仓跟踪 | `masters-portfolio` |
| 逻辑变了吗 / 还能信吗 | 论文漂移 | `thesis-drift` |
| 管理层靠谱吗 / CEO 怎么样 | 管理层评估 | `management-deep-dive` |
| 做空理由 / 致命弱点 / 反驳一下 / 当一回空头 | 压力测试 | `red-team` |
| 晨报 / 今天有什么值得关注 / 帮我盯盘 / 扫一遍关注面 | 信号融合 | `morning-brief` |
| 系统自检 / 校准一下 / 是不是太乐观 / 优化原则 | 系统自审 | `self-review` |
| 帮我看看 / 这只票怎么样 | 模糊（需澄清） | 按模糊兜底反问 |
