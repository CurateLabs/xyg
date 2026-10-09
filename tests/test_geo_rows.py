"""Actual native full-original-row authority, notebook loops and row-page ownership."""

import asyncio
import struct

import numpy as np
import pytest

from test_geo_retained import style
from test_geoscale import BUDGET, I64, U64, query
from xyg import _geoscale as g
from xyg._geo_retained import GeoRowsData, RetainedGeoSource


def rows_fixture():
    descriptor = bytearray(264)
    struct.pack_into("<4s5I5Q", descriptor, 0, b"XYGD", 1, 4, 4326, 1, 0, 5, 8, 6, 0, 0)
    struct.pack_into(
        "<16d", descriptor, 64, 0, 0, 1, 1, 179, 85, 178, 84, -179, -85, -178, -84, 0.5, 0.5, 2, 2
    )
    descriptor[192:197] = bytes([1, 1, 0, 1, 1])
    struct.pack_into("<5Q", descriptor, 200, U64, 7, 1 << 63, 7, 9)
    struct.pack_into("<6I", descriptor, 240, 0, 2, 4, 4, 6, 8)
    chunk = g.read(
        g.encode_chunk_request(
            dict(
                descriptor=descriptor,
                rows=5,
                intervals=dict(
                    starts=np.array([I64, -10, 0, -10, 0], dtype="<i8"),
                    ends=np.array([-10, 0, 0, 0, 0], dtype="<i8"),
                    start_validity=np.array([1, 1, 0, 1, 0], dtype="u1"),
                    end_validity=np.array([1, 1, 0, 1, 0], dtype="u1"),
                ),
                values=np.array([-0.0, np.nan, 42.0, np.inf, 5.0], dtype="<f8"),
            ),
            BUDGET["processor_bytes"],
        ),
        BUDGET["processor_bytes"],
    )
    builder = g.decode_reply(g.execute(g.encode_request(dict(command=1))))["handle"]
    try:
        g.execute(g.encode_request(dict(command=2, handle=builder, payload=chunk)))
        g.execute(g.encode_request(dict(command=3, handle=builder, generation=U64)))
        manifest = g.read(
            g.encode_request(dict(command=21, handle=builder)), BUDGET["processor_bytes"]
        )
    finally:
        g.execute(g.encode_request(dict(command=10, handle=builder)))
    return manifest, chunk


def row_query(info):
    return {
        **query(info),
        "camera": {**query(info)["camera"], "zoom": 4.0},
        "time": dict(kind=1, instant=-10),
    }


def test_native_all_original_rows_pages_after_source_and_frame_disposal_in_notebook_loop():
    manifest, chunk = rows_fixture()
    budget = {**BUDGET, "page_rows": 2}

    async def notebook():
        source = RetainedGeoSource(manifest, lambda _: chunk, budget=budget)
        frame = source.update(row_query(source.info), sequence=1, style=style())
        page = frame.rows()
        source.close()
        frame.close()
        rows = []
        try:
            while True:
                data = page.data
                assert isinstance(data.packet, memoryview) and isinstance(data.records, memoryview)
                rows.extend(data.record(i) for i in range(data.count))
                assert data.count <= 2
                if not data.has_next:
                    with pytest.raises(RuntimeError, match="no next"):
                        page.next_page()
                    break
                next_page = page.next_page()
                data = None
                page.close()
                with pytest.raises(RuntimeError, match="disposed"):
                    page.next_page()
                page = next_page
            assert [r["source_row"] for r in rows] == list(range(5))
            assert [r["feature_id"] for r in rows] == [U64, 7, 1 << 63, 7, 9]
            assert not rows[0]["time_eligible"] and rows[0]["interval_start"] == I64
            assert rows[2]["geometry_null"] and rows[2]["time_eligible"] and not rows[2]["eligible"]
            assert rows[1]["eligible"] and rows[3]["eligible"]  # offscreen still reachable
            assert rows[4]["interval_start"] is None and rows[4]["interval_end"] is None
            assert struct.pack("<d", rows[0]["value"]) == struct.pack("<d", -0.0)
        finally:
            data = None
            page.close()

    asyncio.run(notebook())


def test_native_rows_failure_keeps_old_frame_and_page_recovery_and_private_cursor():
    manifest, chunk = rows_fixture()
    state = {"bad": False}
    source = RetainedGeoSource(
        manifest,
        lambda _: bytes(len(chunk)) if state["bad"] else chunk,
        budget={**BUDGET, "page_rows": 2},
    )
    frame = source.update(row_query(source.info), sequence=1, style=style())
    page = frame.rows()
    try:
        state["bad"] = True
        with pytest.raises(ValueError):
            page.next_page()
        assert source.current is frame and page.data.record(0)["feature_id"] == U64
        state["bad"] = False
        next_page = page.next_page()
        next_page.close()
        with pytest.raises(TypeError):
            page.next_page(cursor=b"forged")
        with pytest.raises(ValueError):
            g.execute(
                g.encode_request(
                    dict(
                        command=15,
                        handle=page.handle,
                        sequence=1,
                        budget=source.budget,
                        payload=bytes(8),
                    )
                )
            )
        second = g.read(
            g.encode_request(dict(command=23, handle=page.handle)), BUDGET["processor_bytes"]
        )
        assert second
        second = None
        with pytest.raises(ValueError) as error:
            g.read(
                g.encode_request(dict(command=23, handle=page.handle)), BUDGET["processor_bytes"]
            )
        assert error.value.status == -9
    finally:
        page.close()
        frame.close()
        source.close()


class DelayedRowsBridge:
    def __init__(self):
        self.native = g.NativeGeoScaleBridge(BUDGET["processor_bytes"])
        self.wait_read = False
        self.wait_dispose = False
        self.entered = asyncio.Event()
        self.release = asyncio.Event()
        self.rows_session = None
        self.rows_data = None

    async def execute(self, request):
        command = struct.unpack_from("<I", request, 8)[0]
        handle = struct.unpack_from("<Q", request, 16)[0]
        if command == 10 and handle == self.rows_session and self.wait_dispose:
            self.entered.set()
            await self.release.wait()
        raw = await self.native.execute(request)
        if command == 15:
            self.rows_session = g.decode_reply(raw)["handle"]
        if command == 16:
            self.rows_data = g.decode_reply(raw)["handle"]
        return raw

    async def read(self, request):
        packet = await self.native.read(request)
        if struct.unpack_from("<Q", request, 16)[0] == self.rows_data and self.wait_read:
            self.entered.set()
            await self.release.wait()
        return packet


@pytest.mark.parametrize("where", ["read", "dispose"])
def test_native_async_rows_cancel_settles_io_and_unreturned_candidate_cleanup(where):
    manifest, chunk = rows_fixture()

    async def exercise():
        bridge = DelayedRowsBridge()

        async def reader(_):
            await asyncio.sleep(0)
            return chunk

        source = await RetainedGeoSource.create_async(
            manifest, reader, budget={**BUDGET, "page_rows": 2}, bridge=bridge
        )
        frame = await source.aupdate(row_query(source.info), sequence=1, style=style())
        await source.aclose()
        bridge.wait_read = where == "read"
        bridge.wait_dispose = where == "dispose"
        task = asyncio.create_task(frame.rows_async())
        await bridge.entered.wait()
        task.cancel()
        await asyncio.sleep(0)
        assert not task.done()
        bridge.release.set()
        with pytest.raises(asyncio.CancelledError):
            await task
        bridge.wait_read = bridge.wait_dispose = False
        with pytest.raises(ValueError):
            g.read(
                g.encode_request(dict(command=23, handle=bridge.rows_data)),
                BUDGET["processor_bytes"],
            )
        assert frame.data.identity["sequence"] == 1
        page = await frame.rows_async()
        following = await page.next_page_async()
        assert following.data.record(0)["source_row"] == 2
        await following.aclose()
        await page.aclose()
        await frame.aclose()

    asyncio.run(exercise())


def test_rows_decoder_rejects_malformed_padding_flags_counts_and_identity():
    manifest, chunk = rows_fixture()
    source = RetainedGeoSource(manifest, lambda _: chunk, budget={**BUDGET, "page_rows": 2})
    frame = source.update(row_query(source.info), sequence=1, style=style())
    page = frame.rows()
    try:
        raw = bytes(page.data.packet)
        owner, seq = struct.unpack_from("<QQ", raw, 16)
        for at, value in [
            (12, 1),
            (40, 2),
            (72, 1),
            (156, 1),
            (176, 1),
            (256 + 28, 1),
            (256 + 56, 1),
            (256 + 24, 255),
        ]:
            bad = bytearray(raw)
            bad[at] = value
            with pytest.raises(ValueError):
                GeoRowsData(bad, owner, seq)
        for at, value in [(32, 4097), (16, owner + 1), (256 + 8, 5)]:
            bad = bytearray(raw)
            struct.pack_into("<Q", bad, at, value)
            with pytest.raises(ValueError):
                GeoRowsData(bad, owner, seq)
        with pytest.raises(IndexError):
            page.data.record(True)
    finally:
        page.close()
        frame.close()
        source.close()
