# Native-input pointer parent sync and exact fixture naming policy — 2026-11-04

Normal local merge with two parents:

- Qualified R5 native-input repair checkpoint
  `b574038e9b00a1e85a4355e63770ec05c8cd5642`.
- Independently approved controller parent
  `c3013b30bf97ce63b1f381a71d4ca1be38e75427`.

Worktree `/home/ubuntu/.t3/worktrees/xyg/t3-5009d7d3`, branch
`t3/graph-pointer-selection`, human author David Spencer. This is a normal
merge, not a rebase, history rewrite or pointer import into the controller.
No root, push, PR, review-thread, queue, credential or issue mutation occurs.
The parent owns new independent final review and all later existing#1092 actions.

## Conflicts and status resolution

`merge.command.json` records actual `git merge --no-commit --no-ff c301...`,
exit1. Exactly the anticipated two conflicts occurred:
`spec/design/graph-interaction.md` and
`spec/releases/0.6.0-api-inventory.json`. Raw conflict bytes are archived as
`*.conflicted.txt.gz`; `conflict-stages.txt` binds the original stage blob ids.
`incoming-browser.patch` preserves the clean browser-design merge.

The graph status/S5 row imports actual #1090 property-default main landing
`7c751db1ba216005fe0f3eaf81922d44b4d01157` at2026-11-04 03:26:23Z and retains
bounded **primary-click/keyboard** implementation status. The native-input
contract/limitations remain exact to b574. Final native-input repair review,
#1091 main acceptance, broader S5b/S6/S7 and #36/M4/#108 remain outstanding.
The historical property FAIL versus later6 pair PASS distinction and earlier
#1089 actual main landing remain intact. No parent keyboard-only snapshot
replaces pointer facts. `browser-wasm.md` imports the same actual-main status
and explicitly retains primary-click scope and pending final repair review.

The API inventory is regenerated officially from the resolved working tree.
Only sourceProvenance/sourceSha256 differ from b574; all contracts,
classifications,685 gaps and preparation-only/unaccepted-freeze status remain.
No capability-matrix source change is needed in this sync; its official check
passes against the current native-input capability contract.

## Concrete audit blocker and authorized policy repair

The initially required full naming suite has **1 failed/116 passed**; the
standalone whole-repository audit finds80 matches. These raw failures remain
unchanged in `naming-tests*` and `naming-whole-repository*` command records/logs.
The matches are literal DOM tag names in five immutable browser JSON reports,
not product branding. No historical receipt or failed audit output is renamed,
annotated, escaped, compressed in place, reconstructed or otherwise rewritten.

After consulting the parent about this concrete blocker, the parent explicitly
authorized a narrow occurrence-level exception, meaningful positive/negative
coverage and the corresponding naming-spec update. This is an additional
**source-policy change requiring final independent review**, not a claim that
the sync changes only the original two metadata paths.

`scripts/check_stale_names.py` retains its existing predicate-per-match scan.
Only the current-product-brand match whose start is the start of an exact
case-sensitive, double-quoted JSON tag-field value is exempt, only in `.json`
browser evidence under `spec/performance/`. The two exact DOM names are
`"XY-SLOT-FIXTURE"` and `"XY-INNER-SLOT-FIXTURE"`. <!-- xyg-stale-name: allow - exact historical test DOM values -->
The literal key must be `"tag"`; indentation/JSON horizontal whitespace may vary.
No whole-line/file/history/JSON exemption, broad value prefix, case folding or
other naming-needle change is introduced. A quoted substring inside an escaped
JSON message is not a tag field. Other brand matches, including ones adjacent
to the allowed value on the same line, and all retired ABI/environment needles
continue through the original guards. The authoritative naming policy explains
why these test element names are not product branding.

The32 added tests cover both names, indentation and JSON spacing; other keys,
locations/extensions; mutated/suffixed/prefixed/case/punctuation lookalikes;
escaped non-field text; and adjacent standalone brand, native ABI/path and env
names on the same line/file. Lowercase/word-prefixed values can lack the
existing uppercase standalone brand needle; tests prove predicate refusal
without inventing a new restriction or changing the old needles.

`naming-tests-final` passes all149 naming tests and
`naming-whole-repository-final` passes the standalone whole-repository audit.
The original117 cases remain unfiltered. Failed earlier logs are preserved.

## Exact production/artifact/proof and history preservation

`before-sync.json` binds both complete Git trees, qualified301 producer inputs,
15 actual artifacts and protected source hashes. `preservation.json` records
the initial metadata-only resolution before the separately authorized naming
policy change. `preservation-final.json` and
`resolved-metadata-and-policy.patch` bind the final six nonreceipt paths:

- `spec/design/graph-interaction.md`, `spec/design/browser-wasm.md` and the
  officially regenerated API inventory: current main metadata plus retained
  pointer facts.
- `scripts/check_stale_names.py`, `tests/test_stale_names.py` and
  `spec/design/xyg-naming.md`: the explicit authorized naming-policy repair.

All other2793 preexisting nonreceipt files, including production/build/tests
for the native-input runtime, remain exact to b574. Every historical file of
both parents is checked against its Git blob: b574 has9682 files, c3019174,
and their unique union9727. The union digest in `preservation-final.json`
binds all actual SHA256 values; original27/P1/motion/slot failures, new native
input baseline failures, qualified69 proof and incoming controller logs remain
byte-exact. Current sync files are append-only additions.

All301 qualified R5 production inputs and15 actual artifacts are byte-identical
across this merge/policy change. Runtime evidence is reused **only** on that
identity:69 real strict-CSP browser journeys, the new native-coordinate
19-request/17-SelectAt capture/full native/WASM/browser XYGR replay,26 wire/
shipping tests,88 focused contracts and full unfiltered foundation. No fresh
post-sync runtime/browser/build or Rust compilation is claimed. Naming policy
is outside those runtime producer inputs and has its own fresh tests/audit.

Core/native SHA256
`3a9b78c81a078e13a78779add5a0e8ad5949d0483a828f483c060840e1e495c6`, raw WASM
`3f53a4747010f6cfc9e7f308c73d35a81d68cd2f6ffecaafb1860aa3cf9053b0`, optimized
module`6ebbdb7f7e6859ad9a08bd2c0237c62aaa6147df8c683b080959b42e7d2fb273`
remain actual exact qualified bytes. Size1922723 raw /783181 Node22 gzip6;
unchanged1878/765KiB gates leave349/179bytes. ABI399/WASM35/GPUv1/Scene34/
painter17, protocol, arenas, package gates, compiler/profile/optimizer/
dependencies/exports/guards/tolerances and canonical rendering remain unchanged.

## Fresh checks and review handoff

| Recorded check | Actual result |
| --- | --- |
| `merge` |Expected exit1/two archived metadata conflicts; resolved normally |
| `inventory-write-final`, `inventory-check-final` |Official provenance/body hashes current;685 gaps retained |
| `metadata-tests` |61 metadata/ownership/WASM-generator tests pass |
| `naming-tests-final` |149 pass, original117 plus32 precise policy cases |
| `naming-whole-repository-final` |Standalone full audit passes |
| `capability-check` |Official generated capability metadata current |
| `ownership` |508 tracked production files classified; pass |
| `native-declarations` |ABI399/538 symbols current |
| `wasm-declarations`, `typecheck` |WASM declarations and Python typing pass |
| `preservation-final` |Both histories, protected files,301 inputs/15 artifacts exact |
| `hooks`, `ruff-check`, `ruff-format` |Mandatory all-files/full-worktree checks before merge commit |

Each command record includes exact argv/cwd/environment/timing/exit plus raw
combined/stdout/stderr hashes. `proof-inputs.json` binds final source/commands
and nonreceipt full-index diff SHA256 versus c301. Whole/full-index and
nonreceipt diff hashes versus c301 are emitted with the committed handoff;
there is no self-referential receipt hash claim.

Reproduce using Node22 from
`/home/ubuntu/.t3/worktrees/xyg/t3-1b0dd836/target/task-tmp/node-v22.23.4-linux-x64/bin`
on PATH, with exact argv in the records and fresh output labels. In particular:

```bash
uv run pytest -q tests/test_stale_names.py
uv run python scripts/check_stale_names.py
uv run pytest -q tests/test_release_inventory.py tests/test_verify_ownership.py tests/test_gen_wasm_abi.py
uv run python scripts/check_release_inventory.py
uv run python scripts/gen_capability_matrix.py --check
uv run python scripts/verify_ownership.py
uv run python scripts/gen_abi_manifest.py --check
uv run python scripts/gen_wasm_abi.py --check
uv run ty check python
uv run --with pre-commit pre-commit run --all-files
uv run ruff check .
uv run ruff format --check .
```

The inherited R5 precision/capability limits are unchanged: native reported
browser precision, strict public effective zoom1, Chromium156/software/small
fixtures, no universal closed-root introspection or subpixel/cross-browser/
scale/competitor claim. SelectionTooLarge remains a labelled pre-execution
seam; the actual10001-source fixture still reaches initialization Budget.
Broader hover/picked-target/gesture/public-host/S5b/S6/S7/#36/M4/#108 and final
review/CI/publication acceptance stay open. Parent final independent review
must assess both the native-input repair and the explicit naming-policy diff
before any root integration/pre-push hooks/push to existing#1092.
