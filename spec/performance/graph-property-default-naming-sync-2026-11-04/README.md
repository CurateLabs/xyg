# Property presentation synchronization with reviewed naming repair

Normal merge of reviewed parent `46c2573c285075eeb03d651966b511c866bd2ffb`
into isolated property branch source
`9b05f31778f623a030ed96551d52ba5ae7a2196d`. The normal `--no-ff --no-commit`
merge completes without conflicts. Exactly three existing nonreceipt files
change: the naming checker, its tests and its authoritative naming specification.
All three are byte-exact to reviewed 46c2573c. No further metadata repair,
property behavior change, broad allowance or historical receipt edit is made.

The parent root branch/worktree is not switched or modified. No remote action,
push, PR update, queue action, history rewrite or issue closure is performed.

## Actual failure and reviewed repair

`naming-before.json` reproduces **exit 1** with the old checker on exact 9b05:
the source-preservation manifest at line 5679 contains a legitimate auxiliary
OSM helper path. It is evidence of a qualified source file, not a retired core
ABI location. Separate raw stdout/stderr, exact argv, environment and exit are
preserved losslessly. No manifest key is renamed, annotated, escaped or removed.

Actual CI on parent 909 and property 9b05 failed this same naming assertion.
The property floor reported **1 failed, 7702 passed, 358 skipped, 113 xfailed,
4 xpassed**; the aggregate release gate inherited dependency failures and wheel
jobs skipped. These remain failed historical CI runs, not passing qualification.
The two additional parent-supplied property CI logs are archived byte-exact in
`ci-job-126318615894.log.gz` and `ci-job-126322626934.log.gz`, with original
paths, byte counts and hashes in `additional-ci-logs.json`. The four earlier
CI logs already present in parent receipts also remain unchanged.

The parent reports final independent `s5a_final_review` approval of corrected
46c2573c, with no blockers. `parent-review.json` verifies the supplied whole PR
binary/full-index digest against accepted main 3c665807:
`7b27d371c25bbacc3199720a912c1b9075b80486a80e78c9fadb3966d2285812`.
It also verifies the source-only correction from initial repair 47d4d651:
`d3b8328ae10ff053a557a05aa65fb1799f404ec62c544653207eb24f3fb0c19d`.
The initial repair, its actual punctuation hole, rejected review and failing
guard results remain immutable historical evidence.

The imported checker allows only the documented complete auxiliary path token,
with explicit start/end, space/tab, quote or backtick delimiters and the reviewed
absolute-prefix grammar. Other punctuation does not create a token boundary.
Retired identities elsewhere on the same JSON line, unrelated paths and
lookalikes still fail. Source manifests, JSON files and receipts remain audited.
The exact reviewed tests include all **63 punctuation negatives**, **12 complete
token positives**, and the original 42 tests: **117 cases** total. No gate,
regression assertion, scan target or historical manifest is weakened locally.

## Fresh integrated checks

- Entire imported naming suite: **117 passed**, including the whole-repository
  test and all punctuation guards.
- Standalone whole-repository naming audit: **PASS**, including the new receipt
  text/JSON and all imported historical receipts.
- Release-inventory, ownership and WASM-generator tests: **61 passed**.
- Ownership audit: **505** tracked production files, PASS.
- Native generated declarations: **538 symbols at ABI399**, PASS.
- WASM generated declarations: PASS; WASM35/Scene34/painter17 unchanged.
- Full Python source typing (`uv run ty check python`): PASS.
- Default preparation inventory check: PASS. The complete snapshot is byte-exact
  to 9b05, retaining **685 actual gaps**, all classifications and
  `preparation-only-not-a-freeze`; no regeneration or freeze claim is needed.
- Full-worktree pre-commit `--all-files`, Ruff check and Ruff format check:
  PASS before the normal merge commit.

`checks.json` binds all fresh validation argv/exits and raw output hashes. This
is scoped local validation, not a new CI run or complete repository/release
acceptance. No multi-hour Python floor, native build, WASM build, shipping
packager or browser qualification is rerun.

## Complete source, artifact and historical identity

`verify-preservation.py` checks all **2,786 tracked nonreceipt paths** outside
the three reviewed naming files against 9b05 Git blobs. Every product Rust,
Python, Node, browser/Worker, build/configuration/toolchain/dependency input,
script, other test, fixture, wire declaration, property presentation spec and
roadmap is exact. No new nonreceipt path is introduced. `reviewed-import.json`
records actual hashes for the three exact imports and the unchanged **20,079
byte** property browser helper, SHA-256
`7b91a3c01770205f4738ca9b64f00802245b4a196e86981c6c98a8e60b695c6f`.

All **699 shipping inputs** retain source SHA-256
`ab3ff61f3cd3769a89d5d1bbf31b28f99031a80e9d686a3ae93a8ee1fd134a53`.
All **15 actual qualified artifacts** are byte-verified against the production
81 receipt, including paired browser/worker/manifests/inline assets and native
and WASM release targets. This is reuse of the actual 81 qualification preserved
through 7e99 and 9b05 by exact identity, **not fresh production/browser
qualification**. The original producer and qualification logs are checked for
integrity in `reused-qualification.json`.

| Artifact | Qualified actual bytes | SHA-256 |
| --- | ---: | --- |
| Optimized WASM | 1,922,561 | `e8011f779e70f58416a751f0067f279d1b9aa9515004c246e2f44c95af192651` |
| Shipping Node gzip6 | 783,148 | `d447f4e3f63a0b189f962d53cba34336224df6cb84e4cd5be7fa430f7366120a` |
| Native core | 6,108,248 | `e88b3f9458effea8f677d187e9e0e72fa4c3f26e43878c118aebf13494a37bad` |

Node 22.23.4 shipping `gzipSync` level 6 reproduces the qualified compressed
hash and size. Explicit **1,878/765-KiB** gates remain **1,923,072/783,360 bytes**,
with **511/212 bytes** headroom. ABI399/WASM35/Scene34/painter17, exports/imports,
validation/guards, compiler/profile/optimizer/dependencies and 16/384-MiB runtime
bounds stay exact. No additional budget or optimization is authorized.

Existing qualified evidence remains intact: **13 shipping tests / zero skips**,
paired assets and inline validation, full unfiltered strict-CSP foundation,
offline inline smoke, both default Python property cases, all **six unmasked
whole-image pairs**, all **101** preservation requests, 21 Python / 31 Node
crosshost tests and 86 focused package/client tests. Original mean <3.5,
fraction-over-96 <.01 and geometry .01px thresholds remain unchanged. No supplied
positions, mask, helper weakening or new layout pass is introduced.

`historical-preservation.json` checks every **8,682** historical receipt file
from 9b05 and every **8,409** from final parent 46c2573c, including shared history,
initial 47d4 failure evidence, its correction receipt, old property/package
failures, screenshots, current shipping proof and the historical case-count
erratum. Every file matches its original Git blob. Imported ABI398 parent
receipts keep their historical scope; they do not replace property ABI399 proof.

## Reproduction and handoff

The unchanged prior `graph-property-default-parent-sync-2026-11-04/run.py`
records separate raw stdout/stderr, argv, cwd, environment, times, exit and
raw/gzip hashes. Set `XYG_SYNC_RECEIPT=<fresh-directory>` and use a new label to
reproduce; existing outputs are refused. Raw `.log` copies remain locally and
are ignored; both raw streams are committed losslessly as `.log.gz`.
The preservation and CI archive scripts write beside themselves and refuse
existing outputs; copy them to a fresh directory before reproducing. Use project
UV and the cached Node 22.23.4 path recorded in command environments.

Final committed whole/nonreceipt binary/full-index hashes against both inputs
are returned separately, avoiding a self-referential receipt digest. Parent
**new independent sync review** is required before root integration, pre-push
hooks, push, dedicated PR update and fresh CI. The implementer does not approve
this integrated candidate. #1089 and #1090 main acceptance, controller work,
#935 intent/digest/safe-pair scope, #36 S5b/S6/S7, M4, #108, issue/milestone
closure, release freeze and publishing are outside this bounded synchronization.
