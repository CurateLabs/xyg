"""Bounded native widget refinement and failure/lifetime regression proof."""

from __future__ import annotations

import asyncio

import pytest

from test_chunked_columns import _artifact_with_overview
from xyg import ChunkedColumns


def test_widget_refines_isolated_and_drains(tmp_path):
    async def run():
        path = tmp_path / "source.xygc"
        _artifact_with_overview(path, [(float(i), float(i % 5)) for i in range(64)])
        with ChunkedColumns(path) as source:
            chart = source.chart(max_points=2, budget_bytes=512, page_bytes=512)
            widget = chart.widget()
            other = source.chart(max_points=2).widget()
        messages = []
        widget.send = lambda msg, buffers=None: messages.append((msg, buffers))
        binding = widget._chunked_binding
        binding.message(dict(type="chunked_mount", mount="A", mount_epoch="1"))

        def navigate(intent, lo, hi):
            widget._on_custom_msg(
                widget,
                dict(
                    type="view_change",
                    mount="A",
                    chunked_intent=str(intent),
                    ranges={"x": [lo, hi], "y": [-1, 6]},
                ),
                [],
            )

        navigate(1, 10, 20)
        navigate(2, 30, 40)
        for _ in range(100):
            await asyncio.sleep(0.01)
            if messages:
                break
        assert messages and messages[-1][0]["type"] == "chunked_frame"
        message = messages[-1][0]
        assert message["intent"] == "2"
        assert widget._figure is chart.figure()  # no invented paint ACK
        binding.message(
            dict(
                type="chunked_painted",
                mount="A",
                intent="2",
                frame=message["spec"]["chunked"]["frame"],
            )
        )
        await widget.when_idle()
        assert list(widget.source_row_ids) == list(range(30, 41))
        assert widget._figure.pick(0, 0)["source_row_id"] == "30"
        assert list(other._figure._chunked_row_ids) == [0, 63]
        assert widget._figure.select_range(30, 40, -1, 6)[0].size == 11
        from xyg import Selection

        selection = Selection(widget._figure, widget._figure.select_range(30, 40, -1, 6))
        assert list(selection.source_row_ids[0]) == list(range(30, 41))
        old = widget._figure
        messages.clear()
        # Cached revisit still succeeds, retaining the same per-widget handle.
        navigate(3, 30, 40)
        for _ in range(100):
            await asyncio.sleep(0.01)
            if messages:
                break
        assert messages[-1][0]["type"] == "chunked_frame"
        assert binding.staged[4]["bytes_read"] == 0
        revisit = messages[-1][0]
        binding.message(
            dict(
                type="chunked_rejected",
                mount="A",
                intent="3",
                frame=revisit["spec"]["chunked"]["frame"],
            )
        )
        assert widget._figure is old
        messages.clear()
        navigate(4, 0, 63)
        for _ in range(100):
            await asyncio.sleep(0.01)
            if messages:
                break
        assert messages[-1][0]["type"] == "chunked_error"
        assert widget._figure is old
        with path.open("r+b") as damaged:
            damaged.truncate(64 + 48 * 16)
        messages.clear()
        navigate(5, 0, 5)
        for _ in range(100):
            await asyncio.sleep(0.01)
            if messages:
                break
        assert messages[-1][0]["type"] == "chunked_error"
        assert widget._figure is old
        navigate(6, 0, 5)
        widget.close()
        other.close()
        assert binding.handle == 0
        assert not binding.thread.is_alive()

    asyncio.run(run())


@pytest.mark.parametrize("host", ["python", "node"])
def test_public_widget_browser_gesture(tmp_path, host):
    """The public widget's comm requests must causally replace the overview."""
    import base64
    import os
    from pathlib import Path

    import pytest

    chromium = os.environ.get("XYG_TEST_CHROMIUM")
    if not chromium:
        if os.environ.get("XY_REQUIRE_BROWSER") == "1":
            pytest.fail("required chunked live browser is not configured")
        pytest.skip("explicit browser required")
    from playwright.async_api import async_playwright

    async def run():
        path = tmp_path / "browser.xygc"
        _artifact_with_overview(
            path,
            [(float(i), float(i % 5)) for i in range(8192)],
            chunk_rows=128,
            overview_indices=[*range(0, 8188, 4), 8191],
        )
        with ChunkedColumns(path) as source:
            chart = source.chart(budget_bytes=1 << 20, page_bytes=1 << 20)
            widget = chart.widget()
        process = None
        if host == "node":
            import json
            from types import SimpleNamespace

            widget.close()
            process = await asyncio.create_subprocess_exec(
                os.environ.get("XYG_NODE", "node"),
                "packages/xy-node/test/chunked-live-bridge.mjs",
                str(path),
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
            )
            initial = json.loads(await process.stdout.readline())

            def request(_widget, msg, _buffers):
                process.stdin.write((json.dumps(msg) + "\n").encode())

            widget = SimpleNamespace(
                spec=initial["spec"],
                buffers=[base64.b64decode(b) for b in initial["buffers"]],
                _on_custom_msg=request,
            )
        try:
            async with async_playwright() as playwright:
                browser = await playwright.chromium.launch(
                    executable_path=chromium,
                    args=[
                        "--no-sandbox",
                        "--use-gl=angle",
                        "--use-angle=swiftshader",
                        "--enable-unsafe-swiftshader",
                    ],
                )
                page = await browser.new_page(viewport={"width": 1000, "height": 600})
                errors = []
                page.on("pageerror", lambda error: errors.append(str(error)))
                await page.route(
                    "https://xyg.test/**",
                    lambda route: route.fulfill(
                        body=Path("python/xyg/static/index.js").read_text(),
                        content_type="text/javascript",
                    ),
                )
                disabled = True

                def forward(msg):
                    if disabled and msg.get("type") == "view_change":
                        return None
                    return widget._on_custom_msg(widget, msg, [])

                await page.expose_function("hostSend", forward)
                widget.picked_rows = []
                if process is None:
                    from dataclasses import replace

                    widget._callbacks = replace(
                        widget._callbacks, on_hover=widget.picked_rows.append
                    )
                deliveries = []

                def send(msg, buffers=None):
                    deliveries.append(
                        asyncio.create_task(
                            page.evaluate(
                                "([msg,bufs])=>window.deliver(msg,bufs.map(b=>new DataView(Uint8Array.from(atob(b),c=>c.charCodeAt(0)).buffer)))",
                                [msg, [base64.b64encode(b).decode() for b in buffers or []]],
                            )
                        )
                    )

                widget.send = send
                reader = None
                if process is not None:

                    async def read_node():
                        import json

                        while line := await process.stdout.readline():
                            record = json.loads(line)
                            if record["kind"] == "message":
                                send(
                                    record["msg"], [base64.b64decode(b) for b in record["buffers"]]
                                )
                            elif record["kind"] == "pick":
                                widget.picked_rows.append(record["row"])
                            else:
                                widget.source_row_ids = record["ids"]
                                widget.source_provenance = record["provenance"]

                    reader = asyncio.create_task(read_node())
                spec = widget.spec
                buffers = [base64.b64encode(b).decode() for b in widget.buffers]
                await page.set_content('<div id="chart"></div>')
                await page.evaluate(
                    """async ([spec,bufs])=>{
                  const {render}=await import('https://xyg.test/client.js');
                  const listeners=new Map();window.requests=[];
                  window.deliver=(msg,buffers)=>{for(const cb of listeners.get('msg:custom')||[])cb(msg,buffers);};
                  window.cleanup=render({el:document.querySelector('#chart'),model:{
                    get:k=>k==='spec'?spec:bufs.map(b=>new DataView(Uint8Array.from(atob(b),c=>c.charCodeAt(0)).buffer)),
                    on:(k,cb)=>{if(!listeners.has(k))listeners.set(k,new Set());listeners.get(k).add(cb)},
                    off:(k,cb)=>listeners.get(k)?.delete(cb),send:msg=>{window.requests.push(msg);return window.hostSend(msg)}
                  }});
                  window.views=[];document.querySelector('#chart').addEventListener('xy:view_change',e=>window.views.push(e.detail));
                  window.exactRows=[];document.querySelector('#chart').addEventListener('xy:hover',e=>{if(e.detail.exact)window.exactRows.push(e.detail.row)});
                  window.frames=[];document.querySelector('#chart').addEventListener('xy:chunked_frame',e=>window.frames.push(e.detail));
                }""",
                    [spec, buffers],
                )
                await page.mouse.move(450, 200)
                await page.mouse.wheel(0, -200)
                await page.wait_for_function("window.views.length>0")
                await page.evaluate(
                    "new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r)))"
                )
                assert await page.evaluate("window.frames.length") == 0
                if process is None:
                    assert list(widget.source_row_ids) == list(
                        widget._chunked_binding.initial_figure._chunked_row_ids
                    )
                else:
                    assert not hasattr(widget, "source_row_ids")
                await page.screenshot(path=str(tmp_path / "disabled.png"))
                disabled = False
                await page.mouse.wheel(0, -250)
                await page.wait_for_function("window.frames.length>0")
                assert not errors, errors
                for _ in range(100):
                    if hasattr(widget, "source_row_ids"):
                        break
                    await asyncio.sleep(0.01)
                frames, views = await page.evaluate("[window.frames,window.views]")
                ranges = frames[-1]["view"]["ranges"]
                assert ranges == views[-1]["ranges"]
                expected = [
                    i
                    for i in range(8192)
                    if ranges["x"][0] <= i <= ranges["x"][1]
                    and ranges["y"][0] <= i % 5 <= ranges["y"][1]
                ]
                assert [int(i) for i in widget.source_row_ids] == expected
                assert len(widget.source_row_ids) > 2048
                assert int(widget.source_provenance["chunks_considered"]) > 0
                first_provenance = dict(widget.source_provenance)
                await page.locator("#chart canvas[data-xy-slot=canvas]").press("ArrowRight")
                for _ in range(100):
                    if widget.picked_rows:
                        break
                    await asyncio.sleep(0.01)
                assert widget.picked_rows
                row = widget.picked_rows[-1]
                assert int(row["source_row_id"]) in expected
                assert row["x"] == float(row["source_row_id"])
                await page.screenshot(path=str(tmp_path / "refined.png"))
                import json

                (tmp_path / "report.json").write_text(
                    json.dumps(
                        {
                            "host": host,
                            "source_rows": 8192,
                            "overview_points": 2048,
                            "ranges": ranges,
                            "source_row_ids": [int(i) for i in widget.source_row_ids],
                            "full_scan_oracle": expected,
                            "pick_callback": row,
                            "provenance": first_provenance,
                            "last_provenance": widget.source_provenance,
                            "browser": browser.version,
                            "negative_control_frames": 0,
                            "errors": errors,
                        },
                        indent=2,
                    )
                )
                frame_count = await page.evaluate("window.frames.length")
                await page.mouse.wheel(0, -60)
                await page.wait_for_function("n=>window.frames.length>n", arg=frame_count)
                await page.evaluate(
                    "new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r)))"
                )
                assert not errors, errors
                await page.evaluate("window.cleanup()")
                await asyncio.gather(*deliveries)
                if process is not None:
                    process.stdin.write(b'{"type":"close"}\n')
                    await process.stdin.drain()
                    assert await process.wait() == 0
                    await reader
                else:
                    widget.close()
                await browser.close()
        finally:
            if process is not None and process.returncode is None:
                process.terminate()
                await process.wait()
            elif process is None:
                widget.close()

    asyncio.run(run())


def test_reentrant_transport_close_drains_worker(tmp_path):
    async def run():
        path = tmp_path / "reentrant.xygc"
        _artifact_with_overview(path, [(float(i), float(i)) for i in range(16)])
        with ChunkedColumns(path) as source:
            widget = source.chart(max_points=2).widget()
        binding = widget._chunked_binding
        binding.message(dict(type="chunked_mount", mount="A", mount_epoch="1"))
        widget.send = lambda *args, **kwargs: widget.close()
        binding.message(
            dict(
                type="view_change", mount="A", chunked_intent="1", ranges={"x": [2, 8], "y": [2, 8]}
            )
        )
        for _ in range(100):
            await asyncio.sleep(0.01)
            if binding.closed:
                break
        assert binding.closed and binding.handle == 0
        assert not binding.thread.is_alive()

    asyncio.run(run())
