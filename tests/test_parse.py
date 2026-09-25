import pytest

from extrusion_monitor.config import Rect, Variable
from extrusion_monitor.ocr import parse_number


def var(**kw):
    return Variable(id="v", name="v", region=Rect(x=0, y=0, w=1, h=1), **kw)


@pytest.mark.parametrize("text,expected", [
    ("185", 185), ("185.5", 185.5), ("185,5", 185.5), ("-12.3", -12.3), (" 1O5 ", 105),
    ("l85", 185), ("1.234,5", 1234.5), ("1,234.5", 1234.5), ("3.20 mm", 3.2), ("", None), ("---", None),
])
def test_parse_auto(text, expected):
    assert parse_number(text) == expected


def test_parse_explicit_comma_thousands():
    assert parse_number("1.250", var(decimal_separator=",")) == 1250


def test_fix_missing_decimal():
    assert parse_number("1855", var(decimals=1, fix_missing_decimal=True)) == pytest.approx(185.5)
    assert parse_number("185.5", var(decimals=1, fix_missing_decimal=True)) == pytest.approx(185.5)


def test_ambiguous_char_inside_number_rejected():
    from extrusion_monitor.acquisition import _AMBIGUOUS
    assert _AMBIGUOUS.search("3?5")
    assert _AMBIGUOUS.search("12.?4")
    assert not _AMBIGUOUS.search("300??")
