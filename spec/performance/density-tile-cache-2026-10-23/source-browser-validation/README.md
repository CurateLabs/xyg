# Source browser validation and observed failures

These checks use the changed checkout's generated client and native core,
with exact artifact/harness hashes in [provenance](provenance.json). They
establish source integration behavior on Linux x64 Chromium, not an immutable
release candidate or the full host/platform matrix.

These are the initial client validation snapshots. Later viewport-admission
and fade-retirement corrections have separate
[source-browser evidence](../review-followup/README.md); the original report
and artifact hashes here remain unchanged.

The [unmodified full foundation report](xyg-tile-final-foundation.json) and
six screenshots pass with local assets and strict CSP. The
[isolated interaction report](interaction.json) passes the existing budgets
for all seven scenarios with 12 repetitions, zero blank frames, and zero tick
overlaps. [Its readable table](interaction.md) retains every measured scenario.
The report's installed distribution version comes from editable installation
metadata; the tested source/client/native hashes are the provenance authority.

Earlier checks ran alongside Rust validation and browser/build work. The
[initial foundation log](initial-foundation-failure.log) records an unhandled
`worker was disposed` page error. The [initial browser log](initial-browser-checks.log)
records six passing smoke families followed by one bar box-zoom p95 of 346 ms,
above the unchanged 300 ms budget. Exact artifact hashes were not captured
for those initial runs, so they remain diagnostic observations.

After other validation stopped, the original foundation harness and the
interaction smoke passed. No assertion, retry policy, timeout, or budget was
changed. This does not identify the rejected promise or prove a cause for the
initial failures. [The comparison investigation](../foundation-comparison/README.md)
records the unchanged Worker source, diagnostic run, and immutable baseline
comparison. The original disposal failure remains unreproduced and must stay
visible when evaluating the final release candidate.

Reproduction commands are in the provenance file. For an interaction run
intended to measure timings, stop competing browser/build workloads and keep
the existing report validator and budgets.
