"""Production native overview host fixture; data stays in the backend."""

import reflex as rx

import reflex_xy
from test_geo_native_overview_host import fixture

source, seed, overview_index, authored = fixture()
facade = authored.host()
TOKEN = reflex_xy.inline(facade)


def index():
    return rx.box(
        reflex_xy.chart(TOKEN, id="geo-native-overview-host", height="600px"), width="800px"
    )


app = rx.App()
app.add_page(index)
reflex_xy.setup(app)
