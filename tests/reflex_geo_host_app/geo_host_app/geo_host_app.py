"""Actual framework fixture; source data stays in the native backend."""

import reflex as rx

import reflex_xy
from test_geo_host import chart_fixture

source, authored = chart_fixture()
TOKEN = reflex_xy.inline(authored)


def index():
    return rx.box(reflex_xy.chart(TOKEN, id="geo-native-host", height="600px"), width="800px")


app = rx.App()
app.add_page(index)
reflex_xy.setup(app)
