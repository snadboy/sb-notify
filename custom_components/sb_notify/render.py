"""What each card looks like on the phone: register entries → HA Android notify payloads.

Pure Python. `since(epoch) -> str` formats a time for the card ("Oct 16 21:15"), and is
passed in so this module needs no time zone of its own.

Companion-app fields used (https://companion.home-assistant.io/docs/notifications/):
tag (replace in place), group (bundle), channel + importance (sound), alert_once
(update without sound), sticky (stays after a tap), timeout (seconds until it clears
itself), clickAction (where a tap goes), actions (buttons → mobile_app_notification_action).
"""

from __future__ import annotations

from collections.abc import Callable

from .const import (
    ACTION_ACK, ACTION_SNOOZE, CH_CRITICAL, CH_HEAD, CH_NOTICE, CH_NOTICE_LOUD, CH_RESOLVED, CH_WARNING,
    GROUP_ALERTS, GROUP_NOTICES, ST_ACKED, TAG_HEAD,
)
from .register import alert_tag, notice_tag

CLEAR = "clear_notification"


def alert(a: dict, *, loud: bool, since: Callable[[float], str], snooze_hours: float) -> dict:
    critical = a["severity"] == "critical"
    acked = a["state"] == ST_ACKED
    bits = [f"since {since(a['first_seen'])}"]
    if a["count"] > 1:
        bits.append(f"{a['count']:,} times")
    if acked:
        bits.append("acknowledged")
    message = "\n".join(p for p in (a["message"], " · ".join(bits)) if p)
    actions = []
    if not acked:
        actions.append({"action": ACTION_ACK + a["key"], "title": "Ack"})
    actions.append({"action": ACTION_SNOOZE + a["key"], "title": f"Snooze {snooze_hours:g} h"})
    if a.get("url"):
        actions.append({"action": "URI", "title": "Open", "uri": a["url"]})
    data = {
        "tag": alert_tag(a["key"]),
        "group": GROUP_ALERTS,
        "channel": CH_CRITICAL if critical else CH_WARNING,
        "importance": "high" if critical else "low",
        "alert_once": not loud,
        "sticky": True,
        "actions": actions,
    }
    if a.get("url"):
        data["clickAction"] = a["url"]
    return {"title": a["title"], "message": message, "data": data}


def resolved(a: dict, *, linger_seconds: float) -> dict:
    data = {
        "tag": alert_tag(a["key"]),
        "group": GROUP_ALERTS,
        "channel": CH_RESOLVED,
        "importance": "low",
        "alert_once": True,
        "timeout": int(linger_seconds),
    }
    if a.get("url"):
        data["clickAction"] = a["url"]
    return {"title": f"Resolved: {a['title']}", "message": a.get("resolve_message") or "Back to normal", "data": data}


def notice(n: dict, *, now: float) -> dict:
    data = {
        "tag": notice_tag(n["key"]),
        "group": GROUP_NOTICES,
        "channel": CH_NOTICE_LOUD if n["loud"] else CH_NOTICE,
        "importance": "default" if n["loud"] else "low",
        "alert_once": not n["loud"],
        "sticky": True,
    }
    if n["expires_at"] is not None:
        data["timeout"] = max(1, int(n["expires_at"] - now))
    if n.get("url"):
        data["clickAction"] = n["url"]
    if not n["message"]:                  # notify needs a message: a one-liner goes there, untitled
        return {"message": n["title"], "data": data}
    return {"title": n["title"], "message": n["message"], "data": data}


def head(open_alerts: list[dict]) -> dict | None:
    """The status card at the top of the Alerts group, or None when nothing is open."""
    pushed = [a for a in open_alerts if a["severity"] != "info"]
    if not pushed:
        return None
    crit = sum(1 for a in pushed if a["severity"] == "critical")
    title = f"Alerts: {len(pushed)} open" + (f" · {crit} critical" if crit else "")
    lines = [a["title"] for a in pushed[:3]]
    if len(pushed) > 3:
        lines.append(f"and {len(pushed) - 3} more")
    return {
        "title": title,
        "message": "\n".join(lines),
        "data": {"tag": TAG_HEAD, "group": GROUP_ALERTS, "channel": CH_HEAD, "importance": "min",
                 "alert_once": True, "sticky": True},
    }


def clear(tag: str) -> dict:
    return {"message": CLEAR, "data": {"tag": tag}}
