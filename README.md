# SB Notify

One door for phone notifications in Home Assistant, in two Android groups:

- **Alerts**: something is broken. A register of open problems, keyed by a stable `key`.
  A new problem notifies; raising it again only refreshes its card; critical re-notifies
  until dismissed; a resolved card clears itself. The card has one button, **Dismiss**: it
  takes the card off the phone and stops reminders; the alert stays open (on the sidebar
  page) until resolved, and comes back once after 24 h if still open, or at once if it
  gets worse.
- **Notifications**: household status (laundry, commute, garage). One card per key,
  replaced in place and cleared when its TTL runs out.

## Services

| Service | Fields | Effect |
| --- | --- | --- |
| `sb_notify.raise` | `key`, `title`, `message`, `severity` (critical / warning / info), `url`, `source`, `ttl` | Open a problem, or refresh it. Notifies again only if severity goes up. `info` never pushes. With `ttl`, it resolves itself if not raised again in time. |
| `sb_notify.resolve` | `key`, `message` | Card becomes "Resolved: …" and clears itself after 15 min. |
| `sb_notify.dismiss` | `key` | Card leaves the phone, reminders stop; back once after 24 h if still open (option; 0 = never), at once if severity goes up. |
| `sb_notify.notify` | `key`, `title`, `message`, `url`, `ttl` (default 4 h, 0 = until cleared), `loud` | Show or replace a notice. |
| `sb_notify.clear` | `key` | Remove a notice. |

| Severity | On open | Re-notify while unacked | Channel |
| --- | --- | --- | --- |
| critical | sound | every 4 h until dismissed | `Alerts: critical` (high) |
| warning | silent | once, after 24 h | `Alerts` (low) |
| info | none (sensor only) | never | none |

Timings, the phone's notify service and the status card are in the integration's options.

From outside HA (REST, long-lived token):

```bash
curl -X POST https://<ha>/api/services/sb_notify/raise \
  -H "Authorization: Bearer $HA_TOKEN" -H "Content-Type: application/json" \
  -d '{"key":"pkdb:task:tier2_backfill","title":"PKDB: tier2_backfill failing","severity":"critical","source":"pkdb"}'
```

## Sidebar page

**SB Notify** in the sidebar: open alerts (worst first; dismissed ones dimmed with when they
come back), live notifications with when they clear, and recently resolved alerts. ⋮ on a
row: Dismiss, Mark resolved, Open link / Clear. ⋮ on Alerts: send a test alert or notification.
It needs the **SB UI Kit** integration (a manifest dependency).

## Entities and events

- `sensor.sb_notify_alerts`: number of open alerts; attributes `critical`, `alerts` (worst first) and `recent` (resolved, newest first). The lists are not recorded.
- `sensor.sb_notify_notifications`: number of live notices; attribute `notifications`.
- Event `sb_notify_alert` on every alert transition: `key`, `state` (open / dismissed / resolved), `severity`.

## Phone

Cards use tags `sbn-a:<key>` (alerts), `sbn-n:<key>` (notices) and `sbn-head` (status card),
groups `sb-notify-alerts` and `sb-notify-notifications`. Android sets a channel's sound and
importance the first time it sees the channel; change them afterwards in the phone's
notification settings for the Home Assistant app.
