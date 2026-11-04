# Property presentation synchronization with reviewed parent

Normal merge of reviewed parent `909dfe303b4f18f4b6332d9a4c13d68b7d2c3e74`
into the isolated property branch at
`7e99ec5da586572d411996599cf37f25dc5566c7`. This continues the independently
reviewed property implementation with metadata and append-only evidence only.
No production, worker, build, dependency, package-policy or test source changes.
The parent root branch/worktree is not switched or modified; no remote action,
push, PR update, queue entry, history rewrite or issue closure is performed.

## Parent identities and resolution

The new parent's parents are reviewed 8a5922af and accepted main
`3c66580731dde0b10a1f18465c0d0df9e73f8862`. Accepted main's tree
`b9f1a546159ca949b62bb644f90e3139b58ba9fb` is exactly reviewed #1088 source
60cee1e5. #1088 actually landed at 2026-11-04T00:40:06Z. This does not establish
that #1089 or #1090 has landed on main.

The parent reports completed `s5a_final_review` approval of 909dfe30. Its whole
binary/full-index PR diff against accepted main hashes to
`c28d535efe848bbf95995674b165653644bc4c7055a7c5710ee662ca1212bc4b`; excluding
performance receipts gives
`50f33afee6481e6db3c018ad00cf59bc0126028acc0ed39f80c783e2c7ea5ecc`.
`parent-review.json` verifies both hashes against actual local Git objects.

The parent also reports completed `m4_defaults_audit` approval of 7e99ec5d,
Greptile 5/5 without findings, and all 21 prior PR rollup checks complete with
applicable successes and ordinary conditional/disabled skips. These reviews
and checks are historical; this new integrated merge still needs a new
independent parent review and fresh PR CI after integration.

`git merge --no-ff --no-commit 909dfe30...` returned the expected conflict exit
1. Its separate raw stdout/stderr are preserved. The only conflict was the
preparation inventory's generation-time provenance commit. The property ABI399
contracts were retained, and the unchanged official inspector regenerated the
snapshot with base provenance 7e99ec5d. **Every other inventory field is exact
to 7e99**, including all source hashes, classifications, contract digest,
preparation-only acceptance and **685 explicit review gaps**.

The S5 roadmap merged cleanly and now records #1088's actual landing and its
historical 1,838/751-KiB P1 gates. S5b remains planned. Property presentation
specifications, ABI399 ownership entry and its human ledger, source
classification, S6 actual #1087 landing, and the current explicit property
**1,878/765-KiB** functionality gates stay unchanged. No new acceptance or
baseline freeze follows from this synchronization.

Only `spec/design/graph-interaction.md` and
`spec/releases/0.6.0-api-inventory.json` differ among existing nonreceipt files
compared with 7e99. `metadata-resolution.json` records exact identities and the
canonical nonreceipt metadata diff digest. Final committed whole and nonreceipt
diff hashes are returned separately to avoid a self-referential receipt hash.

## Complete source and historical preservation

`verify-preservation.py` proves all **2,787 tracked nonreceipt paths** outside
those two metadata files match 7e99 by actual Git blob identity. This protects
every Rust/Python/Node/browser/worker producer, build/configuration/toolchain/
dependency input, script, test, fixture, generated native/WASM declaration,
remaining specification and documentation file. No new nonreceipt path is added.

All **699** recorded shipping build inputs retain source SHA-256
`ab3ff61f3cd3769a89d5d1bbf31b28f99031a80e9d686a3ae93a8ee1fd134a53`.
The complete property browser helper is **20,079 bytes**, SHA-256
`7b91a3c01770205f4738ca9b64f00802245b4a196e86981c6c98a8e60b695c6f`,
byte-exact to 7e99, including ABI399 and every unchanged image/geometry threshold.

All **8,592** historical receipt files from 7e99 and all **8,320** from parent
909dfe30 match their Git blobs byte for byte. This includes the entire newly
imported `graph-resolved-axis-main-sync-2026-11-04` receipt and every property
failure, historical 99-case wording, appended 101-case erratum, qualified
shipping output, crosshost result and six unmasked pair screenshots. Historical
receipts retain their original source/ABI/package scope; importing the parent's
ABI398 qualification does not replace the property's ABI399 qualification.
`historical-preservation.json` records counts and bound manifest digests.

## Qualified artifact reuse

`source-artifact-preservation.json` hashes all **15 actual existing shipping
artifacts**, verifying byte equality to the actual production qualification at
81c9f7f1, preserved and independently reviewed at 7e99. Both package asset sets,
workers, manifests, inline bootstraps, native release library and unoptimized
WASM release target are exact. ESM remains
`3b194aebda9a2d8f30e0503f01310d944efb72edcca4701777a3c211803ddf70`;
IIFE remains
`bdce4a092184e0feb745ea4ebfc57b3929b5ca795d5ec968f9a678e233efeea8`.

| Artifact | Qualified actual bytes | SHA-256 |
| --- | ---: | --- |
| Optimized WASM | 1,922,561 | `e8011f779e70f58416a751f0067f279d1b9aa9515004c246e2f44c95af192651` |
| Shipping Node gzip6 | 783,148 | `d447f4e3f63a0b189f962d53cba34336224df6cb84e4cd5be7fa430f7366120a` |
| Native library | 6,108,248 | `e88b3f9458effea8f677d187e9e0e72fa4c3f26e43878c118aebf13494a37bad` |

Recompressing existing WASM bytes with the unchanged shipping Node 22.23.4
`gzipSync` level 6 reproduces the qualified compressed size/hash. The unchanged
raw/gzip6 gates are **1,923,072 / 783,360 bytes**, leaving **511 / 212 bytes**.
No additional budget is authorized. Native ABI399/WASM35/Scene34/painter17,
exports/imports, compiler/profile/optimizer, validation/guards and 16/384-MiB
runtime bounds remain byte-exact.

This is **reuse of qualified production and browser evidence by exact source
and artifact identity**, not a fresh actual native/WASM build, package run or
browser qualification. `reused-qualification.json` verifies original zero-exit
command records and compressed raw log integrity for the real producers,
shipping packager, **13 shipping tests with zero skips**, paired manifests and
inline assets, full unfiltered strict-CSP foundation, offline inline smoke,
two Python default-property helper cases, all **six whole-image unmasked pairs**,
all **101** preservation requests, 21 Python / 31 Node crosshost tests and 86
focused package/client tests. Geometry remains within .01px, with mean <3.5 and
fraction-over-96 <.01 thresholds unchanged. No performance claim is made.

## Fresh metadata validation and reproduction

- Ownership: PASS; **505** tracked production files classified.
- Native generated declarations: PASS; **538 symbols, ABI399**.
- WASM generated declarations: PASS; WASM35/Scene34/painter17 unchanged.
- Preparation inventory regeneration and default comparison: PASS; **685**
  explicit gaps, unchanged semantics and classifications, freeze unaccepted.
- Full Python source typing (`uv run ty check python`): PASS.
- Affected release-inventory, ownership and WASM-generator tests: **61 passed**.
- Mandatory full-worktree `uv run --with pre-commit pre-commit run --all-files`,
  `uv run ruff check .` and `uv run ruff format --check .`: PASS before the
  normal merge commit. These are named validation gates, not all repository or
  release acceptance.

`checks.json` binds all fresh validation exits and logs. Every command record
includes raw argv, cwd, environment, start/end time, exit and separate stdout /
stderr byte counts and SHA-256 hashes. Both raw streams are retained as lossless
`.log.gz`; ignored raw `.log` copies remain locally. No failure log is removed.
The expected merge conflict is preserved as exit 1.

Use the project UV environment and cached Node 22.23.4 path recorded in each
command. `run.py <fresh-label> <argv...>` refuses existing outputs; set
`XYG_SYNC_RECEIPT=<fresh-directory>` to reproduce checks elsewhere.
The preservation script writes beside itself and refuses existing proof names;
copy it to a fresh receipt directory and run from the repository root. No build
or expensive browser suite needs repeating while the complete identity proof
continues to hold.

Parent **new independent final review** is required before integration,
pre-push hooks, push, dedicated PR update and fresh CI. The implementer does not
approve the new integrated candidate. No #1090 main acceptance, #935
intent/digest/safe-pair closure, #934 closure, #36 S5b/S6/S7 completion, M4 or
#108 acceptance, freeze or publication is claimed.
