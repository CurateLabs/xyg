"""Actual native issued overview ownership, not a count-only mock."""

import asyncio
import struct

import pytest

from test_geo_frame_leases import setup
from test_geo_retained import fixture_manifest
from test_geoscale import BUDGET, query
from xyg import _geo_overview as wire
from xyg import _geoscale as g
from xyg._geo_overview_source import GeoOverviewIndex, GeoOverviewUncertainAllocation, _transport


def build():
    source, seed = setup()
    _, chunk = fixture_manifest()
    pages = {}
    index = GeoOverviewIndex.from_frame(
        seed,
        source,
        budget=BUDGET,
        max_vertices=1000,
        read_chunk=lambda _: chunk,
        read_page=lambda t: pages[t["namespace"], t["page"]],
        write_page=lambda t, b: pages.__setitem__((t["namespace"], t["page"]), bytes(b)),
    )
    q = query(source.info)
    q.update(max_cells=0, max_projected_vertices=0, previous_direct=False)
    return source, seed, index, q


def test_offline_exports_and_retain_survive_all_producers_inside_notebook_loop():
    async def notebook():
        source, seed, index, q = build()
        frame = index.update(q, sequence=2)
        held = frame.retain()
        try:
            assert sum(frame.data.count(i) for i in range(256)) == 2
            source.close()
            seed.close()
            index.close()
            frame.close()
            for fmt in ("png", "jpeg", "webp", "svg", "pdf", "html"):
                artifact = held.export(fmt)
                try:
                    assert len(artifact.bytes) > 50
                    if fmt == "html":
                        assert b"<script" not in artifact.bytes
                finally:
                    artifact.close()
        finally:
            held.close()
            frame.close()
            index.close()
            seed.close()
            source.close()

    asyncio.run(notebook())


def test_resolved_rejected_disposal_keeps_known_owner_retryable(monkeypatch):
    source, seed, index, q = build()
    frame = index.update(q, sequence=2)
    actual = g.execute

    def reject(packet):
        if struct.unpack_from("<I", packet, 8)[0] == 10:
            result = bytearray(256)
            struct.pack_into("<4sII4xQQ", result, 0, b"XYGZ", 1, 2, frame.handle, 0)
            return bytes(result)
        return actual(packet)

    try:
        monkeypatch.setattr(_transport(index), "native_execute", reject)
        with pytest.raises(ValueError, match="confirm settlement"):
            frame.close()
        assert frame._phase == "owned"
        monkeypatch.setattr(_transport(index), "native_execute", actual)
        frame.close()
        assert frame._phase == "closed"
    finally:
        monkeypatch.setattr(_transport(index), "native_execute", actual)
        frame.close()
        index.close()
        seed.close()
        source.close()


def test_lost_query_receipt_never_reallocates_and_original_frame_remains_usable(monkeypatch):
    source, seed, index, q = build()
    frame = index.update(q, sequence=2)
    actual = g.execute
    lost = []

    def execute(packet):
        result = actual(packet)
        if struct.unpack_from("<I", packet, 8)[0] == 28:
            lost.append(wire.reply(result)["handle"])
            raise RuntimeError("lost after actual allocation")
        return result

    try:
        monkeypatch.setattr(_transport(index), "native_execute", execute)
        with pytest.raises(GeoOverviewUncertainAllocation) as caught:
            index.update(q, sequence=3)
        assert index.pending_operation is caught.value.owner
        with pytest.raises(RuntimeError, match="busy"):
            index.update(q, sequence=4)
        assert len(lost) == 1
        assert sum(frame.data.count(i) for i in range(256)) == 2
    finally:
        monkeypatch.setattr(_transport(index), "native_execute", actual)
        # The negative control observed the real receipt; product code has no guessed cleanup.
        for handle in lost:
            wire.validate_mutation(actual(wire.request(10, handle, 3)), handle, 3)
        index._active = None
        frame.close()
        index.close()
        seed.close()
        source.close()


def test_public_density_composition_compile_export_and_explicit_host_gate():
    import xyg

    source, seed, index, q = build()
    frame = None
    try:
        chart = xyg.geo_chart(
            xyg.geo_layer("density", source=index, layer_id=q["layer_id"], query=q, sequence=2),
            camera=q["camera"],
        )
        frame = chart.compile()
        assert sum(frame.data.count(i) for i in range(256)) == 2
        artifact = chart.to_image("svg", frame=frame)
        try:
            assert b"<svg" in artifact.bytes
        finally:
            artifact.close()
        with pytest.raises(NotImplementedError, match="overview"):
            chart.host(frame=frame)
        bad = xyg.geo_chart(
            xyg.geo_layer(
                "density", source=index, layer_id=q["layer_id"], query=q, sequence=3, style={}
            ),
            camera=q["camera"],
        )
        with pytest.raises(ValueError, match="exactly query"):
            bad.compile()
    finally:
        if frame is not None:
            frame.close()
        index.close()
        seed.close()
        source.close()


def test_async_deferred_admission_and_rejected_cleanup_retry():
    from test_geo_retained import style
    from xyg._geo_retained import RetainedGeoSource

    async def proof():
        manifest, chunk = fixture_manifest()

        async def read_chunk(_):
            return chunk

        source = await RetainedGeoSource.create_async(manifest, read_chunk, budget=BUDGET)
        seed = await source.aupdate(query(source.info), sequence=1, style=style())
        pages = {}

        async def read_page(t):
            return pages[t["namespace"], t["page"]]

        async def write_page(t, b):
            pages[t["namespace"], t["page"]] = bytes(b)

        index = await GeoOverviewIndex.from_frame_async(
            seed,
            source,
            budget=BUDGET,
            max_vertices=1000,
            read_chunk=read_chunk,
            read_page=read_page,
            write_page=write_page,
        )
        q = query(source.info)
        q.update(max_cells=0, max_projected_vertices=0, previous_direct=False)
        frame = await index.update_async(q, sequence=2)
        bridge, actual = _transport(index), _transport(index).execute
        try:

            async def reject(packet):
                if struct.unpack_from("<I", packet, 8)[0] == 10:
                    result = bytearray(256)
                    struct.pack_into("<4sII4xQQ", result, 0, b"XYGZ", 1, 2, frame.handle, 0)
                    return bytes(result)
                return await actual(packet)

            bridge.execute = reject
            with pytest.raises(ValueError, match="confirm settlement"):
                await frame.aclose()
            assert frame._phase == "owned"
            bridge.execute = actual
            await asyncio.gather(frame.aclose(), frame.aclose())
            assert frame._phase == "closed"
            started, release = asyncio.Event(), asyncio.Event()

            async def deferred(packet):
                result = await actual(packet)
                if struct.unpack_from("<I", packet, 8)[0] == 28:
                    started.set()
                    await release.wait()
                return result

            bridge.execute = deferred
            updating = asyncio.create_task(index.update_async(q, sequence=3))
            await started.wait()
            closing = asyncio.create_task(index.aclose())
            release.set()
            with pytest.raises((RuntimeError, ValueError, asyncio.CancelledError)):
                await updating
            await closing
            assert index._phase == "closed"
        finally:
            bridge.execute = actual
            await frame.aclose()
            await index.aclose()
            await seed.aclose()
            await source.aclose()

    asyncio.run(proof())


def test_generator_check_is_nonmutating_and_rejects_stale_output(tmp_path):
    import pathlib
    import shutil
    import subprocess

    root = pathlib.Path(__file__).resolve().parents[1]
    (tmp_path / "scripts").mkdir()
    shutil.copyfile(
        root / "scripts/gen_geo_overview_hosts.mjs", tmp_path / "scripts/gen_geo_overview_hosts.mjs"
    )
    (tmp_path / "js").mkdir()
    (tmp_path / "js/src").symlink_to(root / "js/src", target_is_directory=True)
    (tmp_path / "node_modules").symlink_to(root / "node_modules", target_is_directory=True)
    destination = tmp_path / "packages/xy-node/src"
    destination.mkdir(parents=True)
    names = [
        "geoscale.js",
        "geoscale.d.ts",
        "geo-overview.js",
        "geo-overview.d.ts",
        "geo-overview-source.js",
        "geo-overview-source.d.ts",
    ]
    for name in names:
        shutil.copyfile(root / "packages/xy-node/src" / name, destination / name)
    assert (
        subprocess.run(
            ["node", "scripts/gen_geo_overview_hosts.mjs", "--check"],
            cwd=tmp_path,
            capture_output=True,
        ).returncode
        == 0
    )
    target = destination / "geo-overview-source.js"
    target.write_text(target.read_text() + "\n// stale\n")
    before = {name: (destination / name).read_bytes() for name in names}
    result = subprocess.run(
        ["node", "scripts/gen_geo_overview_hosts.mjs", "--check"], cwd=tmp_path, capture_output=True
    )
    assert result.returncode != 0
    assert b"Generated output differs" in result.stderr
    assert before == {name: (destination / name).read_bytes() for name in names}


def test_corrupt_publication_drops_parser_views_before_native_owner_release():
    source, seed, index, q = build()
    transport = _transport(index)
    actual_read, actual_execute = transport.native_read, transport.native_execute
    packets, release_controls = [], []

    def read(packet, budget):
        result = actual_read(packet, budget)
        if struct.unpack_from("<I", packet, 8)[0] == 23:
            result = bytearray(result)
            result[112] ^= 1
            packets.append(result)
        return result

    def execute(packet):
        if struct.unpack_from("<I", packet, 8)[0] == 10 and packets:
            try:
                packets[-1].extend(b"\0")
                release_controls.append(True)
            except BufferError:
                release_controls.append(False)
        return actual_execute(packet)

    try:
        transport.native_read, transport.native_execute = read, execute
        with pytest.raises(ValueError, match="private query snapshot"):
            index.update(q, sequence=2)
        assert release_controls and all(release_controls)
        assert seed.data.record(0)["feature_id"] == (1 << 64) - 1
    finally:
        transport.native_read, transport.native_execute = actual_read, actual_execute
        index.close()
        seed.close()
        source.close()
