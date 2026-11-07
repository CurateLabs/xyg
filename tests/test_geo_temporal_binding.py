"""Public native temporal binding against real retained sessions and frame leases."""

import asyncio

import pytest

import xyg
from test_geo_retained import fixture_manifest, style
from test_geoscale import BUDGET, I64, U64, query


@pytest.mark.parametrize("asynchronous", [False, True])
@pytest.mark.parametrize("mode", ["cursor", "range"])
def test_public_binding_exact_snapshots_races_failure_and_independent_leases(asynchronous, mode):
    async def journey():
        manifest, chunk = fixture_manifest()
        reads = 0
        fail = False
        entered, release = asyncio.Event(), asyncio.Event()
        block = False

        def read(_):
            nonlocal reads
            reads += 1
            if fail:
                raise OSError("storage unavailable")
            return chunk

        async def aread(ticket):
            if block:
                entered.set()
                await release.wait()
            return read(ticket)

        source = (
            await xyg.RetainedGeoSource.create_async(manifest, aread, budget=BUDGET)
            if asynchronous
            else xyg.RetainedGeoSource(manifest, read, budget=BUDGET)
        )
        controller = xyg.TemporalController(instance_id=U64, domain=(I64, (1 << 63) - 1))
        q = query(source.info)
        q.update(time_revision=0, camera_revision=0)
        chart = xyg.geo_chart(
            xyg.geo_layer(
                "points", source=source, layer_id=U64, query=q, sequence=1, style=style()
            ),
            camera=q["camera"],
        )
        binding = chart.bind_temporal(controller, mode)
        leases = []
        try:
            await binding.when_idle()
            assert binding.error is None
            accepted, frame = await binding.snapshot()
            leases.append(frame)
            assert frame.data.record(0)["feature_id"] == U64
            assert source.current is None  # private publication never changes batch ownership
            baseline = reads
            controller.set_selection([U64, 1 << 63])
            await binding.when_idle()
            assert reads == baseline
            if asynchronous:
                block = True
                controller.set_cursor(0)
                await entered.wait()
                controller.set_cursor(1)
                binding.set_camera({**q["camera"], "zoom": 1.0})
                controller.set_cursor(2)
                release.set()
            else:
                controller.set_cursor(0).set_cursor(1).set_cursor(2)
                binding.set_camera({**q["camera"], "zoom": 1.0})
            await binding.when_idle()
            assert binding.error is None
            new_chart, newer = await binding.snapshot()
            leases.append(newer)
            expected = (
                dict(kind=1, instant=2)
                if mode == "cursor"
                else dict(
                    kind=2, start=controller.state["range_start"], end=controller.state["range_end"]
                )
            )
            assert newer.data.identity["time"] == expected
            assert newer.data.identity["camera"]["zoom"] == 1.0
            assert frame.data.identity["time"] != expected
            if mode == "range":
                controller.set_range(-10, 10)
                await binding.when_idle()
                _, range_frame = await binding.snapshot()
                leases.append(range_frame)
                assert range_frame.data.identity["time"] == dict(kind=2, start=-10, end=10)
                newer = range_frame
            fail = True
            controller.set_cursor(3)
            await binding.when_idle()
            assert isinstance(binding.error, OSError)
            _, retained = await binding.snapshot()
            leases.append(retained)
            assert retained.data.identity == newer.data.identity
            fail = False
            controller.set_cursor((1 << 63) - 2)
            await binding.when_idle()
            assert binding.error is None
            final_chart, final = await binding.snapshot()
            leases.append(final)
            # Existing public export path consumes the exact accepted composition.
            if asynchronous:
                artifact = await final.export_async("svg")
                await artifact.aclose()
            else:
                artifact = final_chart.to_image("svg", frame=final)
                assert b"<svg" in artifact.bytes
                artifact.close()
                adapter = final_chart.host(frame=final)
                adapter.close()
            controller.close()
            await binding.aclose()
            assert final.data.record(0)["feature_id"] == U64
            assert frame.data.record(0)["feature_id"] == U64
        finally:
            release.set()
            await binding.aclose()
            for lease in leases:
                await lease.aclose()
            await source.aclose()
            controller.close()

    asyncio.run(journey())


def test_observer_failure_reentrancy_async_rejection_and_unsubscribe():
    async def run():
        with xyg.TemporalController(instance_id=42, domain=(-100, 100)) as controller:
            seen = []

            async def rejected(state):
                raise RuntimeError("observer rejection")

            def reenter(state):
                seen.append(state["cursor"])
                state["selection"].append(U64)
                if state["cursor"] == 1:
                    controller.set_cursor(2)

            stop = controller.subscribe_state(reenter)
            controller.subscribe_state(rejected)
            controller.subscribe_state(lambda _: 1 / 0)
            controller.set_cursor(1)
            await asyncio.sleep(0)
            assert seen == [1, 2]
            assert controller.state["selection"] == []
            stop()
            controller.set_cursor(3)
            assert seen == [1, 2]

    asyncio.run(run())


@pytest.mark.parametrize("large", [False, True])
def test_public_native_membership_and_bounded_fixture_costs(large):
    import json
    import resource
    import struct
    import time

    from test_geo_retained import aggregate_fixture

    async def run():
        start = time.perf_counter()
        manifest, chunk = aggregate_fixture() if large else fixture_manifest()
        source = xyg.RetainedGeoSource(manifest, lambda _: chunk, budget={**BUDGET, "page_rows": 1})
        q = query(source.info)
        q.update(time_revision=0, camera_revision=0, max_cells=1, previous_direct=False)
        chart = xyg.geo_chart(
            xyg.geo_layer(
                "points", source=source, layer_id=U64, query=q, sequence=1, style=style()
            ),
            camera=q["camera"],
        )
        controller = xyg.TemporalController(instance_id=7, domain=(-10, 10))
        binding = chart.bind_temporal(controller)
        frame = page = None
        try:
            await binding.when_idle()
            assert binding.error is None
            _, frame = await binding.snapshot()
            assert frame.data.aggregate is large
            if large:
                page = frame.membership(0, max_projected_vertices=1000000)
                assert struct.unpack_from("<Q", page.data["records"])[0] == U64
                assert len(page.data["cursor"]) == 208
            else:
                assert frame.data.record(0)["feature_id"] == U64
            print(
                json.dumps(
                    dict(
                        rows=32769 if large else 2,
                        elapsed_seconds=time.perf_counter() - start,
                        process_peak_rss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
                        chunk_bytes=len(chunk),
                        packet_bytes=len(frame.data.packet),
                    )
                )
            )
        finally:
            if page:
                page.close()
            if frame:
                frame.close()
            await binding.aclose()
            controller.close()
            source.close()

    asyncio.run(run())


def test_concurrent_sources_and_controller_dispose_during_pending_read():
    async def run():
        manifest, chunk = fixture_manifest()
        blocked, release = asyncio.Event(), asyncio.Event()
        block = False

        async def reader(_):
            if block:
                blocked.set()
                await release.wait()
            return chunk

        sources = [
            await xyg.RetainedGeoSource.create_async(manifest, reader, budget=BUDGET)
            for _ in range(2)
        ]
        controllers = [
            xyg.TemporalController(instance_id=i + 1, domain=(-10, 10)) for i in range(2)
        ]
        bindings = []
        frames = []
        try:
            for source, controller in zip(sources, controllers, strict=True):
                q = query(source.info)
                q.update(time_revision=0, camera_revision=0)
                chart = xyg.geo_chart(
                    xyg.geo_layer(
                        "points", source=source, layer_id=U64, query=q, sequence=1, style=style()
                    ),
                    camera=q["camera"],
                )
                bindings.append(chart.bind_temporal(controller))
            await asyncio.gather(*(b.when_idle() for b in bindings))
            for binding in bindings:
                _, frame = await binding.snapshot()
                frames.append(frame)
            block = True
            controllers[0].set_cursor(1)
            await blocked.wait()
            controllers[0].dispose()
            closing = asyncio.create_task(bindings[0].aclose())
            await asyncio.sleep(0)
            assert not closing.done()
            release.set()
            await closing
            assert frames[0].data.record(0)["feature_id"] == U64
            controllers[1].set_cursor(2)
            await bindings[1].when_idle()
            _, latest = await bindings[1].snapshot()
            frames.append(latest)
            assert latest.data.identity["time"]["instant"] == 2
        finally:
            release.set()
            for binding in bindings:
                await binding.aclose()
            for frame in frames:
                await frame.aclose()
            for source in sources:
                await source.aclose()
            for controller in controllers:
                controller.close()

    asyncio.run(run())


@pytest.mark.parametrize("action", ["close", "cancel"])
def test_source_cancellation_preserves_snapshot_and_releases_binding(action):
    from xyg._geo_temporal import _BINDINGS

    async def run():
        manifest, chunk = fixture_manifest()
        entered, release = asyncio.Event(), asyncio.Event()
        block = False

        async def reader(_):
            if block:
                entered.set()
                await release.wait()
            return chunk

        source = await xyg.RetainedGeoSource.create_async(manifest, reader, budget=BUDGET)
        controller = xyg.TemporalController(instance_id=11, domain=(-10, 10))
        q = query(source.info)
        q.update(time_revision=0, camera_revision=0)
        chart = xyg.geo_chart(
            xyg.geo_layer(
                "points", source=source, layer_id=U64, query=q, sequence=1, style=style()
            ),
            camera=q["camera"],
        )
        binding = chart.bind_temporal(controller)
        leases = []
        try:
            await binding.when_idle()
            _, first = await binding.snapshot()
            leases.append(first)
            block = True
            controller.set_cursor(1)
            await asyncio.wait_for(entered.wait(), 5)
            waiter = asyncio.create_task(binding.when_idle())
            await asyncio.sleep(0)
            waiter.cancel()
            with pytest.raises(asyncio.CancelledError):
                await waiter
            assert not binding._task.done()
            closing = asyncio.create_task(
                source.aclose() if action == "close" else source.acancel()
            )

            # Readers may drain after cancellation; acknowledge their exact read
            # before expecting source disposal or binding settlement to finish.
            async def cancelled():
                while not binding._task.cancelling():
                    await asyncio.sleep(0)

            await asyncio.wait_for(cancelled(), 5)
            release.set()
            await closing
            await binding.when_idle()
            assert binding._task.cancelling() == 0
            assert isinstance(binding.error, RuntimeError)
            _, retained = await binding.snapshot()
            leases.append(retained)
            assert retained.data.identity == first.data.identity
            if action == "cancel":
                block = False
                controller.set_cursor(2)
                await binding.when_idle()
                assert binding.error is None
                _, latest = await binding.snapshot()
                leases.append(latest)
                assert latest.data.identity["time"]["instant"] == 2
            await binding.aclose()
            await binding.aclose()
            assert source not in _BINDINGS
            assert binding._frame is None
            assert first.data.record(0)["feature_id"] == U64
        finally:
            release.set()
            await binding.aclose()
            for lease in leases:
                await lease.aclose()
            await source.aclose()
            controller.close()

    asyncio.run(run())


def test_foreign_thread_controller_updates_and_disposal_use_owner_loop():
    async def run():
        manifest, chunk = fixture_manifest()
        source = xyg.RetainedGeoSource(manifest, lambda _: chunk, budget=BUDGET)
        controller = xyg.TemporalController(instance_id=12, domain=(-10, 10))
        q = query(source.info)
        q.update(time_revision=0, camera_revision=0)
        chart = xyg.geo_chart(
            xyg.geo_layer(
                "points", source=source, layer_id=U64, query=q, sequence=1, style=style()
            ),
            camera=q["camera"],
        )
        binding = chart.bind_temporal(controller)
        lease = None
        try:
            await binding.when_idle()
            await asyncio.to_thread(controller.set_cursor, 3)
            await binding.when_idle()
            assert binding.error is None
            _, lease = await binding.snapshot()
            assert lease.data.identity["time"]["instant"] == 3
            await asyncio.to_thread(controller.dispose)
            await binding.aclose()
            assert binding._frame is None
            assert lease.data.record(0)["feature_id"] == U64
        finally:
            await binding.aclose()
            if lease is not None:
                await lease.aclose()
            await source.aclose()
            controller.close()

    asyncio.run(run())


@pytest.mark.parametrize("asynchronous", [False, True])
@pytest.mark.parametrize("indexed", ["spatial", "hierarchy"])
def test_indexed_composition_private_frames_preserve_default_publication(indexed, asynchronous):
    from test_geo_hierarchy import storage
    from test_geo_spatial import setup
    from xyg._geo_hierarchy import GeoHierarchy

    async def run():
        source, initial, _ = setup()
        pages = {}
        index = private = published = None
        try:
            if indexed == "hierarchy":
                if asynchronous:
                    index = await GeoHierarchy.from_frame_async(initial, source, **storage(pages))
                else:
                    index = GeoHierarchy.from_frame(initial, source, **storage(pages))
            else:
                options = dict(
                    grid=16,
                    max_vertices=1000000,
                    read_page=lambda ticket: pages[ticket["page"]],
                    write_page=lambda ticket, data: pages.__setitem__(ticket["page"], bytes(data)),
                )
                if asynchronous:
                    index = await initial.spatial_index_async(**options)
                else:
                    index = initial.spatial_index(**options)
            q = query(index.info)

            def chart(sequence):
                return xyg.geo_chart(
                    xyg.geo_layer(
                        "points",
                        source=index,
                        layer_id=U64,
                        query=q,
                        sequence=sequence,
                        style=style(),
                    ),
                    camera=q["camera"],
                )

            before = index.current
            private = (
                await chart(2).compile_async(_publish=False)
                if asynchronous
                else chart(2).compile(_publish=False)
            )
            assert index.current is before
            assert private.data.record(0)["feature_id"] == U64
            published = await chart(3).compile_async() if asynchronous else chart(3).compile()
            assert index.current is published
            assert published.data.record(0)["feature_id"] == U64
            assert private.data.scene == published.data.scene
        finally:
            if published is not None:
                await published.aclose()
            if private is not None:
                await private.aclose()
            if index is not None:
                await index.aclose()
            initial.close()
            source.close()

    asyncio.run(run())


@pytest.mark.parametrize("asynchronous", [False, True])
def test_reader_cancelled_error_keeps_snapshot_and_allows_cleanup(asynchronous):
    from contextlib import suppress

    from xyg._geo_temporal import _BINDINGS

    async def run():
        manifest, chunk = fixture_manifest()
        cancel = False

        def read(_):
            if cancel:
                raise asyncio.CancelledError
            return chunk

        async def reader(request):
            return read(request)

        source = (
            await xyg.RetainedGeoSource.create_async(manifest, reader, budget=BUDGET)
            if asynchronous
            else xyg.RetainedGeoSource(manifest, read, budget=BUDGET)
        )
        controller = xyg.TemporalController(instance_id=31, domain=(-10, 10))
        q = query(source.info)
        q.update(time_revision=0, camera_revision=0)
        chart = xyg.geo_chart(
            xyg.geo_layer(
                "points", source=source, layer_id=U64, query=q, sequence=1, style=style()
            ),
            camera=q["camera"],
        )
        binding = chart.bind_temporal(controller)
        leases = []
        try:
            await binding.when_idle()
            _, first = await binding.snapshot()
            leases.append(first)
            cancel = True
            controller.set_cursor(3)
            await binding.when_idle()
            assert isinstance(binding.error, RuntimeError)
            _, retained = await binding.snapshot()
            leases.append(retained)
            assert retained.data.identity == first.data.identity
            cancel = False
            controller.set_cursor(4)
            _, recovery = await binding.snapshot()
            leases.append(recovery)
            assert binding.error is None
            assert recovery.data.identity["time"]["instant"] == 4
            await binding.aclose()
            await binding.aclose()
            assert binding._frame is None
            assert source not in _BINDINGS
        finally:
            # Preserve the test's failure while releasing fixtures on old code.
            with suppress(asyncio.CancelledError):
                await binding.aclose()
            if binding._frame is not None:
                await binding._frame.aclose()
            for frame in leases:
                await frame.aclose()
            await source.aclose()
            controller.close()

    asyncio.run(run())


def test_snapshots_and_authored_styles_are_independent_compositions():
    async def run():
        manifest, chunk = fixture_manifest()
        source = xyg.RetainedGeoSource(manifest, lambda _: chunk, budget=BUDGET)
        controller = xyg.TemporalController(instance_id=32, domain=(-10, 10))
        q = query(source.info)
        q.update(time_revision=0, camera_revision=0)
        authored = dict(
            fill=b"\xff\0\0\xff",
            stroke=b"\0" * 4,
            stroke_width=0.0,
            diameter=6.0,
            opacity=1.0,
            symbol=0,
        )
        chart = xyg.geo_chart(
            xyg.geo_layer(
                "points", source=source, layer_id=U64, query=q, sequence=1, style=authored
            ),
            camera=q["camera"],
        )
        binding = chart.bind_temporal(controller)
        frames = []
        try:
            authored["diameter"] = 100.0
            first_chart, first = await binding.snapshot()
            frames.append(first)
            assert first_chart.layers[0].properties["style"]["diameter"] == 6.0
            first_chart.layers[0].properties["query"]["time"]["instant"] = 5
            first_chart.layers[0].properties["style"]["opacity"] = 0.0
            first_chart.camera["zoom"] = 99.0
            second_chart, second = await binding.snapshot()
            frames.append(second)
            assert second_chart is not first_chart
            assert second_chart.layers[0].source is source
            assert (
                second_chart.layers[0].properties["query"]["time"] == second.data.identity["time"]
            )
            assert second_chart.layers[0].properties["style"]["opacity"] == 1.0
            artifact = second_chart.to_image("svg", frame=second)
            artifact.close()
            controller.set_cursor(2)
            next_chart, next_frame = await binding.snapshot()
            frames.append(next_frame)
            assert next_chart.layers[0].properties["style"]["diameter"] == 6.0
            assert next_frame.data.identity["time"]["instant"] == 2
        finally:
            await binding.aclose()
            for frame in frames:
                await frame.aclose()
            await source.aclose()
            controller.close()

    asyncio.run(run())


@pytest.mark.parametrize("cancelled_caller", [False, True])
def test_terminal_cancelled_pump_cannot_block_private_frame_cleanup(cancelled_caller):
    from xyg._geo_temporal import _BINDINGS

    async def run():
        manifest, chunk = fixture_manifest()
        entered, release = asyncio.Event(), asyncio.Event()
        block = False

        async def reader(_):
            if block:
                entered.set()
                await release.wait()
            return chunk

        source = await xyg.RetainedGeoSource.create_async(manifest, reader, budget=BUDGET)
        controller = xyg.TemporalController(instance_id=33, domain=(-10, 10))
        q = query(source.info)
        q.update(time_revision=0, camera_revision=0)
        chart = xyg.geo_chart(
            xyg.geo_layer(
                "points", source=source, layer_id=U64, query=q, sequence=1, style=style()
            ),
            camera=q["camera"],
        )
        binding = chart.bind_temporal(controller)
        frame = None
        try:
            _, frame = await binding.snapshot()
            block = True
            controller.set_cursor(3)
            await asyncio.wait_for(entered.wait(), 5)
            # Simulate terminal cancellation of the binding's own job, distinct
            # from cancelling a shielded caller (covered by the source tests).
            task = binding._task
            task.cancel()
            release.set()
            await binding.when_idle()
            assert task.cancelled()
            assert isinstance(binding.error, RuntimeError)
            if cancelled_caller:
                asyncio.current_task().cancel()
                with pytest.raises(asyncio.CancelledError):
                    await asyncio.sleep(0)
            await binding.aclose()
            assert binding._frame is None
            assert source not in _BINDINGS
            assert frame.data.record(0)["feature_id"] == U64
        finally:
            release.set()
            await binding.aclose()
            if frame is not None:
                await frame.aclose()
            await source.aclose()
            controller.close()

    asyncio.run(run())


@pytest.mark.parametrize("nested_terminal_close", [False, True])
@pytest.mark.parametrize("trigger", ["cursor", "dispose"])
def test_reentrant_controller_close_delivers_terminal_and_releases_binding(
    nested_terminal_close, trigger
):
    async def journey():
        from xyg._geo_temporal import _BINDINGS

        manifest, chunk = fixture_manifest()
        source = xyg.RetainedGeoSource(manifest, lambda _: chunk, budget=BUDGET)
        controller = xyg.TemporalController(instance_id=88, domain=(-10, 10))
        q = query(source.info)
        q.update(time_revision=0, camera_revision=0)
        chart = xyg.geo_chart(
            xyg.geo_layer(
                "points", source=source, layer_id=U64, query=q, sequence=1, style=style()
            ),
            camera=q["camera"],
        )
        terminal = []

        class ClosingObserver:
            def __hash__(self):
                # Force the adverse legal order in the actual observer set.
                return 0

            def __call__(self, state):
                if not state["disposed"] or nested_terminal_close:
                    controller.close()

        close_from_notification = ClosingObserver()
        stop = controller.subscribe_state(close_from_notification)
        stop_terminal = controller.subscribe_state(lambda state: terminal.append(state["disposed"]))
        binding = chart.bind_temporal(controller)
        lease = replacement = other = None
        try:
            await binding.when_idle()
            _, lease = await binding.snapshot()
            observers = list(controller._observers)
            assert observers.index(close_from_notification) < observers.index(binding._accept)
            if trigger == "dispose":
                controller.dispose()
            else:
                controller.set_cursor(3)
            await asyncio.sleep(0)
            assert binding._closed
            await binding._closing
            assert binding._frame is None
            assert source not in _BINDINGS
            assert terminal[-1] is True
            assert not controller._observers
            assert lease.data.identity["time"]["instant"] == -10
            other = xyg.TemporalController(instance_id=89, domain=(-10, 10))
            rebound = xyg.geo_chart(
                xyg.geo_layer(
                    "points",
                    source=source,
                    layer_id=U64,
                    query=q,
                    sequence=binding._sequence + 1,
                    style=style(),
                ),
                camera=q["camera"],
            )
            replacement = rebound.bind_temporal(other)
            await replacement.when_idle()
            assert replacement.error is None
        finally:
            stop()
            stop_terminal()
            if replacement is not None:
                await replacement.aclose()
            await binding.aclose()
            if lease is not None:
                lease.close()
            if other is not None:
                other.close()
            controller.close()
            source.close()

    asyncio.run(journey())


@pytest.mark.parametrize(
    "pump_cancels, prior_caller_cancel, cancel_close",
    [(1, False, False), (2, False, False), (1, True, False), (2, True, False), (1, False, True)],
)
def test_sync_worker_candidate_is_drained_before_cancelled_binding_close(
    monkeypatch, pump_cancels, prior_caller_cancel, cancel_close
):
    import threading

    from xyg._geo_temporal import _BINDINGS
    from xyg.components import GeoChart

    async def journey():
        manifest, chunk = fixture_manifest()
        entered, release, finished = threading.Event(), threading.Event(), threading.Event()
        blocked = False
        produced = []

        def reader(_):
            if blocked:
                entered.set()
                if not release.wait(5):
                    raise TimeoutError("test worker was not released")
            return chunk

        source = xyg.RetainedGeoSource(manifest, reader, budget=BUDGET)
        controller = xyg.TemporalController(instance_id=92, domain=(-10, 10))
        q = query(source.info)
        q.update(time_revision=0, camera_revision=0)
        chart = xyg.geo_chart(
            xyg.geo_layer(
                "points", source=source, layer_id=U64, query=q, sequence=1, style=style()
            ),
            camera=q["camera"],
        )
        binding = chart.bind_temporal(controller)
        lease = closing = None
        try:
            _, lease = await binding.snapshot()
            original = GeoChart.compile

            def tracked(candidate_chart, **kwargs):
                try:
                    frame = original(candidate_chart, **kwargs)
                    produced.append(frame)
                    return frame
                finally:
                    finished.set()

            monkeypatch.setattr(GeoChart, "compile", tracked)
            blocked = True
            controller.set_cursor(3)
            assert await asyncio.to_thread(entered.wait, 5)
            job = binding._task
            for _ in range(pump_cancels):
                job.cancel()
                await asyncio.sleep(0)
            close_entered = asyncio.Event()

            async def cleanup():
                if prior_caller_cancel:
                    asyncio.current_task().cancel()
                    with pytest.raises(asyncio.CancelledError):
                        await asyncio.sleep(0)
                close_entered.set()
                await binding.aclose()

            closing = asyncio.create_task(cleanup())
            await close_entered.wait()
            if cancel_close:
                closing.cancel()
            await asyncio.sleep(0)
            assert not closing.done(), "cleanup must own the still-running synchronous worker"
            release.set()
            if cancel_close:
                with pytest.raises(asyncio.CancelledError):
                    await closing
            else:
                await closing
            assert job.cancelled()
            assert len(produced) == 1
            assert produced[0]._closed, "unpublished worker result must be released"
            assert binding._frame is None
            assert source not in _BINDINGS
            assert lease.data.record(0)["feature_id"] == U64
        finally:
            release.set()
            if blocked:
                assert await asyncio.to_thread(finished.wait, 5)
            if closing is not None:
                await asyncio.gather(closing, return_exceptions=True)
            await binding.aclose()
            for frame in produced:
                frame.close()
            if lease is not None:
                lease.close()
            controller.close()
            source.close()

    asyncio.run(journey())


def test_loop_shutdown_releases_unpublished_sync_worker_candidate(monkeypatch):
    import threading

    from xyg.components import GeoChart

    manifest, chunk = fixture_manifest()
    entered, release = threading.Event(), threading.Event()
    produced = []
    blocked = False
    original = GeoChart.compile

    def reader(_):
        if blocked:
            entered.set()
            if not release.wait(5):
                raise TimeoutError("shutdown test worker was not released")
        return chunk

    def tracked(candidate_chart, **kwargs):
        frame = original(candidate_chart, **kwargs)
        produced.append(frame)
        return frame

    monkeypatch.setattr(GeoChart, "compile", tracked)
    source = xyg.RetainedGeoSource(manifest, reader, budget=BUDGET)
    controller = xyg.TemporalController(instance_id=93, domain=(-10, 10), cursor=3)
    binding = timer = None

    async def start():
        nonlocal timer, binding, blocked
        blocked = True
        q = query(source.info)
        q.update(time_revision=0, camera_revision=0)
        chart = xyg.geo_chart(
            xyg.geo_layer(
                "points", source=source, layer_id=U64, query=q, sequence=1, style=style()
            ),
            camera=q["camera"],
        )
        binding = chart.bind_temporal(controller)
        assert await asyncio.to_thread(entered.wait, 5)
        # asyncio.run now cancels pending jobs while the native reader finishes.
        timer = threading.Timer(0.05, release.set)
        timer.start()
        return binding

    try:
        binding = asyncio.run(start())
        assert len(produced) == 1
        assert produced[0]._closed, "loop shutdown must not orphan the executor's returned frame"
    finally:
        release.set()
        if timer is not None:
            timer.join()
        if binding is not None:
            asyncio.run(binding.aclose())
        for frame in produced:
            frame.close()
        controller.close()
        source.close()


@pytest.mark.parametrize("cancellations,concurrent", [(1, False), (2, False), (1, True), (2, True)])
def test_cancelled_close_drains_async_frame_and_releases_registration(cancellations, concurrent):
    import struct
    from contextlib import suppress

    from xyg import _geoscale as g
    from xyg._geo_temporal import _BINDINGS

    async def run():
        entered, release = asyncio.Event(), asyncio.Event()
        held = False

        class Bridge(g.NativeGeoScaleBridge):
            async def execute(self, request):
                if held and struct.unpack_from("<I", request, 8)[0] == 10:
                    entered.set()
                    await release.wait()
                return await super().execute(request)

        manifest, chunk = fixture_manifest()

        async def reader(_):
            return chunk

        source = await xyg.RetainedGeoSource.create_async(
            manifest, reader, budget=BUDGET, bridge=Bridge(BUDGET["processor_bytes"])
        )
        controller = xyg.TemporalController(instance_id=994, domain=(-10, 10))
        q = query(source.info)
        q.update(time_revision=0, camera_revision=0)

        def chart(sequence, request):
            return xyg.geo_chart(
                xyg.geo_layer(
                    "points",
                    source=source,
                    layer_id=U64,
                    query=request,
                    sequence=sequence,
                    style=style(),
                ),
                camera=request["camera"],
            )

        binding = chart(1, q).bind_temporal(controller)
        lease = replacement = None
        try:
            await binding.when_idle()
            _, lease = await binding.snapshot()
            accepted = binding._frame
            held = True
            close = asyncio.create_task(binding.aclose())
            await asyncio.wait_for(entered.wait(), 2)
            first_close = close if concurrent else None
            if concurrent:
                close = asyncio.create_task(binding.aclose())
                await asyncio.sleep(0)
            for _ in range(cancellations):
                close.cancel()
                await asyncio.sleep(0)
                assert not close.done(), "cancelled close must drain frame disposal"
            release.set()
            with pytest.raises(asyncio.CancelledError):
                await close
            if first_close is not None:
                await first_close
            held = False
            assert accepted._closed
            assert binding._frame is None
            assert binding._retiring is None
            assert source not in _BINDINGS
            assert lease.data.record(0)["feature_id"] == U64
            replacement = chart(binding._sequence + 1, dict(binding._query)).bind_temporal(
                controller
            )
            await replacement.when_idle()
            assert replacement.error is None
        finally:
            held = False
            release.set()
            with suppress(asyncio.CancelledError):
                await binding.aclose()
            if replacement is not None:
                await replacement.aclose()
            if lease is not None:
                await lease.aclose()
            await source.aclose()
            controller.close()

    asyncio.run(run())
