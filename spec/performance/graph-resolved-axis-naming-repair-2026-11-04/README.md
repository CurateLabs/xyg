# Exact OSM helper-path naming repair

Narrow repair from #1089 head `909dfe303b4f18f4b6332d9a4c13d68b7d2c3e74`. The existing historical source manifest correctly lists `examples/osm/osmium-rs/src/lib.rs`, the independent `osmpbf-nodes` helper crate's real entrypoint. The repository naming gate mistook that path for the retired root ABI location. Historical manifest keys, digests and contents remain unchanged.

## Definitive CI evidence

The supplied completed job logs from run **41750490193** are retained byte-for-byte in deterministic gzip form, with original timestamps, raw-byte counts, raw SHA-256 and gzip SHA-256 in `ci-job.json` and `additional-ci-jobs.json`:

- **126314754073**, Test (Rust + Python + JS): naming failure at **2026-11-04T01:02:37.3113226Z**, historical source-manifest line **5679**. Head is 909dfe30; GitHub's tested merge commit is `a8cc8aa28dca6d43fdb1bc828f586fd1f5f7dfc9`. The later missing host-delegation and consumer-app uploads follow skipped producers after the naming gate; they do not identify another product root cause.
- **126314754097**, Python 3.11 floor: exactly one failure, `test_repository_has_no_stale_native_identity`, caused by the same manifest line. Original summary: **1 failed, 7699 passed, 358 skipped, 113 xfailed, 4 xpassed, 43 warnings**. This is not a zero-skip or passing-floor claim.
- **126318615791**, sibling #1090 run **41751542330**: the same historical manifest line fails at **2026-11-04T01:12:36.3945294Z** for head `9b05f31778f623a030ed96551d52ba5ae7a2196d`. `shared-ci-job.json` records its lossless log and hashes. This is shared-cause evidence; the parent owns any later merge of this reviewed fix into #1090.
- **126318810230**, Release surfaces: aggregates `test=failure`, `python_floor=failure`, and `wheels=skipped`; no separate product root cause.

The parent reported matching comment 6619726772 updated at 01:08:20Z and a local reproduction (exec43589) with exactly the same exit 1. These are recorded as parent-supplied evidence, not additional jobs executed here. The parent downloaded each completed job directly through the job-log API; no whole-workflow failed-log or workflow-completion claim is made. No CI retry, remote mutation, push, PR update or queue action is performed.

## Narrow rule and regression proof

Only `_allowed_src_lib_rs` gains an allowance for the exact repository-qualified auxiliary helper path, optionally under an absolute checkout prefix. Component boundaries reject relative extra prefixes, partial directory names and filename/child-path suffixes. Existing core/engine/WASM/browser path policy is unchanged. The retired root ABI path remains barred. Neither JSON files, receipts nor other qualified paths receive an exemption, and other matches on the same line still fail. The authoritative naming specification records this in §2/§3.

The actual whole-repository before check exits **1**, reporting the original historical manifest plus two equivalent legitimate references in this new receipt. The new focused regressions before the fix show **7 failed, 17 passed, 18 deselected**: valid helper references falsely fail, while guard negatives already remain rejected. After the narrow fix all **24 new regression cases pass**. The complete naming suite reports **42 passed**, including all original tests; their existing function bodies are verified unchanged. The final whole-repository gate is recorded separately.

New guards exercise the actual JSON-manifest path, both CI and local absolute checkout forms, the bare retired root, unrelated qualified paths, directory/prefix lookalikes, filename/child-path suffixes, and retired artifacts/environment names elsewhere on the exact same JSON line. No historical manifest or negative acceptance expectation is edited. The repair receipt itself is part of the final repository naming audit; raw failing inputs and CI diagnostics remain available losslessly in compressed logs.

## Preservation, current checks and handoff

`preservation-proof.py` verifies every preexisting tracked path except the checker, its focused test and the authoritative naming document against the base Git blob. It separately verifies every prior performance receipt, the complete reviewed property-browser helper and actual qualified native/WASM/browser artifact hashes. No Rust, browser, Worker, build, ABI, runtime arena or package gate source changes. Qualified runtime evidence is reused because those sources and artifacts remain exact; no expensive runtime rebuild or fresh runtime qualification is claimed. The two historical native presentation limitations remain as previously recorded.

Current inventory and ownership checks accompany the naming tests. Inventory contracts, classifications, source hashes and all **685** review gaps remain unchanged, so no provenance-only inventory rewrite is needed. Mandatory full-worktree pre-commit, Ruff check and Ruff format check run before commit. `run.py` stores exact argv, environment, stdout/stderr bytes via gzip, exit and timing; command names are append-only. All four job logs are preserved, with no flake diagnosis or CI rerun claim.

`evidence.json` binds source hashes, preservation/artifact proof, exact command records and the source binary/full-index diff. The final handoff provides complete committed incremental and whole-PR binary/full-index diff hashes, avoiding self-referential receipt digests. A **new independent final review remains parent-owned before push**. This implementation evidence is not that review and makes no issue-closure, main-acceptance or publishing claim.
