"""Actual immutable indexed Data authority through native host mounting."""

import struct
from dataclasses import replace

import pytest

import xyg
from test_geo_host import request
from test_geo_retained import fixture_manifest, style
from test_geoscale import BUDGET, U64, query
from xyg._geo_retained import RetainedGeoSource


def indexed_chart_fixture():
    manifest, chunk = fixture_manifest()
    source = RetainedGeoSource(manifest, lambda _: chunk, budget=BUDGET)
    canonical = source.update(query(source.info), sequence=1, style=style())
    pages = {}
    index = canonical.spatial_index(
        grid=16,
        max_vertices=1000000,
        read_page=lambda ticket: pages[ticket["page"]],
        write_page=lambda ticket, packet: pages.__setitem__(ticket["page"], bytes(packet)),
    )
    q = query(index.info)
    frame = index.update(q, sequence=2, style=style())
    chart = xyg.geo_chart(
        xyg.geo_layer("points", source=index, layer_id=U64, query=q, sequence=2, style=style()),
        camera=q["camera"],
    )
    canonical.close()
    source.close()
    index.close()
    return index, chart, frame


def test_indexed_anchor_survives_caller_disposal_and_ack_remount():
    index, chart, original = indexed_chart_fixture()
    adapter = chart.host(frame=original)
    anchor = adapter._anchor
    assert anchor.handle != original.handle
    assert index.current is original
    original.close()
    try:
        for mount in ("first", "second"):
            message, buffers = request(adapter, 1, mount=mount)
            assert "error" not in message
            owner, sequence = struct.unpack("<4sIIIQQ", buffers[0])[4:]
            assert owner == anchor.handle
            if mount == "second":
                assert request(adapter, 4, mount="first", owner=owner, sequence=sequence)[0][
                    "error"
                ]
                assert adapter.mounted
            assert adapter._frame.data.record(0)["feature_id"] == U64
            message, hits = request(
                adapter,
                2,
                mount=mount,
                owner=owner,
                sequence=sequence,
                payload=struct.pack("<3dII", 400, 300, 0, 0, 4),
            )
            assert "error" not in message
            aux = struct.unpack("<4sIIIQQ", hits[0])[4]
            hits = buffers = None
            request(adapter, 5, mount=mount, owner=aux, sequence=sequence)
            if mount == "second":
                adapter.close()
                assert anchor.data.record(0)["feature_id"] == U64
            assert (
                "error" not in request(adapter, 4, mount=mount, owner=owner, sequence=sequence)[0]
            )
        with pytest.raises(RuntimeError, match="disposed"):
            _ = anchor.data
    finally:
        adapter.close()
        original.close()


def test_indexed_host_rejects_mismatches_without_stealing_caller_frame():
    index, chart, frame = indexed_chart_fixture()
    try:
        with pytest.raises(ValueError, match="indexed hosts are pending"):
            chart.host()
        for field in ("camera_revision", "time_revision", "style_revision", "state_revision"):
            layer = chart.layers[0]
            changed = dict(layer.properties["query"])
            changed[field] -= 1
            wrong = replace(
                chart, layers=(replace(layer, properties={**layer.properties, "query": changed}),)
            )
            with pytest.raises(ValueError, match="explicit frame"):
                wrong.host(frame=frame)
        wrong = replace(
            chart,
            layers=(
                replace(chart.layers[0], properties={**chart.layers[0].properties, "sequence": 3}),
            ),
        )
        with pytest.raises(ValueError, match="explicit frame"):
            wrong.host(frame=frame)
        changed_style = bytearray(style())
        changed_style[0] = 127
        wrong = replace(
            chart,
            layers=(
                replace(
                    chart.layers[0],
                    properties={**chart.layers[0].properties, "style": bytes(changed_style)},
                ),
            ),
        )
        with pytest.raises(ValueError, match="explicit frame"):
            wrong.host(frame=frame)
        changed_camera = {**chart.camera, "center_x": 1.0}
        wrong = replace(
            chart,
            camera=changed_camera,
            layers=(
                replace(
                    chart.layers[0],
                    properties={
                        **chart.layers[0].properties,
                        "query": {**chart.layers[0].properties["query"], "camera": changed_camera},
                    },
                ),
            ),
        )
        with pytest.raises(ValueError, match="explicit frame"):
            wrong.host(frame=frame)
        original_rows = index.info["rows"]
        index.info["rows"] += 1
        with pytest.raises(ValueError, match="explicit frame"):
            chart.host(frame=frame)
        index.info["rows"] = original_rows
        # Parsed metadata is convenience, not the immutable packet authority.
        frame.data.identity["sequence"] = 100
        assert frame.data.record(0)["feature_id"] == U64
        facade = chart.host(frame=frame)
        facade.close()
        assert frame.data.record(0)["feature_id"] == U64
    finally:
        frame.close()


def test_anchor_quota_pressure_preserves_caller_and_cleanup_drains():
    _, chart, frame = indexed_chart_fixture()
    copies = []
    try:
        copies = [frame.retain() for _ in range(7)]
        with pytest.raises(ValueError):
            chart.host(frame=frame)
        assert frame.data.record(0)["feature_id"] == U64
        for copy in copies:
            copy.close()
        copies.clear()
        for _ in range(12):
            chart.host(frame=frame).close()
        assert frame.data.record(0)["feature_id"] == U64
    finally:
        for copy in copies:
            copy.close()
        frame.close()


def test_five_native_views_share_quota_with_bounded_auxiliary_pressure():
    _, chart, frame = indexed_chart_fixture()
    facades = []
    try:
        facades = [chart.host(frame=frame) for _ in range(5)]
        for number, facade in enumerate(facades):
            message, _outgoing = request(facade, 1, mount=str(number))
            assert "error" not in message
            assert facade._frame is facade._anchor
            _outgoing = None
        for number in range(3):
            facade = facades[number]
            message, _outgoing = request(
                facade,
                2,
                mount=str(number),
                owner=facade._frame.handle,
                sequence=2,
                payload=struct.pack("<3dII", 400, 300, 0, 0, 4),
            )
            _outgoing = None
            if number == 2:
                assert message["error"] and facade._aux is None
            else:
                assert "error" not in message
        assert all(f._frame.data.record(0)["feature_id"] == U64 for f in facades)
        for number in range(2):
            facade = facades[number]
            assert (
                "error"
                not in request(facade, 5, mount=str(number), owner=facade._aux.handle, sequence=2)[
                    0
                ]
            )
        assert frame.data.record(0)["feature_id"] == U64
    finally:
        for number, facade in enumerate(facades):
            facade.close()
            if facade._aux is not None:
                request(facade, 5, mount=str(number), owner=facade._aux.handle, sequence=2)
            if facade.mounted:
                request(facade, 4, mount=str(number), owner=facade._frame.handle, sequence=2)
            assert facade._anchor is None
        frame.close()
