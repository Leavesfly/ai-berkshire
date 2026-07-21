---
name: masters-portfolio
description: 大师持仓跟踪——解析伯克希尔（巴菲特）、喜马拉雅资本（李录）等机构的 SEC 13F 季度持仓与变动。当用户问"巴菲特最近买了什么"、"李录持仓"、"伯克希尔调仓"、"看看大师们在买什么"、"某机构13F"时使用。
type: executable
confirm_level: light
tools_required: [masters_portfolio.py]
depends_on: []
---

# 大师持仓跟踪：看聪明钱的方向，不抄聪明钱的作业

对 $ARGUMENTS 执行大师/机构 13F 持仓查询与解读。

> "通过观察巴菲特的每一笔投资去逆向理解他的思考，是最好的投资课。" —— 李录
>
> 13F 告诉你大师**买了什么**，永远不会告诉你**为什么买、打算拿多久、多少钱愿意卖**。

## 工具命令（数据全部走工具，禁止凭记忆报持仓）

```bash
# 最新一季持仓（按权重排序 + 前十集中度）
python3 tools/masters_portfolio.py holdings berkshire          # 巴菲特
python3 tools/masters_portfolio.py holdings himalaya           # 李录
python3 tools/masters_portfolio.py holdings <CIK> --top 30     # 任意机构

# 最近两季持仓变动（新建仓/清仓/加减仓，按 CUSIP 精确配对）
python3 tools/masters_portfolio.py diff berkshire

# 按名称找机构 CIK（英文注册名命中率更高）
python3 tools/masters_portfolio.py search Hillhouse
```

指定历史期次：`holdings berkshire --quarter 2025Q4`。

## 执行流程

### 意图识别

| 用户说 | 操作 |
|--------|------|
| "巴菲特最近买了什么" / "伯克希尔调仓了吗" | `diff berkshire` + 解读 |
| "李录/喜马拉雅现在持仓" | `holdings himalaya` + 解读 |
| "看看XX基金的13F" | `search` 找 CIK → `holdings` |
| "大师们都在买什么" | `diff berkshire` + `diff himalaya`，交叉比对共同动作 |

### 解读纪律（必须遵守）

1. **先声明数据边界**：13F 只覆盖美股多头，不含 A股/港股持仓（如李录的比亚迪 H 股不在 13F 里）、债券、现金与空头；披露滞后季末最多 45 天，看到时价格可能已大幅变化。
2. **新建仓 ≠ 买入信号**：只能作为研究线索。标准话术："{大师}新建仓了 {公司}，要不要深入研究一下？说'研究 {公司}'即可"——路由到 `investment-research`。
3. **清仓 ≠ 卖出信号**：必须提示两种可能（估值兑现 / 逻辑变化），13F 不披露卖出理由；用户持有同一标的时建议走 `thesis-drift` 复查自己的论文而不是跟卖。
4. **权重比名单重要**：解读时优先讲集中度与权重变化（大师的仓位=信心），一长串小仓位不值得展开。
5. **对话级快反产出，免抽检**；数字一律引用工具输出原值，禁止转述时改数。

### 与其他流程联动

- 新建仓/大幅加仓标的 → 建议 `investment-research` 深研
- 用户持仓与大师动作冲突 → 建议 `thesis-drift` 复查
- 想按季度持续跟踪 → 建议把关注机构写入用户备忘，每季 13F 窗口期（2/5/8/11 月中）主动扫一次 `diff`
