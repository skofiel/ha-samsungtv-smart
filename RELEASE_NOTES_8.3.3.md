# Release notes — 8.3.3

## Picture mode — the option list now follows the active input (8.3.3b1, #116)

- **Fix: the Picture Mode dropdown could get stuck on the wrong input's modes.**
  Samsung's picture-mode list is **per-input** — a PC / Graphic source exposes
  only `Entertain` / `Graphic`, a normal source (TV, HDMI/AVR) exposes
  `Movie` / `Standard` / `Dynamic` / … The integration fetched
  `supportedPictureModes` **once at startup** and afterwards only *appended*
  newly-seen modes, so:
  - leaving the TV on a PC input, turning it off, then coming back on a normal
    input left the dropdown stuck on `Entertain` / `Graphic`;
  - selecting a valid mode on the remote *added* it to the list but kept the
    stale PC modes — producing a bogus **merged list of two source profiles**;
  - even restarting Home Assistant didn't clear it.
  This broke automations, since standard modes (`Movie`, `Standard`) were
  flagged as invalid choices for the active input.
- **The supported-mode list is now rebuilt from the cloud on every poll**
  (the data was already in the same response we fetch for the current mode, so
  there's no extra API call). Stale modes from a previous input are dropped
  instead of accumulating.
- **Instant refresh on input switch (8.3.3b2):** the picture-mode select now
  watches the media player's `source` and forces a refresh the moment the
  input changes, so the dropdown updates right away instead of waiting for the
  next SmartThings poll — matching the official SmartThings app.
