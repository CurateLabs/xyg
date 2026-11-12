# Rejected rounding experiment and measurement-order correction

Parent: `3abe920bde612af628dc7f48623ef6018cc3b2ed`.

The earlier [single-color receipt](../filter-single-color-2026-11-12/README.md)
lists parent 1, candidate 1, parent 2, candidate 2. That is alternating paired
**A-B-A-B**, not A-B-B-A. Its ABBA wording is an error. This successor and the
authoritative benchmark methodology correct the label while preserving the
earlier receipt, actual run order, inputs, comparisons and raw profiles.

## Private alternative: rejected

A private native variant replaces the two linked-paint round-to-u8 sites with
an exact truncation/fraction comparison. The standalone correctness probe passes
2,034,862 edge and sampled cases; a naive add-half conversion fails the midpoint
neighbor control. Generated assembly avoids the general `round` call. The private
variant passes 35 Node/native/shipping-WASM tests and 26 Python checks with
unchanged fixture bytes. These establish correctness on tested paths, not speed.
No production source, shipping artifact or protocol incorporates this variant.

Actual A-B-B-A CodSpeed walltime runs use the original unredirected benchmark
host, original four IDs and measured calls, matching normal native build profile,
the same materialized 100M-row fixture, 346 active cells, five 100-by-100 views,
explicit 256 MiB, SwiftShader and `gl.finish`. Setup is excluded; indexed replies
report tier 3 and zero canonical query-row reads. The private copied parent native
is byte-identical to the qualified shipping library. Only the private linked
module changes among all 329 recorded compiled inputs.

| Order | Run | Full update best | CLI comparison |
| --- | --- | --- | --- |
| Parent A1 | `6af555a0eaa685ef877f8f93` | 29.84 ms | Regression against older same-library run's 23.26 ms |
| Prototype B1 | `6af555e9eaa685ef877f8fa0` | 24.51 ms | Improvement against A1 |
| Prototype B2 | `6af55628135d6109e58150be` | 29.73 ms | No Change against A1 |
| Parent A2 | `6af5566d135d6109e58150c5` | 29.03 ms | No Change against A1 |

The prototype's full-update improvement does not repeat, so the additional
conversion code is rejected. Query and density comparisons are No Change in
both prototype runs. Cached paint is Regression for both prototypes and the
unchanged final parent against A1; A1 itself is Improvement against the older
run. Those rows execute no native conversion and do not establish its cause.
All four complete comparisons remain in `round-decision.json` in the archived
evidence. Do not select only the favorable first prototype result.

All four invocations exit 0, complete all four benchmarks and acknowledge owner
and browser cleanup without reported errors. Each setup records the actual
native path and digest. All four report environment-metadata write failure;
A1 loses 699 sampled profile events. Failed initial assembly flags, the naive
conversion negative and earlier copied-input build failure remain recorded.
No timing was taken outside CodSpeed CLI. The original complete-input rebuild
failure and repair remain in the preceding compiled-input receipt.

This also demonstrates session-to-session variation in the unchanged native
library's full-update result. Neither the historical single-color comparison nor
this rejected alternative supplies an absolute latency, p95, hardware-GPU,
trusted-pointer, RAF cadence, 50 FPS or competitor guarantee. No new WASM variant
was built or qualified for the rejected native experiment.

## Preservation and readiness

Production, build configuration and all shipping native/WASM/client/Worker bytes
remain parent-identical. The module remains 1,875,559 raw / 785,836 Node22 gzip6 bytes
under unchanged caps. The complete 329-entry compiled-input map remains unchanged.
The successor retains all 66 parent manifests and immutable predecessor sources.

The complete parent 185-path implementation and compiled-input correction has
independent bounded approval: Codex gpt-6.1-sol, high reasoning effort, exact
head 3abe920b, review SHA256
`b04e81724bd2c48be419015e0f9a0469c2a19b5b7709dd8889f7056b8e005624`.
Its archived record distinguishes fresh checks from inherited producer evidence.
This appendix requires its own exact-diff independent review before delivery.
Hosted checks and the merge queue remain required. Whole #112 and milestones 4–7
remain open; this is not a shipping or performance-target qualification.
