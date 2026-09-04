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
  // Dependency provisioning is complete. The conformance operation itself is
  // strictly offline: any accidental host lookup now fails immediately.
  globalThis.fetch = async (url) => { throw new Error(`offline XYTS fixture attempted fetch: ${url}`); };
  const r = await py.runPythonAsync(`
import xyg.kernels as k
import numpy as np
import json
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
usize_max = (1 << (8 * __import__("ctypes").sizeof(__import__("ctypes").c_size_t))) - 1
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
f"{k.BACKEND}|{abi}|{mn}|{mx}|{len(fixture['successful'])}|{fixture['scene_version']}|{fixture['painter_version']}|15"
`);
  const [backend, abi, mn, mx, cases, sceneVersion, painterVersion, filesystemStubs] = r.split("|");
  out({ ok: true, backend, abi: Number(abi), min: Number(mn), max: Number(mx), cases: Number(cases), sceneVersion: Number(sceneVersion), painterVersion: Number(painterVersion), filesystemStubs: Number(filesystemStubs) });
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
        print(
            f"PASS: Pyodide loaded xyg, backend={result['backend']} "
            f"abi={result['abi']} min_max=({result['min']},{result['max']}) "
            f"xyts_cases={result['cases']} Scene=v{result['sceneVersion']} "
            f"painter=v{result['painterVersion']}"
            f" filesystem_stubs={result['filesystemStubs']}"
        )
        return 0
    print(f"FAIL: pyodide could not load/run the wheel: {result.get('error')}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
