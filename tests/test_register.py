"""Offline checks for register.py and render.py.   python3 tests/test_register.py   (or pytest)

The package's __init__ imports Home Assistant, so the pure modules are loaded under a
stand-in package that never runs it.
"""

import importlib
import pathlib
import sys
import types

_pkg = types.ModuleType("sbn")
_pkg.__path__ = [str(pathlib.Path(__file__).resolve().parents[1] / "custom_components" / "sb_notify")]
sys.modules["sbn"] = _pkg
R = importlib.import_module("sbn.register")
V = importlib.import_module("sbn.render")
C = importlib.import_module("sbn.const")

H = 3600
SETTINGS = {"critical": 4 * H, "warning": 24 * H, "resolved": 15 * 60, "snooze": 4 * H}
since = lambda t: f"t{int(t)}"  # noqa: E731


def ops(fx, op=None):
    return [f for f in fx if op is None or f["op"] == op]


def shows(fx):
    return [(f["key"], f["loud"]) for f in ops(fx, "show_alert")]


def test_raise_new_notifies_loud_and_fires_event():
    r = R.Register(SETTINGS)
    fx = r.raise_("pkdb:task:tier2", "tier2 failing", 0, severity="critical")
    assert shows(fx) == [("pkdb:task:tier2", True)]
    assert ops(fx, "event")[0]["state"] == "open"


def test_reraise_same_severity_is_silent_and_counts():
    r = R.Register(SETTINGS)
    r.raise_("k", "t", 0)
    fx = r.raise_("k", "t", 60, message="new text")
    assert shows(fx) == [("k", False)]
    a = r.alerts["k"]
    assert a["count"] == 2 and a["message"] == "new text" and a["notify_count"] == 1


def test_reraise_higher_severity_unacks_and_notifies_loud():
    r = R.Register(SETTINGS)
    r.raise_("k", "t", 0, severity="warning")
    r.ack("k", 10)
    fx = r.raise_("k", "t", 20, severity="critical")
    assert shows(fx) == [("k", True)]
    assert r.alerts["k"]["state"] == "open"


def test_info_never_pushes():
    r = R.Register(SETTINGS)
    assert shows(r.raise_("k", "t", 0, severity="info")) == []
    assert shows(r.tick(10 * 24 * H)) == []
    assert ops(r.resolve("k", 1), "show_resolved") == []


def test_critical_renotifies_every_4h_until_acked():
    r = R.Register(SETTINGS)
    r.raise_("k", "t", 0, severity="critical")
    assert shows(r.tick(4 * H - 1)) == []
    assert shows(r.tick(4 * H)) == [("k", True)]
    assert shows(r.tick(8 * H)) == [("k", True)]
    r.ack("k", 8 * H + 1)
    assert shows(r.tick(20 * H)) == []


def test_warning_renotifies_once():
    r = R.Register(SETTINGS)
    r.raise_("k", "t", 0)
    assert shows(r.tick(24 * H)) == [("k", True)]
    assert shows(r.tick(48 * H)) == []


def test_snooze_clears_then_comes_back():
    r = R.Register(SETTINGS)
    r.raise_("k", "t", 0, severity="critical")
    fx = r.ack("k", 100, snooze=4 * H)
    assert ops(fx, "clear") == [{"op": "clear", "tag": "sbn-a:k"}]
    assert shows(r.raise_("k", "t", 200)) == []        # still snoozed: stays off the phone
    assert shows(r.tick(100 + 4 * H)) == [("k", True)]
    assert r.alerts["k"]["state"] == "open"


def test_resolve_shows_resolved_then_clears_and_forgets():
    r = R.Register(SETTINGS)
    r.raise_("k", "t", 0)
    fx = r.resolve("k", 50, "fixed")
    assert ops(fx, "show_resolved") and ops(fx, "event")[0]["state"] == "resolved"
    assert r.open_alerts() == []
    assert ops(r.tick(50 + 15 * 60 - 1), "clear") == []
    assert ops(r.tick(50 + 15 * 60), "clear") == [{"op": "clear", "tag": "sbn-a:k"}]
    assert "k" not in r.alerts


def test_raise_after_resolve_is_a_new_incident():
    r = R.Register(SETTINGS)
    r.raise_("k", "t", 0)
    r.raise_("k", "t", 10)
    r.resolve("k", 20)
    fx = r.raise_("k", "t", 30)
    assert shows(fx) == [("k", True)] and r.alerts["k"]["count"] == 1


def test_ttl_resolves_stale_alert():
    r = R.Register(SETTINGS)
    r.raise_("k", "t", 0, ttl=2 * H)
    assert ops(r.tick(2 * H), "event") == []
    fx = r.tick(2 * H + 1)
    assert ops(fx, "event")[0]["state"] == "resolved"


def test_resolve_and_ack_unknown_keys_are_noops():
    r = R.Register(SETTINGS)
    assert r.resolve("nope", 0) == [] and r.ack("nope", 0) == []


def test_open_alerts_worst_then_oldest():
    r = R.Register(SETTINGS)
    r.raise_("w1", "w1", 0)
    r.raise_("c1", "c1", 5, severity="critical")
    r.raise_("w0", "w0", -5)
    assert [a["key"] for a in r.open_alerts()] == ["c1", "w0", "w1"]


def test_notice_replace_expire_and_clear():
    r = R.Register(SETTINGS)
    assert ops(r.notify("laundry:dryer", "Dryer running", 0, ttl=0), "show_notice")
    assert r.notices["laundry:dryer"]["expires_at"] is None
    r.notify("laundry:dryer", "Dryer done", 100, ttl=2 * H)
    assert r.notices["laundry:dryer"]["title"] == "Dryer done"
    assert ops(r.tick(100 + 2 * H - 1), "clear") == []
    assert ops(r.tick(100 + 2 * H), "clear") == [{"op": "clear", "tag": "sbn-n:laundry:dryer"}]
    assert r.clear("laundry:dryer") == []


def test_notice_default_ttl():
    r = R.Register(SETTINGS)
    r.notify("k", "t", 0)
    assert r.notices["k"]["expires_at"] == C.DEFAULT_NOTICE_TTL


def test_dump_roundtrip():
    r = R.Register(SETTINGS)
    r.raise_("k", "t", 0, severity="critical")
    r.notify("n", "t", 0)
    r2 = R.Register(SETTINGS, r.dump())
    assert shows(r2.tick(4 * H)) == [("k", True)]


def test_render_alert_buttons_and_channels():
    r = R.Register(SETTINGS)
    r.raise_("k", "PKDB down", 0, severity="critical", url="https://x/", message="m")
    r.raise_("k", "PKDB down", 9, severity="critical", message="m")
    p = V.alert(r.alerts["k"], loud=True, since=since, snooze_hours=4)
    d = p["data"]
    assert d["tag"] == "sbn-a:k" and d["group"] == C.GROUP_ALERTS and d["channel"] == C.CH_CRITICAL
    assert d["alert_once"] is False and d["importance"] == "high"
    assert [x["title"] for x in d["actions"]] == ["Ack", "Snooze 4 h", "Open"]   # url kept on re-raise
    assert p["message"] == "m\nsince t0 · 2 times"
    r.ack("k", 10)
    p = V.alert(r.alerts["k"], loud=False, since=since, snooze_hours=4)
    assert [x["title"] for x in p["data"]["actions"]] == ["Snooze 4 h", "Open"]
    assert "acknowledged" in p["message"] and p["data"]["alert_once"] is True


def test_render_warning_is_quiet_channel():
    r = R.Register(SETTINGS)
    r.raise_("k", "t", 0, url="https://x/")
    d = V.alert(r.alerts["k"], loud=True, since=since, snooze_hours=4)["data"]
    assert d["channel"] == C.CH_WARNING and d["importance"] == "low" and d["clickAction"] == "https://x/"
    assert d["actions"][-1] == {"action": "URI", "title": "Open", "uri": "https://x/"}


def test_render_resolved_times_out():
    r = R.Register(SETTINGS)
    r.raise_("k", "t", 0)
    r.resolve("k", 1)
    p = V.resolved(r.alerts["k"], linger_seconds=900)
    assert p["title"] == "Resolved: t" and p["data"]["timeout"] == 900 and p["data"]["tag"] == "sbn-a:k"


def test_render_notice_timeout_counts_down():
    r = R.Register(SETTINGS)
    r.notify("k", "Dryer done", 0, ttl=7200)
    d = V.notice(r.notices["k"], now=3600)["data"]
    assert d["timeout"] == 3600 and d["group"] == C.GROUP_NOTICES and d["channel"] == C.CH_NOTICE
    r.notify("k", "Garage open?", 0, ttl=0, loud=True)
    p = V.notice(r.notices["k"], now=10)
    assert "timeout" not in p["data"] and p["data"]["channel"] == C.CH_NOTICE_LOUD
    assert p["message"] == "Garage open?" and "title" not in p          # no body: one line, untitled
    r.notify("k", "Dryer done", 0, message="Load 2 of 2")
    assert V.notice(r.notices["k"], now=1)["title"] == "Dryer done"


def test_render_head():
    assert V.head([]) is None
    r = R.Register(SETTINGS)
    r.raise_("i", "info only", 0, severity="info")
    assert V.head(r.open_alerts()) is None
    for i in range(4):
        r.raise_(f"w{i}", f"warn {i}", i)
    r.raise_("c", "crit", 9, severity="critical")
    h = V.head(r.open_alerts())
    assert h["title"] == "Alerts: 5 open · 1 critical"
    assert h["message"].splitlines() == ["crit", "warn 0", "warn 1", "and 2 more"]


if __name__ == "__main__":
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_")]
    for name, fn in tests:
        fn()
        print("ok ", name)
    print(f"{len(tests)} passed")
