"""TemporalController and linked-view coordination (#44)."""

from __future__ import annotations

import pytest

from xy import _native


def _ctrl(instance_id: int, group_id: int = 0, **kwargs):
    return _native.temporal_controller_create(
        instance_id=instance_id,
        group_id=group_id,
        domain_start=0,
        domain_end=1_000_000,
        cursor=100_000,
        window=50_000,
        step=10_000,
        rate_milli=1000,
        loop_enabled=True,
        **kwargs,
    )


def test_linked_views_coordinate_once() -> None:
    a = _ctrl(1, group_id=7)
    b = _ctrl(2, group_id=7)
    c = _ctrl(3, group_id=9)
    try:
        _native.temporal_controller_set_cursor(a, 200_000)
        event = _native.temporal_controller_poll_event(a)
        assert event is not None
        assert event["source_instance"] == 1
        assert _native.temporal_controller_apply_event(b, event) is True
        assert _native.temporal_controller_state(b)["cursor"] == 200_000
        with pytest.raises(_native.TemporalNativeError) as echo:
            _native.temporal_controller_apply_event(a, event)
        assert echo.value.status == -15
        assert _native.temporal_controller_apply_event(c, event) is False
        assert _native.temporal_controller_state(c)["cursor"] == 100_000
        with pytest.raises(_native.TemporalNativeError) as stale:
            _native.temporal_controller_apply_event(b, event)
        assert stale.value.status == -14
    finally:
        _native.temporal_controller_destroy(a)
        _native.temporal_controller_destroy(b)
        _native.temporal_controller_destroy(c)


def test_disposal_stops_playback() -> None:
    handle = _ctrl(1)
    try:
        _native.temporal_controller_play(handle)
        assert _native.temporal_controller_state(handle)["playing"] is True
        _native.temporal_controller_dispose(handle)
        state = _native.temporal_controller_state(handle)
        assert state["playing"] is False
        assert state["disposed"] is True
        with pytest.raises(_native.TemporalNativeError) as exc:
            _native.temporal_controller_tick(handle, 1_000)
        assert exc.value.status == -13
    finally:
        _native.temporal_controller_destroy(handle)


def test_reduced_motion_and_same_process_deliver() -> None:
    a = _ctrl(1, group_id=5)
    b = _ctrl(2, group_id=5)
    try:
        _native.temporal_controller_set_reduced_motion(a, True)
        _native.temporal_controller_play(a)
        assert _native.temporal_controller_state(a)["playing"] is False
        before = _native.temporal_controller_state(a)["cursor"]
        _native.temporal_controller_step(a)
        assert _native.temporal_controller_state(a)["cursor"] != before
        _native.temporal_controller_set_cursor(a, 300_000)
        event = _native.temporal_controller_poll_event(a)
        assert event is not None
        assert _native.temporal_coordinate_deliver(event) == 1
        assert _native.temporal_controller_state(b)["cursor"] == 300_000
    finally:
        _native.temporal_controller_destroy(a)
        _native.temporal_controller_destroy(b)
