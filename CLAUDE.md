# sb-notify — session notes

| | |
|---|---|
| Repo | github.com/snadboy/sb-notify (public since 2026-11-17; created 2026-11-02) — local `~/projects/git/sb-notify`, branch `main` |
| Domain | `sb_notify` (MIT), single config entry |
| Design | Claude Doc "Homelab Incidents & Notifications — Design": https://claude.ai/artifact/X25rMcRs4gBMGPqpBrw6jT |
| Tests | `python3 tests/test_register.py` (offline, 26 checks: register rules + card payloads) |
| Validate | `docker run --rm -v "$PWD/custom_components":/github/workspace/custom_components:ro ghcr.io/home-assistant/hassfest:latest` |
| Quick test deploy | `tar czf - --exclude=__pycache__ -C custom_components sb_notify \| ssh snadboy@homeassistant "cd /config/custom_components && sudo tar xzf -"` then a FULL HA restart |
| Release (Marketplace) | Installed through Marketplace since 2026-11-17 (custom repo, v0.3.0); update entity **`update.sb_notify`** (no `_update` suffix, unlike the other SB repos). Bump `manifest.json` version AND `VERSION` in `frontend/sb-notify.js` (the `?v=` cache-buster) → commit, push → `gh release create vX.Y.Z` → `update.install` on `update.sb_notify` → confirm files → full restart, asked for first (never batched with the install). Use this, not the quick deploy, so Marketplace's record matches the files. |

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
  service exists), services, `mobile_app_notification_action` listener (`SBN_DISMISS:<key>`,
  legacy `SBN_ACK:`/`SBN_SNOOZE:`), head card diffed by (title, message) so it is only sent on change.
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

## 2026-11-17 check (two weeks live)

Working: 7 Matter-misbehaving episodes and 2 mass outages opened and resolved themselves, SDR
resolved via its TTL, short Kuma outages resolved, ~30 laundry/Metra notices came and went,
no sb_notify errors in the HA log.

Fixed: the Kuma storm only resolved at **zero** monitors down, so one chronically-down monitor
(ts-svc: unifi-toolkit, down since 11-03) kept `kuma:storm` open as "1 still down" from 11-15,
re-ringing every 4 h as a critical alert (before SB Notify the card was silent with alert_once).
Now the storm ends at **fewer than 5** down and each monitor still down gets its own warning
(repeat over `watched`); unifi-toolkit was removed from the Kuma automation's three lists (re-add
once fixed). Closed by hand: `kuma:storm`, `kuma-ts_svc_unifi_toolkit`, `test:critical`, and
`input_boolean.kuma_storm_active` turned off.

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
2. Decide the always-on `automation.homelab_ongoing_status_card` (direct push, own channel
   `Homelab Status`): keep, fold into the Alerts group, or retire in favour of the head card.

## Migrated (2026-11-03)

| Automation | Now | Key |
| --- | --- | --- |
| `automation.monitor_washer` (Blackshome appliance blueprint) | blueprint push options off; start/watchdog/end custom actions → `sb_notify.notify`; watchdog device list emptied (pointed at the deleted Pixel 10) | `laundry:washer` |
| `automation.monitor_dryer` (same blueprint) | start/end custom actions → `sb_notify.notify` | `laundry:dryer` |
| `automation.metra_commute_delay_push` | delay → notify loud, 3 h; cleared → notify quiet, 30 min | `metra:inbound` / `metra:outbound` |
| `automation.metra_new_schedule_push` | notify quiet, 24 h | `metra:schedule` |
| `automation.power_outage_detect_and_alert` | raise critical, channel `alarm`; spreading + rack-prod CRITICAL `escalate`; restored → resolve | `power:outage` |
| `automation.power_outage_nut_server_unreachable` | raise warning / resolve | `nut:blind:<sensor>` |
| `automation.utilities_watchdog_independent_of_kuma` | kuma-blind raise critical; host-off raise critical + `escalate`; recovered → resolve | `utilities:watchdog` |
| `automation.uptime_kuma_outage_push_replace_in_place` | one monitor: raise warning; 5+: raise critical; recoveries resolve (a monitor recovering during a storm resolves its own too) | `kuma-<monitor>`, `kuma:storm` |
| `automation.matter_misbehaving_devices_replace_in_place_push` | raise warning; recovered → resolve (also resolves the mass alert) | `matter:misbehaving` |
| `automation.matter_mass_unavailable_alert` | raise critical; `wait_template` for the negated trigger → resolve | `matter:mass-unavailable` |
| `automation.sdr_meter_pipeline_stale_alert` | raise critical, ttl 2.5 h, `escalate` on the 2 h re-nag (no all-clear existed) | `sdr:pipeline` |

HA bell (persistent_notification) calls were left as they were. Garage confirm stays a direct
push (needs its own Open/Cancel actions). Old-style cards were cleared by tag on 2026-11-03,
and the one monitor down at the time (unifi-toolkit) was raised into SB Notify by hand.

Found 2026-11-03: `input_datetime.power_outage_started` was stuck at 2026-11-02 11:06 although
all four UPSes were OL — a ~60 s nas + network-gateway blip landed right on the 60 s debounce
and the restore branch never ran (traces gone, cause not proven). While stuck it suppressed
every NUT-blind alert. Reset to the 1970 sentinel by hand.

Old sticky laundry cards (tags `Laundry - Wash`, `Laundry - Dry`, `Laundry - Wash Watchdog`)
were cleared on the phone. Not yet seen through a real wash/dry cycle or Metra delay.
3. PKDB: `notify.sh` incident channel (health_check anomaly codes → keys), then retire
   its Gotify route and heartbeat bulletin. Bulletin triage lane reads `sensor.sb_notify_alerts`.
