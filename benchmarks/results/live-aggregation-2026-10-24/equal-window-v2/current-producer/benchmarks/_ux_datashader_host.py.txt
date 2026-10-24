#!/usr/bin/env python3
"""Datashader host for the UX benchmark: hvPlot/HoloViews on a Bokeh server.

This is datashader's *interactive* deployment — the bare `Canvas.points`
raster has no pan/zoom and is not what the benchmark measures. Every view
change re-aggregates server-side; below `resample_when` visible rows the plot
switches to raw Bokeh points, which is how this arm meets the "zoom reaches
every point" bar.

Prints META {"port", "n", "sentinels", "build_ms", "mode"} then serves.
"""

from __future__ import annotations

import argparse
import json
import time

from _ux_comparison_data import SENTINELS, make_data, source_identity

WIDTH = 900
HEIGHT = 420
# Match xy's direct-draw budget so the raw-points switch happens at a
# comparable depth to xy's drill-in (§5 / config.SCATTER_DENSITY_THRESHOLD).
RESAMPLE_WHEN = 200_000


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--n", type=int, required=True)
    parser.add_argument("--aggregate-only", action="store_true")
    from _ux_comparison_host import (
        add_arguments,
        inventory,
        load_source,
        metrics_handler,
        observe_datashader,
    )

    add_arguments(parser)
    args = parser.parse_args()

    import holoviews as hv
    import hvplot.pandas  # noqa: F401 — registers the .hvplot accessor
    import pandas as pd
    import panel as pn

    state = {}
    if args.comparison_source:
        x, y, source = load_source(args.comparison_source, args.n)
    else:
        x, y = make_data(args.n)
        source = source_identity(x, y)
    frame = pd.DataFrame({"x": x, "y": y}, copy=False if args.comparison_source else None)
    if args.comparison_source:
        state["canonical_admission"] = inventory((x, y), (frame.x.to_numpy(), frame.y.to_numpy()))
        observe_datashader(source, x, y, state)

    t0 = time.perf_counter()
    options = {} if args.aggregate_only else {"resample_when": RESAMPLE_WHEN}
    plot = frame.hvplot.scatter(
        x="x",
        y="y",
        datashade=True,
        **options,
        **(
            {
                "frame_width": 512,
                "frame_height": 512,
                "xlim": tuple(source["extents"][:2]),
                "ylim": tuple(source["extents"][2:]),
                "xaxis": None,
                "yaxis": None,
                "toolbar": None,
            }
            if args.comparison_source
            else {"width": WIDTH, "height": HEIGHT}
        ),
    ).opts(active_tools=["wheel_zoom"])
    app = pn.panel(plot)
    build_ms = (time.perf_counter() - t0) * 1e3

    # holoviews 1.23 quirk (measured): with `resample_when` neither branch
    # evaluates until a range event fires, so the served page is blank until
    # the first interaction.  Wake the streams from a daemon thread after the
    # session connects — the practical workaround a real deployment needs;
    # its cost lands inside visible-complete, where it belongs.
    dmaps = plot.traverse(lambda o: o, [hv.DynamicMap])
    xr = (float(x.min()), float(x.max()))
    yr = (float(y.min()), float(y.max()))

    def _kick_loop() -> None:
        import time as _time

        for _ in range(10):
            _time.sleep(1.0)
            for dm in dmaps:
                for s in dm.streams:
                    try:
                        if isinstance(s, hv.streams.RangeXY):
                            s.event(x_range=xr, y_range=yr)
                        elif isinstance(s, hv.streams.PlotSize):
                            s.event(width=WIDTH, height=HEIGHT)
                        else:
                            s.event()
                    except Exception:  # noqa: BLE001 — best-effort, per stream
                        pass

    import threading

    if not args.aggregate_only:
        threading.Thread(target=_kick_loop, daemon=True).start()

    # Port 0 makes Bokeh bind an ephemeral port atomically and retain the
    # socket; ``server.port`` is the actual bound port. Bokeh defaults to the
    # exact localhost:<bound port> origin; navigate there (no wildcard port).
    server = pn.serve(
        app,
        port=0,
        address="127.0.0.1",
        show=False,
        start=False,
        threaded=False,
        verbose=False,
        **(
            {"extra_patterns": [(r"/comparison_metrics", metrics_handler(state))]}
            if args.comparison_source
            else {}
        ),
    )
    port = server.port
    if port is None:
        raise RuntimeError("Bokeh did not report its bound TCP port")
    server.start()
    print(
        "META "
        + json.dumps(
            {
                "port": port,
                "hostname": "localhost",
                "n": args.n,
                "source": source,
                "components": ["hvPlot", "HoloViews", "Datashader", "Bokeh", "Panel"],
                "sentinels": [list(s) for s in SENTINELS],
                "build_ms": build_ms,
                "mode": "density" if args.aggregate_only else "datashade+resample",
            }
        ),
        flush=True,
    )
    server.io_loop.start()


if __name__ == "__main__":
    main()
