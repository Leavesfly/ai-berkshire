"""tools/core/ 模块单元测试 — 直接 import，无子进程开销。

运行：python3 -m pytest tests/test_core.py -q
"""

# pythonpath 已在 pyproject.toml [tool.pytest.ini_options] 中配置，无需 sys.path hack


# ---------------------------------------------------------------------------
# core.metrics
# ---------------------------------------------------------------------------


class TestCoreMetrics:
    def test_grade_all_pass(self):
        from core.metrics import grade_indicators

        m = {
            "roe_avg": 25,
            "fcf_5y": 1000,
            "interest_cover": 20,
            "gross_margin": 50,
            "ocf_ni": 1.1,
            "net_margin": 30,
            "dilution_pct": -2,
            "dilution_note": "",
        }
        grades = grade_indicators(m)
        assert len(grades) == 7
        assert all(g[2] == "pass" for g in grades)

    def test_grade_all_fail(self):
        from core.metrics import grade_indicators

        m = {
            "roe_avg": 3,
            "fcf_5y": -100,
            "interest_cover": 1.5,
            "gross_margin": 10,
            "ocf_ni": 0.5,
            "net_margin": 2,
            "dilution_pct": 35,
            "dilution_note": "",
        }
        grades = grade_indicators(m)
        status = {g[0]: g[2] for g in grades}
        assert status["1"] == "fail"
        assert status["2"] == "fail"
        assert status["3"] == "fail"
        assert status["4"] == "fail"
        assert status["5"] == "fail"
        assert status["6"] == "fail"
        assert status["7"] == "fail"

    def test_grade_na_for_none(self):
        from core.metrics import grade_indicators

        m = {
            "roe_avg": None,
            "fcf_5y": None,
            "interest_cover": None,
            "gross_margin": None,
            "ocf_ni": None,
            "net_margin": None,
            "dilution_pct": None,
            "dilution_note": "",
        }
        grades = grade_indicators(m)
        assert all(g[2] == "na" for g in grades)

    def test_grade_edge_cases(self):
        from core.metrics import grade_indicators

        # ROE 9% → edge (between 8 fail and 10 edge)
        m = {
            "roe_avg": 9,
            "fcf_5y": 100,
            "interest_cover": 2.5,
            "gross_margin": 16,
            "ocf_ni": 0.75,
            "net_margin": 5.5,
            "dilution_pct": 16,
            "dilution_note": "",
        }
        grades = grade_indicators(m)
        status = {g[0]: g[2] for g in grades}
        assert status["1"] == "edge"  # ROE 9 < 10
        assert status["3"] == "edge"  # interest 2.5 < 3
        assert status["4"] == "edge"  # gross margin 16 < 18
        assert status["5"] == "edge"  # ocf_ni 0.75 < 0.8
        assert status["6"] == "edge"  # net margin 5.5 < 6
        assert status["7"] == "edge"  # dilution 16 > 15

    def test_rules_constant(self):
        from core.metrics import RULES

        assert len(RULES) == 7
        assert RULES[0] == ("1", "平均ROE", "< 8%")

    def test_thresholds_constant(self):
        from core.metrics import THRESHOLDS

        assert THRESHOLDS["roe_fail"] == 8
        assert THRESHOLDS["dilution_fail"] == 20


# ---------------------------------------------------------------------------
# core.valuation
# ---------------------------------------------------------------------------


class TestCoreValuation:
    def test_exact_decimal(self):
        from decimal import Decimal

        from core.valuation import exact

        assert exact(0.1) == Decimal("0.1")
        assert exact("3.14") == Decimal("3.14")
        assert exact(Decimal("1.5")) == Decimal("1.5")

    def test_fmt_number(self):
        from decimal import Decimal

        from core.valuation import fmt_number

        assert "T" in fmt_number(Decimal("2.5e12"))
        assert "B" in fmt_number(Decimal("3e9"))
        assert "M" in fmt_number(Decimal("5e6"))
        assert "万亿" in fmt_number(Decimal("25000"), "亿")

    def test_cagr_basic(self):
        from core.valuation import cagr

        result = cagr(2261, 6603, 5)
        assert abs(result - 0.2391) < 0.001  # ≈ 23.91%

    def test_cagr_invalid(self):
        import pytest
        from core.valuation import cagr

        with pytest.raises(ValueError):
            cagr(-1, 100, 5)
        with pytest.raises(ValueError):
            cagr(100, 200, 0)

    def test_dcf_intrinsic_value(self):
        from core.valuation import dcf_intrinsic_value

        iv = dcf_intrinsic_value(
            fcf=1600, growth_rate=0.10, discount_rate=0.12,
            terminal_growth=0.025, years=10
        )
        assert iv > 0
        # 内在价值应大于 0 且合理（FCF 1600 亿，10% 增长）
        assert iv > 1600 * 10  # 至少 10 倍 FCF

    def test_dcf_invalid_discount(self):
        import pytest
        from core.valuation import dcf_intrinsic_value

        with pytest.raises(ValueError):
            dcf_intrinsic_value(100, 0.05, 0.02, 0.025)  # discount <= terminal

    def test_reverse_dcf(self):
        from core.valuation import reverse_dcf_implied_growth

        growth = reverse_dcf_implied_growth(
            market_cap=28000, fcf=1600, discount_rate=0.10, terminal_growth=0.025
        )
        # 隐含增长率应在合理范围
        assert -0.1 < growth < 0.5

    def test_reverse_dcf_invalid(self):
        import pytest
        from core.valuation import reverse_dcf_implied_growth

        with pytest.raises(ValueError):
            reverse_dcf_implied_growth(28000, -100, 0.10, 0.025)

    def test_valuation_percentile(self):
        from core.valuation import valuation_percentile

        history = [25, 27, 28, 30, 33, 35, 38, 42, 45, 55]
        pct = valuation_percentile(34, history)
        assert 40 < pct < 60  # 34 在中间偏下

    def test_valuation_percentile_too_few(self):
        import pytest
        from core.valuation import valuation_percentile

        with pytest.raises(ValueError):
            valuation_percentile(20, [25, 30])


# ---------------------------------------------------------------------------
# core.market
# ---------------------------------------------------------------------------


class TestCoreMarket:
    def test_normalize_code(self):
        from core.market import normalize_code

        assert normalize_code("600519") == "600519"
        assert normalize_code("600519.SH") == "600519"
        assert normalize_code("000001.SZ") == "000001"
        assert normalize_code(" 300750.sz ") == "300750"

    def test_market(self):
        from core.market import market

        assert market("600519") == "SH"
        assert market("000001") == "SZ"
        assert market("300750") == "SZ"
        assert market("830799") == "BJ"

    def test_detect_market_type(self):
        from core.market import detect_market_type

        assert detect_market_type("600519") == "A"
        assert detect_market_type("hk00700") == "HK"
        assert detect_market_type("0700.HK") == "HK"
        assert detect_market_type("usAAPL") == "US"

    def test_qq_code(self):
        from core.market import qq_code

        assert qq_code("600519") == "sh600519"
        assert qq_code("hk00700") == "hk00700"
        assert qq_code("0700.HK") == "hk00700"
        assert qq_code("usAAPL") == "usAAPL"
        assert qq_code("sh000300") == "sh000300"  # 指数透传

    def test_yf_ticker(self):
        from core.market import yf_ticker

        assert yf_ticker("hk00700") == "0700.HK"
        assert yf_ticker("usAAPL") == "AAPL"
        assert yf_ticker("600519") == "600519"

    def test_tickflow_symbol(self):
        from core.market import tickflow_symbol

        assert tickflow_symbol("600519") == "600519.SH"
        assert tickflow_symbol("hk00700") == "00700.HK"
        assert tickflow_symbol("usAAPL") == "AAPL.US"

    def test_market_label(self):
        from core.market import market_label

        assert "港股" in market_label("hk00700")
        assert "美股" in market_label("usAAPL")
        assert "A股" in market_label("sh600519")


# ---------------------------------------------------------------------------
# core.formatting
# ---------------------------------------------------------------------------


class TestCoreFormatting:
    def test_fmt_yi(self):
        from core.formatting import fmt_yi

        assert fmt_yi(None) == "-"
        assert fmt_yi("-") == "-"
        assert "亿" in fmt_yi(1.5e8)
        assert "万" in fmt_yi(5e4)
        assert fmt_yi(123.45) == "123.45"

    def test_fmt_pct(self):
        from core.formatting import fmt_pct

        assert fmt_pct(None) == "-"
        assert fmt_pct(25.5) == "25.50%"
        assert fmt_pct("bad") == "bad"

    def test_fmt_num(self):
        from core.formatting import fmt_num

        assert fmt_num(None) == "-"
        assert "万亿" in fmt_num(2.5e12)
        assert "亿" in fmt_num(3e8)
        assert "万" in fmt_num(5e4)
