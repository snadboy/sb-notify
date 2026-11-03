# sb-notify — session notes

| | |
|---|---|
| Repo | github.com/snadboy/sb-notify (private, created 2026-11-02) — local `~/projects/git/sb-notify`, branch `main` |
| Domain | `sb_notify` (MIT), single config entry |
| Design | Claude Doc "Homelab Incidents & Notifications — Design": https://claude.ai/artifact/X25rMcRs4gBMGPqpBrw6jT |
| Tests | `python3 tests/test_register.py` (offline, 20 checks: register rules + card payloads) |
| Validate | `docker run --rm -v "$PWD/custom_components":/github/workspace/custom_components:ro ghcr.io/home-assistant/hassfest:latest` |
| Quick test deploy | `tar czf - --exclude=__pycache__ -C custom_components sb_notify \| ssh snadboy@homeassistant "cd /config/custom_components && sudo tar xzf -"` then a FULL HA restart |
| Release (Marketplace) | bump `manifest.json` version → commit, push → `gh release create vX.Y.Z` → `update.install` on its update entity → confirm files → full restart (never batched with the install). Marketplace needs the repo public, or GitHub connected for a private one. |

## Why it exists (2026-11-02)

PKDB's tier2_backfill failed 1,589 times over 17 days and no alert reached a person: every
alert went to the (non-push) bulletin, and the phone was cluttered with 11 automations'
cards in five groups, none of which ever cleared. User decisions: two groups, **Alerts**
(problems with a lifecycle) and **Notifications** (household status: laundry, Metra,
garage); register lives in HA; name SB Notify.

## Design

- `register.py` — the rules, HA-free; every method returns EFFECTS (show_alert / show_resolved
  / show_notice / clear / event). `render.py` — effects → companion-app payloads, HA-free.
  `__init__.py` — Notifier: Store (`.storage/sb_notify.register`, incl. the head-card
  signature), 30 s tick (started after EVENT_HOMEASSISTANT_STARTED so mobile_app's notify
  service exists), services, `mobile_app_notification_action` listener (`SBN_ACK:<key>`,
  `SBN_SNOOZE:<key>`), head card diffed by (title, message) so it is only sent on change.
- Re-raise: same severity → silent refresh (alert_once), count +1; higher → un-ack,
  un-snooze, loud. Omitted url/source/ttl are kept. Snoozed alerts stay off the phone even
  when re-raised. Resolved cards carry `timeout` AND are cleared by tag when the linger ends.
- A notice with no message is sent untitled with the title as its one line (notify needs a
  message; title + identical message read twice).
- Channels (importance is fixed by Android on first sight): `Alerts: critical` high,
  `Alerts` low, `Alerts: resolved` low, `Alerts: status` min, `Notifications` low,
  `Notifications: with sound` default.

## Verified 2026-11-02 (throwaway HA 2026.11.0b2 container on sdevs, capture script as the phone)

hassfest clean · config flow + options + single-instance abort · raise critical (card +
head) · re-raise silent with count · warning · info not pushed · sensor attrs · phone Ack
and Snooze events · resolve (Resolved card, timeout 900, head updated) · notice show /
replace / clear · register survives a restart. Not yet run on the live HA or a real phone.

## Next steps

1. Live install (needs an HA restart — ask first), add the entry, test against the real phone:
   group bundling, channels, buttons, ordering inside the group.
2. Migrate the homelab automations (Kuma, power, NUT, Matter ×2, utilities watchdog, SDR)
   to raise/resolve; laundry, Metra and garage to notify/clear. Washer watchdog currently
   targets the deleted Pixel 10 device (3b529f2d…) and reaches no one.
3. PKDB: `notify.sh` incident channel (health_check anomaly codes → keys), then retire
   its Gotify route and heartbeat bulletin. Bulletin triage lane reads `sensor.sb_notify_alerts`.
