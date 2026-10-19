"""Read-only all-day calendar for one selected child."""

from datetime import datetime, timedelta

from homeassistant.components.calendar import CalendarEntity, CalendarEvent
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_track_time_change
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from .const import CONF_CHILD_NAME
from .coordinator import ObiadoCoordinator
from .event_text import format_event_text
from .models import MealDay, prune

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    async_add_entities([ObiadoCalendar(entry.runtime_data, entry)])


class ObiadoCalendar(CoordinatorEntity[ObiadoCoordinator], CalendarEntity):
    _attr_has_entity_name = True
    _attr_icon = "mdi:food"
    _attr_supported_features = 0

    def __init__(self, coordinator: ObiadoCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = entry.unique_id
        self._attr_name = f"Obiado — {entry.data[CONF_CHILD_NAME]}"
        self._child_name = entry.data[CONF_CHILD_NAME]

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self.async_on_remove(
            async_track_time_change(
                self.hass,
                lambda _: self.async_write_ha_state(),
                hour=0,
                minute=0,
                second=0,
            )
        )

    def _event(self, item: MealDay) -> CalendarEvent:
        summary, description = format_event_text(self._child_name, item.meals)
        return CalendarEvent(
            start=item.day,
            end=item.day + timedelta(days=1),
            summary=summary,
            description=description,
            uid=f"{self.unique_id}-{item.day.isoformat()}",
        )

    @property
    def event(self) -> CalendarEvent | None:
        today = dt_util.now().date()
        return next(
            (self._event(item) for item in self.coordinator.data or [] if item.day >= today), None
        )

    async def async_get_events(
        self, hass: HomeAssistant, start_date: datetime, end_date: datetime
    ) -> list[CalendarEvent]:
        result = []
        for item in prune(self.coordinator.data or [], dt_util.now().date()):
            start = dt_util.start_of_local_day(item.day)
            end = dt_util.start_of_local_day(item.day + timedelta(days=1))
            if start < end_date and end > start_date:
                result.append(self._event(item))
        return result
