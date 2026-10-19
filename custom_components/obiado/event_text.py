"""Readable plain-text menu for calendar titles and event details."""

import re

_MEAL_WITH_DIET = re.compile(
    r"^(?P<label>[^,]+),\s*dieta\s+(?P<diet>.+?)\s+-\s+(?P<dish>.+)$",
    re.IGNORECASE,
)


def format_event_text(child_name: str, meals: tuple[str, ...]) -> tuple[str, str]:
    """Expose the menu even in cards that render only an event's summary."""
    titles = []
    details = []
    for meal in meals:
        text = " ".join(meal.split())
        match = _MEAL_WITH_DIET.fullmatch(text)
        if match:
            label, diet, dish = (match[group].strip() for group in ("label", "diet", "dish"))
            readable = f"{label}: {dish}"
            titles.append(readable)
            details.append(f"• {readable}\n  Dieta: {diet}")
        else:
            # Keep unfamiliar descriptions intact rather than guessing their fields.
            titles.append(text)
            details.append(f"• {text}")
    summary = "Obiad — " + " · ".join(titles) if titles else f"Obiad — {child_name}"
    description = f"Posiłki — {child_name}\n\n" + "\n\n".join(details)
    return summary, description
