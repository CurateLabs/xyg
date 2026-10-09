"""Actual native immutable-frame duplicate ownership and cancellation proofs."""

import asyncio
import struct

import pytest

from test_geo_retained import fixture_manifest, style
from test_geoscale import BUDGET, U64, query
from xyg import _geoscale as g
from xyg._geo_retained import RetainedGeoSource


def setup():
    manifest, chunk = fixture_manifest()
    source = RetainedGeoSource(manifest, lambda _: chunk, budget=BUDGET)
    return source, source.update(query(source.info), sequence=1, style=style())


def canonical(packet):
    result = bytearray(packet)
    result[16:24] = bytes(8)  # Process-local packet owner only.
    return bytes(result)


def test_duplicate_inside_running_loop_survives_original_and_source_disposal():
    async def notebook():
        source, original = setup()
        owned = original.retain()
        try:
            assert source.current is original
            assert owned.handle != original.handle
            assert canonical(owned.data.packet) == canonical(original.data.packet)
            assert owned.data.identity["session_handle"] == original.handle
            assert owned._query_packet == original._query_packet
            source.close()
            original.close()
            assert owned.data.record(0)["feature_id"] == U64
            rows = owned.rows()
            assert rows.data.record(0)["feature_id"] == U64
            rows.close()
            hit = owned.pick(style=style(), x=400, y=300, tolerance=0, mode=0, max_hits=4)
            assert hit.data["count"] == 1
            hit.close()
            artifact = owned.export("svg")
            assert b"<svg" in artifact.bytes
            artifact.close()
            second = await owned.retain_async()
            try:
                owned.close()
                assert second.data.record(0)["feature_id"] == U64
            finally:
                second.close()
            with pytest.raises(RuntimeError, match="disposed"):
                original.retain()
        finally:
            owned.close()
            original.close()
            source.close()

    asyncio.run(notebook())


def test_indexed_duplicate_never_requeries_disposed_index_session():
    source, original = setup()
    pages = {}
    index = original.spatial_index(
        grid=16,
        max_vertices=1000000,
        read_page=lambda ticket: pages[ticket["page"]],
        write_page=lambda ticket, packet: pages.__setitem__(ticket["page"], bytes(packet)),
    )
    indexed = index.update(query(index.info), sequence=2, style=style())
    owned = indexed.retain()
    try:
        assert index.current is indexed
        assert owned.index_stats == indexed.index_stats
        assert canonical(indexed.data.packet) == canonical(owned.data.packet)
        index.close()
        source.close()
        original.close()
        indexed.close()
        hit = owned.pick(style=style(), x=400, y=300, tolerance=0, mode=0, max_hits=4)
        assert hit.data["count"] == 1
        hit.close()
        rows = owned.rows()
        assert rows.data.record(0)["feature_id"] == U64
        rows.close()
        artifact = owned.export("svg")
        assert b"<svg" in artifact.bytes
        artifact.close()
    finally:
        owned.close()
        indexed.close()
        index.close()
        original.close()
        source.close()


def test_duplicate_pressure_and_disposal_leave_original_usable():
    source, original = setup()
    retained = []
    try:
        for _ in range(7):
            retained.append(original.retain())
        with pytest.raises(ValueError):
            original.retain()
        assert source.current is original and original.data.record(0)["feature_id"] == U64
        for frame in retained:
            frame.close()
        retained.clear()
        for _ in range(20):
            original.retain().close()
        assert original.data.record(0)["feature_id"] == U64
    finally:
        for frame in retained:
            frame.close()
        original.close()
        source.close()


def test_cancelled_async_duplicate_read_settles_then_drops_unreturned_owner():
    async def main():
        manifest, chunk = fixture_manifest()
        entered, release = asyncio.Event(), asyncio.Event()

        class Bridge(g.NativeGeoScaleBridge):
            duplicate = None
            hold = False

            async def execute(self, request):
                reply = await super().execute(request)
                if struct.unpack_from("<I", request, 8)[0] == 26:
                    self.duplicate = g.decode_reply(reply)["handle"]
                return reply

            async def read(self, request):
                reply = await super().read(request)
                if self.hold and struct.unpack_from("<Q", request, 16)[0] == self.duplicate:
                    entered.set()
                    await release.wait()
                return reply

        bridge = Bridge(BUDGET["processor_bytes"])

        async def reader(_):
            return chunk

        source = await RetainedGeoSource.create_async(
            manifest, reader, budget=BUDGET, bridge=bridge
        )
        original = await source.aupdate(query(source.info), sequence=1, style=style())
        try:
            bridge.hold = True
            pending = asyncio.create_task(original.retain_async())
            await entered.wait()
            pending.cancel()
            await asyncio.sleep(0)
            assert not pending.done()
            release.set()
            with pytest.raises(asyncio.CancelledError):
                await pending
            with pytest.raises(ValueError):
                g.read(
                    g.encode_request(dict(command=23, handle=bridge.duplicate)),
                    BUDGET["processor_bytes"],
                )
            assert source.current is original
            bridge.hold = False
            duplicate = await original.retain_async()
            await duplicate.aclose()
        finally:
            release.set()
            await original.aclose()
            await source.aclose()

    asyncio.run(main())
