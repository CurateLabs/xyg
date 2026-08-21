"""TemporalController and linked-view coordination (#44)."""

from __future__ import annotations

from typing import Any

import pytest

import xyg
from xyg import _native


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


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("source_instance", 0),
        ("revision", 0),
        ("cursor", 250_001),
        ("window", -1),
        ("window", 149_999),
    ],
)
def test_inbound_event_rejects_noncanonical_fields(field: str, value: int) -> None:
    handle = _ctrl(2, group_id=7)
    event = {
        "group_id": 7,
        "source_instance": 1,
        "revision": 1,
        "range_start": 100_000,
        "range_end": 250_000,
        "cursor": 200_000,
        "window": 150_000,
    }
    event[field] = value
    try:
        with pytest.raises(_native.TemporalNativeError):
            _native.temporal_controller_apply_event(handle, event)
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


def test_exchange_group_rejects_duplicate_live_instance_id() -> None:
    first = _ctrl(31, group_id=23)
    try:
        with pytest.raises(_native.TemporalNativeError) as collision:
            _ctrl(31, group_id=23)
        assert collision.value.status == -1
        _native.temporal_controller_dispose(first)
        replacement = _ctrl(31, group_id=23)
        _native.temporal_controller_destroy(replacement)
    finally:
        _native.temporal_controller_destroy(first)


def test_same_process_deliver_rejects_malformed_event_without_peers() -> None:
    event = {
        "group_id": 24,
        "source_instance": 1,
        "revision": 1,
        "range_start": 10,
        "range_end": 20,
        "cursor": 20,
        "window": 10,
    }
    with pytest.raises(_native.TemporalNativeError):
        _native.temporal_coordinate_deliver(event)


def test_single_instant_and_repeated_setters_are_canonical_noops() -> None:
    handle = _ctrl(21, group_id=18)
    try:
        initial = _native.temporal_controller_state(handle)
        _native.temporal_controller_set_range(handle, initial["range_start"], initial["range_end"])
        _native.temporal_controller_set_cursor(handle, initial["cursor"])
        assert _native.temporal_controller_state(handle)["revision"] == initial["revision"]
        assert _native.temporal_controller_poll_event(handle) is None
        _native.temporal_controller_set_range(handle, 100, 101)
        assert _native.temporal_controller_state(handle)["window"] == 0
    finally:
        _native.temporal_controller_destroy(handle)


def test_tick_at_nonlooping_bound_reports_no_movement_and_stops_playback() -> None:
    handle = _ctrl(22)
    try:
        _native.temporal_controller_set_loop(handle, False)
        _native.temporal_controller_set_cursor(handle, 1_000_000)
        _native.temporal_controller_play(handle)
        revision = _native.temporal_controller_state(handle)["revision"]
        assert _native.temporal_controller_tick(handle, 20_000) is False
        state = _native.temporal_controller_state(handle)
        assert state["cursor"] == 999_999
        assert state["playing"] is False
        assert state["revision"] == revision
    finally:
        _native.temporal_controller_destroy(handle)


def test_public_controller_is_chainable_and_owns_its_handle() -> None:
    with xyg.TemporalController(
        instance_id=10,
        domain=(0, 1_000),
        cursor=100,
        window=100,
        step=25,
    ) as controller:
        state = (
            controller.set_cursor(200)
            .step()
            .set_rate(2.0)
            .set_direction(-1)
            .set_loop(True)
            .set_reduced_motion(True)
            .state
        )
        assert state["cursor"] == 225
        assert state["rate_milli"] == 2000
        assert state["direction"] == -1
        assert state["loop_enabled"] is True
        assert state["reduced_motion"] is True
        assert controller.tick(1_000) is False
    with pytest.raises(RuntimeError, match="closed"):
        _ = controller.state


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("instance_id", -1),
        ("instance_id", 1 << 64),
        ("rate_milli", 1 << 32),
        ("domain_start", 1 << 63),
    ],
)
def test_python_host_rejects_scalar_wrap_before_ffi(field: str, value: int) -> None:
    kwargs: dict[str, Any] = {
        "instance_id": 1,
        "domain_start": 0,
        "domain_end": 10,
        "rate_milli": 1000,
    }
    kwargs[field] = value
    with pytest.raises(ValueError):
        _native.temporal_controller_create(**kwargs)


@pytest.mark.parametrize(
    ("operation", "value"),
    [
        ("handle", -1),
        ("handle", 1 << 64),
        ("range", 1 << 63),
        ("cursor", -(1 << 63) - 1),
        ("tick", 1 << 63),
        ("rate", 1 << 32),
        ("direction", 1 << 31),
        ("loop", 1),
        ("reduced_motion", "false"),
    ],
)
def test_python_host_rejects_every_temporal_scalar_before_ffi(operation: str, value: Any) -> None:
    handle = _ctrl(1)
    try:
        calls = {
            "handle": lambda: _native.temporal_controller_state(value),
            "range": lambda: _native.temporal_controller_set_range(handle, value, 10),
            "cursor": lambda: _native.temporal_controller_set_cursor(handle, value),
            "tick": lambda: _native.temporal_controller_tick(handle, value),
            "rate": lambda: _native.temporal_controller_set_rate_milli(handle, value),
            "direction": lambda: _native.temporal_controller_set_direction(handle, value),
            "loop": lambda: _native.temporal_controller_set_loop(handle, value),
            "reduced_motion": lambda: _native.temporal_controller_set_reduced_motion(handle, value),
        }
        with pytest.raises(ValueError):
            calls[operation]()
    finally:
        _native.temporal_controller_destroy(handle)


@pytest.mark.parametrize("rate", [0.0, -1.0, float("inf"), float("nan"), float(1 << 32), True, "2"])
def test_public_controller_rejects_invalid_rate(rate: float) -> None:
    with (
        xyg.TemporalController(instance_id=1, domain=(0, 10)) as controller,
        pytest.raises(ValueError),
    ):
        controller.set_rate(rate)


@pytest.mark.parametrize("rate", [float("inf"), float("nan"), float(1 << 32)])
def test_public_controller_constructor_rejects_invalid_rate(rate: float) -> None:
    with pytest.raises(ValueError):
        xyg.TemporalController(instance_id=1, domain=(0, 10), rate=rate)
