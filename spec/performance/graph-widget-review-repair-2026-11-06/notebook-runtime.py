"""Progressive native layout feeding the ordinary notebook FigureWidget.

Keep the existing declarative compiler, Rust geometry/membership kernels and
channel callbacks. Only layout scheduling and revisioned frame delivery live here.
"""

from __future__ import annotations

import asyncio
import copy
import json
import secrets
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from functools import partial

from .channel import handle_message
from .graph_layout import GraphLayoutController
from .widget import FigureWidget


class GraphWidget(FigureWidget):
    def __init__(self, chart, **kwargs):
        self._chart = chart
        self._instance = secrets.token_hex(16)
        self._epoch = None
        self._revision = 0
        self._figures = {}
        self._last_view_state = {"v": 1, "ranges": {}, "selection": None}
        self._closed = False
        self._task = None
        self._loop = None
        self._controller = None
        self._ack = None
        self._pending_api = []
        self._building = False
        self._appended_traces = {}
        self._state_versions = dict.fromkeys(("ranges", "selection", "visibility"), 0)
        self._figure_versions = {}
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="xyg-graph-build")
        super().__init__(None, **kwargs)
        self._wasm_ticks = self.spec.get("wasm_ticks")
        self.spec = {"graph_host": True, "instance": self._instance}
        # FigureWidget registers its virtual handler, which delegates here.

    def _compile(self, checkpoint):
        chart = copy.copy(self._chart)
        chart._figure = chart._widget = None
        mark = self._chart._graphforge_mark
        data = copy.copy(mark.props["nodes"])
        data.x, data.y = checkpoint.x, checkpoint.y
        replacement = replace(
            mark,
            x=None,
            y=None,
            props={**mark.props, "nodes": data, "layout": "preset", "cose": None, "pinned": None},
        )
        chart.children = [replacement if child is mark else child for child in chart.children]
        figure = chart.figure()
        graph_index = next(
            i
            for i, child in enumerate(
                c for c in chart.children if getattr(c, "kind", None) == "graph"
            )
            if child is replacement
        )
        figure._graph_meta[graph_index].update(
            layout=mark.props["layout"], iterations=checkpoint.step, alpha=checkpoint.alpha
        )
        # Reuse the canonical native columns of appended traces; rebuilding a
        # layout frame must not reconstruct these traces from initial authoring.
        # Only copy trace bookkeeping: no append history or duplicate row store.
        for trace_id, trace in self._appended_traces.items():
            figure.traces[trace_id] = copy.copy(trace)
        return figure, figure.build_payload_split()

    async def _run(self, epoch):
        loop = asyncio.get_running_loop()
        mark = self._chart._graphforge_mark
        controller = GraphLayoutController(mark.props["nodes"])
        self._controller = controller

        async def publish(checkpoint):
            self._building = True
            try:
                figure, (spec, buffers) = await loop.run_in_executor(
                    self._executor, self._compile, checkpoint
                )
            finally:
                self._building = False
            if self._closed or self._epoch != epoch:
                return
            self._configure_transport(spec)
            if self._wasm_ticks is not None:
                spec["wasm_ticks"] = self._wasm_ticks
            restore = None
            if self._figure is None and self._last_view_state["ranges"]:
                figure._record_view_ranges(self._last_view_state["ranges"])
                figure._record_selection(copy.deepcopy(self._last_view_state["selection"]))
                restore = copy.deepcopy(self._last_view_state)
                # Row masks are non-durable; a view-state marker is not a mask.
                if restore["selection"] == {"rows": True}:
                    restore.pop("selection")
                    figure._record_selection(None)
            if self._figure is not None:
                figure._view_state_ranges = copy.deepcopy(self._figure._view_state_ranges)
                figure._view_state_selection = copy.deepcopy(self._figure._view_state_selection)
                for previous, current in zip(self._figure.traces, figure.traces, strict=True):
                    current.hidden = previous.hidden
                    current.hidden_categories = set(previous.hidden_categories)
            self._figure = figure
            self._revision += 1
            self._figures[self._revision] = figure
            self._figure_versions[self._revision] = dict(self._state_versions)
            # A single immutable picture is retained until the browser paints it.
            # All events are admitted against exactly this figure/revision.
            self._ack = asyncio.Event()
            # Preserve ordinary saved-widget state without a second buffer send.
            # The browser mirrors this state locally when it accepts the frame.
            snapshot = {
                "graph_host": True,
                "instance": self._instance,
                "graph_snapshot": {
                    "spec": spec,
                    "step": checkpoint.step,
                    "phase": checkpoint.phase,
                    "restore_state": restore,
                },
            }
            with self._lock_property(spec=json.loads(json.dumps(snapshot)), buffers=buffers):
                self.spec = snapshot
                self.buffers = buffers
            self.send(
                {
                    "type": "graph_frame",
                    "spec": spec,
                    "step": checkpoint.step,
                    "phase": checkpoint.phase,
                    "restore_state": restore,
                },
                buffers=buffers,
            )
            await asyncio.wait_for(self._ack.wait(), timeout=30)

        try:
            await controller.layout(
                revision=1,
                layout=mark.props["layout"],
                seed=mark.props["seed"],
                total_steps=mark.props["iterations"],
                cose=mark.props.get("cose"),
                pinned=mark.props.get("pinned"),
                on_update=publish,
                job_id=f"{self._instance}:{epoch}",
            )
        except asyncio.CancelledError:
            raise
        except Exception:
            if not self._closed and self._epoch == epoch:
                self.send({"type": "graph_failed", "code": "XYG_GRAPH_WORKER_FAILED"})
        finally:
            controller.dispose()
            if self._controller is controller:
                self._controller = None

    def send(self, content, buffers=None):
        super().send(
            {
                **content,
                "graph_instance": self._instance,
                "graph_epoch": self._epoch,
                "graph_revision": content.get("graph_revision", self._revision),
            },
            buffers=buffers,
        )

    def _host_call(self, callback, *args, **kwargs):
        if self._closed:
            raise RuntimeError("graph widget disposed")
        try:
            current = asyncio.get_running_loop()
        except RuntimeError:
            current = None
        if self._loop is not None and current is not self._loop:
            self._loop.call_soon_threadsafe(partial(self._host_call, callback, *args, **kwargs))
            return
        if (
            self._figure is None
            or self._epoch is None
            or self._building
            or self._ack is None
            or not self._ack.is_set()
        ):
            self._pending_api.append(
                (self._epoch, partial(self._host_call, callback, *args, **kwargs))
            )
            return
        fields = {
            "select": ("selection",),
            "clear_selection": ("selection",),
            "set_view": ("ranges",),
            "reset_view": ("ranges",),
        }.get(callback.__name__, ())
        for field in fields:
            self._state_versions[field] += 1
            self._figure_versions[self._revision][field] = self._state_versions[field]
        return callback(*args, **kwargs)

    def view_state(self):
        if self._figure is None:
            return copy.deepcopy(self._last_view_state)
        return super().view_state()

    def select(self, **kwargs):
        return self._host_call(super().select, **kwargs)

    def set_view(self, *args, **kwargs):
        return self._host_call(super().set_view, *args, **kwargs)

    def reset_view(self, *args, **kwargs):
        return self._host_call(super().reset_view, *args, **kwargs)

    def clear_selection(self):
        return self._host_call(super().clear_selection)

    def append(self, trace_id, x, y, **kwargs):
        return self._host_call(self._append, trace_id, x, y, **kwargs)

    def _append(self, trace_id, x, y, **kwargs):
        msg, buffers = self._figure.append(trace_id, x, y, **kwargs)
        self._appended_traces[trace_id] = copy.copy(self._figure.traces[trace_id])
        self._configure_transport(msg["spec"])
        snapshot = {
            **self.spec,
            "graph_snapshot": {**self.spec["graph_snapshot"], "spec": msg["spec"]},
        }
        with self._lock_property(spec=json.loads(json.dumps(snapshot)), buffers=buffers):
            self.spec, self.buffers = snapshot, buffers
        # The ordinary append message preserves the native canonical-column and
        # generic renderer contract; the wrapper envelope remains notebook state.
        self.send(msg, buffers=buffers)

    @staticmethod
    def _state(figure):
        return {
            "ranges": copy.deepcopy(figure._view_state_ranges),
            "selection": copy.deepcopy(figure._view_state_selection),
            "visibility": [(t.hidden, set(t.hidden_categories)) for t in figure.traces],
        }

    def _cancel(self):
        if self._loop is not None and self._loop.is_running():
            try:
                current = asyncio.get_running_loop()
            except RuntimeError:
                current = None
            if current is not self._loop:
                self._loop.call_soon_threadsafe(self._cancel)
                return
        if self._ack is not None:
            self._ack.set()
        if self._task is not None:
            self._task.cancel()
        if self._controller is not None:
            self._controller.cancel()

    def _on_custom_msg(self, widget, content, msg_buffers):
        if self._closed or not isinstance(content, dict):
            return
        if self._loop is not None:
            try:
                current = asyncio.get_running_loop()
            except RuntimeError:
                current = None
            if current is not self._loop:
                if not self._loop.is_closed():
                    self._loop.call_soon_threadsafe(
                        self._on_custom_msg, widget, content, msg_buffers
                    )
                return
        if content.get("graph_instance") != self._instance:
            return
        epoch = content.get("graph_epoch")
        if content.get("type") == "graph_mount":
            if not isinstance(epoch, str) or not 0 < len(epoch) <= 64 or epoch == self._epoch:
                return
            self._cancel()
            self._epoch = epoch
            self._figures.clear()
            self._figure_versions.clear()
            if self._figure is not None:
                self._last_view_state = self._figure.view_state()
            self._figure = None
            self._loop = asyncio.get_running_loop()
            self._task = self._loop.create_task(self._run(epoch))
            return
        if epoch == self._epoch and content.get("type") == "graph_dispose":
            self._epoch = None
            self._cancel()
            self._figures.clear()
            return
        revision = content.get("graph_revision")
        if epoch != self._epoch or type(revision) is not int or revision not in self._figures:
            return
        if content.get("type") == "graph_painted":
            if revision == self._revision and self._ack is not None:
                self._figures = {revision: self._figures[revision]}
                self._figure_versions = {revision: self._figure_versions[revision]}
                self._ack.set()
                pending, self._pending_api = self._pending_api, []
                for epoch, callback in pending:
                    if epoch is None or epoch == self._epoch:
                        callback()
        else:
            # Retain the displayed snapshot until the pending picture's ACK.
            # Resolve an event against its exact native-compiled row space;
            # never reinterpret old indices against newer moving geometry.
            figure = self._figures[revision]
            before = self._state(figure)
            reply = handle_message(figure, content, msg_buffers, callbacks=self._callbacks)
            after = self._state(figure)
            for field in before:
                if before[field] == after[field]:
                    continue
                if self._figure_versions[revision][field] != self._state_versions[field]:
                    continue  # a later Python mutation already owns this facet
                self._state_versions[field] += 1
                self._figure_versions[revision][field] = self._state_versions[field]
                if figure is not self._figure:
                    if field == "visibility":
                        for trace, (hidden, categories) in zip(
                            self._figure.traces, after[field], strict=True
                        ):
                            trace.hidden, trace.hidden_categories = hidden, set(categories)
                    else:
                        setattr(self._figure, "_view_state_" + field, copy.deepcopy(after[field]))
                    self._figure_versions[self._revision][field] = self._state_versions[field]
            if reply is not None:
                msg, buffers = reply
                self.send({**msg, "graph_revision": revision}, buffers=buffers)

    def close(self):
        if getattr(self, "_closed", True):
            return
        self._closed = True
        self._pending_api.clear()
        self._figures.clear()
        self._epoch = None
        self._cancel()
        self._executor.shutdown(wait=False, cancel_futures=True)
        super().close()
