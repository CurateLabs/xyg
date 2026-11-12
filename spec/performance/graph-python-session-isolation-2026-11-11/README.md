# Independent Python graph-session lifecycle locks

Parent: `eb9f09d6b7a823392e989d40bbdba4f9f2d070f1`.

The previous Python transport held one process-wide lock throughout native
creation, complete sizing/copy transactions and destruction. A graph build on
one worker could therefore block another owner's creation or retirement,
including retirement called by the notebook event loop. The native ABI already
uses separate owner locks after brief registry discovery.

Python now shares a lifecycle lock by the already validated native instance
identifier. Native create, all sizing/copy retries and close remain serialized
for that instance, including byte-identical OPEN aliases. Different instances
can progress independently. A small weak-reference table stores only locks;
allocation and callbacks run outside its brief discovery mutex. It retains no
native handles, graph state, document or reply cache. Rust remains authoritative
for alias/conflict validation, capacity, state, replay and errors. Closing either
alias still revokes the native lifetime rather than reference-counting it.

## Evidence and limits

Six deterministic real-native controls park either creation or sizing/copy
while an independent owner creates, renders or closes. All six fail against the
exact original module and pass after correction. Existing same-wrapper and
alias close ordering, reentrant conversion, copy bounds, replay, refusal and
Unbound tests remain intact. Matching execution passes 95 Python3.12
transport/widget tests and 39 Python3.11 tests with four existing
Python3.12-only buffer-protocol skips.

Additional real-native controls verify that an alias OPEN cannot split a
sizing/copy transaction and that 24 closed alias lifetimes leave no retained
lock entries after their wrappers are collected. The first successor CRLF run
found that the newly bound transport module lacked an LF pin; its original
failure is retained and the pin is added before qualification.

The actual JupyterLab 4.6.5 1k+1k control passes through CodSpeed, including exact
UUID input/selection, GPU mask, peer isolation and native/thread cleanup. Run:
`6af4142d186b874c4ebbed55`. Its single functional round establishes no speed win.

**Public 100k acceptance still fails.** After this change, the primary is sampled
alive at step 9 while building; the peer reaches the unchanged wall deadline at
step 161. Exact selection and cleanup pass. These are single-run state samples,
not a throughput comparison or reliability qualification. Earlier peer failures
at steps 137 and 145 remain preserved. No default, chunk, deadline, iteration,
algorithm, resource limit, ABI, export or renderer policy changed.

The retained CodSpeed diagnostic profile identifies substantial Python tooltip
construction/encoding work in the large publication. The first diagnostic also
failed acceptance and could not write its profile because its output directory
was absent. The corrected recording preserves the failed acceptance and sampler
profile; neither failed execution receives timing/pass credit. Python perf-frame
instrumentation was enabled for those diagnostic profiles and omitted from the
subsequent normal host controls. No cross-configuration timing comparison is
claimed. The next performance work remains the measured tooltip path.

`checks.json` binds source, original-module controls, commands, failures,
profiles, captures and artifacts. Every previous receipt remains unchanged.
All 324 compiled inputs and all nine native/WASM/client artifacts remain
parent-exact: ABI405/551 native symbols, WASM38/68 functions, zero imports,
1,884,503 raw / 786,337 Node22 gzip6 bytes with 95 bytes below the unchanged cap.
This is host lifecycle isolation, not global memory or whole-milestone proof.

## Reproduce

Use explicit checkout/native loading, Node22, the supplied Chromium and disk
TMPDIR; never synchronize a borrowed environment.

```bash
uv run --no-sync pytest -q tests/test_graph_session_python_transport.py tests/test_graph_widget.py tests/test_graph_widget_regions.py
XYG_NOTEBOOK_SCALE=1000 codspeed exec -m walltime --warmup-time 0s --max-rounds 1 --name native-notebook-1k-owner-isolation-control -- node benchmarks/bench_graph_native_notebook.mjs
XYG_NOTEBOOK_SCALE=100000 codspeed exec -m walltime --warmup-time 0s --max-rounds 1 --name public-native-notebook-100k-owner-isolation -- node benchmarks/bench_graph_native_notebook.mjs
```

The 100k command remains failed acceptance, not an expected green gate.
Independent review, successor source/CRLF controls, mandatory hooks and hosted
new-head checks/queue remain necessary before delivery. Original milestone,
all-host, massive-data, accessibility, exports, competitor and global-resource
requirements remain open; no issue or milestone closure follows.
