"""Small public authoring fixture for actual live geographic host journeys."""

import xyg
from test_geo_retained import fixture_manifest, style
from test_geoscale import BUDGET, U64, query
from xyg._geo_retained import RetainedGeoSource


def live_chart_fixture():
    manifest, chunk = fixture_manifest()
    source = RetainedGeoSource(manifest, lambda _: chunk, budget=BUDGET)
    q = query(source.info)
    for key in ("camera_revision", "time_revision", "state_revision"):
        q[key] = 1
    chart = xyg.geo_chart(
        xyg.geo_layer("points", source=source, layer_id=U64, query=q, sequence=1, style=style()),
        camera=q["camera"],
    )
    return source, chart
