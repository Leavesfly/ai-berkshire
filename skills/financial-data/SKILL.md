---
name: financial-data
description: 财务数据获取与交叉验证规范——所有涉及企业财务数据的研究均需遵循的数据源优先级与双源交叉验证标准（每个关键数据必须来自两个独立来源，误差>1%须标记）。当需要获取美股/港股/A股财务数据、核实财务数字、或确定可靠数据源时参考。本规范被其他多个投研技能引用。
type: shared-spec
confirm_level: light
tools_required: [ashare_data.py, financial_rigor.py, report_audit.py]
depends_on: []
---

# 财务数据获取与交叉验证规范

本规范适用于所有涉及企业财务数据的研究。**每个关键数据必须来自两个独立来源，误差>1%须标记。**

> 验证工具（`tools/financial_rigor.py` / `tools/report_audit.py`）的**权威调用语法与容差分档**见 [`references/verification-playbook.md`](references/verification-playbook.md)，各子流程命令示例与其冲突时以该文件为准。

---

## 数据源优先级

### 美股（PDD、腾讯ADR、网易ADR等）

| 优先级 | 来源 | URL | 获取方式 |
|--------|------|-----|--------|
| 0（程序化，行情+财务） | **tools/ashare_data.py** | — | `python3 tools/ashare_data.py quote us{代码}` 行情；`python3 tools/ashare_data.py financials us{代码}` 财务（yfinance 源，含近4年利润表/毛利率/净利率/ROE） |
| 1（主） | **macrotrends** | macrotrends.net/stocks/charts/{ticker} | 直接访问，无需注册 |
| 2（副） | **stockanalysis** | stockanalysis.com/stocks/{ticker}/financials | 直接访问，无需注册 |
| 3（备3） | **wsj** | wsj.com/market-data/quotes/{ticker}/financials | 直接访问，主/副源不可用时启用 |
| 原始一手 | SEC EDGAR | sec.gov/cgi-bin/browse-edgar | 10-K / 10-Q 原文 |

轮换顺序：0(yfinance) → 1 → 2 → 3 → SEC 原文；任一源不可访问时顺序启用下一个，始终保持两个独立来源。

### 港股（腾讯0700、网易9999、美团3690等）

| 优先级 | 来源 | URL | 获取方式 |
|--------|------|-----|--------|
| 0（程序化，行情+财务） | **tools/ashare_data.py** | — | `python3 tools/ashare_data.py quote hk{5位代码}` 行情；`python3 tools/ashare_data.py financials hk{5位代码}` 财务（yfinance 源，含近4年利润表/毛利率/ROE） |
| 1（主） | **aastocks** | aastocks.com/tc/stocks/analysis/company-fundamental | 直接访问 |
| 2（副） | **macrotrends**（ADR代码） | 腾讯用TCEHY，网易用NTES | 直接访问 |
| 3（备3） | **富途牛牛** | futunn.com/stock/{代码}-HK | 直接访问，主/副源不可用时启用 |
| 原始一手 | HKEX披露易 | hkexnews.hk | 年报PDF |

轮换顺序：0(yfinance) → 1 → 2 → 3 → 披露易原文。

### A股（三七互娱、吉比特等）

| 优先级 | 来源 | URL | 获取方式 |
|--------|------|-----|--------|
| 0（程序化，行情+财务） | **tools/ashare_data.py** | — | `python3 tools/ashare_data.py financials/quote/search {代码}`；行情走腾讯 qt.gtimg.cn，财务走 akshare/同花顺源（含近5年营收/净利润/毛利率/净利率/ROE/资产负债率），失败时自动回退东财 datacenter API |
| 1（主） | **东方财富** | eastmoney.com → 搜股票代码 → 财务报表 | 直接访问 |
| 2（副） | **巨潮资讯** | cninfo.com.cn | 原始年报/季报PDF |
| 3（备3） | **新浪财经** | finance.sina.com.cn → 搜股票代码 → 财务数据 | 直接访问，前两源不可用时启用 |

轮换顺序：0(akshare/THS) → 东财datacenter → 1 → 2 → 3。

### TickFlow 交叉验证（自动，需 API Key）

设置环境变量 `TICKFLOW_API_KEY` 后，`ashare_data.py financials` 命令会自动调用 TickFlow `/v1/financials/metrics` 接口获取最新一期核心指标（ROE/毛利率/净利率/EPS/资产负债率），并与主源数据自动对比，输出差异标记（≤1% ✅ / 1-5% ⚠️ / >5% ❌）。

- **未设置 API Key**：静默跳过，不影响主源取数
- **有 API Key**：自动执行，输出附在财务数据末尾，可直接作为双源验证记录
- 覆盖市场：A股/港股/美股（与主源一致）

---

## 执行规范

### 第一步：获取数据

对每个财务指标（收入、净利润、毛利率、经营现金流、资产负债率等），分别从**来源1**和**来源2**取数。

### 第二步：误差计算与标记

```
误差率 = |来源1数值 - 来源2数值| / 来源1数值 × 100%
```

| 误差 | 处理方式 |
|------|---------|
| ≤ 1% | ✅ 一致，取来源1数值，标注两个来源 |
| 1% ~ 5% | ⚠️ 标记"数据存在差异"，注明两个数值，说明可能原因（汇率/会计口径） |
| > 5% | ❌ 标记"数据存在重大差异"，必须查原始财报核实，不得直接使用 |

### 第三步：数据呈现格式

每个关键数据必须按以下格式标注：

```
收入：1,239亿元 ✅
  - macrotrends: 1,241亿元
  - stockanalysis: 1,237亿元
  - 误差: 0.3%
```

差异示例：
```
净利润：245亿元 ⚠️ 数据存在差异
  - macrotrends: 245亿元（GAAP）
  - stockanalysis: 278亿元（Non-GAAP）
  - 误差: 13.5% — 原因：会计口径不同（GAAP vs Non-GAAP）
```

---

## 网络取数稳定性规则

单次取数失败不中断研究，按以下阶梯降级：

1. 程序化接口失败（ashare_data.py）→ 自动回退内置降级源（A股: akshare→东财API；港美股: yfinance→报错提示走网页）；
2. 单源 WebFetch 失败 → 换 URL（如同站另一页面）重试 1 次；
3. 仍失败 → 按上方轮换顺序启用下一优先级来源；
4. 连续 3 个源失败 → 转 WebSearch 摘要取数，数据标注“仅搜索摘要来源，置信度降级”；
5. 全部失败 → 写“数据不足”，不用推测填补（CLAUDE.md 客观性原则 4）。

无论降级到哪一级，**双源交叉验证要求不变**；只剩单源可用时，数据前标记 `[单源未验证]`（处理方式参照下方未上市公司的单源规则）。

---

## 缓存规则（ashare_data.py 自动维护）

`tools/ashare_data.py` 取数成功后自动写入 `data/cache/`，三级取数：TTL 内缓存 → 网络（成功回写）→ 过期缓存兜底：

| 数据类型 | TTL | 过期后 |
|---------|-----|--------|
| 行情（quote/valuation） | 15 分钟 | 重新取数；网络失败时回退过期缓存 |
| 财务（financials） | 7 天 | 同上 |

- 输出中带 `[缓存数据 抓取于YYYY-MM-DD HH:MM]` 标注时，表示该数据非实时：**TTL内复用**可直接使用；**网络失败回退**的过期缓存仅作参考，报告中须同步标注抓取时间，且不得用于“当前股价/市值”等时效性结论。
- 需强制实时数据（如 exit-review 的卖出决策）时加 `--no-cache` 直连。
- 缓存目录可随时删除重建，不入 git（已在 `.gitignore`）。

---

## 数据复用规则（避免重复取数）

1. **会话内复用**：同一次研究中已完成双源验证的数据点，记入报告附录「关键数据交叉验证记录」后直接复用，**禁止对同一数据点重复取数**。
2. **多 Agent 流程**：team-lead 在任务分派时把已验证数据（股价/市值/总股本/核心财务指标）随 prompt 下发，各 Agent 优先复用，仅对自己维度特有的数据另行取数。
3. **跨流程复用**：下游技能（thesis-tracker / exit-review 等）优先读取上游报告附录中的已验证数据；仅对时效性数据（股价、市值、最新一期财报）重新取数，历史财务数据直接复用并标注“沿用 {上游报告路径} 已验证数据”。

---

## 常见差异原因（不一定是数据错误）

| 原因 | 说明 |
|------|------|
| GAAP vs Non-GAAP | 最常见，尤其是利润类数据 |
| 汇率换算 | 港币/人民币/美元换算时间点不同 |
| 财年定义 | 自然年 vs 财年（如苹果财年10月结束） |
| 合并口径 | 是否含少数股东权益 |
| 数据更新滞后 | 某平台尚未更新最新一期财报 |

---

## 特别规则

1. **未上市公司**（米哈游、莉莉丝等）：只有一手数据来源时，数据前标记 `[估计]`，不执行交叉验证
2. **季度数据 vs 年度数据**：优先使用年度数据做交叉验证，季度数据部分来源可能有滞后
3. **原始财报优先**：若两个来源均与原始财报（10-K/年报PDF）不符，以原始财报为准，标记来源错误

---

## 快速索引

| 场景 | 主要来源 | 备用来源 |
|------|---------|---------|
| PDD / 拼多多 | macrotrends.net/stocks/charts/PDD | stockanalysis.com/stocks/pdd |
| 腾讯 | macrotrends.net/stocks/charts/TCEHY | aastocks（0700.HK） |
| 网易 | macrotrends.net/stocks/charts/NTES | aastocks（9999.HK） |
| 三七互娱 | eastmoney.com（002555） | cninfo.com.cn |
| 吉比特 | eastmoney.com（603444） | cninfo.com.cn |
| Nintendo | macrotrends.net/stocks/charts/NTDOY | stockanalysis.com/stocks/ntdoy |
| Capcom | macrotrends（CCOEY） | stockanalysis（CCOEY） |
