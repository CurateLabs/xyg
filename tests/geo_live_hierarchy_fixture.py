"""Bounded authored selected lane fixture for actual application journeys."""

from test_geo_live_hierarchy_host import fixture


def live_hierarchy_chart_fixture():
    source, scope, lane, frame, chart, old_adapter = fixture()
    old_adapter.close()
    # A later public chart.host/widget creates its own independent anchor.
    return source, scope, lane, frame, chart
