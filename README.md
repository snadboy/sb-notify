# SB Notify

One door for phone notifications in Home Assistant, in two Android groups:

- **Alerts**: something is broken. A register of open problems, keyed by a stable `key`.
  A new problem notifies; raising it again only refreshes its card; critical re-notifies
  until acknowledged; Ack / Snooze buttons on the card; a resolved card clears itself.
- **Notifications**: household status (laundry, commute, garage). One card per key,
  replaced in place and cleared when its TTL runs out.

## Services

| Service | Fields | Effect |
| --- | --- | --- |
| `sb_notify.raise` | `key`, `title`, `message`, `severity` (critical / warning / info), `url`, `source`, `ttl` | Open a problem, or refresh it. Notifies again only if severity goes up. `info` never pushes. With `ttl`, it resolves itself if not raised again in time. |
| `sb_notify.resolve` | `key`, `message` | Card becomes "Resolved: …" and clears itself after 15 min. |
| `sb_notify.ack` | `key`, `snooze` | Stops re-notifying. With `snooze`, the card leaves and comes back when the snooze ends if still open. |
| `sb_notify.notify` | `key`, `title`, `message`, `url`, `ttl` (default 4 h, 0 = until cleared), `loud` | Show or replace a notice. |
| `sb_notify.clear` | `key` | Remove a notice. |

| Severity | On open | Re-notify while unacked | Channel |
| --- | --- | --- | --- |
| critical | sound | every 4 h | `Alerts: critical` (high) |
| warning | silent | once, after 24 h | `Alerts` (low) |
| info | none (sensor only) | never | none |

Timings, the phone's notify service and the status card are in the integration's options.

From outside HA (REST, long-lived token):

```bash
curl -X POST https://<ha>/api/services/sb_notify/raise \
  -H "Authorization: Bearer $HA_TOKEN" -H "Content-Type: application/json" \
  -d '{"key":"pkdb:task:tier2_backfill","title":"PKDB: tier2_backfill failing","severity":"critical","source":"pkdb"}'
```

## Entities and events

- `sensor.sb_notify_alerts`: number of open alerts; attributes `critical` and `alerts` (worst first).
- `sensor.sb_notify_notifications`: number of live notices; attribute `notifications`.
- Event `sb_notify_alert` on every alert transition: `key`, `state` (open / acked / resolved), `severity`.

## Phone

Cards use tags `sbn-a:<key>` (alerts), `sbn-n:<key>` (notices) and `sbn-head` (status card),
groups `sb-notify-alerts` and `sb-notify-notifications`. Android sets a channel's sound and
importance the first time it sees the channel; change them afterwards in the phone's
notification settings for the Home Assistant app.
