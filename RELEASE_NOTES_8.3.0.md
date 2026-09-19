# Release notes — 8.3.0 (since 8.1.0)

> **Status: stable release.** 8.3.0 is the next stable release after **8.1.0**.
> The 8.2.0 beta was never shipped as a stable release, so **8.3.0 includes
> everything from 8.2.0 as well** — those changes are listed under
> *"Also included from the 8.2.0 beta"* at the bottom.
> Field-validated over several days on two Frame TVs (2024 + 2020, OAuth and
> PAT) through the 8.3.0b1–b16 beta series.

> ℹ️ **Folder Gallery card users:** after updating, **re-open your card in the
> visual editor and save once** (re-selecting the Frame TV entity). This writes
> the new `frame_tv_entity` key so the fullscreen-preview buttons work — see the
> *lightbox buttons* note below.

## Speaker output — no more pointless polls in Art Mode (8.3.0 final)

- The Speaker Select now skips its IP Control poll (and refuses switching, with
  a clear message) while the TV is off or displaying Art — the speaker methods
  answer `-32601` in Art Mode, the same firmware ambiguity as the picture
  calibration. The select goes cleanly unavailable and recovers on its own.

## Frame Art — matte selects apply instantly and stay in sync (8.3.0b16)

- **Changing Matte Type / Matte Color now takes effect on the panel
  immediately** — no helper automation needed anymore. `change_matte` alone
  updates the stored matte but (on 2024 Frames at least) the panel keeps
  showing the old frame until the artwork is re-selected; the selects now
  re-select the current artwork automatically after the change, **only while
  Art Mode is actively displaying** (so a matte change can't wake a sleeping
  panel).
- **The two selects stay in sync with the TV**: they now follow the Frame Art
  sensor's `current_matte_id` (already refreshed every few seconds by the art
  coordinator — zero extra TV traffic), so a matte changed on the TV itself or
  via the other select is reflected within ~30 s. Sync helper automations can
  be removed.
- **Correctness fixes**: matte ids reported upper-cased by the TV
  (`SHADOWBOX_POLAR`) no longer produce mixed-case ids on write; picking a
  *color* while the matte type is `none` now raises a clear "select a matte
  type first" error instead of sending an invalid `none_<color>` id; errors
  surface in the UI instead of being silently logged.
- If you had an automation like *"apply matte on select change"* (calling
  `art_change_matte` + `art_select_image`), **delete it** — keeping it would
  double-apply every change.

## Media player — the volume slider hides when audio goes to an external device (8.3.0b15)

- **When the Speaker Select reports an external output** (HDMI-eARC receiver,
  optical, Bluetooth soundbar), **the media player drops the absolute volume
  slider (`volume_set`)** — that command only targets the TV's internal
  speakers and was a silent no-op with an external output.
- **Volume up/down and mute are kept**: the TV relays those keys to the
  external device over CEC/ARC (confirmed with an eARC AVR), and the same
  relay applies to Bluetooth soundbars. So remote-style volume keeps working;
  only the dead slider disappears.
- A `volume_set` service call issued anyway (e.g. by an old automation) logs a
  clear warning instead of failing silently, and legacy automations don't
  error out.
- When the speaker output is unknown (no Speaker Select entity, or it is
  unavailable), the slider stays — no behaviour change.

## Cleanup — ghost "unavailable" diagnostic sensors are removed automatically (8.3.0b14)

- **The old read-only sensors that were replaced by settable controls no longer
  linger as "unavailable" ghosts.** When `Contrast / Brightness / Sharpness /
  Color / Tint` (→ sliders, b8) and `Speaker Select` (→ select, b13) were
  replaced, Home Assistant kept their registry entries and showed them as
  *Indisponible* next to the working replacements. The integration now removes
  those stale registry entries automatically at startup — no manual deletion
  needed.

## Speaker output — settable select, with your eARC receiver as an option (8.3.0b13)

- **The read-only `Speaker Select` diagnostic sensor becomes a real `select`**,
  with two paths:
  - **IP Control (local, primary):** options are **Internal**,
    **AudioOut/Optical**, plus **every external audio device the TV currently
    lists** — e.g. an HDMI-eARC receiver appears by name ("CINEMA 60
    (HDMI-eARC)") while it is reachable, and switching to it goes through the
    TV's own `externalSpeakerControl` with the device id. This is *richer than
    the SmartThings app*, which only offers internal/optical. Discovered live:
    the receiver option comes and goes with the receiver's availability.
  - **SmartThings (cloud fallback):** on TVs without IP Control paired, a
    select backed by the `samsungvd.mediaOutput` capability
    (`supportedOutputList` / `currentOutput` / `setOutput`) is created instead.
    It stays unavailable until the TV populates the output list.
- Polling is gated on the TV being on (a Frame in Art Mode keeps its select),
  and all IP Control calls go through the per-host serialization lock.
- The protocol reference was corrected: `speakerSelectControl` and
  `externalSpeakerControl` were wrongly documented as read-only/absent.

## Picture mode — the working capability is memorized and tried first (8.3.0b12)

- **Once a picture-mode change is *verified applied* through a given SmartThings
  capability, that capability is memorized and tried first on every later
  change** — including after an HA restart (persisted in the config entry). So
  on TVs where `custom.picturemode` returns a lying `COMPLETED` (issue #116),
  the ~5–10 s verify-and-fallback cost is only paid on the *first* change;
  subsequent ones go straight through the working `samsungvd.pictureMode`.
  - The other capability always remains as fallback: if the panel's behaviour
    ever changes (e.g. firmware update), a later verified apply through the
    other capability simply overwrites the memory.
  - Only a **verified** apply is memorized — an unverifiable send (flaky cloud
    read) never updates the memory, so it can't learn the wrong capability.
  - Persisting the learned capability does **not** reload the integration.

## Picture mode — verify the TV applied it, retry via the other capability (8.3.0b11)

- **Fix for picture-mode changes that SmartThings accepts but the TV silently
  ignores** (issue #116, seen on an S90C and a Frame 2020 under self-published
  OAuth app clients: `setPictureMode` returns `200 COMPLETED`, the official app
  and a PAT actuate the panel fine, yet the command from the OAuth client does
  nothing). Previously the integration fell back from `custom.picturemode` to
  `samsungvd.pictureMode` only when the HTTP call *errored* — a lying
  `COMPLETED` meant the fallback never fired. Now, after every accepted send,
  the integration **reads the mode back (~5 s later) and, if the TV still
  reports the old mode, re-sends through the other capability**. If neither
  can be confirmed, a clear warning points at the cloud command channel
  (a duplicate send of the same mode is harmless on TVs where the first one
  worked). Verification is skipped rather than retried when the read-back
  itself fails, so flaky cloud reads can't cause spurious double-sends.

## Picture calibration — stop the sliders flapping available/unavailable (8.3.0b10)

- **Fix: the new Contrast/Brightness/Sharpness/Color/Tint sliders kept dropping
  to *unavailable* then back, without any mode change.** Two causes, both fixed:
  - **Concurrent IP Control calls.** The TV's control server (port 1516) accepts
    one connection at a time and resets overlapping ones. Each slider polled the
    TV independently, on top of the backlight number, color-tone select, state
    coordinator and the media_player art poll — so calls collided
    (`Connection reset by peer` / TLS errors) and entities flapped. All IP
    Control calls to a given TV are now **serialized through a per-host lock**,
    which also steadies the pre-existing backlight/color-tone controls.
  - **State guardrail (Art Mode / off).** Picture calibration only applies to
    normal viewing — in Art Mode the panel has its own Art Mode Brightness /
    Color Temperature, and the IP Control picture methods answer `-32601` there
    (the TV returns the same "Method not found" code whether a method is absent
    *or* just unavailable in the current state, so it can't be interpreted).
    The sliders now read all five values in **one shared `getVideoStates` call**,
    and that call — and every write — is only issued **when the TV is on and out
    of Art Mode**, gated on the media player's own state. So the sliders go
    cleanly **unavailable** when off/in Art Mode and recover on their own; a
    write attempted then gives a clear "the TV must be on and out of Art Mode"
    message and is never permanently disabled.

## Picture calibration — Contrast / Brightness / Sharpness / Color / Tint are now adjustable (8.3.0b8)

- **The five expert picture settings become settable sliders instead of
  read-only sensors.** They were exposed as diagnostic `sensor`s under the wrong
  assumption that their setters didn't work — in fact they're writable over IP
  Control through their dedicated `<field>Control` methods, the same way the
  Backlight and Color Tone controls already are. Each is now a `number` slider
  with the TV's real range (verified on Frame 2024/2025):
  - **Contrast** 0–50, **Color** 0–50, **Sharpness** 0–20,
    **Brightness** −5…+5 (picture brightness, distinct from panel Backlight),
    **Tint** −15…+15.
  - The write is **picture-mode gated**: Dynamic / HDR-dynamic drive these
    automatically and reject manual changes with a `-32002` error. When that
    happens the integration raises a clear message ("switch to Standard, Movie
    or Filmmaker mode and retry") and leaves the slider unchanged — it does not
    touch your picture mode.
  - The old read-only `Contrast/Brightness/Sharpness/Color/Tint` sensors are
    removed (replaced by these sliders). The IP Control state coordinator now
    issues a single `getTVStates` call per cycle instead of two.

## SmartThings polling — power sensor uses a fixed 30 s cadence in Art Mode (8.3.0b7)

- **The shared power/energy coordinator no longer follows the (possibly fast)
  "when on" interval while the Frame is displaying Art.** A Frame in Art Mode
  still draws power, so the coordinator keeps polling — but if you lower
  *SmartThings poll interval when on* for snappier channel / picture-mode updates
  (e.g. 5 s), the power sensor was inheriting that cadence and hitting the cloud
  every few seconds throughout the (often all-day) Art Mode period, even though
  the draw barely changes. Power/energy now polls at a **fixed 30 s keepalive in
  Art Mode**, decoupling the power sensor from the comfort interval: channel and
  picture mode stay responsive while power stops dominating the ST call budget. A
  fully-on TV (not Art) still follows the configured interval.

## Frame Art — `current.jpg` uses the already-downloaded thumbnail first (8.3.0b5)

- **When the artwork changes, `current.jpg` is now taken from the local copy we
  already downloaded (personal/store/other) *first*, and the TV is only queried
  if we don't have it.** Previously the card did the flaky live TV fetch first
  (which returns `SYSTEM_FAIL` on some Frame models), retried three times over
  ~8 s, and only *then* fell back to the cached copy — so `current.jpg` could
  lag ~30–45 s even for artworks whose thumbnail was already on disk. Downloaded
  thumbnails don't change, so the local copy is both instant and more reliable.
  Genuinely new artwork (no local copy yet) still falls back to a live fetch.

## Frame Art — current artwork updates much faster (8.3.0b4)

- **A manual / gallery art change now shows up in the Frame Art sensor and
  `current.jpg` in ~1–2 s instead of up to ~30 s.** Two things caused the lag:
  the art coordinator polled every 15 s, and a *changed* `content_id` had to be
  seen on **two consecutive polls** before being trusted (a guard against
  spurious one-off readings from the TV) — so a change took up to two full
  intervals to surface.
  - The art coordinator now polls every **5 s** (the cheap `get_current_artwork`
    read; the heavier content-list fetch stays throttled separately).
  - When the change arrives as a **WebSocket art broadcast** (`image_selected`,
    matte/slideshow/favorite/rotation) — which is definitive, not a glitch — the
    new `content_id` is **trusted immediately**, skipping the two-poll
    confirmation. The glitch guard still applies to unsolicited TV-side reads.
  - Note: a slow `current.jpg` can still occur if the TV itself returns
    `SYSTEM_FAIL` on the thumbnail request (a firmware issue); the integration
    retries and falls back to a cached copy.

## Folder Gallery card — fullscreen-preview buttons work again in lightbox mode (8.3.0b3)

- **Fix: the lightbox buttons (Display on TV / Unfavourite / Delete / Upload)
  did nothing** when the single tap was set to *Open preview (lightbox)* in the
  visual editor. That mode cleared the card's `action`, but the buttons rely on
  it for the Frame TV entity and the service to call, so every button silently
  no-op'd. The editor now keeps the gallery type's primary action in lightbox
  mode, and the Frame TV entity is also persisted on its own `frame_tv_entity`
  key so the buttons always resolve a target.
  - After updating, **re-open the card in the visual editor and save once** (or
    re-select the Frame TV entity) so the new `frame_tv_entity` is written.

## Art Mode is detected immediately again after the polling rework (8.3.0b2)

On some models (notably 2024 Frames where IP Control can't report the art
state and the TV's REST `PowerState` stays `on` while displaying art),
entering/leaving **Art Mode** is only learned from SmartThings. After the ST
poll was throttled (below), a `select_image` / Art Mode change could take up to
the ST interval (~30 s) to show up in `art_mode_status` / the current art.
The integration now **forces an immediate SmartThings poll on an art-mode
transition** (the local Art WebSocket already broadcasts it), so Art Mode is
reflected within a second or two again — without giving up the throttle for
idle polling.

## SmartThings polling — local WebSocket first, far fewer cloud calls

Ahead of Samsung's move to a **paid SmartThings API** (free access phasing out
around October 2026), this release reworks polling so the **local WebSocket is
the primary state source** and the SmartThings cloud is a throttled fallback,
cutting cloud API usage dramatically.

- **The local WebSocket / UPnP / IP Control drive power, app, volume and mute**
  (every 5 s, unchanged). SmartThings is now only polled for the data that has
  no local equivalent: channel name, source labels, picture mode, sound mode
  and power/energy metering.
- **SmartThings is throttled.** It is polled at a configurable cadence while the
  TV is **ON** (new advanced option *SmartThings poll interval when on*, default
  **30 s**), and at a fixed **30 s keepalive** otherwise. When the TV powers on,
  one SmartThings poll is forced immediately so the cloud-only fields refresh
  right away instead of lagging by the interval.
- **The five power/energy sensors now share a single poll.** Previously each of
  the five `powerConsumptionReport` sensors independently called
  `get_device_status` on the *same* device every 15 s (20 calls/min of pure
  redundancy). They now read from one shared coordinator that makes a single
  call per cycle and **skips entirely while the TV is off** — while still
  polling when the Frame is displaying **Art** (it keeps drawing power), so
  art-mode consumption stays visible.
- **The picture-mode select and the child light sensors** (illuminance /
  brightness) are now power-gated and throttled to the same cadence, instead of
  polling the cloud every 15–30 s regardless of whether the TV is on.

On a realistic 6 h-on / 18 h-off day this takes a fully-equipped Frame TV from
roughly **53,000 SmartThings calls/day to about 7,500 (~86% fewer)**, with the
largest savings while the TV is off.

### New option

*Configure → advanced options → **SmartThings poll interval when on** (seconds)*
— default `30`, range `5`–`600`. Lower it for snappier channel / picture-mode
updates at higher API cost; raise it to minimise calls. Changing it reloads the
integration. The off-state keepalive is fixed at 30 s.

See [`docs/SmartThings_API_Usage.md`](docs/SmartThings_API_Usage.md) for the full
breakdown of what is polled and why.

---

# Also included from the 8.2.0 beta

> 8.2.0 was a beta that was never released as stable; all of the following ships
> as part of 8.3.0 for anyone upgrading directly from 8.1.0.

## Picture mode select — no longer reverts to the old mode after a change

- **Setting the picture mode (e.g. via `select.select_option` or the Picture
  Mode select) no longer snaps back to the previous value.** SmartThings lags
  ~30-45s before it reports the new mode, but the select only skipped polling
  for 5s — so the next poll read the *old* mode from the cloud and reverted the
  selection (issue #116). The select now **holds the mode you set until the
  cloud confirms it** (60s grace window); if the cloud still hasn't confirmed
  after that, it accepts the cloud's value, so a change made on the TV itself is
  still reflected.

## Folder Gallery card — translations (FR, ES, IT, pt-BR, HU) + required Frame TV entity

- **The card is now translated** into French, Spanish, Italian, Brazilian
  Portuguese and Hungarian (with English as the fallback). This covers the
  visual editor (labels, hints, gallery-type and gesture dropdowns), the
  fullscreen-preview buttons (Select / Unfavourite / Upload / Delete / Close),
  the Frame chooser, the empty state and the toasts. The language follows Home
  Assistant's UI language (`hass.locale.language`).
- **The visual editor no longer lets you save an action without a Frame TV
  entity.** If a single/double/long-press action is set to Display / Upload /
  Delete / Unfavourite but the **Frame TV entity** field is empty, the card now
  rejects the config (HA shows the error and blocks the save) instead of
  silently saving an action that has no target to run against.

## Folder Gallery card — gesture actions follow the gallery type

- **The tap / double-tap / long-press action dropdowns in the visual editor now
  offer the actions that fit the gallery's `gallery_type`:**
  - `upload` → **Upload to TV**
  - `personal` → **Display on TV** / **Delete**
  - `favorites` → **Display on TV** / **Unfavourite**
  - `auto` → **Display on TV** (generic)

  So e.g. an upload gallery no longer offers "Display on TV" on double-tap/hold —
  it offers **Upload** instead. Each preset builds the matching
  `samsungtv_smart.art_*` action for the configured Frame TV entity. Choosing a
  gallery type re-scopes the gesture options (a now-invalid choice resets to
  "Nothing").

## Folder Gallery card — per-gallery action buttons (`gallery_type`)

- **New `gallery_type` option** to force the fullscreen-preview action buttons
  for a whole gallery, instead of guessing per image:
  - `personal` → **Select** + **Delete**
  - `favorites` → **Select** + **Unfavourite**
  - `upload` → **Upload**
  - omitted / `auto` → detect per image from the content-id prefix (previous
    behaviour). Also available as a dropdown in the visual editor. Useful for an
    upload folder of plain photos, which would otherwise be guessed per file.

## Folder Gallery card — more options in the visual editor

- The card's visual editor now exposes, in addition to the basic fields:
  - **Server-side thumbnails** (checkbox) and **Thumbnail width** (px).
  - **Actions** for single tap / double tap / long press, each a simple
    dropdown (*Open preview / Display on TV / Nothing*), plus a **Frame TV
    entity** field used to build the "Display on TV" action. No need to hand-
    write the YAML action objects anymore for the common setup.

## Folder Gallery card — server-side resized thumbnails for big folders

- **The gallery now loads small resized thumbnails instead of the originals.**
  Pointing the card at a folder of full-size photos (several MB each, many of
  them) used to make the browser download and decode every original at full
  resolution just to render the grid — slow, memory-heavy, and visually poor.
  The integration now exposes an on-demand thumbnail endpoint
  (`/api/samsungtv_smart/thumbnail`) that returns a small cached JPEG (resized
  with Pillow, cached on disk keyed by file + size + mtime). The card points
  its grid images there, so only kilobytes per tile reach the browser; the
  full-resolution original is still used for the lightbox and tap/hold actions.

  - Enabled by default. Disable per card with `server_thumbnails: false`.
  - Tune the size with `thumbnail_width:` (default `400`).
  - Only local files (`/local/...`) are routed through the resizer; remote URLs
    are used as-is. If Pillow isn't available, the endpoint transparently falls
    back to the original image.
  - The endpoint only ever reads files under `<config>/www` (already public at
    `/local/`) and validates the path against traversal.

## Credits — channel logos source attribution

- The README now credits [jaruba/channel-logos](https://github.com/jaruba/channel-logos)
  explicitly as the source of the channel logos used by the media-player logo
  feature (`logo.py` fetches them from `jaruba.github.io/channel-logos`). It was
  previously only mentioned indirectly as part of the fork lineage.

## README — heads-up about the upcoming SmartThings API pricing change

- Added a notice in the SmartThings Authentication section: Samsung announced
  the SmartThings API is moving to paid tiers (a $4.99/month "Personal" plan
  with a monthly call quota, plus separate commercial tiers), with free access
  phasing out around October 2026. Since this integration's SmartThings calls
  run under each user's own Samsung account, this may eventually affect users
  directly. No code changes are required today — this is purely informational
  until Samsung publishes concrete quotas. (The 8.3.0 polling rework above
  already cuts that usage dramatically.)
