"""Isolated installed-wheel application for the packaged tick journey."""

import os

import reflex as rx

import reflex_xy

port = int(os.environ.get("XYG_REFLEX_PORT", "8179"))
config = rx.Config(
    app_name="packaged_ticks_app",
    frontend_port=port,
    backend_port=port,
    telemetry_enabled=False,
    plugins=[rx.plugins.SitemapPlugin(), rx.plugins.RadixThemesPlugin(), reflex_xy.XYPlugin()],
)
