# Temporal catalog review and hosted-CI correction

Parent: `b8000a60900d4685969a6d68f55324e561199df5` (PR #1115).
This correction retains the bounded six-family UTC/direct-tier contract. It
resolves finite-domain projection and pre-copy transport admission findings,
and the actual hosted Clippy, Python-floor and native-free HTML staging failures.
It does not complete #46, M5 or milestones 4–7.

## Changed behavior

Rust temporal projection reuses Scene's overflow-safe linear fraction. Negating
the axis preserves the prior ordinary `(max-value)/(max-min)` arithmetic order;
opposite finite extremes retain three distinct finite positions. Existing six-
family complete Scene oracles remain exact. Public Python/Node constructors
check the XYTM header, UTF-8 metadata and 40-byte row envelope before snapshot
copying. Python also bounds unsized or understated iterables before copying an
excess row. Node captures the admitted count once. Rust alone retains operation,
viewport, row/LOD, geometry and semantic admission.

Generic Node HTML payload framing imports without koffi or a native library.
Temporal Figures provide their existing native Scene/painter preparation hook;
HTML framing adds no renderer. Python uses the explicit browser namespace in
its existing escaped/CSP-protected bootstrap. The public typing contract includes
TemporalChart and temporal_chart, and the internal Figure attribute is declared
only for type checking. Unchanged WASM adapter functions move before test modules,
without lint suppression, signature changes, or a native/WASM ABI bump.

## Verification and limits

Fresh logs, exact command/exit records, source/artifact/environment bindings and
before-source controls are retained in checks.json. The final public Python and
Node tests inspect visible SVG positions; full foundation executes the actual
packaged Worker and ChartView, checking all three expected colored pixel regions
for both 1e308 and the largest finite f64. All six previous byte oracles remain.
The same native/WASM source request produces complete equal Scene bytes.

The original native library fails all four final finite-projection Python cases.
The exact parent Python package fails all three public-constructor tests.
An initial attempted old-source pytest run loaded the current package through
the repository conftest; it receives no negative-control credit. A subsequent
unfiltered old-source run also encountered missing old client assets. The
isolated selected control is authoritative. Failed helper syntax/collection
attempts and incorrect new-test canvas/dimension assumptions remain recorded;
none is counted as a passing product check. ChartView's canvas excludes Scene's
left/top chrome, while SVG coordinates include those margins.

Historical receipts, packet fixtures, ABI declarations, compiler flags, size
caps, runtime budgets, cleanup deadlines and existing assertions are preserved.
The official preparation inventory refresh changes provenance only, with the
same contracts and 691 explicit gaps. Source hashes advance in a successor
binding; previous bindings and all frozen Core producers remain unchanged.

Completed independent final review and fresh hosted CI/queue delivery are still
required. No comparative latency, large-scale, all-host, accessible temporal
interaction, timezone database, streaming, release or whole-issue acceptance is
established by this repair.
