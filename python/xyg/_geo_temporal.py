"""Bounded native scheduling; all geographic decisions remain Rust-owned."""

import asyncio
from copy import deepcopy
from dataclasses import replace
from weakref import WeakKeyDictionary

_BINDINGS = WeakKeyDictionary()
_MAX = (1 << 64) - 1


class GeoTemporalBinding:
    """Own one private accepted frame. Snapshot callers own independent leases."""

    def __init__(self, chart, controller, mode="cursor"):
        from ._geo_retained import RetainedGeoSource

        if mode not in ("cursor", "range"):
            raise ValueError("mode must be cursor or range")
        asyncio.get_running_loop()
        layer = chart._retained_layer()
        if layer is None or type(layer.source) is not RetainedGeoSource or chart.tile_session:
            raise ValueError("temporal binding requires one canonical retained points composition")
        query, sequence, _ = chart._retained_inputs(layer)
        if controller.state["disposed"]:
            raise RuntimeError("controller disposed")
        if layer.source in _BINDINGS:
            raise RuntimeError("source already has a temporal binding")
        self._source, self._layer, self._template = layer.source, layer, chart
        self._query, self._sequence = (
            {
                **query,
                "source_digest": bytes(query["source_digest"]),
                "camera": dict(query["camera"]),
                "time": dict(query["time"]),
            },
            sequence,
        )
        self._mode, self._closed, self._generation = mode, False, 0
        self._frame = self._chart = self._task = None
        self._retiring = None
        self._lock = asyncio.Lock()
        self.error = None
        self._time = None
        _BINDINGS[self._source] = self
        self._unsubscribe = controller.subscribe_state(self._accept)
        self._accept(controller.state)

    def _accept(self, state):
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
                    if self._source._bridge is None:
                        candidate = await asyncio.to_thread(chart.compile, _publish=False)
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
            await asyncio.shield(task)
            if task is self._task:
                return

    async def snapshot(self):
        """Return (exact public composition, independently owned frame)."""
        await self.when_idle()
        async with self._lock:
            if self._frame is None:
                raise RuntimeError("no accepted temporal frame") from self.error
            return self._chart, await self._frame.retain_async()

    def _detach(self):
        self._closed = True
        self._generation += 1
        self._unsubscribe()

    async def aclose(self):
        """Drain admitted reads and release private frame; caller leases survive."""
        self._detach()
        await self.when_idle()
        async with self._lock:
            if self._retiring is not None:
                await self._retiring.aclose()
                self._retiring = None
            if self._frame is not None:
                await self._frame.aclose()
                self._frame = None
            if _BINDINGS.get(self._source) is self:
                del _BINDINGS[self._source]
