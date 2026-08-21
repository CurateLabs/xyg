"""Ergonomic host wrapper for Rust-owned temporal coordination."""

from __future__ import annotations

import math
from collections.abc import Iterable, Mapping
from types import TracebackType
from typing import Self

from . import _native


def _rate_to_milli(rate: float) -> int:
    if isinstance(rate, bool) or not isinstance(rate, (int, float)):
        raise ValueError("rate must be a real number")
    value = float(rate)
    if not math.isfinite(value):
        raise ValueError("rate must be finite")
    rate_milli = round(value * 1000)
    if rate_milli <= 0 or rate_milli > (1 << 32) - 1:
        raise ValueError("rate must resolve to 1..4294967295 milli-units")
    return rate_milli


class TemporalController:
    """Own a native temporal-controller handle.

    Times are integer UTC microseconds. ``close()`` is deterministic and the
    context-manager form is preferred for short-lived controllers.
    """

    def __init__(
        self,
        *,
        instance_id: int,
        domain: tuple[int, int],
        cursor: int | None = None,
        window: int = 0,
        step: int = 1,
        group_id: int = 0,
        rate: float = 1.0,
        direction: int = 1,
        loop: bool = False,
        reduced_motion: bool = False,
    ) -> None:
        rate_milli = _rate_to_milli(rate)
        self._handle: int | None = _native.temporal_controller_create(
            instance_id=instance_id,
            group_id=group_id,
            domain_start=domain[0],
            domain_end=domain[1],
            cursor=domain[0] if cursor is None else cursor,
            window=window,
            step=step,
            direction=direction,
            rate_milli=rate_milli,
            loop_enabled=loop,
            reduced_motion=reduced_motion,
        )

    def _open_handle(self) -> int:
        if self._handle is None:
            raise RuntimeError("TemporalController is closed")
        return self._handle

    @property
    def state(self) -> dict[str, int | bool | list[int]]:
        """Return the current canonical Rust state."""
        return _native.temporal_controller_state(self._open_handle())

    def set_range(self, start: int, end: int) -> Self:
        _native.temporal_controller_set_range(self._open_handle(), start, end)
        return self

    def set_cursor(self, cursor: int) -> Self:
        _native.temporal_controller_set_cursor(self._open_handle(), cursor)
        return self

    def set_selection(self, ids: Iterable[int]) -> Self:
        """Replace linked views' exact stable-ID selection (empty clears)."""
        _native.temporal_controller_set_selection(self._open_handle(), ids)
        return self

    def step(self) -> Self:
        _native.temporal_controller_step(self._open_handle())
        return self

    def play(self) -> Self:
        _native.temporal_controller_play(self._open_handle())
        return self

    def pause(self) -> Self:
        _native.temporal_controller_pause(self._open_handle())
        return self

    def set_rate(self, rate: float) -> Self:
        """Set playback speed as a positive multiplier (for example ``2.0``)."""
        rate_milli = _rate_to_milli(rate)
        _native.temporal_controller_set_rate_milli(self._open_handle(), rate_milli)
        return self

    def set_direction(self, direction: int) -> Self:
        """Set playback direction to ``1`` (forward) or ``-1`` (reverse)."""
        if direction not in (-1, 1):
            raise ValueError("direction must be -1 or 1")
        _native.temporal_controller_set_direction(self._open_handle(), direction)
        return self

    def set_loop(self, enabled: bool) -> Self:
        _native.temporal_controller_set_loop(self._open_handle(), enabled)
        return self

    def set_reduced_motion(self, enabled: bool) -> Self:
        _native.temporal_controller_set_reduced_motion(self._open_handle(), enabled)
        return self

    def tick(self, elapsed_micros: int) -> bool:
        return _native.temporal_controller_tick(self._open_handle(), elapsed_micros)

    def poll_event(self) -> dict[str, int | list[int]] | None:
        return _native.temporal_controller_poll_event(self._open_handle())

    def apply_event(self, event: Mapping[str, object]) -> bool:
        return _native.temporal_controller_apply_event(self._open_handle(), dict(event))

    def dispose(self) -> None:
        """Stop playback and reject future commands without freeing the handle."""
        _native.temporal_controller_dispose(self._open_handle())

    def close(self) -> None:
        """Release the native handle; idempotent."""
        handle, self._handle = self._handle, None
        if handle is not None:
            _native.temporal_controller_destroy(handle)

    def __enter__(self) -> Self:
        self._open_handle()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()
