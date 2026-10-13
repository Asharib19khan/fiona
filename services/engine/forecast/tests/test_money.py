import pytest
from pydantic import ValidationError

from engine.forecast.money import Money, major_to_minor, round_minor, to_money


@pytest.mark.parametrize(
    ("amount", "expected"),
    [(2.5, 3), (-2.5, -3), (0.49999, 0), (1234.5, 1235), (0.0, 0), (199.99999999, 200)],
)
def test_round_minor_is_half_away_from_zero(amount, expected):
    assert round_minor(amount) == expected


def test_round_minor_rejects_non_finite():
    with pytest.raises(ValueError):
        round_minor(float("nan"))


def test_money_rejects_floats_and_unknown_currencies():
    with pytest.raises(ValidationError):
        Money(minor=1.5, currency="PKR")
    with pytest.raises(ValidationError):
        Money(minor=100, currency="XYZ")


def test_money_normalises_currency_code():
    assert Money(minor=100, currency="pkr").currency == "PKR"


def test_major_to_minor_respects_currency_exponent():
    assert major_to_minor("3500.50", "PKR") == 350050
    assert major_to_minor(1000, "JPY") == 1000
    assert to_money(18450000.4, "PKR") == Money(minor=18450000, currency="PKR")
