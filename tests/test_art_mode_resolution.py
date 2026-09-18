"""Behavioural tests for _art_mode_is_on(), the Art Mode source of truth.

``_art_mode_is_on()`` is what feeds the ``art_mode_status`` attribute, the media
title and the Art Mode switch, and it resolves six sources with a fixed
priority. Issue #248 was re-fixed five times in eight days, each fix reordering
or gating one of those sources — and each shipped with a test that asserted the
new *source text*, so nothing ever pinned what the resolution should actually
return.

These tests pin the behaviour of each layer and, more importantly, the
precedence between them: a change that reorders the cascade has to state which
of these it is deliberately changing.
"""

from types import SimpleNamespace

from tests.helpers import ArtModeStatus, MediaPlayerState, STStatus, make_device

# --------------------------------------------------------------------------
# Layer 1 — a visible app beats every art signal
# --------------------------------------------------------------------------


def test_a_foreground_app_means_the_panel_is_not_showing_art():
    """2024 Frames emit spurious art_mode_changed='on' during normal app use.

    Without this guard the switch and media title flapped back to "Art Mode"
    while Netflix was on screen.
    """
    device = make_device(
        running_app="3201907018807",  # Netflix, genuinely visible
        ip_art_mode=True,
        panel_art=True,
        art_api_art_mode=True,
    )

    assert device._art_mode_is_on() is False


def test_no_foreground_app_does_not_by_itself_mean_art():
    """DEFAULT_APP covers live TV as well as Art Mode, so it decides nothing."""
    device = make_device(running_app=None, panel_art=False)

    assert device._art_mode_is_on() is False


# --------------------------------------------------------------------------
# Layer 2 — the artModeControl cache, when the option is on
# --------------------------------------------------------------------------


def test_the_ip_art_mode_cache_wins_when_the_option_is_on():
    device = make_device(ip_art_mode=True, panel_art=False, art_api_art_mode=False)

    assert device._art_mode_is_on() is True


def test_the_ip_art_mode_cache_is_trusted_when_it_says_off_too():
    device = make_device(ip_art_mode=False, panel_art=True, art_api_art_mode=True)

    assert device._art_mode_is_on() is False


# --------------------------------------------------------------------------
# Layer 3 — the panel's own pictureMode, gated on the TV being a Frame
# --------------------------------------------------------------------------


def test_the_panel_picture_mode_beats_the_websocket_and_the_cloud():
    """getTVStates.pictureMode is the panel's own truth and cannot freeze.

    The art WebSocket channel can miss the transition entirely and pin
    art_mode_status at its pre-transition value (#248 measured four stretches
    of 7-10 hours), so the panel read is consulted first.
    """
    device = make_device(
        panel_art=True,
        art_api_art_mode=False,
        ws_artmode=ArtModeStatus.Off,
    )

    assert device._art_mode_is_on() is True


def test_ambient_on_a_non_frame_is_not_art():
    """Samsung's unrelated Ambient Mode reports the same pictureMode.

    A QN90A sits in 'Ambient' near-permanently and has no Art Mode at all, so
    without the Frame gate art_mode_status read 'on' forever (#248).
    """
    device = make_device(
        panel_art=True,
        frame_tv_support=False,
        is_frame_persisted=False,
        art_api_art_mode=False,
    )

    assert device._art_mode_is_on() is False


# --------------------------------------------------------------------------
# Layer 4/5 — a powered-off panel is never showing art
# --------------------------------------------------------------------------


def test_standby_beats_a_stale_art_websocket():
    """A TV in standby cannot be showing artwork, whatever the socket latched."""
    device = make_device(power_state="standby", art_api_art_mode=True)

    assert device._art_mode_is_on() is False


def test_smartthings_reporting_the_switch_off_beats_a_stale_art_websocket():
    """SmartThings reports 'on' during Art Mode, so 'off' means truly off.

    Covers TVs without IP Control, where the art channel can latch 'on' after a
    cloud or remote power-off it never witnessed.
    """
    device = make_device(st_state=STStatus.STATE_OFF, art_api_art_mode=True)

    assert device._art_mode_is_on() is False


# --------------------------------------------------------------------------
# Layer 6 — the async Art API, corroborated by SmartThings
# --------------------------------------------------------------------------


def test_the_async_art_api_is_used_when_no_local_panel_read_exists():
    device = make_device(art_api_art_mode=True, st_state=STStatus.STATE_ON)

    assert device._art_mode_is_on() is True


def test_smartthings_overrides_an_art_api_false_when_it_sees_art():
    """The art channel can latch False and never get a follow-up event.

    SmartThings polls the TV independently, so its "running app is art" is
    trusted over a local False. It lags 30-45s, which is the accepted cost.
    """
    device = make_device(
        art_api_art_mode=False,
        st_state=STStatus.STATE_ON,
        st_channel_name="art",
    )

    assert device._art_mode_is_on() is True


def test_an_art_api_false_stands_when_smartthings_does_not_see_art():
    device = make_device(
        art_api_art_mode=False,
        st_state=STStatus.STATE_ON,
        st_channel_name="HDMI1",
    )

    assert device._art_mode_is_on() is False


# --------------------------------------------------------------------------
# Layer 7/8 — legacy WebSocket, then SmartThings alone
# --------------------------------------------------------------------------


def test_the_legacy_websocket_status_is_used_when_nothing_better_exists():
    """Only reachable on installs still running the legacy SamsungArt thread.

    disable_art_thread() pins artmode_status at Unsupported whenever the async
    Art API is active, which is every normal install — so this layer is dead
    there. It stays covered because an install without art.py still uses it.
    """
    device = make_device(ws_artmode=ArtModeStatus.On, st_state=STStatus.STATE_ON)

    assert device._art_mode_is_on() is True


def test_smartthings_alone_can_report_art_right_after_startup():
    """Before the async Art API has any value at all."""
    device = make_device(st_state=STStatus.STATE_ON, st_channel_name="art")

    assert device._art_mode_is_on() is True


def test_no_source_at_all_is_unknown_not_false():
    """Reporting False here would claim the panel is on a real input."""
    device = make_device(state=MediaPlayerState.ON)

    assert device._art_mode_is_on() is None


# --------------------------------------------------------------------------
# The art channel must be live for its cached value to mean anything
# --------------------------------------------------------------------------


def test_a_closed_art_channel_does_not_get_to_report_art_mode():
    """art_mode is push-only: a closed socket means nothing is updating it.

    This is the #248 freeze. _receive_loop clears the cache when it exits
    normally, but the bounded force-close and a send failure both drop the
    connection without going through it, and the last value — typically "on",
    since Art Mode is a Frame's last state before power-off — kept being
    reported for as long as the socket stayed down.
    """
    device = make_device(art_api_art_mode=True, art_connected=False)

    assert device._art_mode_is_on() is None


def test_a_closed_art_channel_falls_through_to_the_power_sources():
    device = make_device(
        art_api_art_mode=True,
        art_connected=False,
        st_state=STStatus.STATE_OFF,
    )

    assert device._art_mode_is_on() is False


def test_a_closed_art_channel_still_lets_smartthings_report_art():
    device = make_device(
        art_api_art_mode=False,
        art_connected=False,
        st_state=STStatus.STATE_ON,
        st_channel_name="art",
    )

    assert device._art_mode_is_on() is True


# --------------------------------------------------------------------------
# The panel snapshot reader itself
# --------------------------------------------------------------------------


def _coordinator(picture_mode=None, *, powered_off=False, success=True):
    """A stand-in for the shared getTVStates DataUpdateCoordinator."""
    return SimpleNamespace(
        data={"powered_off": powered_off, "tv": {"pictureMode": picture_mode}},
        last_update_success=success,
    )


def test_ambient_is_the_only_picture_mode_that_means_art():
    device = make_device(coordinator=_coordinator("Ambient"))

    assert device._ip_control_panel_art_cached() is True


def test_any_other_picture_mode_means_a_real_input():
    device = make_device(coordinator=_coordinator("Standard"))

    assert device._ip_control_panel_art_cached() is False


def test_a_stale_snapshot_is_unreadable_not_false():
    """The coordinator keeps serving its last good payload after a failure.

    Without this a TV that stopped answering went on reporting the pictureMode
    it held when last reachable, for as long as it stayed unreachable.
    """
    device = make_device(coordinator=_coordinator("Ambient", success=False))

    assert device._ip_control_panel_art_cached() is None


def test_a_powered_off_panel_is_unreadable():
    device = make_device(coordinator=_coordinator("Ambient", powered_off=True))

    assert device._ip_control_panel_art_cached() is None


def test_no_coordinator_at_all_is_unreadable():
    device = make_device(coordinator=None)

    assert device._ip_control_panel_art_cached() is None


def test_a_snapshot_without_a_picture_mode_is_unreadable():
    device = make_device(coordinator=_coordinator(None))

    assert device._ip_control_panel_art_cached() is None


def test_the_boolean_helper_only_says_yes_for_a_definite_yes():
    """None (unreadable) must not read as ambient."""
    device = make_device(coordinator=_coordinator("Ambient", success=False))

    assert device._ip_control_ambient_mode_active() is False
