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
