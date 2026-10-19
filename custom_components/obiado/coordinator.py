"""Atomic refreshes, persistence, and local-midnight retention."""

import logging
from datetime import date, timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.event import async_track_time_change
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .api import ObiadoClient
from .const import CONF_CHILD_ID, CONF_REFRESH_HOURS, DEFAULT_REFRESH_HOURS, DOMAIN, RETENTION_DAYS
from .models import InvalidAuth, MealDay, ObiadoError, prune

_LOGGER = logging.getLogger(__name__)


class ObiadoCoordinator(DataUpdateCoordinator[list[MealDay]]):
    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, client: ObiadoClient) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            config_entry=entry,
            update_interval=timedelta(
                hours=entry.options.get(
                    CONF_REFRESH_HOURS,
                    entry.data.get(CONF_REFRESH_HOURS, DEFAULT_REFRESH_HOURS),
                )
            ),
        )
        self.client = client
        self.child_id = entry.data[CONF_CHILD_ID]
        self._store = Store(hass, 1, f"{DOMAIN}.{entry.entry_id}")

    async def async_load(self) -> None:
        saved = await self._store.async_load()
        if saved:
            try:
                days = [
                    MealDay(date.fromisoformat(item["date"]), tuple(item["meals"]))
                    for item in saved["days"]
                ]
                self.data = prune(days, dt_util.now().date())
                await self._store.async_save({"days": [item.as_dict() for item in self.data]})
            except (KeyError, TypeError, ValueError):
                _LOGGER.warning("Ignoring invalid Obiado calendar cache")

    async def _async_update_data(self) -> list[MealDay]:
        try:
            days = await self.client.fetch_orders(
                self.child_id,
                dt_util.now().date() - timedelta(days=RETENTION_DAYS),
            )
        except InvalidAuth as err:
            raise ConfigEntryAuthFailed("Obiado login required") from err
        except ObiadoError as err:
            raise UpdateFailed(str(err)) from err
        # Commit only a complete, validated snapshot, including an empty result.
        days = prune(days, dt_util.now().date())
        await self._store.async_save({"days": [item.as_dict() for item in days]})
        return days

    def async_start_retention(self):
        """Purge expired dates even if the portal is unavailable or polls are rare."""

        @callback
        def midnight(_now):
            if self.data is not None:
                self.data = prune(self.data, dt_util.now().date())
                self._store.async_delay_save(
                    lambda: {"days": [item.as_dict() for item in self.data or []]},
                    1,
                )
                # Keep a prior failure flag; local cleanup must not imply recovery.
                self.async_update_listeners()

        return async_track_time_change(self.hass, midnight, hour=0, minute=0, second=0)
