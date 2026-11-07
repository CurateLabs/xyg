"""A shared native clock preserves both accepted composition contracts."""

import asyncio

import xyg
from geo_live_fixture import live_chart_fixture


def test_catalog_export_and_private_geo_binding_share_exact_controller_state():
    async def journey():
        source, geo = live_chart_fixture()
        clock = xyg.TemporalController(instance_id=46050, domain=(-10, 10))
        catalog = xyg.temporal_chart(
            "event",
            [(-1, None, 1, (1 << 64) - 1)],
            domain=(-10, 10),
            timezone="UTC",
            controller=clock,
        )
        binding = geo.bind_temporal(clock)
        frames = []
        try:
            await binding.when_idle()
            assert binding.error is None
            _, first = await binding.snapshot()
            frames.append(first)
            accepted_packet = bytes(first.data.packet)
            assert first.data.identity["time"] == {"kind": 1, "instant": -10}
            assert "cursor -10" in catalog.to_svg()
            clock.set_cursor(2)
            await binding.when_idle()
            assert binding.error is None
            _, current = await binding.snapshot()
            frames.append(current)
            assert current.data.identity["time"] == {"kind": 1, "instant": 2}
            assert "cursor 2" in catalog.to_svg()
            assert source.current is None
            clock.set_selection([(1 << 64) - 1]).set_range(-5, 8)
            await binding.when_idle()
            _, unchanged = await binding.snapshot()
            frames.append(unchanged)
            assert unchanged.data.identity == current.data.identity
            assert "[-5, 8)" in catalog.to_svg()
            assert bytes(first.data.packet) == accepted_packet
            await binding.aclose()
            clock.close()
            assert bytes(first.data.packet) == accepted_packet
            assert not any(frame._closed for frame in frames)
        finally:
            await binding.aclose()
            for frame in frames:
                await frame.aclose()
            clock.close()
            source.close()

    asyncio.run(journey())
