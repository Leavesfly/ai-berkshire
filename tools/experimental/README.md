# tools/experimental/ — 实验性脚本暂存区

本目录存放**尚未毕业**的实验性工具脚本。

## 准入/毕业标准

| 状态 | 条件 |
|------|------|
| **准入** | 有明确实验目标；代码可运行但可能不稳定 |
| **毕业** → 移入 `tools/` | 连续使用 ≥3 次无重大问题；补充 docstring + 退出码约定；通过 ruff check |
| **废弃** → 删除 | 超过 60 天未使用；或被正式工具替代 |

## 当前文件状态

| 文件 | 状态 | 说明 |
|------|------|------|
| `momentum_backtest_v2.py` | 实验 | 动量回测 v2（增加交易成本与基准对比） |
| `stock_screener.py` | 实验 | 多因子选股器（与 quality_screen.py 有重叠，待整合） |
| `xueqiu_scraper.py` | 实验（可选） | 雪球大 V 观点抓取（依赖 playwright）；news-pulse 可选调用，失败时跳过不阻断 |

## 注意事项

- 实验脚本**不受 CI 保护**（ruff/pytest 不覆盖本目录）
- 实验脚本内的 `data/` 子目录为本地测试数据，不入库
- 毕业时须移除对 `tools/experimental/data/` 的硬依赖
