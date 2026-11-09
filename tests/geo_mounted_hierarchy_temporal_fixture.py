"""Finite selected hierarchy for actual application remount journeys."""

from dataclasses import replace

import numpy as np

from test_geo_hierarchy import storage
from test_geo_mounted_temporal import mounted_chart_fixture
from test_geo_retained import style
from test_geoscale import U64
from xyg._geo_hierarchy import GeoHierarchy
from xyg._geo_selected import GeoSelectedScope


def mounted_hierarchy_chart_fixture():
    source, chart = mounted_chart_fixture()
    query = dict(chart.layers[0].properties["query"], state_revision=1)
    original = selected = scope = lane = state = operation = frame = None
    try:
        original = source.update(query, sequence=1, style=style())
        scope = GeoSelectedScope.from_frame(original, namespace=777, layer_id=U64)
        state = scope.state(revision=1, ids=np.array([U64], dtype="<u8"), fill=b"\0\xff\0\xff")
        operation = state.begin(source, query, sequence=2)
        operation.drive()
        selected = operation.prepare(style())
        state.close()
        state = None
        lane = GeoHierarchy.from_selected_frame(selected, source, **storage({}))
        state = scope.state(revision=1, ids=np.array([U64], dtype="<u8"), fill=b"\0\xff\0\xff")
        operation = lane.begin_selected(state, query, sequence=3)
        operation.drive()
        frame = operation.prepare(style())
        state.close()
        state = None
        chart = replace(
            chart,
            layers=(
                replace(
                    chart.layers[0],
                    properties={**chart.layers[0].properties, "query": query, "sequence": 3},
                ),
            ),
        )
        return source, scope, lane, frame, chart
    except BaseException:
        if operation is not None:
            operation.close()
        if frame is not None:
            frame.close()
        if state is not None:
            state.close()
            state = None
        if lane is not None:
            lane.close()
        source.close()
        if original is not None:
            original.close()
            original = None
        if selected is not None:
            selected.close()
            selected = None
        if scope is not None:
            scope.close()
        raise
    finally:
        if state is not None:
            state.close()
        if original is not None:
            original.close()
        if selected is not None:
            selected.close()
