"""The register: every open problem (alert) and household notice, and the rules for them.

Pure Python, no Home Assistant import, so the rules can be tested offline. Every
method takes `now` (epoch seconds) and returns a list of EFFECTS for the caller to
carry out; the register itself never talks to a phone:

    {"op": "show_alert", "key": k, "loud": bool}   send/replace the alert's card
    {"op": "show_resolved", "key": k}              replace it with a short "Resolved" card
    {"op": "show_notice", "key": k, "loud": bool}  send/replace a notice's card
    {"op": "clear", "tag": t}                      remove a card from the phone
    {"op": "event", "key": k, "state": s, "severity": v}   an alert changed state

Alerts:  raise → open → (dismiss → dismissed) → resolve → resolved → gone after `resolved`
         secs, into `history`. Raising an open key again only refreshes it; it notifies
         again only when the severity goes UP. `info` alerts are kept and shown in the
         sensor, never pushed.
Dismiss: the card leaves the phone and reminders stop. The alert stays in the register
         until resolved, and comes back to the phone once after `dismiss` seconds if still
         open (0 = never), or at once if its severity goes up. One button, by design
         (2026-11-02): a dismissed problem must not be able to go quiet for good.
Notices: notify → shown, replaced by key → cleared by `clear` or when their ttl runs out.
"""

from __future__ import annotations

from typing import Any

from .const import (
    DEFAULT_NOTICE_TTL, HISTORY_SIZE, SEVERITIES, ST_DISMISSED, ST_OPEN, ST_RESOLVED, TAG_ALERT, TAG_NOTICE,
)


def rank(severity: str) -> int:
    return SEVERITIES.index(severity) if severity in SEVERITIES else 1


def alert_tag(key: str) -> str:
    return TAG_ALERT + key


def notice_tag(key: str) -> str:
    return TAG_NOTICE + key


def _migrate(a: dict) -> dict:
    """0.1.0 stored `acked` + `snoozed_until`; both became dismissed + `returns_at`."""
    if "snoozed_until" in a:
        a["returns_at"] = a.pop("snoozed_until")
    a.setdefault("returns_at", None)
    if a["state"] == "acked":
        a["state"] = ST_DISMISSED
    return a


class Register:
    """`settings` (seconds): critical, warning, resolved, dismiss (0 = a dismissed alert never returns)."""

    def __init__(self, settings: dict[str, float], data: dict | None = None) -> None:
        self.settings = settings
        data = data or {}
        self.alerts: dict[str, dict[str, Any]] = {k: _migrate(a) for k, a in data.get("alerts", {}).items()}
        self.notices: dict[str, dict[str, Any]] = data.get("notices", {})
        self.history: list[dict[str, Any]] = data.get("history", [])

    def dump(self) -> dict:
        return {"alerts": self.alerts, "notices": self.notices, "history": self.history}

    # ── alerts ────────────────────────────────────────────────────────────────

    def raise_(self, key: str, title: str, now: float, *, message: str = "", severity: str = "warning",
               url: str | None = None, source: str | None = None, ttl: float | None = None,
               channel: str | None = None, escalate: bool = False) -> list[dict]:
        """`escalate`: this update is worse even at the same severity (an outage spreading):
        notify with sound and bring the card back if it was dismissed."""
        severity = severity if severity in SEVERITIES else "warning"
        a = self.alerts.get(key)
        if a is None or a["state"] == ST_RESOLVED:
            a = self.alerts[key] = {
                "key": key, "title": title, "message": message, "severity": severity, "url": url,
                "source": source, "ttl": ttl, "channel": channel, "state": ST_OPEN, "first_seen": now, "last_seen": now,
                "count": 1, "notified_at": None, "notify_count": 0, "returns_at": None,
                "resolved_at": None, "resolve_message": None,
            }
            return [self._event(a)] + self._push(a, now, loud=True)

        went_up = rank(severity) > rank(a["severity"])
        a.update(title=title, message=message, severity=severity, last_seen=now)
        for field, value in (("url", url), ("source", source), ("ttl", ttl), ("channel", channel)):   # left out = keep
            if value is not None:
                a[field] = value
        a["count"] += 1
        if went_up or escalate:           # worse than before: back on the phone, loud
            a["state"] = ST_OPEN
            a["returns_at"] = None
            return [self._event(a)] + self._push(a, now, loud=True)
        if a["state"] == ST_DISMISSED:    # dismissed: stays off the phone
            return []
        return self._push(a, now, loud=False, count=False)   # refresh the text silently

    def resolve(self, key: str, now: float, message: str | None = None) -> list[dict]:
        a = self.alerts.get(key)
        if a is None or a["state"] == ST_RESOLVED:
            return []
        on_phone = a["state"] == ST_OPEN and a["notify_count"] > 0
        a.update(state=ST_RESOLVED, resolved_at=now, resolve_message=message, returns_at=None)
        fx = [self._event(a)]
        if on_phone:                      # say so where it was seen, briefly
            fx.append({"op": "show_resolved", "key": key})
        a["on_phone"] = on_phone
        return fx

    def dismiss(self, key: str, now: float) -> list[dict]:
        a = self.alerts.get(key)
        if a is None or a["state"] != ST_OPEN:
            return []
        a["state"] = ST_DISMISSED
        back = self.settings.get("dismiss") or 0
        a["returns_at"] = now + back if back > 0 else None
        fx = [self._event(a)]
        if a["notify_count"]:
            fx.append({"op": "clear", "tag": alert_tag(key)})
        return fx

    # ── notices ───────────────────────────────────────────────────────────────

    def notify(self, key: str, title: str, now: float, *, message: str = "", url: str | None = None,
               ttl: float | None = None, loud: bool = False) -> list[dict]:
        ttl = DEFAULT_NOTICE_TTL if ttl is None else ttl
        self.notices[key] = {
            "key": key, "title": title, "message": message, "url": url, "loud": loud,
            "posted_at": now, "expires_at": now + ttl if ttl > 0 else None,
        }
        return [{"op": "show_notice", "key": key, "loud": loud}]

    def clear(self, key: str) -> list[dict]:
        if self.notices.pop(key, None) is None:
            return []
        return [{"op": "clear", "tag": notice_tag(key)}]

    # ── time ──────────────────────────────────────────────────────────────────

    def tick(self, now: float) -> list[dict]:
        """Dismissals ending, re-notification, stale TTLs, and retiring what has run its course."""
        fx: list[dict] = []
        s = self.settings
        for key, a in list(self.alerts.items()):
            if a["state"] == ST_RESOLVED:
                if now - a["resolved_at"] >= s["resolved"]:
                    del self.alerts[key]
                    self._remember(a)
                    if a.get("on_phone"):
                        fx.append({"op": "clear", "tag": alert_tag(key)})
                continue
            if a["ttl"] and now - a["last_seen"] > a["ttl"]:
                fx += self.resolve(key, now, "No longer reported; assumed fixed")
                continue
            if a["state"] == ST_DISMISSED:
                if a["returns_at"] is not None and now >= a["returns_at"]:
                    a["returns_at"] = None
                    a["state"] = ST_OPEN
                    fx += [self._event(a)] + self._push(a, now, loud=True)
                continue
            if a["notified_at"] is None:
                continue
            since = now - a["notified_at"]
            if a["severity"] == "critical" and since >= s["critical"]:
                fx += self._push(a, now, loud=True)
            elif a["severity"] == "warning" and a["notify_count"] == 1 and since >= s["warning"]:
                fx += self._push(a, now, loud=True)
        for key, n in list(self.notices.items()):
            if n["expires_at"] is not None and now >= n["expires_at"]:
                fx += self.clear(key)
        return fx

    # ── views ─────────────────────────────────────────────────────────────────

    def open_alerts(self) -> list[dict]:
        """Open and dismissed alerts, worst first, then oldest first."""
        live = [a for a in self.alerts.values() if a["state"] != ST_RESOLVED]
        return sorted(live, key=lambda a: (-rank(a["severity"]), a["first_seen"]))

    # ── internals ─────────────────────────────────────────────────────────────

    def _remember(self, a: dict) -> None:
        self.history.insert(0, {k: a.get(k) for k in (
            "key", "title", "severity", "source", "count", "first_seen", "resolved_at", "resolve_message")})
        del self.history[HISTORY_SIZE:]

    def _push(self, a: dict, now: float, *, loud: bool, count: bool = True) -> list[dict]:
        if a["severity"] == "info":
            return []
        if count or a["notified_at"] is None:
            a["notified_at"] = now
            a["notify_count"] += 1
        return [{"op": "show_alert", "key": a["key"], "loud": loud}]

    @staticmethod
    def _event(a: dict) -> dict:
        return {"op": "event", "key": a["key"], "state": a["state"], "severity": a["severity"]}
