"""Real Home Assistant tests; Linux CI installs the HA test plugin."""

from datetime import date, datetime, timedelta
from unittest.mock import AsyncMock, patch

import pytest

pytest.importorskip("homeassistant")

from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_USERNAME  # noqa: E402
from homeassistant.data_entry_flow import FlowResultType  # noqa: E402
from homeassistant.helpers import config_validation as cv  # noqa: E402
from homeassistant.helpers.update_coordinator import UpdateFailed  # noqa: E402
from homeassistant.util import dt as dt_util  # noqa: E402
from pytest_homeassistant_custom_component.common import MockConfigEntry  # noqa: E402

from custom_components.obiado.calendar import ObiadoCalendar  # noqa: E402
from custom_components.obiado.const import (  # noqa: E402
    CONF_CHILD_ID,
    CONF_CHILD_NAME,
    CONF_REFRESH_HOURS,
    DOMAIN,
)
from custom_components.obiado.coordinator import ObiadoCoordinator  # noqa: E402
from custom_components.obiado.models import InvalidAuth, MealDay, ObiadoError  # noqa: E402


async def test_initial_form_can_be_serialized_for_frontend(hass):
    """Regression: successful flow creation alone does not exercise serialization."""
    from probatio.codecs.fields import to_field_list

    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    assert result["type"] is FlowResultType.FORM
    fields = to_field_list(result["data_schema"], custom_serializer=cv.custom_serializer)
    interval = next(field for field in fields if field["name"] == CONF_REFRESH_HOURS)
    assert interval["selector"]["number"]["mode"] == "box"
    assert interval["default"] == 6


async def test_options_form_can_be_serialized_for_frontend(hass, entry):
    from probatio.codecs.fields import to_field_list

    result = await hass.config_entries.options.async_init(entry.entry_id)
    fields = to_field_list(result["data_schema"], custom_serializer=cv.custom_serializer)
    assert fields[0]["selector"]["number"]["max"] == 168


@pytest.fixture(autouse=True)
def enable_integration(enable_custom_integrations):
    yield


@pytest.fixture
def entry(hass):
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="test-child",
        data={
            CONF_HOST: "rpk.obiado.pl",
            CONF_USERNAME: "test@example.invalid",
            CONF_PASSWORD: "test-only",
            CONF_CHILD_NAME: "Testowy Jan",
            CONF_CHILD_ID: 20,
            CONF_REFRESH_HOURS: 6,
        },
    )
    entry.add_to_hass(hass)
    return entry


async def test_coordinator_replaces_snapshot_and_keeps_it_on_failure(hass, entry):
    client = AsyncMock()
    coordinator = ObiadoCoordinator(hass, entry, client)
    coordinator._store = AsyncMock()
    old = MealDay(dt_util.now().date(), ("Old",))
    new = MealDay(old.day, ("New",))
    coordinator.data = [old]
    client.fetch_orders.return_value = [new]
    await coordinator.async_refresh()
    assert coordinator.data == [new]
    client.fetch_orders.side_effect = ObiadoError("offline")
    with pytest.raises(UpdateFailed):
        await coordinator._async_update_data()
    assert coordinator.data == [new]
    client.fetch_orders.side_effect = None
    client.fetch_orders.return_value = []
    await coordinator.async_refresh()
    assert coordinator.data == []
    assert coordinator.update_interval == timedelta(hours=6)


async def test_calendar_all_day_and_exclusive_range(hass, entry):
    coordinator = ObiadoCoordinator(hass, entry, AsyncMock())
    today = dt_util.now().date()
    coordinator.data = [MealDay(today, ("Zupa", "Napój"))]
    entity = ObiadoCalendar(coordinator, entry)
    start = dt_util.start_of_local_day(today)
    events = await entity.async_get_events(hass, start, start + timedelta(days=1))
    assert len(events) == 1
    assert isinstance(events[0].start, date) and not isinstance(events[0].start, datetime)
    assert events[0].end == today + timedelta(days=1)
    assert events[0].summary == "Obiad — Zupa · Napój"
    assert events[0].description == "Posiłki — Testowy Jan\n\n• Zupa\n\n• Napój"
    assert entity.event.summary == events[0].summary
    assert await entity.async_get_events(hass, start - timedelta(days=1), start) == []
    assert entity.supported_features == 0


async def test_user_flow_and_duplicate(hass):
    data = {
        CONF_HOST: "rpk.obiado.pl",
        CONF_USERNAME: "test@example.invalid",
        CONF_PASSWORD: "test-only",
        CONF_CHILD_NAME: "Testowy Jan",
        CONF_REFRESH_HOURS: 6,
    }
    with (
        patch("custom_components.obiado.config_flow.ObiadoClient") as client,
        patch("custom_components.obiado.async_setup_entry", return_value=True),
    ):
        client.return_value.resolve_child = AsyncMock(return_value=20)
        client.return_value.fetch_orders = AsyncMock(return_value=[])
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": "user"}, data=data
        )
        assert result["type"] is FlowResultType.CREATE_ENTRY
        await hass.async_block_till_done()
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": "user"}, data=data
        )
        assert result["reason"] == "already_configured"


async def test_bad_login_does_not_create_entry(hass):
    with patch("custom_components.obiado.config_flow.ObiadoClient") as client:
        client.return_value.resolve_child = AsyncMock(side_effect=InvalidAuth())
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": "user"},
            data={
                CONF_HOST: "rpk.obiado.pl",
                CONF_USERNAME: "test@example.invalid",
                CONF_PASSWORD: "test-only",
                CONF_CHILD_NAME: "Testowy Jan",
                CONF_REFRESH_HOURS: 6,
            },
        )
        assert result["type"] is FlowResultType.FORM
        assert result["errors"] == {"base": "invalid_auth"}


async def test_options_flow(hass, entry):
    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] is FlowResultType.FORM
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], user_input={CONF_REFRESH_HOURS: 12}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert entry.options[CONF_REFRESH_HOURS] == 12
