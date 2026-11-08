"""One native XYGC owner per mounted chart; Rust owns data policy (§5/§27)."""

from __future__ import annotations

import asyncio
import math
import threading
from collections import deque
from typing import Any

from . import _native

Request = tuple[int, str, str, tuple[float, float, float, float]]


class ChunkedWidgetBinding:
    """Bounded cross-thread mailbox, one read, and acknowledged frame identity."""

    def __init__(self, widget, path, options):
        self.widget, self.options = widget, options
        self.initial_figure = widget._figure
        self.initial_spec = widget.spec
        self.initial_buffers = widget.buffers
        widget.source_row_ids = widget._figure._chunked_row_ids
        widget.source_provenance = widget._figure._chunked_provenance
        import os

        self.source_file_bytes = os.stat(path).st_size
        self.lock = threading.Condition()
        self.closed = False
        self.generation = options["generation"]
        self.pending: Request | None = None
        self.delivery: tuple[Request, Any, str | None] | None = None
        self.staged: tuple[Any, ...] | None = None
        self.reading = False
        self.mount = None
        self.mount_epoch = 0
        self.thread = None
        try:
            self.loop = asyncio.get_running_loop()
        except RuntimeError:
            self.loop = None  # bound by the first mounted event on a running loop
        self.controls = deque()
        self.latest_view = None
        self.scheduled = False
        self.waiters = set()
        self.last_error = None
        self.published = None
        self.output_capacity = (options["budget_bytes"] // 16) * 24
        self.handle = _native.chunked_columns_open(path)

    def _advance(self):
        if self.generation >= (1 << 64) - 1:
            raise OverflowError("chunked chart generation exhausted")
        self.generation += 1
        _native.chunked_columns_cancel_before(self.handle, self.generation)

    def _schedule(self):
        if not self.scheduled and self.loop is not None:
            self.loop.call_soon_threadsafe(self._deliver)
            self.scheduled = True

    def message(self, content):
        """Admit/cancel before scheduling; no foreign-thread callback or figure edit."""
        if not isinstance(content, dict):
            return True
        kind = content.get("type")
        with self.lock:
            if self.closed:
                return True
            if self.loop is None:
                try:
                    self.loop = asyncio.get_running_loop()
                except RuntimeError:
                    raise RuntimeError("mount a chunked widget on a running event loop") from None
            if kind == "chunked_mount":
                mount, epoch = content.get("mount"), content.get("mount_epoch")
                if not isinstance(mount, str) or not 1 <= len(mount) <= 128 or not _decimal(epoch):
                    return True
                if int(epoch) <= self.mount_epoch:
                    return True
                bootstrap = content.get("chunked_frame", self.initial_figure._chunked_generation)
                if bootstrap not in (
                    self.initial_figure._chunked_generation,
                    self.widget._figure._chunked_generation,
                ):
                    raise ValueError("unowned chunked bootstrap frame")
                self._advance()
                self.mount_epoch, self.mount = int(epoch), mount
                self.latest_intent = None
                self.pending = self.delivery = self.staged = self.latest_view = None
                self.controls.clear()
                self.controls.append(
                    {
                        "type": "_chunked_reset",
                        "initial": bootstrap == self.initial_figure._chunked_generation,
                        "epoch": self.mount_epoch,
                    }
                )
                self.last_error = None
                self._schedule()
                return True
            if content.get("mount") != self.mount or self.mount is None:
                return True
            if kind == "chunked_unmount":
                self._advance()
                self.mount = None
                self.pending = self.delivery = self.staged = self.latest_view = None
                self.controls.clear()
                self.last_error = RuntimeError("chunked painter unmounted")
                self._schedule()
                return True
            if kind == "view_change":
                ranges = content.get("ranges")
                if (
                    not isinstance(ranges, dict)
                    or any(
                        not isinstance(ranges.get(axis), (list, tuple)) or len(ranges[axis]) != 2
                        for axis in ("x", "y")
                    )
                    or not _decimal(content.get("chunked_intent"))
                ):
                    return True
                try:
                    bounds = (
                        float(ranges["x"][0]),
                        float(ranges["x"][1]),
                        float(ranges["y"][0]),
                        float(ranges["y"][1]),
                    )
                except (ValueError, TypeError, OverflowError):
                    return True
                if (
                    not all(math.isfinite(v) for v in bounds)
                    or bounds[0] >= bounds[1]
                    or bounds[2] >= bounds[3]
                ):
                    return True
                intent = content["chunked_intent"]
                if self.latest_intent is not None and int(intent) <= int(self.latest_intent):
                    return True
                self._advance()  # ctypes releases the GIL: cancel the active Rust call now
                self.last_error = None
                self.latest_intent = intent
                self.pending = (self.generation, self.mount, intent, bounds)
                self.delivery = None
                self.latest_view = {
                    "type": "view_change",
                    "ranges": {"x": list(bounds[:2]), "y": list(bounds[2:])},
                    "source": str(content.get("source", "view"))[:64],
                    "phase": str(content.get("phase", "end"))[:16],
                }
                if self.thread is None:
                    self.thread = threading.Thread(target=self._run, daemon=True)
                    self.thread.start()
                self._schedule()
                self.lock.notify_all()
                return True
            # A maximum of 16 small controls; lasso ingress is capped before copying.
            control = _control(content)
            if control is None:
                return True
            if len(self.controls) >= 16:
                raise RuntimeError("chunked control mailbox is full")
            control["_mount"] = self.mount
            control["_epoch"] = self.mount_epoch
            self.controls.append(control)
            self._schedule()
            return True

    @property
    def latest_intent(self):
        return self._intent if hasattr(self, "_intent") else None

    @latest_intent.setter
    def latest_intent(self, value):
        self._intent = value

    def _run(self):
        while True:
            with self.lock:
                self.lock.wait_for(lambda: self.closed or self.pending is not None)
                if self.closed:
                    return
                request, self.pending = self.pending, None
                if request is None:
                    continue
                self.reading = True
            generation, mount, intent, bounds = request
            try:
                result = _native.chunked_columns_chart(
                    self.handle,
                    (bounds[0], bounds[1]),
                    (bounds[2], bounds[3]),
                    budget_bytes=self.options["budget_bytes"],
                    page_bytes=self.options["page_bytes"],
                    generation=generation,
                )
                error = None
            except Exception as exc:
                result, error = None, str(exc)
            with self.lock:
                self.reading = False
                if self.closed:
                    return
                if generation == self.generation and mount == self.mount:
                    self.delivery = (request, result, error)
                self._schedule()

    def _deliver(self):
        from .channel import handle_message
        from .components import scatter, scatter_chart

        with self.lock:
            self.scheduled = False
            if self.closed:
                self._settle()
                return
            controls, self.controls = self.controls, deque()
            view, self.latest_view = self.latest_view, None
        # Figure access and user callbacks are owned by this loop, outside the lock.
        for control in controls:
            if self.closed:
                break
            kind = control["type"]
            if kind != "_chunked_reset" and (
                control.get("_mount") != self.mount or control.get("_epoch") != self.mount_epoch
            ):
                continue
            if kind == "_chunked_reset":
                if control.get("epoch") != self.mount_epoch:
                    continue
                state = self.widget._figure.view_state()
                spec = self.initial_spec if control["initial"] else self.widget.spec
                spec = {
                    **spec,
                    "chunked": {
                        **spec["chunked"],
                        "mount_epoch": str(self.mount_epoch),
                        "state": state,
                    },
                }
                if control["initial"]:
                    self.initial_figure._record_view_ranges(state.get("ranges", {}))
                    self.initial_figure._record_selection(state.get("selection"))
                    self.widget._figure = self.initial_figure
                    self.widget.source_row_ids = self.initial_figure._chunked_row_ids
                    self.widget.source_provenance = self.initial_figure._chunked_provenance
                    self.published = None
                    with self.widget.hold_sync():
                        self.widget.buffers = self.initial_buffers
                        self.widget.spec = spec
                else:
                    self.widget.spec = spec
            elif kind in ("chunked_painted", "chunked_rejected"):
                with self.lock:
                    staged = self.staged
                    if (
                        staged is not None
                        and (control.get("mount"), control.get("intent"), control.get("frame"))
                        == staged[:3]
                    ):
                        if kind == "chunked_painted":
                            self.widget._figure = staged[3]
                            self.widget.source_row_ids = staged[3]._chunked_row_ids
                            self.widget.source_provenance = staged[4]
                            self.published = staged
                            with self.widget.hold_sync():
                                self.widget.spec = staged[6]
                                self.widget.buffers = staged[5]
                        elif int(staged[2]) == self.generation:
                            self.last_error = RuntimeError("chunked frame rejected by painter")
                        self.staged = None
            else:
                try:
                    reply = handle_message(
                        self.widget._figure, control, [], callbacks=self.widget._callbacks
                    )
                    if reply is not None:
                        message, buffers = reply
                        message["chunked_frame"] = self.widget._figure._chunked_generation
                        self.widget.send(message, buffers=buffers)
                except Exception as exc:
                    self.last_error = exc
        if view is not None and not self.closed:
            try:
                handle_message(self.widget._figure, view, [], callbacks=self.widget._callbacks)
                self.widget.spec = {
                    **self.widget.spec,
                    "chunked": {
                        **self.widget.spec["chunked"],
                        "state": self.widget._figure.view_state(),
                    },
                }
            except Exception as exc:
                self.last_error = exc
        with self.lock:
            delivery = None
            if not self.closed and self.staged is None:
                delivery, self.delivery = self.delivery, None
        if delivery is not None:
            (generation, mount, intent, _), result, error = delivery
            buffers = None
            if error is None:
                try:
                    ids, x, y, provenance = result
                    figure = scatter_chart(scatter(x, y, density=False)).figure()
                    figure._chunked_row_ids, figure._chunked_generation = ids, str(generation)
                    spec, buffers = figure.build_payload_split()
                    if sum(memoryview(b).nbytes for b in buffers) > 64 * (
                        self.options["budget_bytes"] // 16
                    ) + (64 << 10):
                        raise ValueError("chunked paint output exceeds derived capacity bound")
                    spec: dict[str, Any] = {
                        **self.initial_spec,
                        "columns": spec["columns"],
                        "traces": spec["traces"],
                        "buffer_layout": spec.get("buffer_layout"),
                        "chunked": {"frame": str(generation)},
                    }
                    state = self.widget._figure.view_state()
                    figure._record_view_ranges(state.get("ranges", {}))
                    figure._record_selection(state.get("selection"))
                    spec["chunked"]["state"] = state
                    spec["chunked"]["mount_epoch"] = str(self.mount_epoch)
                except Exception as exc:
                    error = str(exc)
            with self.lock:
                current = not self.closed and generation == self.generation and mount == self.mount
                if current and error is None:
                    self.staged = (
                        mount,
                        intent,
                        str(generation),
                        figure,
                        provenance,
                        buffers,
                        spec,
                    )
                elif current:
                    self.last_error = RuntimeError(error)
            if current:
                message = (
                    dict(type="chunked_error", mount=mount, intent=intent, error=error)
                    if error
                    else dict(type="chunked_frame", mount=mount, intent=intent, spec=spec)
                )
                try:
                    self.widget.send(message, buffers=buffers if error is None else None)
                except Exception as exc:
                    with self.lock:
                        self.staged = None
                        self.last_error = exc
        with self.lock:
            self._settle()

    def _settle(self):
        idle = not (
            self.pending
            or self.reading
            or self.delivery
            or self.staged
            or self.controls
            or self.latest_view
        )
        if not self.closed and not idle:
            return
        for future in tuple(self.waiters):
            if not future.done():
                if self.closed:
                    future.cancel()
                elif self.last_error is not None:
                    future.set_exception(self.last_error)
                else:
                    future.set_result(None)
        self.waiters.clear()

    async def when_idle(self):
        if asyncio.get_running_loop() is not self.loop:
            raise RuntimeError("wait on the chunked widget owning loop")
        with self.lock:
            if len(self.waiters) >= 16:
                raise RuntimeError("chunked waiter limit is 16")
            future = self.loop.create_future()
            self.waiters.add(future)
            self._settle()
        try:
            await future
        finally:
            with self.lock:
                self.waiters.discard(future)

    def memory_report(self):
        """Capacity accounting, distinct from canonical admission or process RSS."""
        import numpy as np

        from ._payload_trace_materialize import PAYLOAD_TRACE_EMIT_MAX_BYTES

        seen = {}

        def array(value):
            while isinstance(value, (memoryview, np.ndarray)):
                parent = value.obj if isinstance(value, memoryview) else value.base
                if parent is None:
                    break
                value = parent
            if isinstance(value, np.ndarray):
                seen[id(value)] = value.nbytes
            elif isinstance(value, (bytes, bytearray)):
                seen[id(value)] = len(value)

        def figure(fig):
            array(getattr(fig, "_chunked_row_ids", None))
            for column in fig.store.columns:
                array(column.values)
                zone = getattr(column, "_zone", None)
                if zone is not None:
                    for value in vars(zone).values():
                        array(value)
            for buffer in getattr(fig, "_chunked_buffers", []):
                array(buffer)

        with self.lock:
            figure(self.initial_figure)
            for buffer in self.initial_buffers:
                array(buffer)
            original_capacity = sum(seen.values())
            for buffer in self.widget.buffers:
                array(buffer)
            for frame in [self.published, self.staged]:
                if frame:
                    figure(frame[3])
                    for buffer in frame[5] or []:
                        array(buffer)
            if self.delivery and self.delivery[1] is not None:
                for value in self.delivery[1][:3]:
                    array(value)
            known = sum(seen.values())
            inflight = self.output_capacity + 48 if self.reading else 0
            return dict(
                host_retained_capacity_bytes=known,
                host_inflight_output_capacity_bytes=inflight,
                host_typed_capacity_bound_bytes=4
                * (
                    2 * self.output_capacity
                    + 2 * (64 * (self.options["budget_bytes"] // 16) + (64 << 10))
                )
                + original_capacity,
                original_overview_capacity_bytes=original_capacity,
                native_source_file_bytes=self.source_file_bytes,
                native_cache_entry_count_bound=min(self.options["page_bytes"], 8 << 20) // 16,
                control_boxed_bytes_bound=2 * 16 * (2048 * 128 + 8192),
                serialization_payload_bound_bytes=64 * (self.options["budget_bytes"] // 16)
                + (64 << 10),
                native_canonical_admission_bytes=self.options["budget_bytes"],
                native_cache_payload_bound_bytes=min(self.options["page_bytes"], 8 << 20),
                native_result_capacity_bound_bytes=max(4 * self.output_capacity, 192),
                existing_trace_emitter_arena_bytes=PAYLOAD_TRACE_EMIT_MAX_BYTES,
                control_mailbox_count=len(self.controls),
                control_mailbox_limit=16,
                pending_intents=int(self.pending is not None),
                active_reads=int(self.reading),
                waiter_count=len(self.waiters),
                staged_frames=int(self.staged is not None),
                completed_results=int(self.delivery is not None),
            )

    def close(self):
        error = None
        with self.lock:
            if self.closed:
                return
            self.closed = True
            try:
                self._advance()
            except Exception as exc:
                error = exc
            self.pending = self.delivery = self.staged = self.latest_view = self.published = None
            self.controls.clear()
            self.lock.notify_all()
        try:
            if self.thread is not None:
                self.thread.join()
        finally:
            _native.chunked_columns_free(self.handle)
            self.handle = 0
            if self.loop and not self.loop.is_closed():
                self.loop.call_soon_threadsafe(self._settle)
        if error is not None:
            raise error


def _decimal(value):
    return (
        isinstance(value, str) and 1 <= len(value) <= 20 and value.isascii() and value.isdecimal()
    )


def _control(content):
    kind = content.get("type")
    fields = {
        "chunked_painted": ("mount", "intent", "frame"),
        "chunked_rejected": ("mount", "intent", "frame"),
        "pick": ("trace", "index", "seq", "chunked_frame"),
        "click": ("trace", "index", "chunked_frame"),
        "select": ("x0", "x1", "y0", "y1", "chunked_frame", "include_rows", "seq"),
        "select_clear": ("chunked_frame",),
        "select_polygon": ("chunked_frame", "include_rows", "seq"),
    }
    if kind not in fields:
        return None
    out = {"type": kind}
    for key in fields[kind]:
        value = content.get(key)
        if not (
            value is None
            or isinstance(value, (int, float, bool))
            or (isinstance(value, str) and len(value) <= 128)
        ):
            return None
        out[key] = value
    if kind == "select_polygon":
        points = content.get("points")
        if not isinstance(points, (list, tuple)) or not 3 <= len(points) <= 2048:
            return None
        try:
            if any(not isinstance(p, (list, tuple)) or len(p) != 2 for p in points):
                return None
            out["points"] = [[float(x), float(y)] for x, y in points]
            if not all(math.isfinite(v) for p in out["points"] for v in p):
                return None
        except (ValueError, TypeError, OverflowError):
            return None
    return out
