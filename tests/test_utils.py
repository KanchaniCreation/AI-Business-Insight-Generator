import pytest

from src.utils import fmt_pct, format_inr, format_money, growth_pct, safe_divide, set_currency


def test_indian_grouping():
    assert format_inr(1120000) == "₹11,20,000" and format_inr(999) == "₹999" and format_inr(-12345.5, 1) == "-₹12,345.5"
    assert format_inr(None) == "N/A" and format_inr(10000000) == "₹1,00,00,000"


def test_currency_switching():
    set_currency("USD")
    assert format_money(1120000) == "$1,120,000" and format_money(-5.5, 1) == "-$5.5"
    set_currency("EUR")
    assert format_money(1000) == "€1,000"
    set_currency("INR")
    assert format_money(1120000) == "₹11,20,000"


def test_unsupported_currency_rejected():
    with pytest.raises(ValueError):
        set_currency("XYZ")


def test_safe_divide_and_growth():
    assert safe_divide(1, 0) == 0 and safe_divide(1, None) == 0 and safe_divide(1, float("nan")) == 0
    assert growth_pct(110, 100) == pytest.approx(10) and growth_pct(5, 0) is None and growth_pct(0, 0) == 0
    assert growth_pct(50, -100) == pytest.approx(150)       # negative base uses |previous|


def test_fmt_pct():
    assert fmt_pct(12.345) == "+12.3%" and fmt_pct(-3, signed=True) == "-3.0%" and fmt_pct(None) == "N/A"
