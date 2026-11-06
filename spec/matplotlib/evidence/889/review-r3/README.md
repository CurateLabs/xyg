# Coincident minor ticks: third #889 repair

Independent Python review requested changes on immutable `1351ae00e0e8dd134a34f23a25df614ec2209156`.
With a NullLocator major tier, Rust's automatic major positions suppressed
coincident minor marks even though the automatic marks themselves had zero
style. Native SVG reproductions reported 0/4 marks for linear domain [0,10]
with minors [2,4,6,8], and 0/3 for log domain [1,100] with minors [1,10,100].
The noncoincident linear case [2.5,7.5] already emitted both marks.

The adapter now puts the independent minor positions and minor style in the
existing authored-major slot, leaves labels off, and disables the redundant
minor slot. No Rust, FFI, ABI, Node production, or empty-array contract change
is retained. Implicit log minor locators retain normal minor styling. The
parameterized SVG regression checks all three scenarios and empty public major
locator state. The basic NullFormatter witness still checks retained tick marks.

Required commands (Node 22 and cargo on PATH, XYG_CHROMIUM pointing to installed
Playwright Chromium):

```bash
uv run pytest tests/pyplot --ignore=tests/pyplot/corpus -q
make check-host-parity
uv run ty check
uv run pytest -q tests/pyplot/test_pdsh_gap_features.py -k 'null_locator or null_major'
uv run pytest -q tests/test_scene_chrome_pack_abi.py tests/test_static_dual_axis_cross_host.py
```

Results: 1188 pyplot passed, 163 optional skipped, 26 qualified xfailed; 1097
host-parity tests passed; typecheck passed; 4 locator regression cases and all
26 legacy chrome/secondary-axis contract tests passed. Source and native/WASM
artifact bindings and lossless log hashes are recorded alongside this file.
The generated mark-fixture side effect is archived as a patch and restored.
Existing R1/R2 evidence remains historical. Rust approval on `3a912365` and
acceptance approval on `1351ae00` cover their unchanged scopes; this repair
requires a fresh independent Python review before PR delivery.
