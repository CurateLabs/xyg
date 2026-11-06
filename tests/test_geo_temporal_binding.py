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
