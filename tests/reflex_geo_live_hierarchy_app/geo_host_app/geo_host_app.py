"""Actual framework fixture; source data stays in the native backend."""

import reflex as rx

import reflex_xy
from geo_live_hierarchy_fixture import live_hierarchy_chart_fixture

source, scope, lane, frame, authored = live_hierarchy_chart_fixture()
facade = authored.host(frame=frame, selected_scope=scope, hierarchy_lane=lane)
frame.close()
TOKEN = reflex_xy.inline(facade)


def index():
    return rx.box(reflex_xy.chart(TOKEN, id="geo-native-host", height="600px"), width="800px")


app = rx.App()
app.add_page(index)
reflex_xy.setup(app)
