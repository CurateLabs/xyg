# Python / Streamlit consumer

After building XYG's native core and client and installing the locked dev group:

```bash
uv run streamlit run examples/streamlit/app.py
uv run pytest tests/test_streamlit_consumer.py -q
```

This example uses only public XYG composition/export APIs and stock Streamlit
HTML embedding. Streamlit is a test/example dependency, never a dependency or
adapter shipped by XYG. Re-runs rebuild deterministic charts. Pan, zoom, hover,
and selection are local to the iframe; selection does not return to Python and
re-runs are full replacements, not incremental streaming. SVG/PNG downloads use
the shared Rust exporters. Hosted Worker/WASM tick URLs are covered separately
by the hosted HTML smoke; this offline iframe does not advertise a live host.

Run both real consumer apps in Chromium with:

```bash
uv run python scripts/consumer_apps_smoke.py --chromium /path/to/chrome
```

The browser gate builds a wheel, verifies its inventory, installs it and the
locked Streamlit test dependencies into a clean environment, and verifies native
loading from that environment. Its PATH contains Python only. This tests actual
installed consumption rather than an editable import from the checkout.
