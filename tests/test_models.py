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


@pytest.mark.parametrize(
    "meals",
    [
        ["<b>Zupa</b> &amp; pieczywo", "Napój"],
        {"0": "<b>Zupa</b> &amp; pieczywo", "2": "Napój"},
        {"3": "<b>Zupa</b> &amp; pieczywo", "10": "Napój"},
        {"soup": "<b>Zupa</b> &amp; pieczywo", "drink": "Napój"},
    ],
)
def test_basket_accepts_array_and_object_values_without_losing_descriptions(meals):
    assert parse_orders({"orders": {"2026-10-19": meals}}, 2026, 10) == [
        MealDay(date(2026, 10, 19), ("Zupa & pieczywo", "Napój"))
    ]


def test_basket_can_mix_arrays_objects_and_empty_days():
    assert parse_orders(
        {
            "orders": {
                "2026-10-19": ["Zupa"],
                "2026-10-20": {"1": "Obiad", "4": "Napój"},
                "2026-10-21": {},
                "2026-10-22": [],
            }
        },
        2026,
        10,
    ) == [
        MealDay(date(2026, 10, 19), ("Zupa",)),
        MealDay(date(2026, 10, 20), ("Obiad", "Napój")),
    ]


@pytest.mark.parametrize(
    "meals, detail",
    [
        ("private meal text", "expected list or object, got str"),
        (None, "expected list or object, got NoneType"),
        ({"0": "Private meal", "2": None}, "item 1 expected string, got NoneType"),
        ({"private-key": {"private-field": "private meal"}}, "item 0 expected string, got dict"),
        (["Private meal", 42], "item 1 expected string, got int"),
        (["Private meal", "  "], "item 1 is blank"),
    ],
)
def test_invalid_meals_report_only_shape_and_reject_partial_snapshot(meals, detail):
    with pytest.raises(InvalidResponse) as error:
        parse_orders({"orders": {"2026-10-18": ["Valid"], "2026-10-19": meals}}, 2026, 10)
    assert str(error.value) == f"Invalid meal descriptions: {detail}"
    assert "private" not in str(error.value).lower()
