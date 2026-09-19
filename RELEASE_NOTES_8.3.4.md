# Release notes — 8.3.4

> **Focus: Art Mode reliability on 2024/2025 Frames** — the art WebSocket now
> heals itself instead of staying dead until a reload, plus firmware-compat
> fixes. Several changes contributed by the community (thanks!).

## Art WebSocket self-healing (no more "why did Art Mode turn off?" reloads)

Two complementary recovery paths so a dropped or wedged art channel comes back
on its own — the long-standing headache behind random Art Mode drops that
previously needed an integration reload (issue #153):

- **Auto-reconnect with bounded backoff** (#152): when the art WebSocket drops
  (standby, network blip, a missed heartbeat PONG on a zombie socket), the
  channel reconnects on its own with exponential backoff capped at 60 s, and
  an idle keepalive keeps a quiet-but-live session open. The reconnect is
  cancelled on a deliberate teardown, so a reload never triggers a reconnect
  loop.
- **Zombie-channel circuit breaker** (#154): the TV's art *app* can crash while
  its network stack keeps the socket open and answering PINGs — the heartbeat
  sees a healthy socket, the receive loop never exits, and every request just
  times out forever. After 3 **consecutive** request timeouts on a live socket
  (any real answer resets the count, so capability probes never trip it) the
  channel is force-closed, handing recovery to the auto-reconnect above. One
  recovery path for every kind of dead channel — no manual reload.
  - If it fires, the log shows:
    `Art API: 3 consecutive request timeouts on a live socket — art channel looks wedged, forcing reconnect`

## Firmware-compat fixes for 2024/2025 Frames (#150)

Small, backward-compatible reads that tolerate the newer API shapes:

- **Art-mode status field**: art API 5.x returns the state under `status`
  instead of `value` — the getter now reads whichever is present.
- **Matte list field**: newer firmware renamed `matte_type_list` →
  `matte_list`; matte enumeration accepts either.
- **Art-mode detection** trusts the art WebSocket over REST `PowerState`, which
  2025 Frames report as `standby` while actively displaying art.
- **Upload type detection**: the real image format is sniffed (JPEG/PNG/MPO →
  correct wire type) instead of a hard-coded label, which the 2024/2025 Frames
  require to accept an upload.

## Fix: integration no longer fails to load without Pillow (#155)

The upload-type detection above imported Pillow at module scope, so on any
install where Pillow wasn't present the whole integration failed to load —
taking media_player, remote and every KEY/app button (home, source, netflix…)
down with it. The import is now lazy: a missing Pillow only degrades
upload-type detection (it falls back to the caller's hint), never breaks the
integration. Pillow is declared in the manifest so detection works wherever
it's available.
