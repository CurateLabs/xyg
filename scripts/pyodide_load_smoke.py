#!/usr/bin/env python3
"""Load the built Pyodide wheel in a real Pyodide runtime (node) and call a
native kernel through the ctypes seam.

"Builds" is not "loads": Pyodide's dynamic linker must instantiate the module
and the `xyg_*` C-ABI symbols must be callable. This is the regression probe for
the release wheel's exception-free Rust build: it installs the exact artifact,
checks the ABI version, calls a native kernel, and exits non-zero on failure.

Usage: python scripts/pyodide_load_smoke.py <wheel-path-or-https-url>
Requires: node with the `pyodide` npm package resolvable from CWD.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

_DRIVER = r"""
import { loadPyodide } from "pyodide";
import fs from "node:fs";
const wheelPath = process.argv[2];
const fixturePath = process.argv[3];
const filterFixturePath = process.argv[4];
const isUrl = wheelPath.startsWith("https://") || wheelPath.startsWith("http://");
const name = isUrl
  ? new URL(wheelPath).pathname.split("/").pop()
  : wheelPath.split("/").pop();
const out = (o) => console.log("RESULT " + JSON.stringify(o));
try {
  const py = await loadPyodide();
  await py.loadPackage(["numpy", "micropip"]);
  const micropip = py.pyimport("micropip");
  if (isUrl) {
    await micropip.install(wheelPath);
  } else {
    py.FS.mkdirTree("/wheels");
    py.FS.writeFile("/wheels/" + name, fs.readFileSync(wheelPath));
    await micropip.install("emfs:/wheels/" + name);
  }
  py.FS.mkdirTree("/fixtures");
  py.FS.writeFile("/fixtures/xyts_cross_host.json", fs.readFileSync(fixturePath));
  py.FS.writeFile("/fixtures/filter_session.bin", fs.readFileSync(filterFixturePath));
  // Dependency provisioning is complete. The conformance operation itself is
  // strictly offline: any accidental host lookup now fails immediately.
  globalThis.fetch = async (url) => { throw new Error(`offline XYTS fixture attempted fetch: ${url}`); };
  const r = await py.runPythonAsync(`
import xyg.kernels as k
import numpy as np
import json
import struct
mn, mx = k.min_max(np.array([3.0, 1.0, 2.0]))
from xyg import _native
abi = _native._lib.xyg_abi_version()
fixture = json.load(open("/fixtures/xyts_cross_host.json", encoding="utf-8"))
for case in fixture["successful"]:
    scene = bytes.fromhex(case["scene_hex"])
    assert scene[:4] == b"XYGS"
    assert len(_native.scene_raster_commands(scene)) > 16
    assert _native.scene_svg(scene).startswith('<svg xmlns="http://www.w3.org/2000/svg"')
    assert _native.scene_browser_painter(scene) == bytes.fromhex(case["painter_hex"])
lib = _native._lib
# The C ABI transport must exist on Emscripten as well as native targets.
# Replay unchanged complete packets, including capacity/error responses.
from xyg.filter_session import decode_reply, execute_packet, request
filter_stream = open("/fixtures/filter_session.bin", "rb").read()
handle = lib.xyg_filter_session_new(1 << 20)
assert handle
at = filter_packets = 0
try:
    while at < len(filter_stream):
        size, capacity, code, output_size, required = struct.unpack_from("<IIiIQ", filter_stream, at)
        at += 24
        packet = filter_stream[at:at + size]
        at += size
        expected = filter_stream[at:at + output_size]
        at += output_size
        try:
            reply = execute_packet(handle, packet, capacity)
        except RuntimeError as error:
            assert code == -4 and f"required capacity {required}" in str(error)
        else:
            assert code == 0 and reply == expected
        filter_packets += 1
    assert at == len(filter_stream) and filter_packets == 47
finally:
    lib.xyg_filter_session_free(handle)

# Exercise actual XYFJ progress/advance/cancel through that same C ABI.
# Filesystem sources remain unavailable; this is an admitted in-memory source.
from xyg import scatter, scatter_chart
def filter_control(operation, token=0, payload=b""):
    return struct.pack("<4sIIIQQ", b"XYFJ", 1, operation, 0, token, 0) + payload

with scatter_chart(scatter(x=[0], y=[0])).filter_session(
    {"a": list(range(70000))}, source_id=113, budget_bytes=8 << 20
) as session:
    handle = session._handle
    configure = request(3, revision=2, source_id=113, budget_bytes=8 << 20,
        args=(1, 0, 1), payload=struct.pack("<QdQQQd", 1, 32768., 2, 0, 1, 32768.))
    reply = execute_packet(handle, filter_control(1, payload=configure))
    filter_progress = 0
    for _ in range(1024):
        if reply[:4] != b"XYFJ":
            break
        assert len(reply) == 32 and struct.unpack_from("<I", reply, 4)[0] == 1
        token, visited, total = struct.unpack_from("<QQQ", reply, 8)
        assert token and visited <= total == 70000
        filter_progress += 1
        reply = execute_packet(handle, filter_control(2, token))
    else:
        raise AssertionError("filter cooperative completion deadline")
    assert filter_progress > 0 and decode_reply(reply)["status"] == 0
    assert decode_reply(execute_packet(handle, filter_control(2, token)))["status"] == 5
    query = request(5, revision=3, source_id=113, budget_bytes=8 << 20, bounds=(0., 32767.))
    before = decode_reply(execute_packet(handle, query))
    assert before["selected_count"] == 32768 and before["views"][0]["counts"] == (32768, 0)
    assert before["rows_read"] == 0 and before["tier"] == 3
    rebuild = request(4, revision=4, source_id=113, budget_bytes=8 << 20)
    pending = execute_packet(handle, filter_control(1, payload=rebuild))
    assert pending[:4] == b"XYFJ" and len(pending) == 32
    pending_token = struct.unpack_from("<Q", pending, 8)[0]
    assert decode_reply(execute_packet(handle, filter_control(3, pending_token)))["status"] == 4
    after = decode_reply(execute_packet(handle,
        request(5, revision=5, source_id=113, budget_bytes=8 << 20, bounds=(0., 32767.))))
    assert after["selected_count"] == before["selected_count"]
    assert after["filter_hash"] == before["filter_hash"] and after["rows_read"] == 0
filter_cooperative = True
# ABI 396: all five additions must operate on the actual Emscripten library.
# Validation is store-independent, not an unavailable-filesystem stub.
control = struct.pack("<4sIQdiI", b"XYDC", 1, 7, 0.5, 2, 1) + struct.pack("<III", 2, 1, 3)
assert _native.tile_paint_control_valid(b"")
assert _native.tile_paint_control_valid(control)
assert not _native.tile_paint_control_valid(control[:-1])
assert not _native.tile_paint_control_valid(control + b"x")
assert not _native.tile_paint_control_valid(b"bogus")
assert not _native.tile_paint_control_valid(struct.pack("<4sIQdiI", b"XYDC", 1, 7, np.nan, 2, 0))
assert lib.xyg_tile_paint_control_valid(None, 0) == 1
assert lib.xyg_tile_paint_control_valid(None, 1) == 0
assert lib.xyg_tile_paint_control_valid(None, 3105) == 0
limits = np.zeros(2, dtype=np.uint64)
assert lib.xyg_canonical_drill_limits(0, limits.ctypes.data) == 1
assert tuple(limits) == (200_000, 80_000_000)
assert lib.xyg_canonical_drill_limits(2, limits.ctypes.data) == 0
estimate = _native.canonical_drill_estimate(2_000_000, (0, 100, 0, 100), (0, 10, 0, 10))
assert estimate == 20_000
assert _native.canonical_drill_admit(estimate)
assert not _native.canonical_drill_admit(2_000_000)
assert _native.canonical_drill_admit(2_000_000, refinement=True)
x = np.array([1e12, 1e12 + 0.001, np.nan, 1e12 + 0.003, 2e12, np.inf])
y = np.array([0., 1., 2., 3., 100., 101.])
zx, zy = k.zone_maps(x, 2), k.zone_maps(y, 2)
drill = _native.canonical_drill_query(x, y, zx[0], zx[1], zy[0], zy[1],
    1e12, 1e12 + 0.003, 0., 3., chunk_size=2)
assert drill["status"] == "complete" and drill["count"] == 3
assert drill["indices"].tolist() == [0, 1, 3]
assert drill["candidate_chunks"] == 2 and drill["rows_read"] == 4
assert drill["read_bytes"] == 64
usize_max = (1 << (8 * __import__("ctypes").sizeof(__import__("ctypes").c_size_t))) - 1
assert lib.xyg_tile_store_paint_capacity(256, 256) == 0
assert lib.xyg_tile_store_paint(0, 0, 1, 0, 1, 256, 256, 1, None, 0, None, 0) == 0
assert lib.xyg_pyramid_spill(0) == 0
assert lib.xyg_tile_store_fetch(0, 0, 0, 0, None, None) == 0
assert lib.xyg_tile_store_compose(0, 0, 1, 0, 1, 1, 1, 1, None) == -1
assert lib.xyg_tile_store_compose_color(0, 0, 1, 0, 1, 1, 1, 1, None, 0, None, 0) == -1
assert lib.xyg_tile_store_append(0, None, None, 0) == 0
assert lib.xyg_tile_store_stats(0, None) == 0
assert lib.xyg_tile_budget_set(0) == 0
assert lib.xyg_tile_store_free(0) == 0
assert lib.xyg_chunked_columns_open(None, 0) == 0
assert lib.xyg_chunked_columns_cancel_before(0, 0) == 0
assert lib.xyg_chunked_columns_rows(0) == (1 << 64) - 1
assert lib.xyg_chunked_columns_overview(0, 0, None, None, None, None) == usize_max
assert lib.xyg_chunked_columns_read(0, 0, 1, 0, 1, 0, 0, 0, None, None, 0, None) == usize_max
assert lib.xyg_chunked_columns_read_page(0, 0, 1, 0, 1, 0, 0, 0, 0, None, None, 0, None) == usize_max
assert lib.xyg_chunked_columns_free(0) == 0
f"{k.BACKEND}|{abi}|{mn}|{mx}|{len(fixture['successful'])}|{fixture['scene_version']}|{fixture['painter_version']}|17|{filter_packets}|{int(filter_cooperative)}"
`);
  const [backend, abi, mn, mx, cases, sceneVersion, painterVersion, filesystemStubs, filterPackets, filterCooperative] = r.split("|");
  out({ ok: true, backend, abi: Number(abi), min: Number(mn), max: Number(mx), cases: Number(cases), sceneVersion: Number(sceneVersion), painterVersion: Number(painterVersion), filesystemStubs: Number(filesystemStubs), filterPackets: Number(filterPackets), filterCooperative: filterCooperative === "1" });
} catch (e) {
  out({ ok: false, error: String(e.message || e).split("\n").slice(-4).join(" ") });
}
"""


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: pyodide_load_smoke.py <wheel>", file=sys.stderr)
        return 2
    source = sys.argv[1]
    if source.startswith(("https://", "http://")):
        wheel_source = source
    else:
        wheel = Path(source).resolve()
        if not wheel.exists():
            print(f"wheel not found: {wheel}", file=sys.stderr)
            return 2
        wheel_source = str(wheel)

    # Write the driver into CWD so its `import "pyodide"` resolves against the
    # node_modules of the directory where `npm install pyodide` was run (node
    # resolves ESM imports relative to the importing file's location).
    driver = Path.cwd() / "_pyodide_load_driver.mjs"
    driver.write_text(_DRIVER, encoding="utf-8")
    try:
        proc = subprocess.run(
            [
                "node",
                str(driver),
                wheel_source,
                str(Path(__file__).resolve().parents[1] / "tests/fixtures/xyts_cross_host.json"),
                str(
                    Path(__file__).resolve().parents[1] / "tests/fixtures/filter_tier_c/session.bin"
                ),
            ],
            capture_output=True,
            text=True,
            check=False,
        )
    finally:
        driver.unlink(missing_ok=True)

    result = None
    for line in proc.stdout.splitlines():
        if line.startswith("RESULT "):
            result = json.loads(line[len("RESULT ") :])
    if result is None:
        print("no result from pyodide driver", file=sys.stderr)
        print(proc.stdout[-2000:], file=sys.stderr)
        print(proc.stderr[-2000:], file=sys.stderr)
        return 1

    if result.get("ok"):
        if result.get("filterPackets") != 47 or result.get("filterCooperative") is not True:
            print("FAIL: Pyodide filter transport proof missing or incomplete")
            return 1
        print(
            f"PASS: Pyodide loaded xyg, backend={result['backend']} "
            f"abi={result['abi']} min_max=({result['min']},{result['max']}) "
            f"xyts_cases={result['cases']} Scene=v{result['sceneVersion']} "
            f"painter=v{result['painterVersion']}"
            f" filesystem_stubs={result['filesystemStubs']}"
            f" filter_packets={result['filterPackets']} cooperative={result['filterCooperative']}"
        )
        return 0
    print(f"FAIL: pyodide could not load/run the wheel: {result.get('error')}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
