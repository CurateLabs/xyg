"""Actual framework fixture; source data stays in the native backend."""

import reflex as rx

import reflex_xy
from geo_live_fixture import live_chart_fixture

source, authored = live_chart_fixture()
facade = authored.host()
TOKEN = reflex_xy.inline(facade)


def index():
    return rx.box(reflex_xy.chart(TOKEN, id="geo-native-host", height="600px"), width="800px")


app = rx.App()
app.add_page(index)
reflex_xy.setup(app)
