"""Constants for SB Notify."""

DOMAIN = "sb_notify"

# Severities, quietest first; the index is the rank used to tell "went up".
SEVERITIES = ["info", "warning", "critical"]

# Alert states.
ST_OPEN = "open"
ST_ACKED = "acked"
ST_RESOLVED = "resolved"      # lingers on the phone for `resolved_minutes`, then is removed

# Options (config entry) and their defaults.
CONF_NOTIFY = "notify_service"
CONF_CRITICAL_HOURS = "critical_renotify_hours"
CONF_WARNING_HOURS = "warning_renotify_hours"
CONF_RESOLVED_MINUTES = "resolved_minutes"
CONF_SNOOZE_HOURS = "snooze_hours"
CONF_HEAD = "head_card"
DEFAULTS = {
    CONF_NOTIFY: "notify.mobile_app_pixel_snadboy",
    CONF_CRITICAL_HOURS: 4.0,     # critical re-notifies this often until acked
    CONF_WARNING_HOURS: 24.0,     # warning re-notifies ONCE, this long after it opened
    CONF_RESOLVED_MINUTES: 15.0,  # a "Resolved" card stays this long, then clears itself
    CONF_SNOOZE_HOURS: 4.0,       # the phone's Snooze button
    CONF_HEAD: True,              # "Alerts: 2 open · 1 critical" status card at the top of the group
}

DEFAULT_NOTICE_TTL = 4 * 3600     # a notice with no ttl clears itself after this long

# Android grouping. Two groups by design (2026-11-02): problems vs household notices.
GROUP_ALERTS = "sb-notify-alerts"
GROUP_NOTICES = "sb-notify-notifications"

# Android notification channels. A channel's importance is fixed when the phone first
# sees it, so loud and quiet traffic use different channels, not a flag.
CH_CRITICAL = "Alerts: critical"
CH_WARNING = "Alerts"
CH_RESOLVED = "Alerts: resolved"
CH_HEAD = "Alerts: status"
CH_NOTICE = "Notifications"
CH_NOTICE_LOUD = "Notifications: with sound"

TAG_HEAD = "sbn-head"
TAG_ALERT = "sbn-a:"              # + key
TAG_NOTICE = "sbn-n:"             # + key

# Phone action ids: "<prefix><key>". The key may itself contain ':' or '|'.
ACTION_ACK = "SBN_ACK:"
ACTION_SNOOZE = "SBN_SNOOZE:"

STORE_KEY = f"{DOMAIN}.register"
STORE_VERSION = 1
TICK_SECONDS = 30

SIGNAL_UPDATE = f"{DOMAIN}_update"
EVENT_ALERT = f"{DOMAIN}_alert"   # fired on every alert transition: key, state, severity
