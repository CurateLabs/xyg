"""Bounded native scheduling; all geographic decisions remain Rust-owned."""

import asyncio
from collections.abc import Mapping
from copy import deepcopy
from dataclasses import replace
from functools import partial
from weakref import WeakKeyDictionary

from ._geoscale import _settle

_BINDINGS = WeakKeyDictionary()
_MAX = (1 << 64) - 1


def _copy_chart(chart):
    # Canonical digests may borrow native memory. Copy values, not source owners.
    layers = []
    for layer in chart.layers:
        properties = dict(layer.properties)
        query = dict(properties["query"])
        query["source_digest"] = bytes(query["source_digest"])
        query["camera"] = dict(query["camera"])
        query["time"] = dict(query["time"])
        properties["query"] = query
        if isinstance(properties["style"], Mapping):
            style = dict(properties["style"])
            style["fill"], style["stroke"] = bytes(style["fill"]), bytes(style["stroke"])
            properties["style"] = style
        layers.append(replace(layer, properties=deepcopy(properties)))
    return replace(
        chart,
        layers=tuple(layers),
        camera=deepcopy(dict(chart.camera)),
        legend=deepcopy(chart.legend),
        tile_vector_styles=deepcopy(chart.tile_vector_styles),
    )


class GeoTemporalBinding:
    """Own one private accepted frame. Snapshot callers own independent leases."""

    def __init__(self, chart, controller, mode="cursor"):
        from ._geo_retained import RetainedGeoSource

        if mode not in ("cursor", "range"):
            raise ValueError("mode must be cursor or range")
        self._loop = asyncio.get_running_loop()
        layer = chart._retained_layer()
        if layer is None or type(layer.source) is not RetainedGeoSource or chart.tile_session:
            raise ValueError("temporal binding requires one canonical retained points composition")
        query, sequence, _ = chart._retained_inputs(layer)
        if controller.state["disposed"]:
            raise RuntimeError("controller disposed")
        if layer.source in _BINDINGS:
            raise RuntimeError("source already has a temporal binding")
        self._template = _copy_chart(chart)
        self._source, self._layer = layer.source, self._template.layers[0]
        # The typed request is a heterogeneous mapping; Rust validates each
        # named field when it is encoded. Preserve field values and copy owners.
        self._query: dict = {
            **query,
            "source_digest": bytes(query["source_digest"]),
            "camera": dict(query["camera"]),
            "time": dict(query["time"]),
        }
        self._sequence = sequence
        self._mode, self._closed, self._generation = mode, False, 0
        self._frame = self._chart = self._task = None
        self._retiring = None
        self._lock = asyncio.Lock()
        self.error = None
        self._time = None
        _BINDINGS[self._source] = self
        self._unsubscribe = lambda: None
        try:
            self._unsubscribe = controller.subscribe_state(self._accept)
            self._accept(controller.state)
        except BaseException:
            self._closed = True
            self._unsubscribe()
            if _BINDINGS.get(self._source) is self:
                del _BINDINGS[self._source]
            raise

    def _accept(self, state):
        # Native controller notifications run on the mutating thread. Only the
        # binding's owning loop may update intent or create coroutine tasks.
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None
        if loop is not self._loop:
            try:
                self._loop.call_soon_threadsafe(self._accept, deepcopy(state))
            except RuntimeError:
                if not self._loop.is_closed():
                    raise
            return
        if self._closed:
            return
        if state["disposed"]:
            self._closing = asyncio.create_task(self.aclose())
            self._closing.add_done_callback(
                lambda task: None if task.cancelled() else task.exception()
            )
            self._detach()
            return
        time = (
            dict(kind=1, instant=state["cursor"])
            if self._mode == "cursor"
            else dict(kind=2, start=state["range_start"], end=state["range_end"])
        )
        if time == self._time:
            return
        self._time = time
        self._query["time"] = time
        self._query["time_revision"] += 1
        self._schedule()

    def _schedule(self):
        self._generation += 1
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._pump())

    async def _pump(self):
        while not self._closed:
            generation = self._generation
            async with self._lock:
                candidate = None
                cancellation = self._source._cancel_generation
                synchronous = self._source._bridge is None
                try:
                    if self._retiring is not None:
                        await self._retiring.aclose()
                        self._retiring = None
                    self._sequence += 1
                    if (
                        max(
                            self._sequence,
                            self._query["time_revision"],
                            self._query["camera_revision"],
                        )
                        > _MAX
                    ):
                        raise OverflowError("geographic revision exhausted")
                    query = deepcopy(self._query)
                    layer = replace(
                        self._layer,
                        properties={
                            **self._layer.properties,
                            "query": query,
                            "sequence": self._sequence,
                        },
                    )
                    chart = replace(self._template, layers=(layer,), camera=query["camera"])
                    if synchronous:
                        # A plain Future is not cancelled by loop shutdown's
                        # task sweep. Keep ownership until the worker settles.
                        worker = self._loop.run_in_executor(
                            None, partial(chart.compile, _publish=False)
                        )
                        candidate, interrupted = await _settle(worker)
                        if interrupted:
                            self._retiring = candidate
                            await self._retiring.aclose()
                            self._retiring = None
                            raise asyncio.CancelledError
                    else:
                        candidate = await chart.compile_async(_publish=False)
                    if self._closed or generation != self._generation:
                        self._retiring = candidate
                        await self._retiring.aclose()
                        self._retiring = None
                    else:
                        old, self._frame = self._frame, candidate
                        self._chart = chart
                        self.error = None
                        if old is not None:
                            self._retiring = old
                            await self._retiring.aclose()
                            self._retiring = None
                except asyncio.CancelledError:
                    task = asyncio.current_task()
                    if task is not None:
                        # Acknowledge only source-owned task.cancel() requests.
                        # Other task cancellation (for example loop shutdown) is
                        # still terminal; reader-raised cancellation has no count.
                        owned = 0 if synchronous else self._source._cancel_generation - cancellation
                        for _ in range(min(owned, task.cancelling())):
                            task.uncancel()
                        if task.cancelling():
                            raise
                    # Source cancellation is an operation failure, not cancellation
                    # of callers waiting on this pump. Keep the last accepted lease.
                    self.error = RuntimeError("geographic source read cancelled")
                    if self._source._disposal is not None:
                        self._detach()
                        if _BINDINGS.get(self._source) is self:
                            del _BINDINGS[self._source]
                except Exception as error:
                    self.error = error.with_traceback(None)
            if generation == self._generation:
                return

    def set_camera(self, camera):
        """Schedule a complete authored camera snapshot with current temporal state."""
        if self._closed:
            raise RuntimeError("binding disposed")
        self._query["camera"] = deepcopy(camera)
        self._query["camera_revision"] += 1
        self._schedule()

    async def when_idle(self):
        """Wait for admitted work and latest pending replacement to settle."""
        while self._task is not None:
            task = self._task
            try:
                await asyncio.shield(task)
            except asyncio.CancelledError:
                waiter = asyncio.current_task()
                if waiter is None or waiter.cancelling() or not task.cancelled():
                    raise
                # A terminal child cancellation cannot make private-owner cleanup
                # permanently inaccessible. Genuine caller cancellation propagates.
                self.error = RuntimeError("geographic operation cancelled")
            if task is self._task:
                return

    async def snapshot(self):
        """Return (exact public composition, independently owned frame)."""
        await self.when_idle()
        async with self._lock:
            if self._frame is None:
                raise RuntimeError("no accepted temporal frame") from self.error
            return _copy_chart(self._chart), await self._frame.retain_async()

    def _detach(self):
        self._closed = True
        self._generation += 1
        self._unsubscribe()

    async def aclose(self):
        """Drain admitted reads and release private frame; caller leases survive."""
        self._detach()
        waiter = asyncio.current_task()
        cancellation = 0 if waiter is None else waiter.cancelling()
        interrupted = False
        job = self._task
        if job is not None:
            try:
                _, interrupted = await _settle(job)
            except asyncio.CancelledError:
                if not job.cancelled():
                    raise
                # Child cancellation is terminal work completion. A new caller
                # cancellation remains observable after private-owner teardown.
                interrupted = waiter is not None and waiter.cancelling() > cancellation
        async with self._lock:
            if self._retiring is not None:
                await self._retiring.aclose()
                self._retiring = None
            if self._frame is not None:
                await self._frame.aclose()
                self._frame = None
            if _BINDINGS.get(self._source) is self:
                del _BINDINGS[self._source]
        if interrupted:
            raise asyncio.CancelledError
