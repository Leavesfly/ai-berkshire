---
name: watchlist-monitor
description: 观察清单监控——维护关注标的的买卖区间并批量扫描触发信号。当用户想"盯一下这几只股票"、"跌到多少提醒我"、"扫一遍观察清单"、"我的自选股怎么样了"时使用。
---

# 观察清单监控：把"问才动"变成"主动盯"

对 $ARGUMENTS 执行观察清单操作（添加/移除/查看/扫描）。

> 巴菲特的做法：先研究透一家好公司，算出愿意支付的价格，然后**耐心等价格进入区间**。
> 本流程就是那张"等待清单"——标的与价格区间来自上游研究，扫描只做纪律性提醒。

## 工具命令（全部操作走工具，禁止手工编辑后不校验）

```bash
# 添加/更新（区间可只设一边；note 记论文红线）
python3 tools/watchlist.py add --code hk00700 --name 腾讯 --buy-below 400 --sell-above 700 --note "红线：游戏流水连续两季下滑"

# 查看 / 移除
python3 tools/watchlist.py list
python3 tools/watchlist.py remove --code hk00700

# 批量扫描（默认15分钟行情缓存；盘中决策场景加 --no-cache）
python3 tools/watchlist.py scan

# 有触发信号时推送到钉钉/飞书（需先 export WATCHLIST_WEBHOOK=<机器人地址>）
python3 tools/watchlist.py scan --notify

# 生成定时扫描配置（launchd/cron，只生成不安装，安装命令由用户自行执行）
python3 tools/watchlist.py schedule --every 60
```

扫描信号：🟢 进入买入区 / 🔴 触发卖出关注 / 📉 接近52周低点 / ⚡ 单日异动 ≥5%。

## 执行流程

### 意图识别

| 用户说 | 操作 |
|--------|------|
| "盯一下腾讯，跌到400以下告诉我" | `add`（补齐 code；用户没给价格则先问，或建议走研究流程定价） |
| "把美团从清单里去掉" | `remove` |
| "我的观察清单/自选股怎么样了" | `scan` + 解读 |
| "扫一遍清单" | `scan` + 解读 |

### 关键纪律

1. **买入区间必须有出处**：用户未给出 `--buy-below` 时，不允许拍脑袋填数。两个合规来源：
   - 上游研究报告的估值结论（`reports/{公司名}/` 下最新报告的目标价/安全边际价）；
   - 现场快速估值：`financial_rigor.py reverse-dcf` / `three-scenario` 推导后与用户确认。
2. **扫描后必须解读**：不止列信号，对每个触发标的给一句"下一步"：
   - 🟢 进入买入区 → "要现在核对买入清单吗？（investment-checklist）"
   - 🔴 卖出关注 / ⚡ 异动 → exit-review / news-pulse
   - 📉 接近52周低点 → 先确认是机会还是基本面恶化（可转 thesis-drift）
3. **与决策链路联动**：`investment-research` / `investment-checklist` 给出"观望+理想买点"结论时，主动提议"要不要把 {公司} 加入观察清单，跌到 {价格} 提醒你"。
4. **输出轻量**：本流程为对话级快反产出，免抽检；价格全部来自工具输出，禁止转述时改数。

### 定期巡检建议

用户问"多久扫一次"时的建议：持有期标的每周一次 + 财报季加密；等待买点的标的可以更频繁。本技能不驻留后台，由用户说"扫一遍清单"触发；想要无人值守监控时，用 `schedule` 命令生成定时任务配置（配合 `--notify` 推送，需用户自行执行安装命令并配置 webhook）。
