"""Native43-issued Data matches the ordinary explicit static host composition."""

import struct

import numpy as np
import pytest

import xyg
from test_geo_hierarchy import storage
from test_geo_host import request
from test_geo_retained import fixture_manifest, style
from test_geoscale import BUDGET, U64, query
from xyg import _geoscale as g
from xyg._geo_hierarchy import _FRAMES, _request, drive_hierarchy
from xyg._geo_retained import OwnedGeoData, RetainedGeoSource, _attach_frame
from xyg._geo_selected import GeoSelectedScope


def selected_request(command, handle, sequence, **fields):
    packet = bytearray(_request(38 if command == 43 else 39, handle, sequence, **fields))
    struct.pack_into("<I", packet, 8, command)
    return bytes(packet)


def test_actual43_static_frame_matches_and_malformed_authoring_cannot_gain_exception():
    manifest, chunk = fixture_manifest()
    source = RetainedGeoSource(manifest, lambda _: chunk, budget=BUDGET)
    q = dict(query(source.info), state_revision=1)
    initial = source.update(q, sequence=1, style=style())
    scope = GeoSelectedScope.from_frame(initial, namespace=777, layer_id=U64)
    q = dict(query(source.info), state_revision=1)
    state = scope.state(revision=1, ids=np.array([U64], dtype="<u8"), fill=b"\0\xff\0\xff")
    operation = state.begin(source, q, sequence=2)
    operation.drive()
    selected = operation.prepare(style())
    pages = {}
    options = storage(pages)
    root = frame = adapter = candidate = None
    try:
        root = g.decode_reply(
            g.execute(
                _request(
                    37,
                    selected.handle,
                    2,
                    budget=source.budget,
                    payload=struct.pack("<IIQQ", 1024, 0, 1000000, 64 << 20),
                )
            )
        )["handle"]
        assert (
            drive_hierarchy(
                root, 2, source.budget, source._reader, options["read_page"], options["write_page"]
            )["code"]
            == 18
        )
        candidate = scope.state(revision=1, ids=np.array([U64], dtype="<u8"), fill=b"\0\xff\0\xff")
        issued = selected_request(
            43, root, 3, budget=source.budget, query=q, payload=struct.pack("<Q", candidate.handle)
        )
        reply = g.decode_reply(g.execute(issued))
        assert reply["handle"] == candidate.handle
        candidate._live = False  # Raw43 consumed this issued State into Query.
        assert (
            drive_hierarchy(
                reply["handle"],
                3,
                source.budget,
                source._reader,
                options["read_page"],
                options["write_page"],
            )["code"]
            == 19
        )
        data_reply = g.decode_reply(
            g.execute(
                selected_request(44, reply["handle"], 3, budget=source.budget, payload=style())
            )
        )
        assert data_reply["handle"] == reply["handle"]
        packet = g.read(
            g.encode_request(dict(command=23, handle=reply["handle"])),
            source.budget["processor_bytes"],
        )
        frame = OwnedGeoData(reply["handle"], g.SceneData(packet), None)
        _attach_frame(source, frame, 3, issued, style(), _FRAMES.add)
        chart = xyg.geo_chart(
            xyg.geo_layer(
                "points", source=source, layer_id=U64, query=q, sequence=3, style=style()
            ),
            camera=q["camera"],
        )
        for invalid in (issued[:256], issued + b"\0", issued[:232] + bytes(8) + issued[240:]):
            frame._query_packet = invalid
            with pytest.raises((ValueError, struct.error)):
                chart.host(frame=frame)
        frame._query_packet = issued
        _FRAMES.discard(frame)
        with pytest.raises(ValueError, match="private provenance"):
            chart.host(frame=frame)
        _FRAMES.add(frame)
        adapter = chart.host(frame=frame)
        frame.close()
        source.close()
        message, _ = request(adapter, 1)
        assert "error" not in message, message
        assert adapter._frame.data.selection["ids"].tolist() == [U64]
        assert "error" not in request(adapter, 4, owner=adapter._frame.handle, sequence=3)[0]
    finally:
        if adapter:
            adapter.close()
        if frame:
            frame.close()
        if root:
            g.execute(_request(10, root, 2))
        if candidate:
            candidate.close()
        selected.close()
        initial.close()
        source.close()
        scope.close()
