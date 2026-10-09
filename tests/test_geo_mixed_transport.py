"""Actual native mixed ownership and thin Python framing/cleanup evidence."""

import asyncio
import gc
import struct
import weakref

import pytest

from test_geoscale import BUDGET, I64, U64, query, source_fixture
from xyg import _geo_mixed as mixed
from xyg import _geo_tiles as tiles
from xyg import _geocatalog as catalog
from xyg import _geoscale as scale
from xyg import _native


async def authorities(raster_color=(0, 0, 255, 255)):
    _, chunk = source_fixture()
    bridge = scale.NativeGeoScaleBridge(BUDGET["processor_bytes"])
    builder = scale.decode_reply(scale.execute(scale.encode_request(dict(command=1))))["handle"]
    session = source_frame = tile_session = tile_frame = None
    try:
        scale.execute(scale.encode_request(dict(command=2, handle=builder, payload=chunk)))
        scale.execute(scale.encode_request(dict(command=3, handle=builder, generation=U64)))
        manifest = scale.read(scale.encode_request(dict(command=21, handle=builder)), 128 << 20)
        session = scale.decode_reply(
            scale.execute(scale.encode_request(dict(command=4, budget=BUDGET, payload=manifest)))
        )["handle"]

        async def reader(_ticket):
            return chunk

        source = (
            await scale.drive_session(
                bridge, handle=session, sequence=0, budget=BUDGET, read_chunk=reader
            )
        )["source"]
        authored = query(source)
        authored["camera"].update(world_wrap=False, width=64.0, height=64.0)
        authored["time"] = dict(kind=2, start=I64, end=I64 + 1)
        scale.execute(
            scale.encode_request(
                dict(command=5, handle=session, sequence=1, budget=BUDGET, query=authored)
            )
        )
        await scale.drive_session(
            bridge, handle=session, sequence=1, budget=BUDGET, read_chunk=reader
        )
        source_frame = await scale.prepare_scene_data(
            bridge,
            handle=session,
            sequence=1,
            budget=BUDGET,
            style=scale.encode_style(
                dict(
                    fill=b"\xff\0\0\xff",
                    stroke=b"\0" * 4,
                    stroke_width=0.0,
                    diameter=8.0,
                    opacity=1.0,
                    symbol=0,
                )
            ),
        )
        packet = source_frame.data.packet
        snapshot = (
            bytes(packet[80:144])
            + bytes(packet[144:208])
            + bytes(packet[208:212])
            + bytes(4)
            + bytes(packet[216:232])
            + bytes(8)
        )
        packet = None
        point = bytearray(96)
        struct.pack_into("<4s4I", point, 0, b"XYGD", 1, 1, 4326, 1)
        struct.pack_into("<2Q", point, 24, 1, 1)
        struct.pack_into("<d", point, 64, 10.0)
        point[80] = 1
        struct.pack_into("<Q", point, 88, U64)
        sources = [
            tiles.GeoTileSource(
                kind + 1,
                1,
                kind + 7,
                1,
                1,
                kind,
                0,
                0,
                1024 if kind else 262144,
                1,
                1,
                "local/vector" if kind else "https://example.test/{z}/{x}/{y}",
                "" if kind else "Tiles",
                not kind,
            )
            for kind in range(2)
        ]
        tile_session = tiles.GeoTileSession(
            sources,
            lambda receipt: bytes(point) if receipt["key"]["kind"] else bytes(raster_color) * 65536,
            view_id=9,
            budget=128 << 20,
        )
        empty = catalog.encode_request(dict(camera=authored["camera"], layers=[]), 128 << 20)
        tile_frame = tile_session.prepare(
            authored["camera"],
            catalog=empty,
            vector_styles=[
                dict(
                    layer_id=8,
                    kind=1,
                    style=dict(
                        fill=b"\0\xff\0\xff",
                        stroke=b"\0" * 4,
                        stroke_width=0.0,
                        diameter=6.0,
                        opacity=1.0,
                        symbol=0,
                    ),
                )
            ],
            image_id=42,
        )
        context = mixed.tile_descriptor(
            tiles.read(
                tiles.encode_request(
                    23, tile_frame.handle, epoch=tile_frame.epoch, budget=128 << 20
                ),
                128 << 20,
            )
        )
        assert context["handle"] == tile_frame.handle
        coord = mixed.reply(tiles.execute(mixed.request(1)))["handle"]
        request = mixed.request(
            2,
            coord,
            budget=128 << 20,
            authorities=(
                source_frame.handle,
                1,
                tile_frame.handle,
                tile_frame.epoch,
                tile_session.handle,
                9,
                0,
            ),
            snapshot=snapshot,
            stamps=context["stamps"],
        )
        context = snapshot = None
        return dict(
            packet=request,
            coord=coord,
            source=source_frame,
            source_session=session,
            builder=builder,
            tile=tile_frame,
            tile_session=tile_session,
        )
    except BaseException:
        if tile_frame:
            tile_frame.close()
        if tile_session:
            tile_session.close()
        if source_frame:
            await source_frame.dispose()
        if session is not None:
            scale.execute(scale.encode_request(dict(command=10, handle=session)))
        scale.execute(scale.encode_request(dict(command=10, handle=builder)))
        raise


async def dispose_authorities(a):
    a["packet"] = None
    a["tile"].close()
    a["tile_session"].close()
    await a["source"].dispose()
    scale.execute(scale.encode_request(dict(command=10, handle=a["source_session"])))
    scale.execute(scale.encode_request(dict(command=10, handle=a["builder"])))
    tiles.execute(mixed.request(5, a["coord"]))


@pytest.mark.parametrize("raster_color", [(0, 0, 255, 255), (0, 0, 0, 255), (255, 255, 255, 255)])
def test_actual_native_python_mixed_scene_freeze_and_original_disposal(raster_color):
    async def run():
        a = await authorities(raster_color)
        frame = mixed.prepare(a["packet"], budget=128 << 20)
        try:
            frame.commit()
            assert frame.data.visible_vertices == 2
            assert struct.unpack_from("<q", frame.data.snapshot, 136)[0] == I64
            assert struct.unpack_from("<Q", frame.data.snapshot, 120)[0] == U64
            await dispose_authorities(a)
            retained = frame.retain_source_authority(budget=128 << 20)
            scale.execute(scale.encode_request(dict(command=10, handle=retained["handle"])))
            artifact = frame.export("png")
            try:
                from io import BytesIO

                from PIL import Image

                image = Image.open(BytesIO(artifact.bytes)).convert("RGBA")
                assert image.getpixel((32, 32)) == (255, 0, 0, 255)
                assert image.getpixel((2, 2)) == raster_color
                footer = [image.getpixel((x, y)) for y in range(51, 63) for x in range(41, 61)]
                assert any(max(p[:3]) < 64 and p[3] == 255 for p in footer)
                assert (255, 255, 255, 255) in footer
                assert b"Tiles" in artifact.snapshot
                image.close()
            finally:
                artifact.close()
            artifact = frame.export("html")
            try:
                assert b"Tiles" in artifact.bytes and b"default-src 'none'" in artifact.bytes
                assert b"<script" not in artifact.bytes
            finally:
                artifact.close()
        finally:
            frame.close()
        frame.close()
        with pytest.raises(RuntimeError, match="disposed"):
            _ = frame.data

    asyncio.run(run())


def test_python_failed_identity_drops_packet_views_before_disposal(monkeypatch):
    async def run():
        a = await authorities()
        actual_read, actual_execute, actual_decoder = tiles.read, tiles.execute, mixed.MixedData
        references, disposed = [], []

        def decode(packet):
            data = actual_decoder(packet)
            references.append(weakref.ref(data))
            return data

        def read(packet, budget):
            data = bytearray(actual_read(packet, budget))
            struct.pack_into("<Q", data, 80, 0)
            return bytes(data)

        def execute(packet):
            if packet[:4] == b"XYMX" and struct.unpack_from("<I", packet, 8)[0] == 5:
                gc.collect()
                assert references and references[-1]() is None
                disposed.append(struct.unpack_from("<Q", packet, 16)[0])
            return actual_execute(packet)

        monkeypatch.setattr(mixed, "MixedData", decode)
        monkeypatch.setattr(tiles, "read", read)
        monkeypatch.setattr(tiles, "execute", execute)
        try:
            with pytest.raises(ValueError, match="identity changed"):
                mixed.prepare(a["packet"], budget=128 << 20)
            assert len(disposed) == 1
            with pytest.raises(_native.GeoNativeError):
                actual_read(mixed.request(20, disposed[0], nonce=1, budget=128 << 20), 128 << 20)
        finally:
            monkeypatch.setattr(tiles, "execute", actual_execute)
            monkeypatch.setattr(tiles, "read", actual_read)
            await dispose_authorities(a)

    asyncio.run(run())


def test_python_disposal_failure_keeps_retryable_owner_after_views_drop(monkeypatch):
    async def run():
        a = await authorities()
        frame = mixed.prepare(a["packet"], budget=128 << 20)
        actual = tiles.execute
        attempts = []

        def execute(packet):
            if packet[:4] == b"XYMX" and struct.unpack_from("<I", packet, 8)[0] == 5:
                assert frame._data is None
                attempts.append(packet)
                if len(attempts) == 1:
                    raise _native.GeoNativeError(-9)
            return actual(packet)

        monkeypatch.setattr(tiles, "execute", execute)
        try:
            with pytest.raises(_native.GeoNativeError):
                frame.close()
            with pytest.raises(RuntimeError, match="disposed"):
                _ = frame.data
            frame.close()
            frame.close()
            assert len(attempts) == 2
        finally:
            monkeypatch.setattr(tiles, "execute", actual)
            frame.close()
            await dispose_authorities(a)

    asyncio.run(run())
