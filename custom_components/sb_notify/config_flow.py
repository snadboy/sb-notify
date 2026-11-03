"""One entry (no settings needed to add it); the options hold the phone and the timings."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers import selector

from .const import (
    CONF_CRITICAL_HOURS, CONF_HEAD, CONF_NOTIFY, CONF_RESOLVED_MINUTES, CONF_SNOOZE_HOURS, CONF_WARNING_HOURS,
    DEFAULTS, DOMAIN,
)


def _num(lo: float, hi: float, step: float, unit: str) -> selector.NumberSelector:
    return selector.NumberSelector(selector.NumberSelectorConfig(
        min=lo, max=hi, step=step, unit_of_measurement=unit, mode=selector.NumberSelectorMode.BOX))


class SbNotifyConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None):
        await self.async_set_unique_id(DOMAIN)
        self._abort_if_unique_id_configured()
        return self.async_create_entry(title="SB Notify", data={}, options=dict(DEFAULTS))

    @staticmethod
    @callback
    def async_get_options_flow(entry: config_entries.ConfigEntry) -> config_entries.OptionsFlow:
        return SbNotifyOptionsFlow()


class SbNotifyOptionsFlow(config_entries.OptionsFlow):
    async def async_step_init(self, user_input: dict[str, Any] | None = None):
        if user_input is not None:
            return self.async_create_entry(data=user_input)
        o = {**DEFAULTS, **self.config_entry.options}
        schema = vol.Schema({
            vol.Required(CONF_NOTIFY, default=o[CONF_NOTIFY]): selector.TextSelector(),
            vol.Required(CONF_CRITICAL_HOURS, default=o[CONF_CRITICAL_HOURS]): _num(0.25, 48, 0.25, "h"),
            vol.Required(CONF_WARNING_HOURS, default=o[CONF_WARNING_HOURS]): _num(1, 168, 1, "h"),
            vol.Required(CONF_RESOLVED_MINUTES, default=o[CONF_RESOLVED_MINUTES]): _num(1, 240, 1, "min"),
            vol.Required(CONF_SNOOZE_HOURS, default=o[CONF_SNOOZE_HOURS]): _num(0.25, 48, 0.25, "h"),
            vol.Required(CONF_HEAD, default=o[CONF_HEAD]): selector.BooleanSelector(),
        })
        return self.async_show_form(step_id="init", data_schema=schema)
