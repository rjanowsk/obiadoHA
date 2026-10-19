"""Validated portal data and snapshot operations, independent of Home Assistant."""

import math
import re
from dataclasses import dataclass
from datetime import date, timedelta
from html import unescape
from urllib.parse import urlsplit

from .const import RETENTION_DAYS


class ObiadoError(Exception):
    """A portal request or response failed."""


class InvalidAuth(ObiadoError):
    """Credentials were rejected."""


class ChildNotFound(ObiadoError):
    """A child name is missing or ambiguous."""


class InvalidResponse(ObiadoError):
    """The portal returned an unexpected structure."""


def validate_refresh_hours(value: object) -> float:
    """Validate submitted input separately from the serializable UI schema."""
    if isinstance(value, bool):
        raise ValueError("Invalid refresh interval")
    hours = float(value)
    if not math.isfinite(hours) or not 1 <= hours <= 168:
        raise ValueError("Invalid refresh interval")
    return hours


def normalize_host(value: str) -> str:
    """Only accept a catering tenant on Obiado, always using HTTPS."""
    parsed = urlsplit(value.strip() if "://" in value else f"https://{value.strip()}")
    host = (parsed.hostname or "").lower()
    if (
        parsed.scheme != "https"
        or not re.fullmatch(r"[a-z0-9](?:[a-z0-9-]*[a-z0-9])?\.obiado\.pl", host)
        or host in {"api.obiado.pl", "logowanie.obiado.pl", "www.obiado.pl"}
        or parsed.username
        or parsed.password
        or parsed.port
        or parsed.path not in {"", "/"}
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError("Invalid Obiado catering address")
    return host


def normalize_name(value: str) -> str:
    return " ".join(value.split()).casefold()


@dataclass(frozen=True, order=True)
class MealDay:
    day: date
    meals: tuple[str, ...]

    def as_dict(self) -> dict:
        return {"date": self.day.isoformat(), "meals": list(self.meals)}


def parse_orders(payload: object, year: int, month: int) -> list[MealDay]:
    """Parse the date -> collection of descriptions mapping used by the basket UI."""
    if not isinstance(payload, dict):
        raise InvalidResponse("Missing orders mapping")
    # PHP encodes an empty associative array as [], not {}.
    if payload.get("orders") == []:
        return []
    if not isinstance(payload.get("orders"), dict):
        raise InvalidResponse("Missing orders mapping")
    result = []
    for raw_day, meals in payload["orders"].items():
        try:
            day = date.fromisoformat(raw_day)
        except (TypeError, ValueError) as err:
            raise InvalidResponse("Invalid order date") from err
        if (day.year, day.month) != (year, month):
            raise InvalidResponse("Order outside requested month")
        # Vue's basket v-for iterates both arrays and object values. In particular,
        # PHP arrays with gaps in their indices are encoded as JSON objects.
        if isinstance(meals, dict):
            meals = list(meals.values())
        elif not isinstance(meals, list):
            raise InvalidResponse(
                f"Invalid meal descriptions: expected list or object, got {type(meals).__name__}"
            )
        for index, meal in enumerate(meals):
            if not isinstance(meal, str):
                raise InvalidResponse(
                    f"Invalid meal descriptions: item {index} expected string, got {type(meal).__name__}"
                )
            if not meal.strip():
                raise InvalidResponse(f"Invalid meal descriptions: item {index} is blank")
        # Descriptions can contain HTML; calendars should only receive plain text.
        descriptions = tuple(unescape(re.sub(r"<[^>]*>", "", meal)).strip() for meal in meals)
        if descriptions:
            result.append(MealDay(day, descriptions))
    return sorted(result)


def prune(days: list[MealDay], today: date) -> list[MealDay]:
    cutoff = today - timedelta(days=RETENTION_DAYS)
    return sorted(item for item in days if item.day >= cutoff)


def months_between(start: date, end: date) -> list[tuple[int, int]]:
    result = []
    year, month = start.year, start.month
    while (year, month) <= (end.year, end.month):
        result.append((year, month))
        year, month = (year + 1, 1) if month == 12 else (year, month + 1)
    return result
