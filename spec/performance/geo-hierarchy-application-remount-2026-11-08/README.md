# Selected hierarchy temporal remount in actual applications

Implementation base: `4003b564d1b5073c38cce7bdf43dc941306c68a0`.
This continuation adds application fixtures, operator modes and evidence for the
reviewed native sequence-floor repair. It changes no production Python/Node,
Rust, browser client, ABI, admission policy, default, resource cap or deadline.
The same native405/WASM38 artifacts and 324 compiled inputs are retained.

## Scenarios and oracles

The finite two-row source carries selected identity `18446744073709551615` and
private native hierarchy authority. Both actual applications keep independent
caller Data and the original source publication alive through replacement.

| Given / when | Then / evidence |
| --- | --- |
| Actual JupyterLab, live Python 3.11 kernel and anywidget; trusted canvas ArrowRight | Native camera center becomes nonzero; browser records a trusted key event |
| Hold a real native prepared reply, close the binding, then release that reply | Abort completes; accepted publication stays at sequence5; consumed sequence6 remains the automatic floor |
| Clear the actual Output, wait for release, then redisplay the same widget and bind cursor23 | Actual release ACK precedes remount; privately issued hierarchy sequence7 is newer than6; camera, complete selected ID and caller lease survive |
| Accept an empty half-open range, then restore cursor6 | Selected intent remains exact with zero visible vertices; green pixels14→0→14; the entire restored canvas RGBA SHA256 equals the earlier remounted canvas |
| Actual VS Code1.103.2, embedded Node22.17.0, programmatic public camera update | Native camera and changed framebuffer persist through temporal supersession; this is not a trusted canvas-pan claim |
| Native page failure, empty range, restore, real prepared abort and WebviewPanel reload | Complete RGBA hashes survive failure/restoration/reload; accepted10, aborted11, new12 preserve strict sequence ordering |
| Dispose the actual WebviewPanel while a native page read is admitted | Admitted read settles, native owners drain, independent caller Data survives until explicitly closed |

Jupyter assertions live in
`tests/notebook_geo_mounted_hierarchy_temporal.ipynb`, using
`tests/geo_mounted_hierarchy_temporal_fixture.py`. VS Code assertions live in
`tests/vscode_geo_mounted_hierarchy_temporal/`. The existing application operators
select them with `XYG_GEO_HIERARCHY=1`; indexed and hierarchy modes are mutually
exclusive. Existing canonical/indexed assertions and action deadlines remain.
New VS Code native gates use the existing45-second action bound.

## Reproduction

Use a checkout with its dependencies, exact native core and generated browser
artifacts installed, plus JupyterLab/ipykernel/ipywidgets/anywidget, Playwright
Chromium, an installed VS Code and a display. Export `XYG_NATIVE_LIB` to this
checkout's `target/release/libxyg_core.so`; export `PYTHONPATH` to its `python`
and `tests` directories. The source receipt pins the actual executable versions
and artifacts. This is source-checkout consumption in installed applications,
not an installed-XYG-wheel test.

```bash
XYG_GEO_HIERARCHY=1 XYG_GEO_JUPYTER=/path/to/jupyter-lab \
  XYG_CHROMIUM=/path/to/chromium XYG_GEO_NOTEBOOK_REPORT=/path/to/report.json \
  node scripts/geo_notebook_mounted_temporal_smoke.mjs

XYG_GEO_HIERARCHY=1 python scripts/geo_vscode_mounted_temporal_smoke.py \
  --code /path/to/code --output /path/to/output
```

The notebook's cold-server startup path retains its existing100×100ms probe
bound. Cold startup previously failed under load and is **not** qualified by this
receipt. The recorded hierarchy run instead uses an explicitly separately
started private loopback Jupyter server with the input notebook copied to its
root as `geographic.ipynb`, then sets `XYG_GEO_JUPYTER_URL` to its origin. The
operator verifies served cell types/source against the committed input before
opening Chromium and records the input SHA256. It does not stop a caller-owned
server. The reproduction evidence includes the private server start command,
root setup and graceful shutdown. Negative controls reject different notebook
input, a remote prestarted URL and simultaneous hierarchy/indexed modes.

The existing VS Code operator accepts `--tcp-xvfb` for an authenticated private
Xvfb when Unix X11 sockets are unavailable. Its local cookie is never retained
in committed evidence. No VS Code action deadline or assertion is relaxed.

`checks.json` binds exact sources, historical predecessors, reports, raw and
compressed logs, captures and unchanged shipping artifacts. Current sources have
an append-only successor binding; all earlier receipts remain unchanged. The
prior correction's native negative controls and review remain applicable through
source identity; this continuation makes no new production-repair claim.

## Limits

Jupyter's report retains anywidget deprecation, GL readback stalls and CSS Color4
fallback warnings. No complete theme/alpha fidelity claim follows from the
within-host framebuffer comparisons. VS Code uses a public programmatic camera
update; only the notebook route supplies trusted keyboard input here. Neither
journey proves keyboard-only task completion or full accessibility.

These are two-row selected hierarchy application journeys. Five simultaneous
automatic bindings, ordinary hierarchy/overview/mixed-tile automation, massive
scale, global memory accounting, full attributed exports, installed-wheel and
competitor qualification remain open. Earlier Jupyter startup and Worker timing
failures remain unexplained; passing these journeys is not a reliability repair.
The combined module remains1,895,719 raw /786,385 Node22 gzip6 bytes, with only47
bytes below the unchanged gzip cap. No rebuild or72GB source scan was performed.
Independent final review, current-main freshness, hosted final-head CI and the
mandatory queue remain delivery requirements. #50/#39 and milestones4–7 remain
open.
