# Release notes — 8.3.1

## Picture mode — send the display NAME, not the internal id (8.3.1b2, #116)

- **Root cause of #116 found (credit: @androidnerd's SmartThings CLI
  forensics): `custom.picturemode:setPictureMode` expects the display NAME
  (`"Movie"`), not the internal id (`"modeMovie"`).** Sending the id returns
  `200 COMPLETED` while doing nothing on the panel; sending the name actuates
  it. This also demystifies the "PAT worked, OAuth didn't" symptom: the legacy
  PAT-era code sent plain names, and the name→id mapping was introduced
  together with OAuth support — correlation, not an OAuth block.
- The integration now tries each capability with the **name first, then the
  id**, verifying each accepted send as before, and **memorizes the verified
  (capability + argument form) pair** (persisted across restarts) so the
  matrix cost is only paid on the first change.
- Verification now accepts both representations of the target: some models
  report `pictureMode` as the display name (Frame 2024: `"Dynamique"`), others
  as the id — both are normalized through the name↔id map.

## Art Mode Brightness / Color Temperature — unavailable outside Art Mode (8.3.1b1)

- **The two Art Mode sliders are now *unavailable* whenever the panel is not
  actually displaying Art Mode**, instead of holding (and graphing) a value
  that no longer means anything. These settings only apply to the art display;
  outside Art Mode the TV either can't answer or answers with bogus defaults.
- **Fixes phantom jumps to 100 %**: debug logs showed a standby read right
  after an integration reload returning `brightness = 10` (the TV's max) while
  the panel was off — the slider then displayed 100 % even though nobody set
  it. The art-mode gate is now cross-checked against the Frame Art sensor
  (which correctly knew the TV was off during that window), so stale
  media-player state right after a reload can no longer let a bogus read
  through.
- History becomes honest: gaps while the TV is off/normal viewing, real values
  while art is displayed.
- ⚠️ **Automations note**: if you have automations that set the Art Mode
  brightness on a schedule, add a condition that Art Mode is actually on
  (`art_mode_status == "on"` / the Frame Art switch) — setting the value while
  the entity is unavailable is pointless (the panel isn't showing art) and may
  be skipped by Home Assistant.
- Known Samsung behaviour, unchanged by this release: some 2024 Frames reset
  the art brightness to maximum on their own after a power cycle. If that
  bothers you, an opt-in "re-apply last brightness on Art Mode entry" can be
  added later — open an issue.
