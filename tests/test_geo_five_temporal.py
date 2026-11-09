"""Public widgets retain five issued lanes without duplicating canonical storage."""

import asyncio
from dataclasses import replace

import numpy as np
import pytest

import xyg
from geo_mounted_hierarchy_temporal_fixture import mounted_hierarchy_chart_fixture
from test_geo_retained import style
from test_geoscale import U64


def test_five_widgets_share_original_and_preserve_canonical_exclusion():
    async def run():
        source, scope, lane, frame, chart = mounted_hierarchy_chart_fixture()
        lanes, frames, widgets, bindings = [lane], [frame], [], []
        controller = xyg.TemporalController(instance_id=991, domain=(-100, 100))
        try:
            for i in range(5):
                current = chart
                if i:
                    fork = lane.fork()
                    lanes.append(fork)
                    state = scope.state(
                        revision=1, ids=np.array([U64], dtype="<u8"), fill=b"\0\xff\0\xff"
                    )
                    try:
                        op = fork.begin_selected(
                            state, chart.layers[0].properties["query"], sequence=4
                        )
                        op.drive()
                        frames.append(op.prepare(style()))
                    finally:
                        state.close()
                    current = replace(
                        chart,
                        layers=(
                            replace(
                                chart.layers[0],
                                properties={**chart.layers[0].properties, "sequence": 4},
                            ),
                        ),
                    )
                widget = current.widget(
                    frame=frames[i], selected_scope=scope, hierarchy_lane=lanes[i]
                )
                frames[i].close()
                widgets.append(widget)
                bindings.append(widget.bind_temporal(controller))
                assert widget._adapter._source is source
                with pytest.raises(RuntimeError, match="already"):
                    widget.bind_temporal(controller)
            source.close()
            assert len({lane.handle for lane in lanes}) == 5
            with pytest.raises(RuntimeError, match="already"):
                chart.bind_temporal(controller)
            # Caller originals are independently retained; explicit disposal is safe.
            for frame in frames:
                frame.close()
            for n in range(90):
                await asyncio.to_thread(controller.set_cursor, n)
            await asyncio.sleep(0)
            assert all(binding._active is None for binding in bindings)  # premount
            for binding in bindings:
                await binding.aclose()
            rebound = widgets[0].bind_temporal(controller)
            await rebound.aclose()
        finally:
            for binding in bindings:
                await binding.aclose()
            for widget in widgets:
                widget.close()
                if widget._geo_rpc_task is not None:
                    await widget._geo_rpc_task
            controller.close()
            for frame in frames:
                frame.close()
            source.close()
            for lane in lanes:
                lane.close()
            scope.close()

    asyncio.run(run())


def test_admission_closed_queued_loop_cannot_starve_ready_loop():
    """Scheduler unit proof only; actual native/browser proof is separate."""
    from types import SimpleNamespace

    from xyg._geo_live_host import _AutomaticAdmission

    admission = _AutomaticAdmission()
    abandoned = asyncio.new_event_loop()
    owner = SimpleNamespace()
    admission.owner = owner

    class Waiting:
        def __init__(self, loop):
            self._loop = loop
            self.wakes = 0

        def _schedule(self):
            self.wakes += 1

    async def run():
        ready = Waiting(asyncio.get_running_loop())
        old = Waiting(abandoned)
        assert not admission.request(old)
        admission.owner = None
        with admission.lock:
            admission._wake()
        abandoned.close()  # its queued callback will never execute
        assert not admission.request(ready)
        await asyncio.sleep(0)
        assert ready.wakes == 1
        assert old not in admission.queue
        assert admission.request(ready)
        assert admission.owner is ready
        admission.owner = None

    try:
        asyncio.run(run())
    finally:
        abandoned.close()


def test_failed_foreign_loop_binding_rolls_back_only_its_issued_lane():
    from geo_five_temporal_fixture import five_hierarchy_widgets

    async def run():
        source, scope, lanes, widgets, chart = five_hierarchy_widgets()
        controller = xyg.TemporalController(instance_id=992, domain=(-100, 100))
        bindings = [widget.bind_temporal(controller) for widget in widgets]
        try:
            await bindings[0].aclose()

            def foreign():
                async def attempt():
                    with pytest.raises(RuntimeError, match="another event loop"):
                        widgets[0].bind_temporal(controller)

                asyncio.run(attempt())

            await asyncio.to_thread(foreign)
            for widget in widgets[1:]:
                with pytest.raises(RuntimeError, match="already"):
                    widget.bind_temporal(controller)
            bindings[0] = widgets[0].bind_temporal(controller)
            with pytest.raises(RuntimeError, match="already"):
                chart.bind_temporal(controller)
        finally:
            for binding in bindings:
                await binding.aclose()
            for widget in widgets:
                widget.close()
                if widget._geo_rpc_task:
                    await widget._geo_rpc_task
            controller.close()
            source.close()
            for lane in lanes:
                lane.close()
            scope.close()

    asyncio.run(run())
