# Cold-admission repair: bounded v3 control

This preserves the exact six-cell local control produced at 1,000 actual
mapped rows for the file-entry and cold-raster admission repair. It is
exploratory correctness evidence, not hosted or competitive scale acceptance.
The producer records base `959e1004924774711a35df7ab1317cca30b18d68` with dirty
harness hashes; its final implementation is `e70e6f83ebf5f293bf2b2c014a9c8cf35b63bd75`.
The rejected actual-scale run [40075049750](https://github.com/CurateLabs/xyg/actions/runs/40075049750)
remains [unchanged and rejected](../hosted-main-959e1004/README.md).

`report.json.gz` is lossless original JSON; decoded SHA256 is
`d596cb52ecee97095c1b81d1f802c5c68b590c4f7c7e6ea80b51b18c5434dd2d`. All three arms and both fresh repetitions are retained,
each with cold admission, all 32 warm windows and the separate empty control.
The unchanged independent verifier reported six successful cells and no
failures, with explicit source SHA and artifact root. Original output is in
`verification-with-sha.txt`; full measurement stdout is in `run.log`.

`validation.txt` records exact reproduction commands, test results, real
file-entry import failure and the old producer's premature admission of a
35-frame delayed bootstrap. The fixed subprocess tests exercise preparation
and the actual native POST handler from an unrelated cwd without PYTHONPATH.
The raw diagnostic stderr remains in `entry-baseline.stderr`.

Both Bokeh cold outputs adopted 512×512 images with observed data revision 1
and backend revision 2. Binding and image bytes travel together in the
existing update; every warm Bokeh update retains one 1,048,576-byte RGBA image.
Two earlier diagnostic reports are retained separately as `development-*.gz`:
their failed/intermediate implementations are not substitutes for final cells.
The exact original handoff `README.txt` explains their limits and disposition.

Runtime/environment/source manifests, grids, numeric proofs and transport
observations are retained in the complete report; the optional environment
freeze is separate. Fourteen exact benchmark producer files live under
`producer/` with `.txt` appended to each original path. Their bytes match the
report and `producer-source-bindings.json`. No rebuilt native/client bytes
substitute for the recorded binary hashes. Source files were temporary and
are not recreated by inspecting this receipt.

`SHA256SUMS` covers every retained file except itself. The commands in
`validation.txt` reproduce the bounded run after the repository's normal
native/client setup. Do not emulate hosted authority or generate large arrays
for inspection. Local validation does not establish 100M/1B capacity, natural
gesture latency, a winner, larger-than-RAM proof or #11/#108 release acceptance.
A reviewed main landing and a fresh accepted hosted execution remain required.
