"""Actual native private hierarchy tickets and independent retained frames."""

import asyncio

import pytest

from test_geo_retained import style
from test_geo_spatial import setup
from test_geoscale import U64, query
from xyg._geo_hierarchy import GeoHierarchy, is_hierarchy_frame


def storage(pages, **extra):
    return dict(
        grid=1024,
        max_vertices=1000000,
        max_write_bytes=64 << 20,
        read_page=lambda t: pages[(t["namespace"], t["page"])],
        write_page=lambda t, b: pages.__setitem__((t["namespace"], t["page"]), bytes(b)),
        **extra,
    )


def test_frame_exact_scene_disposal_independent_rows_pick_and_retain():
    source, old, _ = setup()
    index = frame = retained = None
    try:
        index = GeoHierarchy.from_frame(old, source, **storage({}))
        source.close()
        frame = index.update(query(index.info), sequence=2, style=style())
        assert frame.data.scene == old.data.scene
        assert frame.data.record(0)["feature_id"] == U64
        assert frame._source is source
        assert is_hierarchy_frame(frame)
        assert not is_hierarchy_frame(old)
        assert frame.hierarchy_stats["passes"] == 1
        retained = frame.retain()
        assert is_hierarchy_frame(retained)
        index.close()
        frame.close()
        rows = retained.rows()
        assert rows.data.record(0)["feature_id"] == U64
        rows.close()
        hit = retained.pick(style=style(), x=400, y=300, tolerance=0, mode=0, max_hits=4)
        assert hit.data["count"] == 1
        hit.close()
    finally:
        if retained:
            retained.close()
        if frame:
            frame.close()
        if index:
            index.close()
        old.close()
        source.close()


def test_callback_mutation_and_backing_budget_preserve_old_frame():
    source, old, _ = setup()
    pages = {}
    options = storage(pages)

    def write(t, b):
        t["raw"] = b"\0" * 128
        t["namespace"] = 0
        t["encoded_bytes"] *= 2
        raise OSError("storage failed")

    options["write_page"] = write
    try:
        with pytest.raises(OSError, match="storage failed"):
            GeoHierarchy.from_frame(old, source, **options)
        assert old.data.record(0)["feature_id"] == U64
        index = GeoHierarchy.from_frame(old, source, **storage(pages))
        try:
            frame = index.update(query(index.info), sequence=2, style=style())
            frame.close()
        finally:
            index.close()
    finally:
        old.close()
        source.close()


def test_async_cancel_write_settles_before_exact_ack():
    async def run():
        source, old, _ = setup()
        entered, release = asyncio.Event(), asyncio.Event()

        async def write(t, b):
            entered.set()
            await release.wait()

        options = storage({})
        options["write_page"] = write
        pending = asyncio.create_task(GeoHierarchy.from_frame_async(old, source, **options))
        try:
            await entered.wait()
            pending.cancel()
            await asyncio.sleep(0.01)
            assert not pending.done()
            release.set()
            with pytest.raises(asyncio.CancelledError):
                await pending
            assert old.data.record(0)["feature_id"] == U64
        finally:
            release.set()
            old.close()
            source.close()

    asyncio.run(run())
