#!/usr/bin/env python3
"""AI Berkshire 环境自检工具 — 一键检查取数与验算链路是否就绪。

在启动研究流程（尤其多 Agent 类子流程）前运行，快速判断当前环境哪些能力
可用、哪些需要降级，替代根 SKILL.md「执行环境自检」节的手工核对。

检查项：
    1. Python 版本 >= 3.8
    2. curl 可用（ashare_data.py 取数依赖）
    3. 关键数据源域名连通性（腾讯行情 / 东方财富 / macrotrends / SEC EDGAR）
    4. 核心工具脚本可编译（含财报管道/决策日志/观察清单/筛选/组合计算等全量工具）
    5. 数据库依赖可用（akshare: A股财务 / yfinance: 港美股财务）
    6. matplotlib 可用（图表首选方案；缺失时图表降级 Mermaid/表格，不影响结论）
    7. reports/ 目录可写（报告落盘前提）

用法：
    python3 tools/doctor.py

退出码：0=全部就绪 / 1=存在降级项（对照输出中的降级建议执行）。
单个域名探测超时 8 秒，全程通常 <30 秒。
"""

import os
import py_compile
import subprocess
import sys
import tempfile

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_PROBE_TIMEOUT = 8

# (检查项, 通过时说明, 失败时降级建议)
_CORE_TOOLS = [
    "financial_rigor.py",
    "report_audit.py",
    "report_export.py",
    "ashare_data.py",
    "chart_gen.py",
    "morningstar_fair_value.py",
    "filings_fetch.py",
    "filings_parse.py",
    "masters_portfolio.py",
    "decision_log.py",
    "watchlist.py",
    "quality_screen.py",
    "portfolio_calc.py",
    "company_facts.py",
]

_PROBE_URLS = [
    ("腾讯行情 qt.gtimg.cn", "https://qt.gtimg.cn/q=sh600519",
     "A股/港股/美股程序化行情不可用 → 走网页源（东财/aastocks/macrotrends）"),
    ("东方财富 eastmoney.com", "https://datacenter.eastmoney.com/",
     "A股财务接口不可用 → 走巨潮/新浪网页源或过期缓存"),
    ("macrotrends.net", "https://macrotrends.net/",
     "美股主源不可用 → 换 stockanalysis/wsj，见 financial-data 轮换顺序"),
    ("SEC EDGAR sec.gov", "https://www.sec.gov/files/company_tickers.json",
     "美股财报原文管道不可用 → filings_fetch 降级 WebSearch「公司名 + 10-K」"),
]


def _check_python():
    ok = sys.version_info >= (3, 8)
    detail = f"Python {sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    advice = "升级到 Python >= 3.8，否则 tools/ 全部不可用 → 验算降级为双源人工比对"
    return ok, detail, advice


def _check_curl():
    try:
        r = subprocess.run(["/usr/bin/curl", "--version"],
                           capture_output=True, timeout=5)
        ok = r.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        ok = False
    advice = "curl 缺失 → ashare_data.py/morningstar 取数不可用，改走 WebFetch 网页源"
    return ok, "/usr/bin/curl", advice


def _probe_url(url):
    """HEAD 探测域名连通性（跟随跳转，只看能否建立响应）。"""
    try:
        r = subprocess.run(
            ["/usr/bin/curl", "-s", "-o", "/dev/null", "-w", "%{http_code}",
             "--noproxy", "*", "-m", str(_PROBE_TIMEOUT), "-I", "-L",
             "-H", "User-Agent: Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)",
             url],
            capture_output=True, timeout=_PROBE_TIMEOUT + 4,
        )
        code = r.stdout.decode().strip()
        # 任何 HTTP 响应（含 403/405，说明网络通、仅方法受限）都算连通
        return r.returncode == 0 and code.isdigit() and int(code) < 500
    except (OSError, subprocess.TimeoutExpired):
        return False


def _check_tool_compile(name):
    path = os.path.join(_ROOT, "tools", name)
    if not os.path.exists(path):
        return False, f"tools/{name} 缺失", "从仓库恢复该文件，或对应验算环节降级为人工比对"
    try:
        py_compile.compile(path, doraise=True)
        return True, f"tools/{name}", ""
    except py_compile.PyCompileError as e:
        return False, f"tools/{name} 编译失败: {e.msg.splitlines()[0]}", "修复语法错误后重跑自检"


def _check_akshare():
    """检查 akshare 可用性（A股财务数据主源）。"""
    try:
        r = subprocess.run(
            [sys.executable, "-c", "import akshare; print(akshare.__version__)"],
            capture_output=True, timeout=30,
        )
        if r.returncode == 0:
            return True, f"akshare {r.stdout.decode().strip()}", ""
    except (OSError, subprocess.TimeoutExpired):
        pass
    advice = "A股财务降级为东财datacenter API（curl）；安装：pip install akshare"
    return False, "", advice


def _check_yfinance():
    """检查 yfinance 可用性（港股/美股财务数据主源）。"""
    try:
        r = subprocess.run(
            [sys.executable, "-c", "import yfinance; print(yfinance.__version__)"],
            capture_output=True, timeout=30,
        )
        if r.returncode == 0:
            return True, f"yfinance {r.stdout.decode().strip()}", ""
    except (OSError, subprocess.TimeoutExpired):
        pass
    advice = "港美股财务降级为网页双源验证（macrotrends/stockanalysis/aastocks）；安装：pip install yfinance"
    return False, "", advice


def _check_tickflow():
    """检查 tickflow 可用性（财务数据交叉验证源）。"""
    try:
        r = subprocess.run(
            [sys.executable, "-c", "import tickflow; print(tickflow.__version__)"],
            capture_output=True, timeout=30,
        )
        if r.returncode == 0:
            ver = r.stdout.decode().strip()
            has_key = bool(os.environ.get("TICKFLOW_API_KEY", ""))
            detail = f"tickflow {ver}" + (" | API Key ✅" if has_key else " | API Key 未设置（交叉验证不可用）")
            return True, detail, ""
    except (OSError, subprocess.TimeoutExpired):
        pass
    advice = "财务交叉验证不可用（不影响主源取数）；安装：pip install tickflow，并设置 TICKFLOW_API_KEY"
    return False, "", advice


def _check_matplotlib():
    """检查 matplotlib 可用性（图表首选方案）；导入损坏也视为不可用。"""
    try:
        r = subprocess.run(
            [sys.executable, "-c", "import matplotlib; print(matplotlib.__version__)"],
            capture_output=True, timeout=30,
        )
        if r.returncode == 0:
            return True, f"matplotlib {r.stdout.decode().strip()}", ""
    except (OSError, subprocess.TimeoutExpired):
        pass
    advice = "图表降级为 Mermaid/表格方案（不影响结论）；启用首选 PNG：pip install matplotlib"
    return False, "", advice


def _check_pypdf():
    """检查 pypdf 可用性（A股/港股年报 PDF 章节抽取；美股 HTML 不依赖）。"""
    try:
        r = subprocess.run(
            [sys.executable, "-c", "import pypdf; print(pypdf.__version__)"],
            capture_output=True, timeout=30,
        )
        if r.returncode == 0:
            return True, f"pypdf {r.stdout.decode().strip()}", ""
    except (OSError, subprocess.TimeoutExpired):
        pass
    advice = "PDF 财报章节抽取不可用（美股 HTML 不受影响）；安装：pip install pypdf"
    return False, "", advice


def _check_reports_writable():
    reports = os.path.join(_ROOT, "reports")
    try:
        os.makedirs(reports, exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=reports, prefix=".doctor-", delete=True):
            pass
        return True, "reports/ 可写", ""
    except OSError as e:
        return False, f"reports/ 不可写: {e}", "检查目录权限；仍失败则报告输出到对话中"


def main():
    print("=" * 66)
    print("AI Berkshire 环境自检 (doctor)")
    print("=" * 66)

    rows = []  # (状态, 检查项, 说明/降级建议)
    degraded = False

    ok, detail, advice = _check_python()
    rows.append(("✅" if ok else "❌", "Python >= 3.8", detail if ok else f"{detail} → {advice}"))
    degraded |= not ok

    ok, detail, advice = _check_curl()
    rows.append(("✅" if ok else "❌", "curl 可用", detail if ok else advice))
    curl_ok = ok
    degraded |= not ok

    for label, url, advice in _PROBE_URLS:
        if not curl_ok:
            rows.append(("⚠️", f"连通性: {label}", "curl 缺失，跳过探测 → " + advice))
            degraded = True
            continue
        ok = _probe_url(url)
        rows.append(("✅" if ok else "⚠️", f"连通性: {label}", "可达" if ok else advice))
        degraded |= not ok

    for name in _CORE_TOOLS:
        ok, detail, advice = _check_tool_compile(name)
        rows.append(("✅" if ok else "❌", f"工具编译: {name}", detail if ok else f"{detail} → {advice}"))
        degraded |= not ok

    ok, detail, advice = _check_akshare()
    rows.append(("✅" if ok else "⚠️", "akshare（A股财务主源）", detail if ok else advice))
    degraded |= not ok

    ok, detail, advice = _check_yfinance()
    rows.append(("✅" if ok else "⚠️", "yfinance（港美股财务主源）", detail if ok else advice))
    degraded |= not ok

    ok, detail, advice = _check_tickflow()
    rows.append(("✅" if ok else "⚠️", "tickflow（财务交叉验证）", detail if ok else advice))
    # tickflow 缺失不算降级（仅影响交叉验证，不影响主源取数）

    ok, detail, advice = _check_matplotlib()
    rows.append(("✅" if ok else "⚠️", "matplotlib（图表首选方案）", detail if ok else advice))
    degraded |= not ok

    ok, detail, advice = _check_pypdf()
    rows.append(("✅" if ok else "⚠️", "pypdf（PDF财报章节抽取）", detail if ok else advice))
    # pypdf 缺失不算降级（仅影响 A股/港股 PDF 解析，美股 HTML 与其他链路不受影响）

    ok, detail, advice = _check_reports_writable()
    rows.append(("✅" if ok else "⚠️", "报告目录可写", detail if ok else f"{detail} → {advice}"))
    degraded |= not ok

    width = max(len(r[1]) for r in rows) + 2
    print()
    for status, item, note in rows:
        print(f"  {status} {item:<{width}} {note}")
    print()

    if degraded:
        print("  ⚠️ 存在降级项：按上方建议降级执行（降级策略详见根 SKILL.md「执行环境自检」节），")
        print("     启动流程前须向用户告知降级方式与影响。")
        sys.exit(1)
    print("  ✅ 全部就绪：取数与验算链路可正常使用。")
    sys.exit(0)


if __name__ == "__main__":
    main()
