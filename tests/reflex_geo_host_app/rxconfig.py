import reflex as rx

import reflex_xy

config = rx.Config(
    app_name="geo_host_app",
    frontend_port=8139,
    backend_port=8139,
    plugins=[rx.plugins.SitemapPlugin(), rx.plugins.RadixThemesPlugin(), reflex_xy.XYPlugin()],
)
