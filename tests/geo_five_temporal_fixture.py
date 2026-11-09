"""Five issued selected histories with one canonical Source and one Scope."""

from dataclasses import replace

import numpy as np

from geo_mounted_hierarchy_temporal_fixture import mounted_hierarchy_chart_fixture
from test_geo_retained import style
from test_geoscale import U64


def five_hierarchy_widgets():
    source, scope, original, frame, chart = mounted_hierarchy_chart_fixture()
    lanes, widgets, frames = [original], [], [frame]
    try:
        for index in range(5):
            current = chart
            if index:
                lane = original.fork()
                lanes.append(lane)
                state = scope.state(
                    revision=1, ids=np.array([U64], dtype="<u8"), fill=b"\0\xff\0\xff"
                )
                try:
                    operation = lane.begin_selected(
                        state, chart.layers[0].properties["query"], sequence=4
                    )
                    operation.drive()
                    frames.append(operation.prepare(style()))
                finally:
                    state.close()
                current = replace(
                    chart,
                    layers=(
                        replace(
                            chart.layers[0],
                            properties={**chart.layers[0].properties, "sequence": 4},
                        ),
                    ),
                )
            widget = current.widget(
                frame=frames[index], selected_scope=scope, hierarchy_lane=lanes[index]
            )
            widgets.append(widget)
            frames[index].close()  # adapter confirmed an independent immutable lease
        source.close()  # hierarchy retains canonical/index storage, never copies it
        return source, scope, lanes, widgets, chart
    except BaseException:
        for widget in widgets:
            widget.close()
        for frame in frames:
            frame.close()
        source.close()
        for lane in lanes:
            lane.close()
        scope.close()
        raise
