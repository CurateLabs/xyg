"""Actual native selected-frame rejection before temporal authority is erased."""

import struct
from types import SimpleNamespace

import numpy as np
import pytest

from test_geo_retained import fixture_manifest, style
from test_geoscale import BUDGET, U64, query
from xyg import _geo_overview as overview
from xyg import _geoscale as scale
from xyg._geo_retained import RetainedGeoSource
from xyg._geo_selected import GeoSelectedScope


@pytest.mark.parametrize("empty", [False, True])
def test_full_and_empty_selected_frame_rejects_before_dispatch_and_preserves_issued_state(empty):
    manifest, chunk = fixture_manifest()
    source = RetainedGeoSource(manifest, lambda _: chunk, budget=BUDGET)
    q = {**query(source.info), "state_revision": 1}
    original = source.update(q, sequence=1, style=style())
    scope = GeoSelectedScope.from_frame(original, namespace=U64, layer_id=q["layer_id"])
    ids = np.array([] if empty else [U64, U64], dtype="<u8")
    selected = state = issued = None
    try:
        state = scope.state(revision=2, ids=ids, fill=bytes([0, 255, 0, 255]))
        operation = state.begin(source, {**q, "state_revision": 2}, sequence=2)
        operation.drive()
        selected = operation.prepare(style())
        assert selected.data.selection is not None
        assert selected.data.selection["ids"].tolist() == ([] if empty else [U64])
        issued = scope.state(revision=2, ids=ids, fill=bytes([0, 255, 0, 255]))
        before = bytes(selected.data.packet)
        for budget in (BUDGET, {**BUDGET, "processor_bytes": 4096}):
            raw = overview.request(
                27, selected.handle, 2, budget=budget, payload=struct.pack("<Q", 1000000)
            )
            answer = scale.execute(raw)
            receipt = overview.reply(answer)
            assert receipt["code"] == 17
            assert (receipt["handle"], receipt["sequence"]) == (selected.handle, 2)
            assert receipt["ticket"] is None
            assert answer[32:] == bytes(224)
            assert scale.execute(raw) == answer
        assert (
            scale.read(scale.encode_request(dict(command=23, handle=selected.handle)), 128 << 20)
            == before
        )
        calls = []

        def dispatch(request):
            calls.append(request)
            return scale.execute(request)

        with pytest.raises(overview.GeoOverviewUnsupportedSelected):
            dispatch(overview.builder_request(selected, budget=BUDGET, max_vertices=1000000))
        assert not calls
        forged = SimpleNamespace(
            handle=selected.handle,
            data=SimpleNamespace(selection=None, identity={"sequence": 2}),
        )
        assert (
            overview.reply(
                scale.execute(overview.builder_request(forged, budget=BUDGET, max_vertices=1000000))
            )["code"]
            == 17
        )
        newer = issued.begin(source, {**q, "state_revision": 2}, sequence=3)
        newer.drive()
        assert bytes(selected.data.packet) == before
        assert original.data.record(0)["feature_id"] == U64
        ordinary = overview.builder_request(original, budget=BUDGET, max_vertices=1000000)
        assert ordinary == overview.request(
            27, original.handle, 1, budget=BUDGET, payload=struct.pack("<Q", 1000000)
        )
        builder = overview.reply(dispatch(ordinary))["handle"]
        scale.execute(overview.request(10, builder, 1))
    finally:
        if selected is not None:
            selected.close()
        original.close()
        source.close()
        if state is not None:
            state.close()
        if issued is not None:
            issued.close()
        scope.close()
