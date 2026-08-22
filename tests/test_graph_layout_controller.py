from __future__ import annotations

import asyncio
import threading
from concurrent.futures import ThreadPoolExecutor

import numpy as np
import pytest

from xyg import (
    GraphLayoutController,
    GraphLayoutDisposed,
    GraphLayoutError,
    GraphLayoutSuperseded,
)
from xyg._graph import GraphData


def _data(n: int = 3) -> GraphData:
    return GraphData(
        ids=np.arange(n, dtype=np.uint64),
        sources=np.arange(n - 1, dtype=np.uint64),
        targets=np.arange(1, n, dtype=np.uint64),
        x=np.linspace(-0.5, 0.5, n),
        y=np.zeros(n),
    )


def test_progressive_layout_runs_off_event_loop_and_emits_phases() -> None:
    async def scenario() -> None:
        controller = GraphLayoutController(_data())
        phases: list[tuple[str, int, int]] = []
        heartbeat = False

        async def pulse() -> None:
            nonlocal heartbeat
            await asyncio.sleep(0)
            heartbeat = True

        pulse_task = asyncio.create_task(pulse())
        result = await controller.layout(
            revision=7,
            total_steps=10,
            chunk_steps=4,
            on_update=lambda update: phases.append((update.phase, update.step, update.revision)),
        )
        await pulse_task
        await asyncio.sleep(0)
        assert heartbeat
        assert result.phase == "complete"
        assert result.revision == 7
        assert phases[0] == ("initial", 1, 7)
        assert phases[-1] == ("complete", 10, 7)
        controller.dispose()

    asyncio.run(scenario())


def test_supersession_drops_stale_updates_and_instances_are_isolated() -> None:
    async def scenario() -> None:
        first = GraphLayoutController(_data(600))
        peer = GraphLayoutController(_data())
        old_updates = []
        old = asyncio.create_task(
            first.layout(
                revision=1, total_steps=100_000, chunk_steps=1, on_update=old_updates.append
            )
        )
        await asyncio.sleep(0)
        current, peer_result = await asyncio.gather(
            first.layout(revision=2, total_steps=2),
            peer.layout(revision=1, total_steps=2),
        )
        with pytest.raises(GraphLayoutSuperseded):
            await old
        count = len(old_updates)
        await asyncio.sleep(0)
        assert len(old_updates) == count
        assert current.revision == 2
        assert peer_result.revision == 1
        first.dispose()
        peer.dispose()

    asyncio.run(scenario())


def test_drag_reheat_preserves_new_pin_and_dispose_fails_closed() -> None:
    async def scenario() -> None:
        controller = GraphLayoutController(_data())
        result = await controller.reheat(
            revision=1,
            x=np.array([-0.5, 0.25, 0.5]),
            y=np.array([0.0, -0.25, 0.0]),
            pinned=np.array([0, 1, 0], dtype=np.uint8),
            total_steps=12,
            cose={"bounds": (-1.0, -1.0, 1.0, 1.0)},
        )
        assert result.x[1] == 0.25
        assert result.y[1] == -0.25
        controller.dispose()
        with pytest.raises(GraphLayoutDisposed):
            await controller.layout(revision=2)

    asyncio.run(scenario())


def test_callback_failure_is_stable_and_worker_remains_usable() -> None:
    async def scenario() -> None:
        controller = GraphLayoutController(_data())
        with pytest.raises(GraphLayoutError, match="consumer failed"):
            await controller.layout(
                revision=1,
                total_steps=2,
                on_update=lambda _update: (_ for _ in ()).throw(RuntimeError("consumer failed")),
            )
        result = await controller.layout(revision=2, total_steps=2)
        assert result.revision == 2
        controller.dispose()

    asyncio.run(scenario())


@pytest.mark.parametrize("value", [True, "1", 1.9])
def test_revision_identity_rejects_coercion(value: object) -> None:
    async def scenario() -> None:
        controller = GraphLayoutController(_data())
        with pytest.raises(TypeError, match="revision must be an integer"):
            await controller.layout(revision=value)  # type: ignore[arg-type]
        controller.dispose()

    asyncio.run(scenario())


@pytest.mark.parametrize(
    ("field", "value"), [("total_steps", False), ("total_steps", "2"), ("chunk_steps", 1.5)]
)
def test_step_counts_reject_coercion(field: str, value: object) -> None:
    async def scenario() -> None:
        controller = GraphLayoutController(_data())
        with pytest.raises(TypeError, match=f"{field} must be an integer"):
            await controller.layout(revision=1, **{field: value})
        controller.dispose()

    asyncio.run(scenario())


def test_checkpoints_expose_read_only_rust_coordinates() -> None:
    async def scenario() -> None:
        controller = GraphLayoutController(_data())
        updates = []
        result = await controller.layout(revision=1, total_steps=2, on_update=updates.append)
        for checkpoint in [*updates, result]:
            assert not checkpoint.x.flags.writeable
            assert not checkpoint.y.flags.writeable
            with pytest.raises(ValueError, match="read-only"):
                checkpoint.x[0] = 42.0
        controller.dispose()

    asyncio.run(scenario())


def test_dispose_cannot_split_active_state_from_executor_submission() -> None:
    class PausingExecutor(ThreadPoolExecutor):
        def __init__(self) -> None:
            super().__init__(max_workers=1, thread_name_prefix="xyg-layout-test")
            self.entered = threading.Event()
            self.release = threading.Event()

        def submit(self, fn, /, *args, **kwargs):
            self.entered.set()
            assert self.release.wait(timeout=5)
            return super().submit(fn, *args, **kwargs)

    async def scenario() -> None:
        controller = GraphLayoutController(_data(600))
        original = controller._executor
        executor = PausingExecutor()
        controller._executor = executor
        original.shutdown(wait=True)
        callbacks = []
        disposal_threads = []

        def coordinate_dispose() -> None:
            assert executor.entered.wait(timeout=5)
            dispose_thread = threading.Thread(target=controller.dispose)
            disposal_threads.append(dispose_thread)
            dispose_thread.start()
            executor.release.set()

        coordinator = threading.Thread(target=coordinate_dispose)
        coordinator.start()
        task = asyncio.create_task(
            controller.layout(
                revision=1, total_steps=100_000, chunk_steps=1, on_update=callbacks.append
            )
        )
        await asyncio.to_thread(coordinator.join, 5)
        await asyncio.to_thread(disposal_threads[0].join, 5)
        with pytest.raises(GraphLayoutDisposed):
            await task
        delivered = len(callbacks)
        await asyncio.sleep(0)
        assert len(callbacks) == delivered

    asyncio.run(scenario())


def test_active_dispose_is_terminal_and_suppresses_late_callbacks() -> None:
    async def scenario() -> None:
        controller = GraphLayoutController(_data(600))
        callbacks = []
        task = asyncio.create_task(
            controller.layout(
                revision=1, total_steps=100_000, chunk_steps=1, on_update=callbacks.append
            )
        )
        while not callbacks:
            await asyncio.sleep(0)
        controller.dispose()
        with pytest.raises(GraphLayoutDisposed):
            await task
        delivered = len(callbacks)
        await asyncio.sleep(0)
        assert len(callbacks) == delivered

    asyncio.run(scenario())
