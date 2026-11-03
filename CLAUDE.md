# sb-notify — session notes

| | |
|---|---|
| Repo | github.com/snadboy/sb-notify (private — making it public was blocked by the permission classifier; the user can flip it) — created 2026-11-02 — local `~/projects/git/sb-notify`, branch `main` |
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
- ONE phone button, **Dismiss** (user, 2026-11-02: "Ack" was jargon; Snooze not worth a second
  button). Dismiss = card off the phone + reminders stop; alert stays open (page/sensor) until
  resolved; back once after `dismiss_return_hours` (24, 0 = never) or at once if severity goes
  up — so a dismissed problem cannot go quiet for good. 0.1.0 `acked`/`snoozed_until` migrate to
  dismissed/`returns_at`; SBN_ACK:/SBN_SNOOZE: presses from old cards count as Dismiss.
- Re-raise: same severity → silent refresh (alert_once), count +1; higher → loud, un-dismissed.
  Omitted url/source/ttl are kept. Dismissed alerts stay off the phone when re-raised.
  Resolved cards carry `timeout` AND are cleared by tag when the linger ends. The head card
  counts only open (not dismissed, not info) alerts.
- Sidebar page `/sb-notify` (`frontend/sb-notify.js`, SB UI Kit rows, depends on sb_ui_kit):
  reads `sensor.sb_notify_alerts` (`alerts`, `recent` = lingering resolved + 30-entry history)
  and `sensor.sb_notify_notifications`; acts via the services. List attributes are in
  `_unrecorded_attributes`. Panel registered once per HA run in async_setup_entry.
- A notice with no message is sent untitled with the title as its one line (notify needs a
  message; title + identical message read twice).
- Channels (importance is fixed by Android on first sight): `Alerts: critical` high,
  `Alerts` low, `Alerts: resolved` low, `Alerts: status` min, `Notifications` low,
  `Notifications: with sound` default.

## Live

0.2.0 deployed to the live HA 2026-11-02 22:23 (quick deploy + restart); entry `01M6FRJ5AT5PE3R9YHN67P6XGK`.
Phone check of 0.1.0 cards done by the user (they used Ack/Snooze → feedback that became Dismiss).
Test keys `test:critical` / `test:warning` may still be in the register — resolve them when done.
Other Claude sessions restart HA too (SB Modes released + restarted at 21:55 and 22:10 the same
evening): check the Supervisor log for a recent restart before doing another.

## Verified 2026-11-02 (throwaway HA 2026.11.0b2 container on sdevs, capture script as the phone)

hassfest clean · config flow + options + single-instance abort · raise critical (card +
head) · re-raise silent with count · warning · info not pushed · sensor attrs · phone Ack
and Snooze events · resolve (Resolved card, timeout 900, head updated) · notice show /
replace / clear · register survives a restart. 0.2.0: Dismiss + legacy Ack event, info
dismiss, resolve → Recently resolved at once; page screenshotted at 1280 px and 412 px (dark),
⋮ menu open, no console errors. Rig: scratchpad `ha_up.sh` + `shot.js` (Chromium from
~/.cache/ms-playwright, playwright module from ~/.npm/_npx); remove the container's root-owned
config with `docker run --rm --entrypoint rm -v …` (a plain rm fails silently on them).

## Next steps

1. Confirm on the real phone: Dismiss button, group bundling, channel sounds, head-card order.
2. Migrate the homelab automations (Kuma, power, NUT, Matter ×2, utilities watchdog, SDR)
   to raise/resolve; laundry, Metra and garage to notify/clear. Washer watchdog currently
   targets the deleted Pixel 10 device (3b529f2d…) and reaches no one.
3. PKDB: `notify.sh` incident channel (health_check anomaly codes → keys), then retire
   its Gotify route and heartbeat bulletin. Bulletin triage lane reads `sensor.sb_notify_alerts`.
