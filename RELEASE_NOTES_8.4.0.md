# Release notes — 8.4.0

> **Status: stable release.** 8.4.0 also folds in the entire **8.3.4** line
> (Art Mode reliability + 2024/2025 firmware-compat), which was only ever
> published as betas — see *"Also included: the 8.3.4 Art Mode reliability
> line"* at the bottom, and `RELEASE_NOTES_8.3.4.md` for the detail.

## Highlights

- **Artwork identification (opt-in, new)** — show the title, artist, date and a
  short bio of the art on your Frame, in your language.
- **Art Mode stops turning off "randomly"** — the art WebSocket now heals
  itself (auto-reconnect + zombie-channel circuit breaker), no more reload.
- **2024/2025 Frame firmware compatibility** (art-mode detection, matte list,
  upload type).
- **Batch folder upload** with idempotent re-runs and optional duplicate
  detection.
- **Ambient light sensor stays live while the TV is off.**
- **Art Mode switch no longer thrashes an off-network TV**, and re-applies once
  it's back.

---

## Artwork identification (opt-in, new)

Identify the artwork currently shown on a Frame TV so Home Assistant can
display its **title, artist, date and a short artist bio** — and even a couple
of description paragraphs — with each viewer reading it in their own language.

### How it works — two stages, cache-first

1. **Reverse image search** (Google Cloud Vision *Web Detection*) turns the
   thumbnail into concrete candidate titles/artists pulled from the real web.
2. **LLM confirmation** (Anthropic, OpenAI *or* Gemini) is handed those
   candidates and the image, and confirms only if one genuinely matches what it
   sees — otherwise it returns "not identified". Reverse-search-first is what
   stops the hallucinations a bare vision model produces on obscure works — it
   even identifies photographs, not just famous paintings.

Results are **cached** so each artwork is identified only once — keyed by the
Samsung Art-Store id (`SAM-*`, stable across TV resets) or, for personal
uploads, by the image content itself (so a recycled local id can never surface
another image's metadata). Successful identifications are kept indefinitely;
"not identified" is retried after two weeks; transport errors are never cached.

**Cost is tiny**: Google Vision is free under ~1000 requests/month, and — since
the same few dozen artworks rotate — the cache serves almost everything after a
short warm-up, so the LLM is rarely called.

### Setup

Under **Settings → Devices & Services → the TV → Configure → Art
Identification**: enable the feature, paste your Google Vision API key, pick the
LLM provider (Anthropic/OpenAI/Gemini), paste its key, optionally set a model
(blank = `claude-haiku-4-5` / `gpt-4o` / `gemini-2.5-flash`), and choose whether
to also identify personal photos (off by default — they're rarely in the art
index). Keys are stored in the config entry (never in your YAML/Git).

### The metadata sensor (automatic)

When enabled, a **`sensor.<tv>_art_metadata`** is created. It watches the
artwork on screen and, on every change (debounced ~8 s so a fast slideshow
doesn't fire per frame), runs the pipeline automatically and publishes:

- **state** = the artwork title (in the HA instance language), or `Unidentified`;
- **attributes** = `artist`, `date`, `confidence`, `artist_biography`,
  `artwork_description`, `visual_description`, `matched_candidate`,
  `suggested_search_query`, `source` (`cache`/`fresh`), `content_id`, and a full
  **`translations`** map (see below).

Enabling/disabling the feature adds/removes this sensor (a reload); editing an
API key does not reload. There is also a manual **`samsungtv_smart.art_identify`**
service (returns the metadata via a response variable; `force: true` bypasses
the cache) for testing or on-demand use.

### Multilingual (5 languages)

Metadata is produced in **`en`, `fr`, `es`, `it`, `pt-BR`** in a single LLM
call. The sensor exposes the descriptive fields in the HA instance language for
a plain card, **plus a full `translations` attribute** `{lang: {…}}` so a
frontend card can show each viewer the description **in their own browser/UI
language** — a FR user and an EN user on the same dashboard each read it in
their language. `artist` / `date` / `confidence` stay language-independent.

**Per-viewer language card** (`custom:button-card` reads the viewer's language;
replace `samsung_hacs`):

```yaml
type: custom:button-card
entity: sensor.samsung_hacs_art_metadata
show_icon: false
show_entity_picture: true
entity_picture: >
  [[[ return states['sensor.samsung_hacs_frame_art'].attributes.current_thumbnail_url ]]]
name: |
  [[[
    const a = entity.attributes;
    if (!a.identified) return 'Artwork not identified';
    const lang = (hass.language || 'en').split('-')[0];
    const t = (a.translations && (a.translations[lang] || a.translations.en)) || {};
    return `${t.title}\n${a.artist} · ${a.date}\n\n${t.artist_biography || ''}`;
  ]]]
styles:
  card: [{ padding: 12px }]
  name: [{ white-space: pre-line }, { font-size: 13px }]
```

**Simple card** (instance language, plain Markdown, no custom card needed):

```yaml
type: markdown
content: >
  {% set m = 'sensor.samsung_hacs_art_metadata' %}
  {% set thumb = state_attr('sensor.samsung_hacs_frame_art', 'current_thumbnail_url') %}
  {% if thumb %}![art]({{ thumb }}){% endif %}


  {% if is_state_attr(m, 'identified', true) %}
  ## {{ states(m) }}

  **{{ state_attr(m, 'artist') }}** · {{ state_attr(m, 'date') }}


  {{ state_attr(m, 'artist_biography') }}
  {% else %}
  _Artwork not identified_
  {% endif %}
```

### Troubleshooting

Debug logging traces the whole pipeline — the gating decision, the thumbnail
read, the **Vision candidates**, the **raw LLM reply**, cache hit/miss, timing,
and each sensor trigger:

```yaml
logger:
  logs:
    custom_components.samsungtv_smart.art_identify: debug
    custom_components.samsungtv_smart.sensor: debug
```

Typical lines: `Vision candidates best_guess=[…]`, `LLM (anthropic/…) raw
reply: {…}`, `identified=True title=… in 6.3s`, `cache HIT (…)`.

## Ambient light sensor stays live while the TV is off

The Frame's ambient light sensor runs independently of TV power (it drives the
panel's art auto-dimming and is useful for room-light automations), and
SmartThings keeps publishing it in standby. The `Light Level` / brightness
sensors now keep updating at a slow keepalive cadence while the TV is off,
instead of freezing at their last value.

## Art Mode switch — no thrashing on an off-network TV

When the Art Mode switch is turned on while the TV is off and it never becomes
reachable after the power-on (deep standby / dropped Wi-Fi), the switch now
**aborts instead of the 8 s stabilise wait + 5× retry loop** (~60 s of futile
hammering). The request is **not lost**: it is remembered and **re-applied
automatically the moment the media_player reports the TV back online** — no
reliance on an automation re-firing. The deferred request is dropped if Art
Mode is turned off in the meantime, or superseded by a new explicit turn-on.

---

## Also included: the 8.3.4 Art Mode reliability line

8.4.0 carries everything from the 8.3.4 betas (full detail in
`RELEASE_NOTES_8.3.4.md`):

- **Art WebSocket self-healing** — auto-reconnect with bounded backoff, plus a
  zombie-channel circuit breaker (force-reconnect after consecutive request
  timeouts on a live socket). Together they close the long-standing "why did Art
  Mode turn off randomly?" bug that previously needed an integration reload.
- **2024/2025 Frame firmware-compat** — art-mode status field (`status`/`value`),
  matte list field (`matte_list`/`matte_type_list`), WS-over-REST art-mode
  detection, and real image-format upload-type detection.
- **`art_upload_batch` service** — upload a whole folder, idempotently (a
  per-folder sidecar skips unchanged files so re-runs upload 0 duplicates) and
  throttled (large batches complete instead of failing partway), with an opt-in
  perceptual duplicate check against the art already on the TV.
- **Robustness** — a missing/broken Pillow no longer takes the whole
  integration down (lazy import).
