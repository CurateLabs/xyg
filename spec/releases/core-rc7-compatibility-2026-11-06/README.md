# Authentic Core rc.7 compatibility coverage (#936 / #108)

This receipt adds tested **Core 0.6.0-rc.7** coverage. It reserves no XYG
candidate, freezes no artifact cohort, and claims no stable Core 0.6.0.
Core #1096 remains open (live read 2026-11-06). #1097's declaration validator
was already merged; real artifact/schema qualification is separate evidence.

## Artifact and source identity

Core tag `v0.6.0-rc.7` is annotated tag object
`7c4352274161a7a811cc2baa2241db4b3e9bc74c`, resolving to
`f871a2a1c2a397d8d74dfabcede611f3b5e5f906`.
The npm facade and Linux x64 GNU addon were downloaded read-only from the
public registry. Their SHA-512 integrity values were recomputed over the
actual tarball bytes before extraction. Exact URLs, SHA-256, integrity,
generator, Node version and hashes of all 112 produced IPC files are in
[the generation receipt](../../../tests/fixtures/graphforge/results-0.6.0-rc.7/generation.json).
Retained registry attestation responses bind both SHA-512 subjects to that
same source commit. These checks decode and cross-check the published SLSA
statements; they do not claim independent Sigstore signature verification.
Tarballs remain in this worktree's ignored `target/core-compat-artifacts`;
redownload their exact URLs and verify integrity to reproduce elsewhere.

Core's actual Rust descriptor and schema registry was exported at that commit
with `scripts/sync_graphforge_contract_corpus.py`. Its 96 contracts are
byte-identical to rc.5's corpus. Rust verifies their canonical fields against
both the runtime ledger and new real IPC. No production Rust ledger/admission
repair or ABI change was necessary; the Rust change only extends a test.
A final-source native rebuild produced the same SHA-256 as the qualified
native library, preserving the earlier host/ABI proof against identical bytes.
The original 0.5.2 and rc.5 corpora and generator remain unchanged.

The first run of the frozen old generator produced 110 fixtures and two
failures, retained here in `initial-manifest.json` and `initial-generator.log`.
Core rc.7 changed `cluster` to an options-object API. The dedicated rc.7
generator supplies `directed` and `vectorProperty` by name, yielding all 112
fixtures with no failures. No manifest was edited to suppress those failures.

## Qualification and bounds

`checks.json` binds commands, source files, artifact hashes and raw logs.
The qualification covers all 96 algorithms plus find on Python and Node,
and byte-identical native/WASM documents for that catalog. Existing unsupported
schema tests cover stable `GF_RESULT_SCHEMA_VERSION` errors, schema/version,
next action, table bypass rejection and absence of row identities. Native/WASM
error documents are compared byte-for-byte. The normal WASM producer passed
its unchanged optimization, ABI and size gates. No resource/tolerance/size
limit was relaxed. The release-contract tests accept declared rc.7 and reject
unqualified rc.6 and final 0.6.0; this is declaration validation, not installed
XYG release-cohort proof. This evidence is Linux x64 GNU, not all platforms,
packaged notebook/browser interaction, or a published XYG pairing.

## Remaining acceptance

- #108/#884 still need maintainer selection of actual unused XYG and compatible
  Core candidates, exact packaged artifacts and the complete release matrix.
  Later Core packed candidates and final 0.6.0 are not qualified here.
- Editor #90 remains OPEN. Main `019bc09cb5153c2c840e6c4da375f91bf3229830`
  has no `docs/engineering/RESULT_SCHEMAS.md`, but open PR #85's branch
  `issue-80-typed-canonical-projection`, commit
  `9f7aa389a75c5055a3aa6512c527bae27ede5c76`, still authors the ledger and
  says XYG vendors it. `editor-ledger-snapshot.md` preserves the live file.
  Deletion/pointer conversion and coverage-only testing of the actual editor
  integration remain external acceptance; absence on pre-integration main
  does not prove rollout. No external repository was mutated.
- Shared `spec/api/graphforge-integration.md` and `spec/design/host-parity.md`
  were intentionally not edited for this task. The parent should add rc.7
  exact coverage and this receipt to their compatibility sections when the
  notebook worker's scope has settled. Accepted-main changes to those files
  entered only through the normal merge.
- Parent owns independent final review, CI and queue. None of #936/#884/#108
  is closed by this preparation. No push, publication or GitHub mutation occurred.

## Reproduce

Use Node 22.23.4, the repository Rust toolchain and `uv` project environment.
The six optional Dunamai tests were rerun with `uv run --with dunamai`; the
final release-contract run has 153 passes and no skips. Python has 24 passes,
Node/WASM 66 passes with no skips, and ABI smoke has 673 passing checks.
Download/verify/extract the two exact packages from `generation.json` into
`target/core-compat-artifacts/node_modules/@curatelabs/`. Then:

```sh
node scripts/gen_graphforge_rc7_result_fixtures.cjs "$PWD/target/core-compat-artifacts/node_modules/@curatelabs/graphforge" target/core-rc7-regenerated
# UUIDs are freshly minted: new runs are semantically equivalent, not byte-identical.
# Compare contracts/failures, then qualify the new coherent results and bases together.
python3 scripts/sync_graphforge_contract_corpus.py --core-repo target/core-compat-source --output tests/fixtures/graphforge/core/0.6.0-rc.7
cargo test -p xyg-engine graphforge::ledger::tests::pinned_core -- --nocapture
cargo build --release
node js/build.mjs
npm run build:wasm
uv run pytest tests/test_graphforge.py tests/test_graphforge_contract_corpus.py tests/test_release_version.py tests/test_check_release_version.py tests/test_verify_release_cohort.py -q
XYG_NATIVE_LIB="$PWD/target/release/libxyg_core.so" node --test packages/xy-node/test/graphforge.test.mjs packages/xy-node/test/graphforge-wasm-parity.test.mjs
make check-ci
uv run --with pre-commit pre-commit run --all-files
uv run ruff check .
uv run ruff format --check .
```

For corpus reproduction, `target/core-compat-source` is a local read-only source
object store initialized under this worktree and fetched from
`https://github.com/CurateLabs/graphforge` at the exact commit above. CI uses
its existing sparse Core checkout with full history, now pinned to rc.7, and
checks all three retained corpora. Binary artifact and hash-bound text bytes
have explicit LF checkout attributes, covered by the Windows conversion test.

Verify retained source/log bindings from the repository root:

```sh
python3 - <<'PYCODE'
import hashlib, json
from pathlib import Path
r = json.loads(Path("spec/releases/core-rc7-compatibility-2026-11-06/checks.json").read_text())
for p, expected in r["sourceSha256"].items():
    assert hashlib.sha256(Path(p).read_bytes()).hexdigest() == expected, p
for c in r["checks"]:
    assert c["exitCode"] == 0
    assert hashlib.sha256(Path(c["log"]).read_bytes()).hexdigest() == c["sha256"], c["name"]
print("source and raw-log hashes verified")
PYCODE
```
