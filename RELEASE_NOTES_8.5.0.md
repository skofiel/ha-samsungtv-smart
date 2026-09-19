# Release notes — 8.5.0

> **Status: stable release.** Builds on 8.4.0 — no breaking changes. The only
> new moving part is an optional bundled Lovelace card; everything else is
> unchanged.

## Highlights

- **One-click artwork upload — no coding, from any device.** A new bundled
  Lovelace card lets you pick an image on your phone or laptop and push it
  straight to The Frame in a single tap. No pre-placed file, no folder sensor,
  no service call to hand-write.
- **iPhone HEIC photos just work.** Uploads are transcoded to JPEG
  server-side, so the HEIC files iPhones produce (often disguised behind a
  `.jpeg` name) are accepted instead of being silently rejected by the TV.

---

## One-click artwork upload (new)

Until now, getting a *new* picture onto The Frame with this integration took a
bit of setup — dropping a file where Home Assistant could see it, then calling
the `art_upload` service. The SmartThings app is easier for that, but it only
works when you're in front of the TV.

**8.5.0 adds a proper GUI for it.** The integration now bundles a Lovelace card,
`samsung-art-upload-card`, that is registered automatically — nothing to install
or configure as a resource. Add it to any dashboard:

```yaml
type: custom:samsung-art-upload-card
# entity: media_player.the_frame   # optional — a picker appears if omitted and you have several Frames
# matte: shadowbox_polar           # optional default matte
# title: Upload to The Frame       # optional
```

Then, from your phone or laptop, pick an image and tap **Upload to Frame**.
That's it — the picture is pushed to the TV and displayed.

### How it works

The card POSTs the selected file to a small **authenticated** endpoint the
integration now exposes (`/api/samsungtv_smart/art_upload`). That endpoint
reuses the existing `art_upload` flow — ensure Art Mode, upload, refresh, and
retry the TV-side thumbnail — and reports back the new content id. Because it
rides on the same service, everything the service already does (matte, art-mode
handling, thumbnail retry) applies unchanged.

### Choosing the target Frame

- Pin a TV with `entity:` in the card config and it always uploads there.
- Omit `entity:` and, if you have **more than one** Frame, the card shows a
  selector so you can choose per upload. With a single Frame there's no
  selector — it just uploads to it.

### iPhone HEIC handling

iPhones hand browsers **HEIC/HEIF** images — frequently with a misleading
`.jpeg` name and `image/jpeg` content type — which The Frame does not accept
(the upload used to fail with *"no content_id returned"*). The upload endpoint
now inspects the real bytes: genuine JPEG/PNG pass through untouched, and
anything else is decoded and re-encoded to JPEG before being sent to the TV.
This adds `pillow-heif` to the requirements (installed automatically); if the
HEIC codec is ever unavailable it degrades gracefully without affecting the rest
of the integration.

---

## Upgrade notes

- No configuration changes required. Existing services, entities and the
  `folder-gallery-card` are unchanged.
- After updating, **restart Home Assistant** (so `pillow-heif` is installed and
  the new card resource is registered), then hard-refresh your browser
  (Ctrl-Shift-R) before adding the card.
- The card is optional — if you don't add it, nothing about your setup changes.

---

## Changelog

- **New:** bundled `samsung-art-upload-card` Lovelace card (auto-registered).
- **New:** authenticated `/api/samsungtv_smart/art_upload` HTTP endpoint.
- **New:** server-side HEIC/HEIF → JPEG transcoding for uploads (`pillow-heif`).
- **Change:** the `art_upload` service now returns the upload result
  (`content_id`) so callers can read it back.
- **Fix:** bundled card resources register immediately when the integration is
  reloaded after Home Assistant has already started (previously only on the next
  full restart).
