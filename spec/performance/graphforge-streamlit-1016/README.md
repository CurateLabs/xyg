# Bounded GraphForge Streamlit #1016 evidence

Local correctness receipt, 2026-10-31. Parent baseline `1440bec9`, followed
by a normal merge of validated combined defaults/CoSE commit
`465ec0a0acc16340947ea599fee7e0486f12b6d0` into
`fab6aa90c94844ed78865721af90a2aebd95dfd0`. The consumer changes were tested
on that merge plus the source bytes hashed in `environment.json`.

This is a small repository consumer acceptance slice. No Python/Rust/Node
package implementation, dependency lock, ABI, application adapter, or CI job
changes. The wheel was built from the merged package code, then verified and
installed into a clean environment; the repository example, tests and fixture
producer consumed that installation. No unpackaged diagnostic module was used.
The wheel version names the merge baseline; exact consumer harness hashes
bind the accompanying uncommitted-at-test-time implementation. The containing
commit records the final source and receipt together.

## Executed proof

- **Source checkout:** 137 focused tests passed: the AppTests, public-host
  export comparisons, dependency boundaries and wheel/sdist verifier tests.
  Raw output and JUnit: `source-tests.*`.
- **Installed wheel, locked Streamlit 1.66.1:** the existing unconditional
  `consumer_apps_smoke.py` gate passed. All 13 AppTest/package-boundary tests
  executed with zero skips. Python imports/native loads resolve inside the
  clean wheel install; Python apps run with Node absent from their PATH.
  Existing Node and packaged tick/density qualification remained green.
  Full raw report: `installed-consumers.json`; run output:
  `installed-consumer-run.txt.gz`; tests: `installed-app-tests.*`.
- **Installed wheel, supported floor Streamlit 1.56.0:** all 13 tests passed
  without skips; the same bounded GraphForge browser journey passed.
  `floor-app-tests.*`, `floor-browser.json`, `floor-install.txt` and
  `floor-packages.txt` retain this independent floor resolution. The main gate
  uses the lock; this floor probe intentionally installs exact 1.56.0 with its
  own resolved dependencies and does not change the lock.
- **Installed wheel without Streamlit:** both unconditional package-boundary
  tests passed and the optional AppTest module skipped once for absent
  Streamlit (`minimal-tests.*`). Broken installed framework imports do not
  qualify for this skip.
- **Other checks:** 118 release-surface/verify-local tests passed; `ty check`
  passed; generated styling capability matrix remained current. Mandatory
  full-worktree hooks/Ruff results are in `checks.txt`.

The actual browser was cached Playwright Chromium **156.0.8078.4**, explicitly
selected by path, with software WebGL flags recorded in `environment.json`.
This VM has no `/usr/bin/google-chrome-stable`. The explicit Chromium option
is the repository's authorized browser-smoke workflow, not an implied system
Chrome or hardware-renderer qualification.

## Output contract and inspectable artifacts

`graphforge-property` uses the existing Core 0.5.2 property fixture: **5 nodes,
5 edges, zero analytical layers**. It omits `layers` from the public composition
call. Tests pin label classes/legend, caption fallbacks and relationship labels;
the browser checks actual label-color paint and Rust-admitted canvas captions.
At the initial scale the collision plan may omit some captions. This recipe
does not override defaults to force every label to appear.

`graphforge-pagerank` uses **4 nodes, 5 edges and one PageRank result layer**
from the same existing Core fixture generation. XYG does not compute PageRank.
Its default score-size encoding is neutral, so the browser measures nonwhite
plot ink rather than requiring an artificial color override.

Both views use 720×360 CSS-pixel charts; default native PNG output is
1440×720. The public-host producer is independent of the example's builder.
`direct-public-host.json` retains the source Arrow/manifest SHA-256 values,
generation IDs, counts, captions/legend and exact HTML/PNG/SVG hashes.
The installed browser requires iframe HTML and both downloaded formats to
match that direct public-Python oracle byte-for-byte. The retained
`*-download.png` / `*-download.svg` files are the actual downloads; `*-home.png`
files show the initial running app. HTML files, compressed HTML and the full
shared-client bundles remain in the ignored local `consumer-apps-smoke/`
artifact directory and the existing CI artifact upload, rather than being
duplicated into git. Their hashes and reproduction command are retained here.

`installed-graphforge-browser.json` and `floor-browser.json` record actual
property chromatic pixel counts (1,441), neutral PageRank ink pixels (4,894),
static preview decoding, two switch-away/return cycles per view, unchanged
HTML on return and observed retirement of outgoing iframe execution contexts.
Trusted box-brush and wheel gestures change browser-local state without a
Python comm bridge. No external requests, CSP violations or page errors were
observed. Downloads use `on_click="ignore"` to preserve the current snapshot.

Lifecycle proof is specifically **browser snapshot-document retirement**.
The app does not receive a ChartView handle or call its destructor; the smoke
does not add cleanup callbacks. General live-view/Worker/GPU cleanup remains
with the existing shared/Node qualification. There is no tested UUID event
round-trip to Python and no custom Streamlit component in XYG.

## Reproduce

From this checkout, with Rust 1.96.0, Node, uv and a local Chromium executable:

```bash
uv sync --locked --group dev --group consumers
cargo build --release
npm ci
npm ci --prefix packages/xy-node
node js/build.mjs
npm run build:wasm
uv run --group consumers pytest tests/test_streamlit_consumer.py tests/test_streamlit_package_boundary.py tests/test_dependencies.py tests/test_verify_wheel.py tests/test_verify_sdist.py -q
uv run python scripts/consumer_apps_smoke.py --chromium /path/to/chromium
```

The recorded run used the gate's `--wheel` option with the previously built
exact wheel under `/tmp/graphforge-streamlit-wheel/`; its SHA-256 is recorded
in `environment.json` and `installed-consumers.json`. Omit that option to
rebuild and verify a fresh local wheel. Published artifacts are not involved.

For the separate floor/minimal proof, build a wheel with `uv build --wheel`,
create a fresh venv with `uv venv`, and install the wheel plus pytest and
`streamlit==1.56.0` (or omit Streamlit for the absent-framework case). Run
the same two consumer test modules using that venv's Python, `--noconftest`
and an empty temporary pytest config from outside checkout import paths.
Run the floor example with that Python's `-m streamlit` from a temporary
working directory. The bounded browser helper can be invoked directly with
the existing runner's paint oracle and the same direct-host producer; the
required locked-wheel proof remains the single existing consumer gate above.
`floor-browser-command.txt` retains the explicit separate-floor commands.

## Limits and parent integration

This receipt proves bounded local fixtures, not medium/large/massive graph
capacity, benchmark superiority, every default/event/export contract or
final release-cohort installation. No competitor timing win is claimed.
The full multi-hour pytest suite was not run for this example/test/docs slice.
No new Release surfaces job is needed: the existing required consumer job
already executes these additions, preserving the merge queue workflow.

#1016 and Milestone 4 stay open. Broader #36/#934/#935 acceptance, authorized
remote #31/#40 host-list updates, independent review of the final combined
diff and parent CI integration remain with the parent task. No remote object,
pull request, tag or publication was changed by this slice.
