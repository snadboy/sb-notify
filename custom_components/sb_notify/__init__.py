"""SB Notify — one door for phone notifications, in two Android groups.

Alerts (something is broken): `sb_notify.raise` / `.resolve` / `.dismiss` keep a register
of open problems keyed by a stable `key`. A new problem notifies; raising it again only
refreshes its card; critical re-notifies until dismissed; a resolved card clears itself.
The card's one button, Dismiss, takes it off the phone; it comes back once after a day
if the problem is still open.

Notifications (household status): `sb_notify.notify` / `.clear` show one card per key,
replaced in place and cleared when its ttl runs out.

The rules live in register.py and the card layouts in render.py (both HA-free and
tested offline); this module stores the register, runs the clock and talks to the phone.
External systems (PKDB, Windmill, Ansible) call the same services over HA's REST API.

The sidebar page (/sb-notify) is one JS module served by this integration. It reads the
two sensors' attributes and calls the services, so it needs no API of its own.
"""

from __future__ import annotations

import logging
import time
from datetime import timedelta
from pathlib import Path
from typing import Any

import voluptuous as vol

from homeassistant.components import frontend, panel_custom
from homeassistant.components.http import StaticPathConfig
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EVENT_HOMEASSISTANT_STARTED, Platform
from homeassistant.core import CoreState, Event, HomeAssistant, ServiceCall, callback
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.storage import Store
from homeassistant.loader import async_get_integration
from homeassistant.util import dt as dt_util

from . import render
from .const import (
    ACTION_DISMISS, CONF_CRITICAL_HOURS, CONF_DISMISS_HOURS, CONF_HEAD, CONF_NOTIFY, CONF_RESOLVED_MINUTES,
    CONF_WARNING_HOURS, DEFAULTS, DOMAIN, EVENT_ALERT, LEGACY_ACTIONS, PANEL_URL, SEVERITIES, SIGNAL_UPDATE,
    STATIC_URL, STORE_KEY, STORE_VERSION, TAG_HEAD, TICK_SECONDS,
)
from .register import Register

_LOGGER = logging.getLogger(__name__)
PLATFORMS = [Platform.SENSOR]

_secs = vol.All(cv.time_period, lambda td: td.total_seconds())
SCHEMAS = {
    "raise": vol.Schema({
        vol.Required("key"): cv.string,
        vol.Required("title"): cv.string,
        vol.Optional("message", default=""): cv.string,
        vol.Optional("severity", default="warning"): vol.In(SEVERITIES),
        vol.Optional("url"): cv.string,
        vol.Optional("source"): cv.string,
        vol.Optional("ttl"): _secs,
        vol.Optional("channel"): cv.string,
        vol.Optional("escalate", default=False): cv.boolean,
    }),
    "resolve": vol.Schema({vol.Required("key"): cv.string, vol.Optional("message"): cv.string}),
    "dismiss": vol.Schema({vol.Required("key"): cv.string}),
    "notify": vol.Schema({
        vol.Required("key"): cv.string,
        vol.Required("title"): cv.string,
        vol.Optional("message", default=""): cv.string,
        vol.Optional("url"): cv.string,
        vol.Optional("ttl"): _secs,
        vol.Optional("loud", default=False): cv.boolean,
    }),
    "clear": vol.Schema({vol.Required("key"): cv.string}),
}


def _since(t: float) -> str:
    return dt_util.as_local(dt_util.utc_from_timestamp(t)).strftime("%b %-d %H:%M")


class Notifier:
    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.hass = hass
        self.opts = {**DEFAULTS, **entry.options}
        self.store = Store(hass, STORE_VERSION, STORE_KEY)
        self.register = Register(self._seconds())
        self._head: tuple | None = None
        self._unsubs: list = []

    def _seconds(self) -> dict[str, float]:
        o = self.opts
        return {"critical": o[CONF_CRITICAL_HOURS] * 3600, "warning": o[CONF_WARNING_HOURS] * 3600,
                "resolved": o[CONF_RESOLVED_MINUTES] * 60, "dismiss": o[CONF_DISMISS_HOURS] * 3600}

    async def async_load(self) -> None:
        data = await self.store.async_load() or {}
        self.register = Register(self._seconds(), data)
        head = data.get("head")
        self._head = tuple(head) if head else None

    @callback
    def start(self) -> None:
        self._unsubs.append(self.hass.bus.async_listen("mobile_app_notification_action", self._on_action))

        async def _tick(_now=None) -> None:
            await self.apply(self.register.tick(time.time()))

        @callback
        def _go(_event: Event | None = None) -> None:
            self._unsubs.append(async_track_time_interval(self.hass, _tick, timedelta(seconds=TICK_SECONDS)))
            self.hass.async_create_task(_tick())

        # The phone's notify service only exists once mobile_app is up: start the clock then.
        if self.hass.state is CoreState.running:
            _go()
        else:
            self._unsubs.append(self.hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STARTED, _go))

    @callback
    def stop(self) -> None:
        while self._unsubs:
            self._unsubs.pop()()

    # ── services ──────────────────────────────────────────────────────────────

    async def handle(self, call: ServiceCall) -> None:
        d: dict[str, Any] = dict(call.data)
        now = time.time()
        r = self.register
        match call.service:
            case "raise":
                fx = r.raise_(d.pop("key"), d.pop("title"), now, **d)
            case "resolve":
                fx = r.resolve(d["key"], now, d.get("message"))
            case "dismiss":
                fx = r.dismiss(d["key"], now)
            case "notify":
                fx = r.notify(d.pop("key"), d.pop("title"), now, **d)
            case "clear":
                fx = r.clear(d["key"])
        await self.apply(fx)

    async def _on_action(self, event: Event) -> None:
        action = str(event.data.get("action") or "")
        for prefix in (ACTION_DISMISS, *LEGACY_ACTIONS):
            if action.startswith(prefix):
                await self.apply(self.register.dismiss(action[len(prefix):], time.time()))
                return

    # ── effects ───────────────────────────────────────────────────────────────

    async def apply(self, fx: list[dict]) -> None:
        r = self.register
        now = time.time()
        for f in fx:
            match f["op"]:
                case "event":
                    self.hass.bus.async_fire(EVENT_ALERT, {k: f[k] for k in ("key", "state", "severity")})
                case "show_alert":
                    await self._send(render.alert(r.alerts[f["key"]], loud=f["loud"], since=_since))
                case "show_resolved":
                    await self._send(render.resolved(r.alerts[f["key"]], linger_seconds=r.settings["resolved"]))
                case "show_notice":
                    await self._send(render.notice(r.notices[f["key"]], now=now))
                case "clear":
                    await self._send(render.clear(f["tag"]))
        await self._update_head()
        if fx:
            self.store.async_delay_save(lambda: {**r.dump(), "head": list(self._head) if self._head else None}, 1)
            async_dispatcher_send(self.hass, SIGNAL_UPDATE)

    async def _update_head(self) -> None:
        card = render.head(self.register.open_alerts()) if self.opts[CONF_HEAD] else None
        sig = (card["title"], card["message"]) if card else None
        if sig == self._head:
            return
        self._head = sig
        await self._send(card or render.clear(TAG_HEAD))

    async def _send(self, payload: dict) -> None:
        domain, _, service = self.opts[CONF_NOTIFY].partition(".")
        try:
            await self.hass.services.async_call(domain, service, payload, blocking=True)
        except Exception:  # noqa: BLE001 — one failed send must not stop the rest, or the register
            _LOGGER.warning("SB Notify: %s.%s failed for %s", domain, service, payload.get("data", {}).get("tag"),
                            exc_info=True)


async def _register_panel(hass: HomeAssistant) -> None:
    """The sidebar page. Once per HA run: an options change reloads the entry, not this."""
    if hass.data.get(f"{DOMAIN}_panel"):
        return
    hass.data[f"{DOMAIN}_panel"] = True
    integration = await async_get_integration(hass, DOMAIN)
    try:
        await hass.http.async_register_static_paths(
            [StaticPathConfig(STATIC_URL, str(Path(__file__).parent / "frontend"), False)])
        await panel_custom.async_register_panel(
            hass, frontend_url_path=PANEL_URL, webcomponent_name="sb-notify-panel", sidebar_title="SB Notify",
            sidebar_icon="mdi:bell-badge-outline", module_url=f"{STATIC_URL}/sb-notify.js?v={integration.version}",
            embed_iframe=False, require_admin=False)
    except Exception:  # noqa: BLE001 — the page is a convenience; the notifications must work without it
        _LOGGER.exception("SB Notify: could not register the sidebar page")


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    await _register_panel(hass)
    notifier = Notifier(hass, entry)
    await notifier.async_load()
    entry.runtime_data = notifier
    hass.data[DOMAIN] = notifier
    for name, schema in SCHEMAS.items():
        hass.services.async_register(DOMAIN, name, notifier.handle, schema=schema)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    notifier.start()
    entry.async_on_unload(entry.add_update_listener(_reload))
    return True


async def _reload(hass: HomeAssistant, entry: ConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    notifier: Notifier = entry.runtime_data
    notifier.stop()
    await notifier.store.async_save({**notifier.register.dump(),
                                     "head": list(notifier._head) if notifier._head else None})
    for name in SCHEMAS:
        hass.services.async_remove(DOMAIN, name)
    hass.data.pop(DOMAIN, None)
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def async_remove_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Integration deleted: take the page out of the sidebar too."""
    if hass.data.pop(f"{DOMAIN}_panel", None):
        frontend.async_remove_panel(hass, PANEL_URL)
