"""Two sensors: open alerts and live notices — counts, with the entries as attributes.

sensor.sb_notify_alerts is what the bulletin's triage lane and dashboards read.
"""

from __future__ import annotations

from homeassistant.components.sensor import SensorEntity, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import dt as dt_util

from .const import SIGNAL_UPDATE


def _iso(t: float | None) -> str | None:
    return dt_util.utc_from_timestamp(t).isoformat() if t else None


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, add: AddEntitiesCallback) -> None:
    add([AlertsSensor(entry), NoticesSensor(entry)])


class _Base(SensorEntity):
    _attr_should_poll = False
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, entry: ConfigEntry) -> None:
        self.notifier = entry.runtime_data
        self._attr_unique_id = f"{entry.entry_id}_{self._kind}"

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(async_dispatcher_connect(self.hass, SIGNAL_UPDATE, self._refresh))

    @callback
    def _refresh(self) -> None:
        self.async_write_ha_state()


class AlertsSensor(_Base):
    _kind = "alerts"
    _attr_name = "SB Notify alerts"
    _attr_icon = "mdi:alert-circle-outline"

    @property
    def native_value(self) -> int:
        return len(self.notifier.register.open_alerts())

    @property
    def extra_state_attributes(self) -> dict:
        alerts = self.notifier.register.open_alerts()
        return {
            "critical": sum(1 for a in alerts if a["severity"] == "critical"),
            "alerts": [{
                "key": a["key"], "title": a["title"], "message": a["message"], "severity": a["severity"],
                "state": a["state"], "source": a["source"], "url": a["url"], "count": a["count"],
                "first_seen": _iso(a["first_seen"]), "last_seen": _iso(a["last_seen"]),
                "snoozed_until": _iso(a["snoozed_until"]),
            } for a in alerts],
        }


class NoticesSensor(_Base):
    _kind = "notifications"
    _attr_name = "SB Notify notifications"
    _attr_icon = "mdi:bell-outline"

    @property
    def native_value(self) -> int:
        return len(self.notifier.register.notices)

    @property
    def extra_state_attributes(self) -> dict:
        return {"notifications": [{
            "key": n["key"], "title": n["title"], "message": n["message"], "url": n["url"],
            "posted_at": _iso(n["posted_at"]), "expires_at": _iso(n["expires_at"]),
        } for n in sorted(self.notifier.register.notices.values(), key=lambda n: -n["posted_at"])]}
