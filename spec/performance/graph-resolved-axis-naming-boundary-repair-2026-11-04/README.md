# Exact helper-token boundary correction

New repair from `47d4d6514671b12c8f263a3d640416af1983621c`. That attempt and its receipt remain immutable. Independent `s5a_final_review` requested changes on source diff `7598b93ec17f399a2b7dab33bdc291e95c5c99507630256e6d5482631be502e7`: the helper allowance treated punctuation as an implicit delimiter and accepted prefixed/suffixed lookalikes of the otherwise valid OSM entrypoint. The forwarded review request is archived losslessly in `review-request.txt.gz`; metadata and hashes are in `review-request.json`. This receipt records implementation disposition, not approval of the new candidate.

## P2 disposition and proof

**Reproduced, corrected, pending new independent review.** The previous blacklist of path characters was too permissive. The allowance now requires a complete path token bounded by the start/end of the line, spaces/tabs, string quotes or Markdown backticks. The existing auxiliary helper path and absolute checkout-prefix grammar remain the same. Punctuation such as plus, at, tilde, percent, equals, hash, colon, question mark and brackets no longer creates a boundary. No glob, URI, Windows normalization, broad whitespace rule or general path parser is introduced.

The existing core/engine/WASM/JS return branch remains identical. Scan targets, file/line allowlists, match patterns and other checker functions remain identical. There is no exemption for JSON, receipts or whole lines: bare retired ABI locations, unrelated qualified paths and retired identities elsewhere on the same JSON line still fail.

The new real JSON fixtures cover **63 punctuation lookalikes**: 21 punctuation characters at the prefix, suffix and suffix-with-text positions. They include all four concrete reviewer cases. Twelve positive text fixtures retain relative and actual absolute checkout paths in bare, quoted, backticked, space-separated and tab-separated forms; prior JSON-key positives remain unchanged.

- Before correction: **63 failed, 12 passed, 42 deselected**. Every new punctuation negative exposed acceptance by 47d4; the positive forms already passed.
- After correction: **75 passed, 42 deselected**.
- Complete focused suite: **117 passed**, including all prior 42 cases. The final standalone whole-repository naming audit, including this completed receipt, is recorded in its own command/log pair.

The full prior 42-case suite remains in place, including the retired root and same-JSON identity guards. `preservation.json` verifies unchanged AST bodies for every preexisting test/helper function. Source and raw failure logs preserve the actual negative inputs; they are not escaped or inserted into historical source manifests to bypass the gate.

## Preservation and qualification scope

`preservation-proof.py` verifies every preexisting tracked file except the intended checker, test and naming-spec edits against the base Git blobs. All historical receipts, including the entire rejected47 attempt, original historical source manifest and four original CI logs, remain byte-identical. The release preparation inventory is byte-identical, with all **685** gaps and classifications retained. Fresh inventory and ownership checks accompany this correction; no inventory rewrite is required.

Actual qualified native/WASM/browser artifacts are hash-verified against the prior manifest. No Rust, browser, Worker, native/WASM ABI, arena/runtime budget, package gate, build or runtime behavior changes. Prior qualified runtime evidence is reused by exact source/artifact identity; no runtime rebuild or qualification rerun is claimed. ABI398/WASM35/Scene34/painter17, the 1,838/751-KiB gates and the earlier native presentation limitations remain unchanged.

The preserved CI floor result remains **1 failed, 7699 passed, 358 skipped, 113 xfailed, 4 xpassed** for the old naming failure; no zero-skip, passing-CI or rerun claim is made. The new patch does not repeat CI or fix sibling branches separately. Parent owns any later integration into #1090.

## Reproduction and handoff

`run.py <fresh-name> <argv...>` retains exact argv, environment, exit, timing and losslessly compressed stdout/stderr with raw/gzip hashes. It refuses duplicate command names and disables environment-hook native/browser builds. `verified-files.json.gz` retains the verified per-file blob/hash ledger. `evidence.json` binds final sources, review request, command outcomes, preservation and source binary/full-index diff hashes; the final handoff separately includes complete committed incremental and whole-PR binary/full-index hashes without self-reference.

Run all of `tests/test_stale_names.py`, the standalone checker over the repository, inventory and ownership checks, then full-worktree pre-commit/Ruff before committing. The final naming audit includes the new receipt's text and JSON. No push, PR mutation, queue action, history rewrite, issue closure or publishing occurs. **A new independent final review remains required before the parent pushes.** Additional actual review findings received before the final candidate will be incorporated; the rejected47 review does not approve this corrected patch.
