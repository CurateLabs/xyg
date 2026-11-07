# Mounted native geographic temporal replacement — local review candidate

This successor advances the canonical mounted lane of M6/#50/#39. It does not
close those issues or full milestones4–7. Implementation base is
`7e720104f2d3f0508e6c93211980c09808f42bc6`, with ordered parents
`bea7eab191e6ff54b1999087edf23b3d98695899` and
`43c35f67b95ae4e78e3e96f200a0e6be8642199c`. Accepted main remains43c35f67;
its tree equals independently approved1f9e0637. The inherited root contains queued
public10k graph work and is not described here as accepted main. No force-worker,
frozen-export, rendered-filter or ABI402 catalog work was merged into this lane.
Parent independent review and delivery remain required.

## Fresh implementation and qualification

`GeoWidget.bind_temporal` and the host returned by `attachGeoWebview().bindTemporal`
automatically replace an already mounted canonical geographic painter from exact
native controller state. They share source exclusion with snapshot binding, retain
one active/one latest intent, invalidate before CAS, preserve camera ordering, and
hold source claims through actual drain/release. Numeric intent/revision planes
use XYHTv1 binary controls; all preparation, geometry, membership, picking and
paint remain in the existing Rust/XYGH/XYPB path. See the
[normative contract](../../design/geo-mounted-temporal-hosts.md).

Fresh actual-host results are separate from inherited snapshot evidence:

- Packaged strict-CSP Chromium156 with Node22.23.4/native ABI401: selected direct
  points, full-u64 IDs/namespace, exact signed time and half-open range endpoints,
  original painter/picks, held replies and supersession, real pointer drag plus
  two ordered pans and wheel zoom, failed-read retained paint, exact drain retry,
  controller close during publication, release/remount/rebind, independent caller
  Data and complete explicit cleanup. The visible colored-pixel centroid moves
  from400 to about343.66, matching the Rust camera after every ordered delta.
- The same packaged host with32769 canonical rows and one aggregate cell:
  all32769 exact member IDs/source ordinals across nine real pages and full-u64 identity, forged-key rejection
  with auxiliary release, zero-members/zero-colored-pixels range, recovery,
  unfinished native read through disposal and independent caller survival.
- Live JupyterLab/IPython/anywidget using Python3.11.17, actual binary comm and
  native painter: premount latest intent, automatic cursor/range replacement,
  foreign-thread mutation, camera persistence, failure-retained frame, rebind,
  caller survival and real native release ACK. Phase pixels are47 →0 →47.
  Notebook warnings (anywidget export deprecation, color parsing and GL readback)
  are retained separately from page errors; no page errors or external requests
  passed unnoticed. Newer kernel comms arrive on a different loop: the dispatcher
  regression first failed and now proves thread-safe owning-loop admission.
- Real VS Code1.103.2 with embedded Node22.17.0 and an actual WebviewPanel:
  native picks, visible framebuffer/centroid, premount time, unfinished read with
  newer intent, failed-read retained picture, range/cursor rebinding, real reload,
  independent caller survival and actual panel disposal while reading. A separate
  successful1.145.2/embedded Node24.22.1 intermediate-source probe is recorded
  distinctly; it does not qualify the final client artifact.
  The screenshot is a real X11 capture, not a generated rendering.

Python/Node regression coverage includes premount disposal, stale mount messages,
1000-notification bounded admission, both snapshot/mounted claim orders, failed
postMessage/drain/realm cleanup and retry, callback reentrancy, repeated waiter
cancellation, reader-originated CancelledError, default unbound-reader threading,
and exact synchronous executor draining.25 selected native replacements cross the
fixed16 birth-bank limit without changing it: the finished canonical selected
query now retires through its existing cancel/47 guard after independent Data
preparation. Native membership authenticates the complete Rust provenance key;
its independent session handle is not the painter's Data handle.

`checks.json` records commands, explicit artifact paths, exits and raw log names.
The initial final-check batch includes a failed aggregate test whose baseline
was sampled before the normal initial mount publication; its corrected recheck
is separate. Other failed attempts, including startup errors and the original
abandoned draft, remain failures. `exploratory-attempts.json` does not retroactively
bind intermediate working code to the final source: those intermediate source
bytes were not all retained. Only the final successful rechecks qualify this
candidate. No timeout/disconnect/GC or mock callback count proves native release.

## Reproduction

Set `TMPDIR=/var/tmp`, put the supplied Node22 executable first on PATH, and select
this checkout's `XYG_NATIVE_LIB="$PWD/target/release/libxyg_core.so"` explicitly.
The native artifact is the own-worktree ABI401 build, SHA256
`b93f21b8f19799897566a5447279f0a79729b7814c0391db302cd31a050a31bd`.
Its full Rust source tree is bound in `current-bindings.json`; it differs from
accepted main because the inherited root also contains the queued graph work.
No Rust source or C ABI signature changed in this candidate. Browser bundles are
regenerated and ignored, with exact Python/client copy hashes in the receipt.
There is no new WASM module. Prior WASM parity remains inherited evidence.

```sh
uv sync --group dev
npm ci
npm ci --prefix packages/xy-node
cargo build --release
node js/build.mjs
uv run pytest tests/test_geo_mounted_temporal.py tests/test_geo_temporal_binding.py tests/test_geo_live_host.py -q
node --test packages/xy-node/test/geo-mounted-temporal.test.mjs
XYG_CHROMIUM=/path/to/chrome node tests/browser/geo_mounted_temporal_test.mjs
XYG_CHROMIUM=/path/to/chrome XYG_GEO_SELECTED=0 XYG_GEO_AGGREGATE=1 node tests/browser/geo_mounted_temporal_test.mjs
XYG_CHROMIUM=/path/to/chrome XYG_GEO_JUPYTER=/path/to/jupyter-lab node scripts/geo_notebook_mounted_temporal_smoke.mjs
uv run python scripts/geo_vscode_mounted_temporal_smoke.py --code /path/to/code --output target/task-tmp/mounted-vscode --tcp-xvfb
uv run make check-ci
uv run python scripts/verify_ownership.py
uv run python scripts/check_release_inventory.py
uv run ty check
uv run --with pre-commit pre-commit run --all-files
uv run ruff check .
uv run ruff format --check .
```

The VS Code helper accepts an existing DISPLAY instead of `--tcp-xvfb`. The latter
uses an authenticated private TCP X display when the supplied /tmp quota prevents
X11 lock/socket creation; it requires `sudo -n Xvfb`, logs no cookie, and removes
its own authority file/server. It does not substitute disconnect for native
teardown. The app fixture awaits real release or realm-destroyed cleanup.

Normal CI discovers the pytest and Node lifecycle tests. The existing Chromium
host job now executes selected and aggregate mounted temporal journeys. Jupyter
and VS Code journeys remain explicit reproducible application receipts rather
than requiring those applications in every CI job. Merge-group triggers and
queue gates are preserved; the full `make check-ci` contract suite passed772 cases.

## Exact limits and handoff

Fresh evidence covers small direct selected views and a32769-row aggregate view,
not massive benchmarks. Indexed/hierarchy/overview/mixed-tile automatic bindings,
complete attributed frozen exports, full-source accessibility, full linked/pinned
focus UI, five automatic large views, massive latency/memory and fresh competitor
qualification remain open. Existing explicit indexed/hierarchy mounts, selected
snapshot identity, native temporal semantics and historical exports are inherited,
not reclassified as new acceptance. No Matplotlib/Seaborn/Plotly/Bokeh/Altair/
Datashader/HoloViews/hvPlot superiority is inferred from these lifecycle tests.

`current-bindings.json` is an append-only successor to the historical Core binding
chain. `source.patch.gz` is the canonical full-index binary product diff against
the implementation base, excluding this receipt to avoid self-reference. Parent
handoff additionally records the final committed full diff hashes against both
base7e720104 and accepted main43c35f67, ordered parents and every changed path.
No GitHub mutations, pushes, PRs, watches or release actions were performed.
