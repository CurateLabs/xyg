"""Required installed wheel → JupyterLab → kernel comm → native → actual paint proof."""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def test_installed_kernel_chunked_viewport(tmp_path):
    chrome = os.environ.get("XYG_TEST_CHROMIUM")
    if not chrome:
        if os.environ.get("XY_REQUIRE_BROWSER") == "1":
            pytest.fail("required installed chunked browser is not configured")
        pytest.skip("requires explicit Chromium")
    from PIL import Image
    from playwright.async_api import async_playwright

    def command(argv, name, **kwargs):
        result = subprocess.run(
            argv,
            cwd=ROOT,
            env={**os.environ, "TMPDIR": os.environ.get("TMPDIR", "/tmp")},
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            **kwargs,
        )
        (tmp_path / name).write_bytes(result.stdout)
        assert result.returncode == 0, result.stdout.decode(errors="replace")[-6000:]
        return result.stdout.decode().strip()

    wheel_env = tmp_path / "installed"
    command(["uv", "venv", "--python", sys.executable, str(wheel_env)], "venv.log")
    # Always build the current checkout, using the ordinary verified prebuilt path.
    build_env = {
        **os.environ,
        "XYG_REQUIRE_CARGO": "1",
        "XYG_SKIP_CARGO": "1",
        "XYG_REQUIRE_WASM": "1",
    }
    build = subprocess.run(
        ["uv", "build", "--wheel", "--out-dir", str(tmp_path / "wheel")],
        cwd=ROOT,
        env=build_env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    (tmp_path / "wheel.log").write_bytes(build.stdout)
    assert build.returncode == 0, build.stdout.decode(errors="replace")
    wheel = next((tmp_path / "wheel").glob("*.whl"))
    python = wheel_env / "bin/python"
    command(
        [
            "uv",
            "pip",
            "install",
            "--python",
            str(python),
            str(wheel),
            "jupyterlab==4.6.5",
            "ipykernel==7.4.0",
        ],
        "install.log",
    )
    site = Path(
        command(
            [str(python), "-I", "-c", "import site;print(site.getsitepackages()[0])"], "site.log"
        )
    )
    native = site / "xyg/_native_lib/libxyg_core.so"
    client = site / "xyg/static/index.js"
    assert native.is_file() and client.is_file()
    assert (
        hashlib.sha256(client.read_bytes()).digest()
        == hashlib.sha256((ROOT / "python/xyg/static/index.js").read_bytes()).digest()
    )
    data = tmp_path / "data"
    kernel = data / "kernels/python3"
    kernel.mkdir(parents=True)
    (kernel / "kernel.json").write_text(
        json.dumps(
            {
                "argv": [str(python), "-m", "ipykernel_launcher", "-f", "{connection_file}"],
                "display_name": "Python 3",
                "language": "python",
            }
        )
    )
    setup = """import asyncio, hashlib, json, pathlib, struct, sys
import xyg
import resource
from IPython.display import display
from xyg import ChunkedColumns, scatter, scatter_chart
from xyg import _native
rows = [(float(i), float((i * 53) % 997) / 997) for i in range(16384)]
path = pathlib.Path('source.xygc')
chunks = [rows[i:i+128] for i in range(0,len(rows),128)]
start = 64 + 48*len(chunks)
header = bytearray(64)
struct.pack_into('<4sIQIIQQI',header,0,b'XYGC',2,len(rows),128,len(chunks),start,start+16*len(rows),2048)
with path.open('wb') as f:
 f.write(header)
 for i,c in enumerate(chunks):
  xs,ys=zip(*c);f.write(struct.pack('<QII4d',i*128,len(c),0,min(xs),max(xs),min(ys),max(ys)))
 for x,y in rows:f.write(struct.pack('<2d',x,y))
 for i in [*range(0,16376,8),16383]:f.write(struct.pack('<Q2d',i,*rows[i]))
source = ChunkedColumns(path)
chart = source.chart(budget_bytes=65536,page_bytes=16384)
chart.width=640;chart.height=400
clicks=[];selections=[]
chart.on_click=clicks.append
chart.on_hover=lambda row: None
chart.on_select=lambda s: selections.append([int(i) for i in s.source_row_ids.get(0,[])])
w=chart.widget()
other_chart=source.chart();other_chart.width=640;other_chart.height=400
other=other_chart.widget()
source.close()
assert w._chunked_binding.handle != other._chunked_binding.handle
received=[]
original_message=w._chunked_binding.message
def record_message(content):
 received.append(dict(content));return original_message(content)
w._chunked_binding.message=record_message
home=json.loads(json.dumps(w.spec))
display_handle=display(w,display_id=True)
display(other)
print('CHUNKED SETUP',json.dumps({'python':sys.executable,'package':xyg.__file__,'native':str(_native._find_library()),'native_sha256':hashlib.sha256(_native._find_library().read_bytes()).hexdigest(),'process_peak_rss_kib':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,'client_sha256':hashlib.sha256(pathlib.Path(xyg.__file__).parent.joinpath('static/index.js').read_bytes()).hexdigest(),'overview_provenance':chart.source_provenance}))
"""
    # JSON metadata uses decimal strings for u64 IDs; report never supplies paint.
    oracle = """await w.when_idle()
ranges=w.view_state()['ranges']
expected=[i for i,(x,y) in enumerate(rows) if ranges['x'][0]<=x<=ranges['x'][1] and ranges['y'][0]<=y<=ranges['y'][1]]
assert list(w.source_row_ids)==expected
accepted=list(w.source_row_ids)
oracle=scatter_chart(scatter([rows[i][0] for i in expected],[rows[i][1] for i in expected],density=False),width=640,height=400)
of=oracle.figure()
for axis in ['x','y']:of.set_axis(axis,domain=home[axis+'_axis']['range'],margin=0)
ow=oracle.widget()
display(ow)
negative=scatter_chart(scatter([rows[int(i)][0] for i in chart.source_row_ids],[rows[int(i)][1] for i in chart.source_row_ids],density=False),width=640,height=400)
display(negative.widget())
print('CHUNKED ORACLE',json.dumps({'actual_spec':w._figure.build_payload_split()[0],'oracle_spec':ow.spec,'ranges':ranges,'ids':expected,'provenance':w.source_provenance,'memory':w._chunked_binding.memory_report(),'other_ids':[int(i) for i in other._figure._chunked_row_ids]}))
"""
    inspect = """await w.when_idle()
print('CHUNKED IDENTITY',json.dumps({'received':received,'clicks':clicks,'selections':selections,'accepted':[int(i) for i in w.source_row_ids]}))
"""
    fail = """last_ids=[int(i) for i in w.source_row_ids]
print('CHUNKED FAILURE READY')
"""
    failure_oracle = """try:
 await w.when_idle()
except RuntimeError:
 pass
assert [int(i) for i in w.source_row_ids]==last_ids
fo=scatter_chart(scatter([rows[i][0] for i in last_ids],[rows[i][1] for i in last_ids],density=False),width=640,height=400)
ff=fo.figure()
for axis in ['x','y']:ff.set_axis(axis,domain=home[axis+'_axis']['range'],margin=0)
display(fo.widget())
print('CHUNKED FAILED',json.dumps({'ids':last_ids,'memory':w._chunked_binding.memory_report()}))
"""
    remount = "display_handle.update(w);print('CHUNKED REMOUNTED')"
    rebound = "print('CHUNKED REBOUND',json.dumps({'clicks':clicks,'mount_epoch':w._chunked_binding.mount_epoch,'ids':[int(i) for i in w.source_row_ids]}))"
    cells = [
        setup,
        oracle,
        inspect,
        fail,
        failure_oracle,
        remount,
        rebound,
        "w.close();other.close();ow.close();print('CHUNKED CLOSED',w._chunked_binding.handle)",
    ]
    notebook = {
        "cells": [
            {
                "cell_type": "code",
                "execution_count": None,
                "metadata": {},
                "outputs": [],
                "source": s.splitlines(keepends=True),
            }
            for s in cells
        ],
        "metadata": {
            "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"}
        },
        "nbformat": 4,
        "nbformat_minor": 5,
    }
    (tmp_path / "chunked.ipynb").write_text(json.dumps(notebook))

    async def run():
        import socket

        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        env = {
            **os.environ,
            "PYTHONPATH": str(site),
            "PYTHONNOUSERSITE": "1",
            "XYG_NATIVE_LIB": str(native),
            "JUPYTER_DATA_DIR": str(data),
            "JUPYTER_RUNTIME_DIR": str(tmp_path / "runtime"),
            "JUPYTER_CONFIG_DIR": str(tmp_path / "config"),
        }
        with (tmp_path / "server.log").open("wb") as log:
            server = await asyncio.create_subprocess_exec(
                str(wheel_env / "bin/jupyter-lab"),
                "--no-browser",
                "--ServerApp.ip=127.0.0.1",
                f"--ServerApp.port={port}",
                f"--ServerApp.root_dir={tmp_path}",
                "--IdentityProvider.token=",
                "--ServerApp.password=",
                cwd=tmp_path,
                env=env,
                stdout=log,
                stderr=log,
            )
            try:
                async with async_playwright() as pw:
                    browser = await pw.chromium.launch(
                        executable_path=chrome,
                        args=[
                            "--no-sandbox",
                            "--use-gl=angle",
                            "--use-angle=swiftshader",
                            "--enable-unsafe-swiftshader",
                        ],
                    )
                    page = await browser.new_page(viewport={"width": 1200, "height": 900})
                    origin = f"http://127.0.0.1:{port}"
                    for _ in range(100):
                        try:
                            response = await page.request.get(origin + "/api/status")
                            if response.ok:
                                break
                        except Exception:
                            pass
                        await asyncio.sleep(0.1)
                    errors = []
                    external = []
                    page.on("pageerror", lambda e: errors.append(str(e)))

                    async def route(r):
                        if r.request.url.startswith(origin) or not r.request.url.startswith(
                            ("http:", "https:")
                        ):
                            await r.continue_()
                        else:
                            external.append(r.request.url)
                            await r.abort()

                    await page.route("**/*", route)
                    await page.add_init_script("""window.chunkedFrames=[];window.chunkedErrors=[];window.exactRows=[];window.selected=[];
 document.addEventListener('xy:chunked_frame',e=>window.chunkedFrames.push(e.detail));
 document.addEventListener('xy:chunked_error',e=>window.chunkedErrors.push(e.detail));
 document.addEventListener('xy:hover',e=>{if(e.detail.exact){const r=e.target.getBoundingClientRect();window.exactRows.push({row:e.detail.row,client:e.detail.cursor?[r.left+e.detail.cursor.px[0],r.top+e.detail.cursor.px[1]]:null})}});
 document.addEventListener('xy:select',e=>window.selected.push({total:e.detail.total,ids:(e.detail.source_row_ids||[]).flatMap(s=>Array.from(s.ids,String))}));""")
                    await page.goto(origin + "/lab/tree/chunked.ipynb")
                    await page.locator(".jp-Notebook .jp-Cell").first.wait_for(timeout=45000)
                    select = page.get_by_role("button", name="Select", exact=True)
                    if await select.count():
                        await select.click()
                    await page.wait_for_function(
                        "document.querySelector('.jp-Notebook .cm-content')&&document.body.innerText.includes('Idle')",
                        timeout=45000,
                    )

                    async def cell(index, prefix):
                        editor = (
                            page.locator(".jp-Notebook .jp-Cell").nth(index).locator(".cm-content")
                        )
                        await editor.click()
                        await page.keyboard.press("Shift+Enter")
                        text = page.locator(".jp-OutputArea").get_by_text(prefix, exact=False).last
                        await text.wait_for(timeout=45000)
                        raw = await text.inner_text()
                        return (
                            json.loads(raw.split(prefix, 1)[1].strip())
                            if prefix
                            not in ["CHUNKED FAILURE READY", "CHUNKED CLOSED", "CHUNKED REMOUNTED"]
                            else raw
                        )

                    setup_receipt = await cell(0, "CHUNKED SETUP")
                    assert str(site) in setup_receipt["package"]
                    assert (
                        setup_receipt["native_sha256"]
                        == hashlib.sha256(native.read_bytes()).hexdigest()
                    )
                    assert setup_receipt["overview_provenance"]["detail_rows_read"] == 0
                    canvases = page.locator(".jp-OutputArea canvas[data-xy-slot=canvas]")
                    canvas = canvases.nth(0)
                    await canvas.scroll_into_view_if_needed()
                    box = await canvas.bounding_box()
                    await page.mouse.move(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
                    await page.mouse.wheel(0, -1200)
                    await page.wait_for_function("window.chunkedFrames.length>0", timeout=20000)
                    data_receipt = await cell(1, "CHUNKED ORACLE")
                    await canvases.nth(2).evaluate(
                        '(c,ranges)=>c.closest(".xy").xy.applyState({ranges},{animate:false,history:false})',
                        data_receipt["ranges"],
                    )
                    (tmp_path / "camera-debug.json").write_text(
                        json.dumps(
                            {
                                "actual": await canvas.evaluate('(c)=>c.closest(".xy").xy.state()'),
                                "oracle": await canvases.nth(2).evaluate(
                                    '(c)=>c.closest(".xy").xy.state()'
                                ),
                                "receipt": data_receipt,
                            },
                            indent=2,
                        )
                    )
                    await page.mouse.move(1, 1)
                    await canvas.scroll_into_view_if_needed()
                    await canvas.screenshot(path=str(tmp_path / "refined.png"))
                    await canvases.nth(2).scroll_into_view_if_needed()
                    await canvases.nth(2).screenshot(path=str(tmp_path / "oracle.png"))
                    import base64

                    async def paint(surface, name):
                        await page.evaluate(
                            "new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r)))"
                        )
                        png = await surface.evaluate("c=>c.toDataURL('image/png').split(',')[1]")
                        (tmp_path / name).write_bytes(base64.b64decode(png))

                    await paint(canvas, "refined-paint.png")
                    await paint(canvases.nth(2), "oracle-paint.png")
                    a, b = [
                        Image.open(tmp_path / n).convert("RGBA")
                        for n in ["refined-paint.png", "oracle-paint.png"]
                    ]
                    assert a.size == b.size and a.tobytes() == b.tobytes(), (
                        "independent full-scan pixel oracle mismatch"
                    )
                    # Old overview is a negative pixel control under the same camera.
                    await canvases.nth(3).evaluate(
                        '(c,ranges)=>c.closest(".xy").xy.applyState({ranges},{animate:false,history:false})',
                        data_receipt["ranges"],
                    )
                    await canvases.nth(3).screenshot(path=str(tmp_path / "overview-control.png"))
                    await paint(canvases.nth(3), "overview-control-paint.png")
                    control = Image.open(tmp_path / "overview-control-paint.png").convert("RGBA")
                    assert a.tobytes() != control.tobytes()
                    await canvas.scroll_into_view_if_needed()
                    await page.evaluate("window.exactRows=[]")
                    await canvas.focus()
                    await page.keyboard.press("Home")
                    for _ in range(20):
                        await page.keyboard.press("ArrowRight")
                    await page.wait_for_function(
                        "window.exactRows.some(h=>h.row.index===20)", timeout=5000
                    )
                    hit = await page.evaluate("window.exactRows.at(-1)")
                    assert hit["client"]
                    await page.mouse.click(*hit["client"])
                    # A trusted pointer box selection uses the real modebar and accepted frame.
                    root = canvas.locator("xpath=..")
                    await root.locator("[data-xy-modebar-select-trigger]").click()
                    await root.locator("[data-xy-modebar-select-item=select]").click()
                    box = await canvas.bounding_box()
                    await page.mouse.move(
                        box["x"] + box["width"] * 0.2, box["y"] + box["height"] * 0.2
                    )
                    await page.mouse.down()
                    await page.mouse.move(
                        box["x"] + box["width"] * 0.8, box["y"] + box["height"] * 0.8, steps=8
                    )
                    await page.mouse.up()
                    await page.wait_for_function(
                        "window.selected.some(s=>s.total>0&&s.ids.length===s.total)", timeout=5000
                    )
                    identity = await cell(2, "CHUNKED IDENTITY")
                    (tmp_path / "pointer-debug.json").write_text(
                        json.dumps({"identity": identity, "hit": hit}, indent=2)
                    )
                    assert identity["clicks"] and identity["selections"]
                    assert int(identity["clicks"][-1]["source_row_id"]) in identity["accepted"]
                    selection_state = await canvas.evaluate(
                        '(c)=>c.closest(".xy").xy.state().selection.range'
                    )
                    selected_oracle = [
                        i
                        for i in data_receipt["ids"]
                        if selection_state["x0"] <= i <= selection_state["x1"]
                        and selection_state["y0"] <= ((i * 53) % 997) / 997 <= selection_state["y1"]
                    ]
                    assert identity["selections"][-1] == selected_oracle
                    await cell(3, "CHUNKED FAILURE READY")
                    await canvas.scroll_into_view_if_needed()
                    await canvas.evaluate(
                        '(c)=>c.closest(".xy").xy.applyState({ranges:{x:[0,16383],y:[0,1]},selection:null},{animate:false,history:false})'
                    )
                    await page.wait_for_function("window.chunkedErrors.length>0", timeout=20000)
                    await cell(4, "CHUNKED FAILED")
                    await canvases.nth(4).evaluate(
                        '(c)=>c.closest(".xy").xy.applyState({ranges:{x:[0,16383],y:[0,1]}},{animate:false,history:false})'
                    )
                    await page.mouse.move(1, 1)
                    await canvas.scroll_into_view_if_needed()
                    await canvas.screenshot(path=str(tmp_path / "failure-retained.png"))
                    await canvases.nth(4).scroll_into_view_if_needed()
                    await canvases.nth(4).screenshot(path=str(tmp_path / "failure-oracle.png"))
                    await paint(canvas, "failure-retained-paint.png")
                    await paint(canvases.nth(4), "failure-oracle-paint.png")
                    a, b = [
                        Image.open(tmp_path / n).convert("RGBA")
                        for n in ["failure-retained-paint.png", "failure-oracle-paint.png"]
                    ]
                    assert a.size == b.size and a.tobytes() == b.tobytes()
                    before_remount = await canvas.evaluate('(c)=>c.closest(".xy").xy.state()')
                    await cell(5, "CHUNKED REMOUNTED")
                    await canvas.wait_for()
                    await page.wait_for_function(
                        "document.querySelectorAll('.jp-OutputArea canvas[data-xy-slot=canvas]').length===5"
                    )
                    assert (
                        await canvas.evaluate('(c)=>c.closest(".xy").xy.state().ranges')
                        == before_remount["ranges"]
                    )
                    await paint(canvas, "remounted-paint.png")
                    assert (
                        Image.open(tmp_path / "remounted-paint.png").convert("RGBA").tobytes()
                        == a.tobytes()
                    )
                    await page.evaluate("window.exactRows=[]")
                    await canvas.focus()
                    await page.keyboard.press("Home")
                    await page.wait_for_function("window.exactRows.length>0", timeout=5000)
                    await page.keyboard.press("Enter")
                    rebound_receipt = await cell(6, "CHUNKED REBOUND")
                    assert len(rebound_receipt["clicks"]) > len(identity["clicks"])
                    assert rebound_receipt["mount_epoch"] > 1
                    assert (
                        int(rebound_receipt["clicks"][-1]["source_row_id"])
                        in rebound_receipt["ids"]
                    )
                    await cell(7, "CHUNKED CLOSED")
                    assert not errors, errors
                    assert not external, external
                    report = {
                        "setup": setup_receipt,
                        "data": data_receipt,
                        "identity": identity,
                        "rebound": rebound_receipt,
                        "remount_picture_exact": True,
                        "frames": await page.evaluate("window.chunkedFrames"),
                        "failures": await page.evaluate("window.chunkedErrors"),
                        "pixel_oracle_exact": True,
                        "failure_oracle_exact": True,
                        "old_overview_control_differs": True,
                        "external": external,
                        "errors": errors,
                        "wheel_sha256": hashlib.sha256(wheel.read_bytes()).hexdigest(),
                        "browser": browser.version,
                    }
                    (tmp_path / "report.json").write_text(json.dumps(report, indent=2))
                    await browser.close()
            finally:
                server.terminate()
                await server.wait()

    asyncio.run(run())
