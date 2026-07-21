# 数据验证步骤模板

本文件定义 `tools/financial_rigor.py` 标准验证步骤的通用模板。各子流程在数据收集后引用本模板执行验证，仅需补充流程特有的参数说明。

> 完整子命令语法与容差分档见 [`skills/financial-data/references/verification-playbook.md`](../skills/financial-data/references/verification-playbook.md)。

## 核心原则

- 涉及金额、市值、估值的计算**必须调用工具**，禁止心算
- 每个关键数据点至少 2 个独立来源
- 工具输出结果直接嵌入报告附录「关键数据交叉验证记录」
- 工具报告 ❌ 偏差过大时，必须排查原因后才能继续分析

## 标准验证三步

### Step 1 — 市值验算（精确十进制）

```bash
python3 tools/financial_rigor.py verify-market-cap \
  --price {股价} --shares {总股本} --reported {报告市值} --currency {币种}
```

**目的**：防止单位错误（港币亿 vs 人民币亿 vs 美元亿，容易漏写/多写一个零）。

### Step 2 — 关键数据多源交叉验证

```bash
python3 tools/financial_rigor.py cross-validate \
  --field {字段名} --values '{"来源1": 数值, "来源2": 数值}' --unit {单位}
```

对收入、净利润、现金储备分别执行。

### Step 3 — 估值指标精确验算

```bash
python3 tools/financial_rigor.py verify-valuation \
  --price {股价} --eps {EPS} --bvps {每股净资产} --fcf-per-share {每股FCF} --dividend {每股股息}
```

输出 PE/PB/ROE/股息率/FCF Yield 等指标精确值。

## 必须验证的数据点

| 数据点 | 验证方式 | 常见陷阱 |
|--------|---------|---------|
| 总股本 | 至少 2 源确认 | AB股结构下经济权益 ≠ 投票权 |
| 当前股价和市值 | verify-market-cap | 单位错误（亿 vs 万亿） |
| 最近财年收入和净利润 | cross-validate | GAAP vs Non-GAAP 口径 |
| 现金储备和净现金 | cross-validate | 是否含短期投资、债务口径差异 |
| 管理层持股比例 | 区分经济权益/投票权 | AB股公司需分别标注 |

## 扩展验证（按需叠加）

| 场景 | 命令 | 适用流程 |
|------|------|---------|
| 三情景估值 | `three-scenario` | investment-research / exit-review |
| 反向 DCF | `reverse-dcf` | investment-research / watchlist-monitor |
| 估值历史分位 | `valuation-percentile` | investment-research |
| 同业对标 | `peer-compare` | investment-research / quality-screen |
| DCF 敏感性矩阵 | `dcf-matrix` | investment-research |
| 盈余操纵初筛 | `m-score` | earnings-review / quality-screen |
| 财务困境风险 | `altman-z` | earnings-review / quality-screen |
| 利润含金量 | `accruals` | earnings-review |
| 凯利仓位 | `kelly` | portfolio-review / investment-checklist |

## 常见错误防范

- **市值单位**：港币亿 vs 人民币亿 vs 美元亿，容易漏写/多写一个零
- **FCF 口径**：不同来源对资本支出的定义可能不同（是否含租赁、收购等）
- **债务口径**：是否包含经营租赁负债
- **持股比例**：AB股公司的经济权益 ≠ 投票权
- **财年定义**：自然年 vs 财年（如苹果财年 10 月结束）
