"""AI Berkshire 工具层冒烟测试 — 全离线，不依赖网络与外部包。

覆盖：核心计算命令的退出码语义（0=通过/1=不通过/2=参数错误）、
纯函数单元、决策日志与观察清单的本地读写（临时目录隔离，不污染 data/）。

运行：python3 -m pytest tests/ -q
"""

import json
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOOLS = os.path.join(ROOT, "tools")
sys.path.insert(0, TOOLS)


def run_tool(script, *args):
    """以子进程运行工具，返回 (exit_code, stdout+stderr)。"""
    r = subprocess.run(
        [sys.executable, os.path.join(TOOLS, script), *args],
        capture_output=True, text=True, timeout=60, cwd=ROOT,
    )
    return r.returncode, r.stdout + r.stderr


# ---------------------------------------------------------------------------
# financial_rigor.py
# ---------------------------------------------------------------------------

class TestFinancialRigor:
    def test_cagr_ok(self):
        code, out = run_tool("financial_rigor.py", "cagr",
                             "--begin", "2261", "--end", "6603", "--years", "5")
        assert code == 0
        assert "+23.9" in out  # (6603/2261)^(1/5)-1 ≈ 23.91%

    def test_cagr_bad_args(self):
        code, _ = run_tool("financial_rigor.py", "cagr",
                           "--begin", "-1", "--end", "100", "--years", "5")
        assert code == 2

    def test_calc_exact(self):
        code, out = run_tool("financial_rigor.py", "calc", "--expr", "510 * 9.11e9")
        assert code == 0 and "4646100000000" in out.replace(",", "").replace(".00", "")

    def test_market_cap_pass_and_fail(self):
        code, _ = run_tool("financial_rigor.py", "verify-market-cap",
                           "--price", "100", "--shares", "1e9", "--reported", "1e11")
        assert code == 0
        code, _ = run_tool("financial_rigor.py", "verify-market-cap",
                           "--price", "100", "--shares", "1e9", "--reported", "2e11")
        assert code == 1  # 偏差 50% → 验证不通过

    def test_cross_validate_major_diff(self):
        code, _ = run_tool("financial_rigor.py", "cross-validate",
                           "--field", "revenue",
                           "--values", '{"a": 100, "b": 101, "c": 200}')
        assert code == 1

    def test_valuation_percentile(self):
        code, out = run_tool("financial_rigor.py", "valuation-percentile",
                             "--metric", "PE", "--current", "34",
                             "--history", "[25,27,28,30,33,35,38,42,45,55]")
        assert code == 0 and "分位" in out

    def test_valuation_percentile_too_few(self):
        code, _ = run_tool("financial_rigor.py", "valuation-percentile",
                           "--current", "20", "--history", "[25,30]")
        assert code == 2

    def test_peer_compare(self):
        code, out = run_tool(
            "financial_rigor.py", "peer-compare",
            "--target", '{"name":"T","PE":18,"ROE":22}',
            "--peers", '[{"name":"A","PE":12,"ROE":11},{"name":"B","PE":24,"ROE":35}]')
        assert code == 0 and "同业中位" in out

    def test_dcf_matrix_terminal_guard(self):
        code, _ = run_tool("financial_rigor.py", "dcf-matrix",
                           "--fcf", "100", "--growth", "0.05",
                           "--discount", "0.02", "--terminal-growth", "0.025")
        assert code == 2  # 贴现率 ≤ 永续增长 → 参数错误

    def test_dcf_matrix_ok(self):
        code, out = run_tool("financial_rigor.py", "dcf-matrix",
                             "--fcf", "1600", "--growth", "0.05,0.10",
                             "--discount", "0.10,0.12", "--terminal-growth", "0.025",
                             "--market-cap", "28000")
        assert code == 0 and "敏感性矩阵" in out

    def test_altman_z_safe_and_distress(self):
        args = ["altman-z", "--working-capital", "3000", "--retained-earnings", "8000",
                "--ebit", "2300", "--equity-value", "28000",
                "--total-liabilities", "6000", "--total-assets", "16000"]
        code, out = run_tool("financial_rigor.py", *args)
        assert code == 0 and "安全区" in out
        code, out = run_tool("financial_rigor.py", "altman-z",
                             "--working-capital", "-2000", "--retained-earnings", "-3000",
                             "--ebit", "-500", "--equity-value", "500",
                             "--total-liabilities", "9000", "--total-assets", "10000")
        assert code == 1 and "困境区" in out

    def test_accruals_pass_and_fail(self):
        code, _ = run_tool("financial_rigor.py", "accruals", "--net-income", "1941",
                           "--cfo", "2200", "--total-assets", "16000")
        assert code == 0
        code, out = run_tool("financial_rigor.py", "accruals", "--net-income", "3000",
                             "--cfo", "800", "--total-assets", "16000")
        assert code == 1 and "应计" in out

    def test_m_score_missing_fields(self):
        code, out = run_tool("financial_rigor.py", "m-score",
                             "--current", '{"revenue": 100}', "--prior", '{"revenue": 90}')
        assert code == 2 and "缺少字段" in out

    def test_kelly_positive_and_negative(self):
        code, out = run_tool("financial_rigor.py", "kelly",
                             "--win-prob", "0.6", "--win", "0.5", "--loss", "0.3")
        assert code == 0 and "半凯利" in out
        code, _ = run_tool("financial_rigor.py", "kelly",
                           "--win-prob", "0.3", "--win", "0.2", "--loss", "0.5")
        assert code == 1  # 期望为负


# ---------------------------------------------------------------------------
# decision_log.py / watchlist.py（临时路径隔离）
# ---------------------------------------------------------------------------

class TestDecisionLog:
    def test_add_list_review_offline(self, tmp_path, monkeypatch):
        import decision_log
        monkeypatch.setattr(decision_log, "_LOG_PATH", str(tmp_path / "d.jsonl"))
        import argparse
        args = argparse.Namespace(
            company="测试公司", code="", skill="investment-research",
            verdict="买入", price=100.0, currency="CNY",
            reason="单测", report="", date="2026-01-01")
        decision_log.cmd_add(args)
        records = decision_log._load_records()
        assert len(records) == 1 and records[0]["verdict"] == "买入"
        # 无 code 的记录不参与 review（不触发网络）
        decision_log.cmd_review()

    def test_add_rejects_bad_verdict(self, tmp_path, monkeypatch):
        import decision_log
        monkeypatch.setattr(decision_log, "_LOG_PATH", str(tmp_path / "d.jsonl"))
        import argparse
        import pytest
        args = argparse.Namespace(
            company="X", code="", skill="s", verdict="梭哈",
            price=None, currency="", reason="", report="", date="")
        with pytest.raises(SystemExit) as e:
            decision_log.cmd_add(args)
        assert e.value.code == 2


class TestWatchlist:
    def test_add_update_remove(self, tmp_path, monkeypatch):
        import watchlist
        monkeypatch.setattr(watchlist, "_WL_PATH", str(tmp_path / "wl.json"))
        import argparse
        args = argparse.Namespace(code="hk00700", name="腾讯",
                                  buy_below=400.0, sell_above=None, note="")
        watchlist.cmd_add(args)
        items = watchlist._load()
        assert len(items) == 1 and items[0]["buy_below"] == 400.0
        # 二次 add 应为更新而非重复
        args2 = argparse.Namespace(code="hk00700", name=None,
                                   buy_below=380.0, sell_above=700.0, note=None)
        watchlist.cmd_add(args2)
        items = watchlist._load()
        assert len(items) == 1 and items[0]["buy_below"] == 380.0
        assert items[0]["name"] == "腾讯"  # 未传 name 时保留原值
        watchlist.cmd_remove("hk00700")
        assert watchlist._load() == []

    def test_notify_without_webhook(self, monkeypatch):
        import watchlist
        monkeypatch.delenv("WATCHLIST_WEBHOOK", raising=False)
        assert watchlist._notify("test") is False  # 未配置时跳过推送不报错

    def test_schedule_min_interval(self):
        code, _ = run_tool("watchlist.py", "schedule", "--every", "1")
        assert code == 2


# ---------------------------------------------------------------------------
# quality_screen.py / portfolio_calc.py 纯函数
# ---------------------------------------------------------------------------

class TestQualityScreenGrading:
    def test_grade_all_pass(self):
        import quality_screen
        m = {"roe_avg": 25, "fcf_5y": 1000, "interest_cover": 20,
             "gross_margin": 50, "ocf_ni": 1.1, "net_margin": 30,
             "dilution_pct": -2, "dilution_note": ""}
        grades = quality_screen._grade(m)
        assert all(g[2] == "pass" for g in grades)

    def test_grade_fail_and_na(self):
        import quality_screen
        m = {"roe_avg": 3, "fcf_5y": None, "interest_cover": 1.5,
             "gross_margin": 10, "ocf_ni": 0.5, "net_margin": 2,
             "dilution_pct": 35, "dilution_note": ""}
        status = {g[0]: g[2] for g in quality_screen._grade(m)}
        assert status == {"1": "fail", "2": "na", "3": "fail", "4": "fail",
                          "5": "fail", "6": "fail", "7": "fail"}


class TestPortfolioCalc:
    def test_pearson(self):
        import portfolio_calc
        assert abs(portfolio_calc._pearson([1, 2, 3], [2, 4, 6]) - 1.0) < 1e-9
        assert abs(portfolio_calc._pearson([1, 2, 3], [3, 2, 1]) + 1.0) < 1e-9
        assert portfolio_calc._pearson([1, 1, 1], [1, 2, 3]) is None  # 零方差

    def test_cli_offline_no_corr(self):
        holdings = json.dumps([
            {"name": "A", "code": "600519", "weight": 0.5, "expected_return": 0.10},
            {"name": "现金", "code": "cash", "weight": 0.5, "expected_return": 0.04},
        ])
        code, out = run_tool("portfolio_calc.py", "--holdings", holdings, "--no-corr")
        assert code == 0 and "集中度分析" in out and "加权预期回报" in out

    def test_cli_bad_holdings(self):
        code, _ = run_tool("portfolio_calc.py", "--holdings", "not-json")
        assert code == 2


# ---------------------------------------------------------------------------
# filings_fetch.py（离线部分：市场识别与参数校验）
# ---------------------------------------------------------------------------

class TestFilingsFetch:
    def test_detect_market(self):
        import filings_fetch
        assert filings_fetch._detect_market("usAAPL") == "US"
        assert filings_fetch._detect_market("hk00700") == "HK"
        assert filings_fetch._detect_market("0700.HK") == "HK"
        assert filings_fetch._detect_market("600519") == "A"

    def test_fetch_requires_url_or_latest(self):
        code, _ = run_tool("filings_fetch.py", "fetch")
        assert code == 2

    def test_no_command_exits_2(self):
        code, _ = run_tool("filings_fetch.py")
        assert code == 2


# ---------------------------------------------------------------------------
# filings_parse.py（离线：HTML转文本/章节切分/跨年diff 纯函数）
# ---------------------------------------------------------------------------

_FAKE_10K = "\n".join(
    # 目录页（密集列一遍，应被去重逻辑丢弃）
    [f"Item {n}. placeholder" for n in ("1", "1A", "3", "7")]
    # 正文
    + ["Item 1. Business", "We design products." * 5,
       "Item 1A. Risk Factors", "Competition may harm results significantly." * 8,
       "Item 3. Legal Proceedings", "Various lawsuits pending resolution now." * 4,
       "Item 7. Management Discussion", "Revenue increased due to strong demand." * 6])


class TestFilingsParse:
    def test_html_to_text_strips_tags(self):
        import filings_parse
        text = filings_parse._html_to_text(
            "<html><style>x{}</style><p>Hello <b>World</b></p><div>Next&amp;</div></html>")
        assert "Hello" in text and "World" in text and "Next&" in text
        assert "<" not in text.replace("<", "") or "style" not in text

    def test_split_sections_us_items(self):
        import filings_parse
        sections = filings_parse.split_sections(_FAKE_10K)
        idents = [s[0] for s in sections]
        assert "item1a" in idents and "item7" in idents

    def test_pick_section_by_alias(self):
        import filings_parse
        body = filings_parse.pick_section(_FAKE_10K, "risk")
        assert body and "Competition" in body
        assert filings_parse.pick_section(_FAKE_10K, "mda").startswith("Item 7")

    def test_diff_sections(self):
        import filings_parse
        old = "公司面临激烈的市场竞争风险与不确定性。汇率波动可能影响公司海外业务的盈利能力。"
        new = "公司面临激烈的市场竞争风险与不确定性。监管政策变化可能对主营业务造成重大不利影响。"
        _len_chg, added, removed, ratio = filings_parse.diff_sections(old, new)
        assert any("监管" in s for s in added)
        assert any("汇率" in s for s in removed)
        assert 0 < ratio < 1

    def test_bad_section_name(self):
        code, _ = run_tool("filings_parse.py", "extract", "/nonexistent.htm",
                           "--section", "nosuch")
        assert code == 2


# ---------------------------------------------------------------------------
# masters_portfolio.py（离线：CIK解析与CUSIP聚合）
# ---------------------------------------------------------------------------

class TestMastersPortfolio:
    def test_resolve_cik(self):
        import masters_portfolio
        cik, label = masters_portfolio._resolve_cik("berkshire")
        assert cik == "0001067983" and "巴菲特" in label
        cik, _ = masters_portfolio._resolve_cik("1061768")
        assert cik == "0001061768"
        import pytest
        with pytest.raises(ValueError):
            masters_portfolio._resolve_cik("not-a-fund-name")

    def test_aggregate_by_cusip(self):
        import masters_portfolio
        rows = [
            {"issuer": "CHEVRON CORP NEW", "class": "COM", "cusip": "166764100",
             "value": 100.0, "shares": 10.0, "putcall": ""},
            {"issuer": "CHEVRON CORPORATION", "class": "COM", "cusip": "166764100",
             "value": 50.0, "shares": 5.0, "putcall": ""},
            {"issuer": "APPLE INC", "class": "COM", "cusip": "037833100",
             "value": 30.0, "shares": 3.0, "putcall": "Put"},
        ]
        agg = masters_portfolio._aggregate(rows)
        # 同 CUSIP 不同写法应合并；期权单独成键
        assert len(agg) == 2
        chevron = agg["166764"]
        assert chevron["value"] == 150.0 and chevron["shares"] == 15.0
        assert any("[Put]" in a["name"] for a in agg.values())

    def test_fmt_value(self):
        import masters_portfolio
        assert masters_portfolio._fmt_value(2.5e9) == "2.5B"
        assert masters_portfolio._fmt_value(3e6) == "3M"


# ---------------------------------------------------------------------------
# decision_log 基准映射 / company_facts / report_export（全离线）
# ---------------------------------------------------------------------------

class TestBenchmarkMapping:
    def test_bench_for(self):
        import decision_log
        assert decision_log._bench_for("600519")[0] == "sh000300"
        assert decision_log._bench_for("hk00700")[0] == "hkHSI"
        assert decision_log._bench_for("usAAPL")[0] == "us.INX"


class TestCompanyFacts:
    def test_set_get_remove(self, tmp_path, monkeypatch):
        import company_facts
        monkeypatch.setattr(company_facts, "_BASE", str(tmp_path))
        import argparse
        args = argparse.Namespace(code="hk00700", name="腾讯", category="financial",
                                  key="2025年营收", value="6603亿CNY", source="单测")
        company_facts.cmd_set(args)
        doc = company_facts._load("hk00700")
        assert doc["name"] == "腾讯" and len(doc["facts"]) == 1
        # 同 key 同分类二次 set 应为更新
        args.value = "6604亿CNY"
        company_facts.cmd_set(args)
        doc = company_facts._load("hk00700")
        assert len(doc["facts"]) == 1 and doc["facts"][0]["value"] == "6604亿CNY"
        company_facts.cmd_remove("hk00700", "2025年营收")
        assert company_facts._load("hk00700")["facts"] == []

    def test_volatile_key_rejected(self, tmp_path, monkeypatch):
        import company_facts
        monkeypatch.setattr(company_facts, "_BASE", str(tmp_path))
        import argparse
        import pytest
        args = argparse.Namespace(code="600519", name=None, category="valuation",
                                  key="当前市值", value="2万亿", source="")
        with pytest.raises(SystemExit) as e:
            company_facts.cmd_set(args)
        assert e.value.code == 2


class TestReportExport:
    def test_md_to_html_core_elements(self):
        import report_export
        md = ("# 标题\n\n> 引用\n\n| A | B |\n|---|---|\n| 1 | **2** |\n\n"
              "- 列表项\n\n段落 `code` [链接](https://x.y)\n")
        html = report_export.md_to_html(md, "/tmp")
        for frag in ("<h1>", "<blockquote>", "<table>", "<strong>2</strong>",
                     "<li>", "<code>code</code>", '<a href="https://x.y">'):
            assert frag in html

    def test_export_roundtrip(self, tmp_path):
        import report_export
        md_path = tmp_path / "r.md"
        md_path.write_text("# 测试报告\n\n结论段落", encoding="utf-8")
        out = report_export.export(str(md_path), str(tmp_path / "r.html"))
        content = open(out, encoding="utf-8").read()
        assert "<title>测试报告</title>" in content and "结论段落" in content


# ---------------------------------------------------------------------------
# 全量工具可编译（doctor 的开发时等价物）
# ---------------------------------------------------------------------------

def test_all_tools_compile():
    import py_compile
    for name in os.listdir(TOOLS):
        if name.endswith(".py"):
            py_compile.compile(os.path.join(TOOLS, name), doraise=True)
