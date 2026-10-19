from datetime import date

import pytest

from custom_components.obiado.models import (
    InvalidResponse,
    MealDay,
    months_between,
    normalize_host,
    parse_orders,
    prune,
    validate_refresh_hours,
)


@pytest.mark.parametrize(
    "value", [float("nan"), float("inf"), -float("inf"), 0, 169, "bad", None, True]
)
def test_invalid_refresh_interval(value):
    with pytest.raises((ValueError, TypeError)):
        validate_refresh_hours(value)


@pytest.mark.parametrize("value", [1, 6, 6.5, 168, "12"])
def test_valid_refresh_interval(value):
    assert validate_refresh_hours(value) == float(value)


@pytest.mark.parametrize("value", ["rpk.obiado.pl", "https://RPK.obiado.pl/"])
def test_host(value):
    assert normalize_host(value) == "rpk.obiado.pl"


@pytest.mark.parametrize(
    "value",
    [
        "http://rpk.obiado.pl",
        "evil.test",
        "rpk.obiado.pl.evil.test",
        "https://user:pass@rpk.obiado.pl",
        "https://rpk.obiado.pl:443",
        "https://rpk.obiado.pl/calendar/user",
        "api.obiado.pl",
        "logowanie.obiado.pl",
    ],
)
def test_host_rejects_wrong_destination(value):
    with pytest.raises(ValueError):
        normalize_host(value)


def test_basket_and_boundary_retention():
    days = parse_orders(
        {
            "orders": {
                "2026-10-19": ["<b>Zupa</b> &amp; pieczywo", "Napój"],
                "2026-10-13": ["Obiad"],
                "2026-10-12": ["Obiad"],
            }
        },
        2026,
        10,
    )
    assert [item.day.day for item in prune(days, date(2026, 10, 18))] == [13, 19]
    assert days[-1].meals == ("Zupa & pieczywo", "Napój")
    assert days[-1].as_dict()["date"] == "2026-10-19"


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"orders": None},
        {"orders": {"bad-date": ["Zupa"]}},
        {"orders": {"2026-11-01": ["Zupa"]}},
        {"orders": {"2026-10-19": "Zupa"}},
        {"orders": {"2026-10-19": [None]}},
    ],
)
def test_invalid_snapshot_rejected(payload):
    with pytest.raises(InvalidResponse):
        parse_orders(payload, 2026, 10)


def test_empty_and_year_rollover():
    assert parse_orders({"orders": {}}, 2026, 10) == []
    assert parse_orders({"orders": []}, 2026, 10) == []
    assert months_between(date(2026, 12, 20), date(2027, 2, 1)) == [
        (2026, 12),
        (2027, 1),
        (2027, 2),
    ]
    assert prune([MealDay(date(2026, 1, 1), ("Zupa",))], date(2026, 10, 18)) == []
