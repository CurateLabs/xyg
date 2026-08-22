"""Off-thread progressive graph layout scheduling.

Rust owns every force and position decision.  This module only schedules bounded
native ticks, rejects stale revisions, and transports immutable checkpoints back
to an interactive Python event loop.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Mapping
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from numbers import Integral
from threading import Event, Lock
from time import monotonic
from typing import Any

import numpy as np
import numpy.typing as npt

from . import _native
from ._graph import GraphData


class GraphLayoutError(RuntimeError):
    """Stable base error for progressive graph scheduling failures."""


class GraphLayoutSuperseded(GraphLayoutError):
    """Raised when a newer render revision supersedes a layout job."""


class GraphLayoutDisposed(GraphLayoutError):
    """Raised when work is requested from a disposed controller."""


@dataclass(frozen=True)
class GraphLayoutCheckpoint:
    """One immutable Rust-produced progressive layout checkpoint."""

    x: npt.NDArray[np.float64]
    y: npt.NDArray[np.float64]
    alpha: float
    step: int
    phase: str
    revision: int
    job_id: str | int | None


ProgressCallback = Callable[[GraphLayoutCheckpoint], None]


class GraphLayoutController:
    """Schedule one graph's progressive Rust layout on a dedicated thread.

    Controllers are intentionally per live graph.  A newer revision cancels the
    prior job, while callbacks are delivered on the caller's asyncio loop only
    after the revision is checked again.  ``reheat`` is the same Rust CoSE
    kernel restarted from authored drag positions and a new pin mask.
    """

    def __init__(self, data: GraphData) -> None:
        self._data = data
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="xyg-layout")
        self._lock = Lock()
        self._cancel: Event | None = None
        self._revision = 0
        self._disposed = False

    async def layout(
        self,
        *,
        revision: int,
        layout: str = "cose",
        seed: int = 0,
        total_steps: int = 300,
        chunk_steps: int = 8,
        max_wall_ms: float = 30_000,
        cose: Mapping[str, Any] | None = None,
        x: npt.ArrayLike | None = None,
        y: npt.ArrayLike | None = None,
        pinned: npt.ArrayLike | None = None,
        job_id: str | int | None = None,
        on_update: ProgressCallback | None = None,
    ) -> GraphLayoutCheckpoint:
        """Run initial/update/complete phases without blocking the event loop."""
        revision = _positive_u32(revision, "revision")
        total_steps = _bounded_int(total_steps, "total_steps", 1, 1_000_000)
        chunk_steps = _bounded_int(chunk_steps, "chunk_steps", 1, 1_000)
        if not np.isfinite(max_wall_ms) or not 0 < max_wall_ms <= 300_000:
            raise ValueError("max_wall_ms must be in (0, 300000]")
        if on_update is not None and not callable(on_update):
            raise TypeError("on_update must be callable")
        if job_id is not None and not isinstance(job_id, (str, int)):
            raise TypeError("job_id must be a string or integer")

        loop = asyncio.get_running_loop()
        cancel = Event()

        def publish(checkpoint: GraphLayoutCheckpoint) -> None:
            if on_update is None:
                return

            async def deliver() -> None:
                with self._lock:
                    current = (
                        not self._disposed and self._revision == revision and not cancel.is_set()
                    )
                if current:
                    on_update(checkpoint)

            asyncio.run_coroutine_threadsafe(deliver(), loop).result()

        with self._lock:
            if self._disposed:
                raise GraphLayoutDisposed("graph layout controller is disposed")
            if revision <= self._revision:
                raise ValueError("revision must be newer than the active revision")
            if self._cancel is not None:
                self._cancel.set()
            self._cancel = cancel
            self._revision = revision
            # Submission is part of the active-state transition. Holding the
            # lifecycle lock prevents dispose() from shutting down the executor
            # between publishing the revision and enqueuing its native job.
            future = loop.run_in_executor(
                self._executor,
                self._run,
                revision,
                layout,
                seed,
                total_steps,
                chunk_steps,
                float(max_wall_ms),
                cose,
                x,
                y,
                pinned,
                job_id,
                cancel,
                publish,
            )

        try:
            result = await future
        except asyncio.CancelledError:
            cancel.set()
            with self._lock:
                if self._disposed:
                    raise GraphLayoutDisposed("graph layout controller was disposed") from None
            raise
        except GraphLayoutSuperseded:
            with self._lock:
                if self._disposed:
                    raise GraphLayoutDisposed("graph layout controller was disposed") from None
            raise
        except Exception as exc:
            raise GraphLayoutError(f"progressive graph layout failed: {exc}") from exc
        with self._lock:
            if self._disposed:
                raise GraphLayoutDisposed("graph layout controller was disposed")
            if self._revision != revision or cancel.is_set():
                raise GraphLayoutSuperseded("graph layout was superseded")
            if self._cancel is cancel:
                self._cancel = None
        return result

    async def reheat(
        self,
        *,
        revision: int,
        x: npt.ArrayLike,
        y: npt.ArrayLike,
        pinned: npt.ArrayLike,
        **options: Any,
    ) -> GraphLayoutCheckpoint:
        """Restart Rust CoSE from drag coordinates and the current pin mask."""
        return await self.layout(
            revision=revision, layout="cose", x=x, y=y, pinned=pinned, **options
        )

    def cancel(self) -> None:
        """Cooperatively cancel the active job at its next bounded tick chunk."""
        with self._lock:
            if self._cancel is not None:
                self._cancel.set()

    def dispose(self) -> None:
        """Reject future work and release this graph's dedicated worker thread."""
        with self._lock:
            if self._disposed:
                return
            self._disposed = True
            if self._cancel is not None:
                self._cancel.set()
        self._executor.shutdown(wait=False, cancel_futures=True)

    def _run(
        self,
        revision: int,
        layout: str,
        seed: int,
        total_steps: int,
        chunk_steps: int,
        max_wall_ms: float,
        cose: Mapping[str, Any] | None,
        x: npt.ArrayLike | None,
        y: npt.ArrayLike | None,
        pinned: npt.ArrayLike | None,
        job_id: str | int | None,
        cancel: Event,
        publish: ProgressCallback,
    ) -> GraphLayoutCheckpoint:
        data = self._data
        initial_x = data.x if x is None else np.ascontiguousarray(x, dtype=np.float64)
        initial_y = data.y if y is None else np.ascontiguousarray(y, dtype=np.float64)
        parents = _parents(data)
        handle = _native.graph_force_create(
            data.n_nodes,
            data.sources,
            data.targets,
            x=initial_x,
            y=initial_y,
            seed=seed,
            algorithm=layout,
            cose=cose,
            pinned=pinned,
            parents=parents,
        )
        started = monotonic()
        step = 0
        last: GraphLayoutCheckpoint | None = None
        try:
            while step < total_steps:
                if cancel.is_set():
                    raise GraphLayoutSuperseded("graph layout was superseded")
                if (monotonic() - started) * 1000 > max_wall_ms:
                    raise TimeoutError("graph layout exceeded max_wall_ms")
                take = 1 if step == 0 else min(chunk_steps, total_steps - step)
                out_x, out_y, alpha = _native.graph_force_tick(handle, data.n_nodes, take)
                out_x.setflags(write=False)
                out_y.setflags(write=False)
                step += take
                phase = (
                    "complete"
                    if step >= total_steps or alpha < 0.001
                    else ("initial" if step == 1 else "update")
                )
                last = GraphLayoutCheckpoint(out_x, out_y, alpha, step, phase, revision, job_id)
                publish(last)
                if phase == "complete":
                    return last
        finally:
            _native.graph_force_destroy(handle)
        assert last is not None
        return last


def _positive_u32(value: int, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, Integral):
        raise TypeError(f"{name} must be an integer")
    value = int(value)
    if value <= 0 or value > 0xFFFFFFFF:
        raise ValueError(f"{name} must be a nonzero u32")
    return value


def _bounded_int(value: int, name: str, minimum: int, maximum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, Integral):
        raise TypeError(f"{name} must be an integer")
    value = int(value)
    if value < minimum or value > maximum:
        raise ValueError(f"{name} must be in [{minimum}, {maximum}]")
    return value


def _parents(data: GraphData) -> npt.NDArray[np.uint64] | None:
    if data.parent_indices is None:
        return None
    parents = np.full(data.n_nodes, np.iinfo(np.uint64).max, dtype=np.uint64)
    validity = (
        np.ones(data.n_nodes, dtype=bool)
        if data.parent_validity is None
        else np.asarray(data.parent_validity, dtype=bool)
    )
    if len(data.parent_indices) != data.n_nodes or len(validity) != data.n_nodes:
        raise ValueError("CoSE compound parent metadata must have length n_nodes")
    parents[validity] = np.asarray(data.parent_indices, dtype=np.uint64)[validity]
    return parents
