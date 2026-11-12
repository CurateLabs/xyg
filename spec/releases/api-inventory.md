# Source API inventory for 0.6 preparation

The [machine inventory](0.6.0-api-inventory.json) records the current declared
surface for [#108](https://github.com/CurateLabs/xyg/issues/108). It is preparation
for review, not an accepted API freeze or a publication decision. Its base commit
identifies the checkout's parent; its SHA-256 source records identify the actual
working-tree bytes read at generation, including uncommitted changes.

The issued paged-source continuation intentionally adds `ChunkedColumns.column`
to the Python and Node declarations and a version field to Node's binary
`filterRequest` framing. Existing declarations remain present; the native-only
XYGC attach and remaining browser/global-budget work are specified in
[Filter Tier C](../design/filter-tier-c.md#issued-native-paged-sources-continuation).
This preparation refresh retains the 698 explicit review gaps and does not
accept a freeze or qualify the complete filtering milestone.

```bash
npm ci
uv run python scripts/check_release_inventory.py
uv run pytest tests/test_release_inventory.py -q
# After reviewing intentional declaration changes:
uv run python scripts/check_release_inventory.py --write
# Additional acceptance prerequisite; currently fails on unclassified exports:
uv run python scripts/check_release_inventory.py --require-classified
```

The normal Python Test job already discovers the inventory tests. Its existing
`npm ci` installs the pinned compiler before tests. No new required job, status,
or runtime dependency is introduced. The inspector executes no XYG package or
native module: Python uses the standard-library AST, and JavaScript uses
the TypeScript version locked by `package-lock.json`. The pinned TypeScript 7
synchronous API is an inspection dependency, not a second API implementation.
A checkout without that compiler fails with the `npm ci` remedy.

## Authorities and coverage

| Surface | Export authority | Recorded declaration contract and review references |
| --- | --- | --- |
| Python `xyg` | `python/xyg/__init__.py`: `__all__` and `_EXPORTS` | Resolve lazy targets without importing them; record functions, annotations, positional/keyword defaults, overloads, class fields and their declaration order, declared methods and protocols, decorators, base references, and statically raised exception references. Public composition, examples, export, and interaction specifications retain behavioral authority. |
| `xyg.pyplot` | Its explicit `__all__` and local import targets | Same declarations, including exported Axes/Figure methods; [corpus compatibility](../matplotlib/compat.md) and `tests/pyplot/corpus/` define supported behavior, loud refusals, and differences. An accidental non-`__all__` module attribute is not promoted into a supported shim API. |
| Node | `packages/xy-node/package.json` export map, including every declared subpath | Compiler-resolved named exports and aliases, callable parameter/return types, declared class members, explicit defaults, and existing `.d.ts` declarations. Runtime JavaScript parameters and referenced literal default bindings are retained alongside `.d.ts` signatures where available. [Host parity](../design/host-parity.md) and the package README own loading errors, ownership, and supported-host behavior. |
| Browser | `js/src/60_entries.ts` and the browser package export map | Compiler-resolved value/type exports, typed signatures, defaults, class members, interfaces and aliases. [Browser API](../api/browser-wasm.md), [design](../design/browser-wasm.md), and WASM conformance own Worker ownership, cancellation, disposal, error codes, CSP, and offline requirements. Worker/WASM asset entrypoints are package exports, not invented JavaScript functions. |
| Native C ABI | Generated [JSON manifest](../abi/xyg-abi.json) and [C header](../abi/xyg.h) | Symbol inventory, ABI version, and the generator's signature digest reference the canonical signatures and pointer/return metadata without duplicating generated declarations. Run `scripts/gen_abi_manifest.py --check`; never hand-edit those authorities. These are internal exact-match contracts. |
| CLI and builds | `pyproject.toml` project scripts and Hatch hook mappings; documented repository operator scripts | Installed CLI entrypoints, hook source paths, and declared operator argument names/options/default expressions. The project currently declares no installed `[project.scripts]` CLI. Repository maintenance scripts are not silently advertised as installed product commands. |
| Environment configuration | Source environment lookups in shipped Python/Node/Rust code and `hatch_build.py` | Names, direct lookup defaults and source references; documented browser-discovery constants are included. `XYG_ABI_TRACE_*` diagnostics and `CODSPEED_ENV` benchmark controls remain internal; the Rust SIMD kill switch is included. Build/development/export controls retain their actual scope; a raw lookup default is not a claim about every downstream effective behavior. |

Rust environment inspection does not infer test-only ownership from directory or
module names. An external fixture is omitted only when its source starts with
the exact module-wide inner attribute `#![cfg(test)]` followed by a newline.
That actual guard excludes the entire module outside tests even under an
unconditional parent declaration. Missing, changed, outer, commented or otherwise
unrecognized guards are scanned conservatively; production modules under a
`tests/` directory remain inventoried. Existing inline `#[cfg(test)] mod` handling
is unchanged. The [R7 review disposition](../performance/graph-picked-target-r7-2026-11-04/README.md)
records positive/negative regression proof and the preserved P2 reproduction.

Python typing remains source annotations plus `py.typed`; the inspector does not
manufacture stubs. Node declarations may be inferred JavaScript types or existing
`.d.ts` contracts; callable `any` positions are recorded as review gaps. Browser
type exports retain their actual TypeScript declarations. Shared definitions use
source-file/symbol references, so multiple exports/subpaths do not copy the same
contract. Generated JSON is compact and deterministic; inspect records directly:

```bash
jq '.contracts.surfaces["xyg"].symbols[] | select(.name == "scatter")' spec/releases/0.6.0-api-inventory.json
jq '.contracts.definitions["python/xyg/components.py#scatter"]' spec/releases/0.6.0-api-inventory.json
jq '.contracts.surfaces.node.symbols[] | select(.status == "stable")' spec/releases/0.6.0-api-inventory.json
jq '.gaps' spec/releases/0.6.0-api-inventory.json
```

## Classification and limits

Classification records existing promises, with their evidence, rather than
inventing stability from an export. The currently published Python composition
posture is experimental. Reflex is unsupported and excluded under #1063. The Node README explicitly promises a
stable `createEngine`/chart-builder API; its named chart constructors and engine
alias carry that evidence. Native-loader code sets carry the explicit stable
code promise in host parity. Other exports remain **unclassified** unless their
own declaration explicitly marks them experimental. Classification does not
waive a required capability or acceptance journey. Apply the
[compatibility policy](compatibility-policy.md) when accepting the final list.

The inventory's `gaps` are part of its output. Inherited APIs are referenced by
base rather than exhaustively expanded. Dataclass/NamedTuple-generated methods,
computed runtime exports, prototype augmentation, indirect returned objects,
non-root Python submodules, and transitively referenced unexported type aliases
need their owning types, source, and conformance evidence. A static signature
cannot establish value-dependent defaults, result validity, error wording,
callback effects, resource ownership, event ordering, accessibility, or cleanup.
Dynamic environment names beyond the explicitly discovered constants require
manual reconciliation. These limits prevent claiming a completed #108 freeze
from this preparatory declaration check.

`contractSha256` binds the semantic inventory. The checker rejects changed
exports, signatures, types, explicit defaults, class fields, operator options,
environment lookups, entrypoints, or the generated ABI declaration digest.
Implementation-only edits preserving those records can pass. The separate
`sourceSha256` records remain the bytes read at generation: passing a semantic
check after a body-only edit does **not** make the old byte hashes current and
cannot qualify an artifact/source freeze. Neither the snapshot nor a file that
embeds the snapshot is included in its source hash set, so generation has no
self-hash cycle.

After all APIs/ABI manifests settle, regenerate from the final candidate source,
review classifications and outstanding gaps, and retain it with that candidate's
exact package hashes and behavioral acceptance. Do not turn an older inventory,
retained Linux cohort, or successful declaration test into a final freeze claim.

The ABI 399 property-default preparation update records the private
`xyg_graph_semantic_chrome_rgba8` accessor (537 → 538 native symbols), its
generated ABI digests, and the compiler-resolved Node `ABI_VERSION` and
`assertAbiVersion` default changing from 398 to 399. The actual regenerated
inventory retains **685 explicit review gaps**; no classification was added or
changed. The [metadata repair receipt](../performance/graph-property-default-metadata-2026-11-03/README.md)
preserves both preceding repository-gate failures and the exact semantic delta.
This preparation snapshot remains unaccepted as a baseline freeze.


The bounded S5b attachment preparation adds the explicitly `@experimental`
`attachWasmGraphSession` value and its five exported option/handle/snapshot/camera/
load types. The regenerated inventory records those declarations and the actual
new source hashes; it still contains **685 explicit review gaps**. No existing
classification was changed to manufacture a freeze. Snapshot fields reference
internal semantic/ref types, and static declarations alone do not establish
keyboard timing, GPU validation, Worker ownership or complete behavioral
acceptance. The [helper API](../api/browser-wasm.md#experimental-retained-graph-session)
and [attachment receipt](../performance/graph-s5b-attachment-2026-11-04/README.md)
retain that scope. Broader S5b/S6/S7, #36/M4 and #108 remain open; this inventory
is still preparation, not an accepted API freeze or publication decision.

The S5b R2 preparation refresh records the required Rust Clear-applicability
fact and accepted snapshot's `clearAction.applicable`, plus the synchronous
keyboard admission/default timing and three-unit shared sampler isolation.
No existing classification or ABI signature changes. The actual inventory still
has 685 review gaps; transitive semantic types and runtime/module compatibility
continue to require the owning source and real browser proof. This is not a
stable/freezable baseline waiver. The [R2 receipt](../performance/graph-s5b-attachment-r2-2026-11-04/README.md)
retains the old-same-ABI fail-closed proof and explicit refusal timing contract.

The bounded primary-click preparation adds no public declaration or alias.
Existing experimental attachment snapshots/events now follow Rust SelectAt
with Replace/Shift Add/Ctrl-or-Meta Toggle and the documented CSS coordinate
admission boundaries. The refreshed inventory still has 685 explicit gaps and
remains unaccepted as a freeze; broader hover/gesture/public-host and S5b/S6/S7
acceptance are outstanding. [Pointer proof and limits](../performance/graph-s5b-pointer-selection-2026-11-04/README.md)
retain this distinction.

The narrow pointer motion-path repair refresh changes no declaration or
classification. Active CSS motion paths on the canvas or traversed/shadow
ancestors now reject pointer admission even when the transform matrix and
individual rotate are none. Ordinary no-path defaults remain eligible. The
[motion-path receipt](../performance/graph-s5b-pointer-motion-path-repair-2026-11-04/README.md)
records the source/artifact provenance and real regressions; the actual685 gaps
and unaccepted freeze/broader scope remain unchanged.

The narrow slotted-ancestor repair refresh adds no declaration or classification.
Pointer eligibility follows available assigned slots before light-DOM parents
and shadow-host fallback, applying existing guards to nested display wrappers.
Plain/scaled slots remain eligible. [Slot proof and disposition](../performance/graph-s5b-pointer-slotted-ancestor-repair-2026-11-04/README.md)
retain the actual failure/repair and source/artifact provenance; the685 explicit
gaps, preparation-only freeze and broader acceptance limits remain unchanged.

The native pointer-input repair preserves every API declaration/classification
and the685 preparation gaps. Trusted native event offsets at browser precision,
strict effective currentCSSZoom1 and conservative inspectable-ancestry guards
replace rectangle-derived coordinate mapping; closed roots do not certify
transform absence. This is a body/behavior provenance refresh, not an accepted
freeze or broader S5b/M4/#36/#108 acceptance. See the
[native input receipt](../performance/graph-s5b-pointer-native-input-repair-2026-11-04/README.md).

The #46 partial candidate adds experimental temporal composition declarations
and exact XYTM framing/compiler boundaries. Its preparation snapshot has689
explicit review gaps. This is not a release freeze or catalog acceptance;
[limitations and package blocker](../design/temporal-catalog.md) remain open.
