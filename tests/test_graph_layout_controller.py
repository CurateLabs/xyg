from __future__ import annotations

import asyncio

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
