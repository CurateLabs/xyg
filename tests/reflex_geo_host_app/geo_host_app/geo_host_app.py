"""Actual framework fixture; source data stays in the native backend."""

import reflex as rx

import reflex_xy
from test_geo_indexed_host import indexed_chart_fixture

index_source, authored, caller_frame = indexed_chart_fixture()
facade = authored.host(frame=caller_frame)
caller_frame.close()
TOKEN = reflex_xy.inline(facade)


def index():
    return rx.box(reflex_xy.chart(TOKEN, id="geo-native-host", height="600px"), width="800px")


app = rx.App()
app.add_page(index)
reflex_xy.setup(app)
