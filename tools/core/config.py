"""统一配置常量 — 零外部依赖。

集中管理各工具散落的魔法数字，避免多处维护。

用法：
    from core.config import CACHE_TTL_QUOTE, CURL_TIMEOUT

环境变量清单（全部可选，缺失时自动降级）：
    TICKFLOW_API_KEY      TickFlow 交叉验证源 API Key（ashare_data.py）
    EDGAR_UA              SEC EDGAR User-Agent（utils.py，默认 ai-berkshire-research-skill）
    WATCHLIST_WEBHOOK     观察清单信号推送 Webhook URL（watchlist.py）
    EASTMONEY_SEARCH_TOKEN 东方财富搜索 Token（ashare_data.py，内置默认值）
"""

# ---------------------------------------------------------------------------
# 缓存 TTL（秒）
# ---------------------------------------------------------------------------

CACHE_TTL_QUOTE = 15 * 60  # 行情类：15 分钟
CACHE_TTL_FINANCIALS = 7 * 86400  # 财务类：7 天
CACHE_TTL_KLINE = 86400  # 日K线：1 天

# ---------------------------------------------------------------------------
# 网络请求
# ---------------------------------------------------------------------------

CURL_TIMEOUT = 15  # 单次请求超时（秒）
CURL_RETRIES = 1  # 失败后重试次数
CURL_RETRY_WAIT = 2  # 重试间隔（秒）

# ---------------------------------------------------------------------------
# 环境自检（doctor.py）
# ---------------------------------------------------------------------------

PROBE_TIMEOUT = 8  # 域名探测超时（秒）

# ---------------------------------------------------------------------------
# 数据源 URL（各工具共用的基础地址）
# ---------------------------------------------------------------------------

# 腾讯行情（A股/港股/美股实时报价 + 日K线）
QQ_QUOTE_URL = "https://qt.gtimg.cn/q={code}"
QQ_KLINE_URL = "https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param={code},day,,,{days},qfq"

# 东方财富（A股搜索 + 财务数据降级源 + 港股公告）
EASTMONEY_SEARCH_URL = "https://searchadapter.eastmoney.com/api/suggest/get"
EASTMONEY_DATACENTER_URL = "https://datacenter.eastmoney.com/securities/api/data/get"
EASTMONEY_HK_ANN_URL = "https://np-anotice-stock.eastmoney.com/api/security/ann?"

# SEC EDGAR（美股财报原文 + 13F 持仓）
EDGAR_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
EDGAR_SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik}.json"
EDGAR_ARCHIVES_URL = "https://www.sec.gov/Archives/edgar/data/{cik}/{accession}/{file}"
EDGAR_BROWSE_URL = "https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&company="

# 巨潮资讯（A股财报原文）
CNINFO_SEARCH_URL = "http://www.cninfo.com.cn/new/information/topSearch/query"
CNINFO_ANN_URL = "http://www.cninfo.com.cn/new/hisAnnouncement/query"
CNINFO_STATIC_URL = "http://static.cninfo.com.cn/"

# Morningstar（公允价值参考）
MORNINGSTAR_SCREENER_URL = "https://lt.morningstar.com/api/rest.svc/klr5zyak8x/security/screener"
