"""UI configuration, interval options, and credential renewal."""

import hashlib
import logging
from datetime import timedelta

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import NumberSelector, NumberSelectorConfig, NumberSelectorMode
from homeassistant.util import dt as dt_util

from .api import ObiadoClient
from .const import (
    CONF_CHILD_ID,
    CONF_CHILD_NAME,
    CONF_REFRESH_HOURS,
    DEFAULT_REFRESH_HOURS,
    DOMAIN,
    RETENTION_DAYS,
)
from .models import (
    ChildNotFound,
    InvalidAuth,
    InvalidResponse,
    ObiadoError,
    normalize_host,
    validate_refresh_hours,
)

_LOGGER = logging.getLogger(__name__)

INTERVAL = NumberSelector(
    NumberSelectorConfig(
        min=1,
        max=168,
        step="any",
        mode=NumberSelectorMode.BOX,
    )
)


def schema(defaults=None):
    defaults = defaults or {}
    return vol.Schema(
        {
            vol.Required(CONF_HOST, default=defaults.get(CONF_HOST, "rpk.obiado.pl")): str,
            vol.Required(CONF_USERNAME, default=defaults.get(CONF_USERNAME, "")): str,
            vol.Required(CONF_PASSWORD): str,
            vol.Required(CONF_CHILD_NAME, default=defaults.get(CONF_CHILD_NAME, "")): str,
            vol.Required(
                CONF_REFRESH_HOURS, default=defaults.get(CONF_REFRESH_HOURS, DEFAULT_REFRESH_HOURS)
            ): INTERVAL,
        }
    )


class ObiadoConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def _validate(self, data):
        data[CONF_HOST] = normalize_host(data[CONF_HOST])
        data[CONF_CHILD_NAME] = " ".join(data[CONF_CHILD_NAME].split())
        client = ObiadoClient(
            async_get_clientsession(self.hass),
            data[CONF_HOST],
            data[CONF_USERNAME],
            data[CONF_PASSWORD],
        )
        data[CONF_CHILD_ID] = await client.resolve_child(data[CONF_CHILD_NAME])
        # Check actual calendar access before accepting the configuration.
        await client.fetch_orders(
            data[CONF_CHILD_ID], dt_util.now().date() - timedelta(days=RETENTION_DAYS)
        )
        return data

    async def async_step_user(self, user_input=None):
        errors = {}
        if user_input is not None:
            try:
                interval = validate_refresh_hours(user_input[CONF_REFRESH_HOURS])
            except (ValueError, TypeError):
                return self.async_show_form(
                    step_id="user",
                    data_schema=schema(),
                    errors={CONF_REFRESH_HOURS: "invalid_interval"},
                )
            try:
                data = await self._validate({**user_input, CONF_REFRESH_HOURS: interval})
            except ValueError:
                errors[CONF_HOST] = "invalid_host"
            except InvalidAuth:
                errors["base"] = "invalid_auth"
            except ChildNotFound:
                errors[CONF_CHILD_NAME] = "child_not_found"
            except InvalidResponse as err:
                _LOGGER.error("Obiado setup rejected the response: %s", err)
                errors["base"] = "invalid_response"
            except ObiadoError:
                errors["base"] = "cannot_connect"
            else:
                unique = hashlib.sha256(
                    f"{data[CONF_HOST]}:{data[CONF_CHILD_ID]}".encode()
                ).hexdigest()
                await self.async_set_unique_id(unique)
                self._abort_if_unique_id_configured()
                return self.async_create_entry(title=data[CONF_CHILD_NAME], data=data)
        return self.async_show_form(step_id="user", data_schema=schema(user_input), errors=errors)

    async def async_step_reauth(self, entry_data):
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(self, user_input=None):
        entry = self._get_reauth_entry()
        errors = {}
        if user_input is not None:
            try:
                data = await self._validate({**entry.data, **user_input})
            except InvalidAuth:
                errors["base"] = "invalid_auth"
            except ChildNotFound:
                errors["base"] = "child_not_found"
            except InvalidResponse as err:
                _LOGGER.error("Obiado reauthentication rejected the response: %s", err)
                errors["base"] = "invalid_response"
            except ObiadoError:
                errors["base"] = "cannot_connect"
            else:
                if data[CONF_CHILD_ID] != entry.data[CONF_CHILD_ID]:
                    return self.async_abort(reason="wrong_account")
                return self.async_update_reload_and_abort(entry, data_updates=data)
        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_USERNAME, default=entry.data[CONF_USERNAME]): str,
                    vol.Required(CONF_PASSWORD): str,
                }
            ),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return ObiadoOptionsFlow()


class ObiadoOptionsFlow(config_entries.OptionsFlow):
    async def async_step_init(self, user_input=None):
        errors = {}
        if user_input is not None:
            try:
                interval = validate_refresh_hours(user_input[CONF_REFRESH_HOURS])
            except (ValueError, TypeError):
                errors[CONF_REFRESH_HOURS] = "invalid_interval"
            else:
                return self.async_create_entry(data={CONF_REFRESH_HOURS: interval})
        interval = self.config_entry.options.get(
            CONF_REFRESH_HOURS,
            self.config_entry.data.get(CONF_REFRESH_HOURS, DEFAULT_REFRESH_HOURS),
        )
        return self.async_show_form(
            step_id="init",
            errors=errors,
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_REFRESH_HOURS, default=interval): INTERVAL,
                }
            ),
        )
