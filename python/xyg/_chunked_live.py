"""Native XYGC widget orchestration; selection/admission remain in Rust (§5)."""

from __future__ import annotations

import asyncio
import math
import threading

from . import _native


class ChunkedWidgetBinding:
    """One independent native handle, active read, and latest intent per widget."""

    def __init__(self, widget, path, options):
        self.widget = widget
        self.options = options
        self.initial_figure = widget._figure
        self.staged = None
        self.lock = threading.Condition()
        self.closed = False
        self.generation = options["generation"]
        self.pending = None
        self.mount = None
        self.thread = None
        self.loop = None
        self.delivery = None
        self.scheduled = False
        self.mount_epoch = 0
        self.handle = _native.chunked_columns_open(path)

    def message(self, content):
        if not isinstance(content, dict):
            return True
        kind = content.get("type")
        if self.closed:
            return True
        if kind in ("chunked_painted", "chunked_rejected"):
            with self.lock:
                staged = self.staged
                if (
                    staged is not None
                    and (content.get("mount"), content.get("intent"), content.get("frame"))
                    == staged[:3]
                ):
                    if kind == "chunked_painted":
                        self.widget._figure = staged[3]
                        self.widget.source_row_ids = staged[3]._chunked_row_ids
                        self.widget.source_provenance = staged[4]
                    self.staged = None
                    if self.delivery is not None and not self.scheduled:
                        self.scheduled = True
                        self.loop.call_soon_threadsafe(self._deliver)
            return True
        if kind == "chunked_mount":
            mount = content.get("mount")
            if not isinstance(mount, str) or len(mount) > 128:
                return True
            epoch = content.get("mount_epoch")
            if not isinstance(epoch, str) or not epoch.isdecimal() or len(epoch) > 20:
                return True
            with self.lock:
                if self.closed or int(epoch) <= self.mount_epoch:
                    return True
                self.mount_epoch = int(epoch)
                self.generation += 1
                _native.chunked_columns_cancel_before(self.handle, self.generation)
                self.mount = mount
                self.staged = None
                self.widget._figure = self.initial_figure
                self.pending = self.delivery = None
            return True
        if kind == "chunked_unmount":
            with self.lock:
                if content.get("mount") == self.mount and not self.closed:
                    self.generation += 1
                    _native.chunked_columns_cancel_before(self.handle, self.generation)
                    self.mount = None
                    self.staged = None
                    self.pending = self.delivery = None
            return True
        if kind != "view_change":
            return False
        try:
            ranges = content["ranges"]
            if not isinstance(ranges, dict) or any(
                not isinstance(ranges.get(axis), (list, tuple)) or len(ranges[axis]) != 2
                for axis in ("x", "y")
            ):
                return True
            bounds = tuple(float(v) for axis in ("x", "y") for v in ranges[axis])
            if len(bounds) != 4 or not all(math.isfinite(v) for v in bounds):
                return True
            if bounds[0] >= bounds[1] or bounds[2] >= bounds[3]:
                return True
            intent = content["chunked_intent"]
            if not isinstance(intent, str) or not intent.isdecimal() or len(intent) > 20:
                return True
            loop = asyncio.get_running_loop()
        except (KeyError, TypeError, ValueError, RuntimeError):
            return True
        with self.lock:
            if self.closed or self.mount is None or content.get("mount") != self.mount:
                return True
            if self.loop is not None and self.loop is not loop:
                # Comm dispatch can move loops. Publication stays on the original loop.
                loop = self.loop
            self.loop = loop
            self.generation += 1
            _native.chunked_columns_cancel_before(self.handle, self.generation)
            self.pending = (self.generation, self.mount, intent, bounds)
            self.delivery = None
            if self.thread is None:
                self.thread = threading.Thread(target=self._run, daemon=True)
                self.thread.start()
            self.lock.notify()
        return False  # normal durable view-state and callback processing still runs

    def _run(self):
        while True:
            with self.lock:
                self.lock.wait_for(lambda: self.closed or self.pending is not None)
                if self.closed:
                    return
                request, self.pending = self.pending, None
            generation, mount, intent, bounds = request
            try:
                result = _native.chunked_columns_chart(
                    self.handle,
                    bounds[:2],
                    bounds[2:],
                    budget_bytes=self.options["budget_bytes"],
                    page_bytes=self.options["page_bytes"],
                    generation=generation,
                )
                error = None
            except Exception as exc:
                result, error = None, str(exc)
            with self.lock:
                if self.closed or generation != self.generation or mount != self.mount:
                    continue
                self.delivery = (request, result, error)
                if not self.scheduled:
                    self.scheduled = True
                    try:
                        self.loop.call_soon_threadsafe(self._deliver)
                    except RuntimeError:
                        self.scheduled = False
                        self.delivery = None

    def _deliver(self):
        from .components import scatter, scatter_chart

        with self.lock:
            self.scheduled = False
            if self.staged is not None:
                return
            delivery, self.delivery = self.delivery, None
            if self.closed or delivery is None:
                return
            (generation, mount, intent, _), result, error = delivery
            if generation != self.generation or mount != self.mount:
                return
            buffers = None
            if error is not None:
                message = dict(type="chunked_error", mount=mount, intent=intent, error=error)
            else:
                try:
                    ids, x, y, provenance = result
                    figure = scatter_chart(scatter(x, y)).figure()
                    figure._chunked_row_ids = ids
                    figure._chunked_generation = str(generation)
                    spec, buffers = figure.build_payload_split()
                    spec["chunked"] = dict(frame=str(generation))
                    figure._record_view_ranges(self.widget._figure.view_state().get("ranges", {}))
                    self.staged = (mount, intent, str(generation), figure, provenance)
                    message = dict(type="chunked_frame", mount=mount, intent=intent, spec=spec)
                except Exception as exc:
                    self.staged = None
                    message = dict(type="chunked_error", mount=mount, intent=intent, error=str(exc))
        # Transport callbacks may synchronously close the widget. Never join a
        # worker while retaining the condition it needs to observe cancellation.
        self.widget.send(message, buffers=buffers)

    def close(self):
        with self.lock:
            if self.closed:
                return
            self.closed = True
            self.staged = None
            self.generation += 1
            _native.chunked_columns_cancel_before(self.handle, self.generation)
            self.pending = self.delivery = None
            self.lock.notify_all()
        if self.thread is not None:
            self.thread.join()
        _native.chunked_columns_free(self.handle)
        self.handle = 0
