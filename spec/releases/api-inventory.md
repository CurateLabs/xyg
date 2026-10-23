# Source API inventory for 0.6 preparation

The [machine inventory](0.6.0-api-inventory.json) records the current declared
surface for [#108](https://github.com/CurateLabs/xyg/issues/108). It is preparation
for review, not an accepted API freeze or a publication decision. Its base commit
identifies the checkout's parent; its SHA-256 source records identify the actual
working-tree bytes read at generation, including uncommitted changes.

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
native/Reflex module: Python uses the standard-library AST, and JavaScript uses
the TypeScript version locked by `package-lock.json`. The pinned TypeScript 7
synchronous API is an inspection dependency, not a second API implementation.
A checkout without that compiler fails with the `npm ci` remedy.

## Authorities and coverage

| Surface | Export authority | Recorded declaration contract and review references |
| --- | --- | --- |
| Python `xyg` | `python/xyg/__init__.py`: `__all__` and `_EXPORTS` | Resolve lazy targets without importing them; record functions, annotations, positional/keyword defaults, overloads, class fields and their declaration order, declared methods and protocols, decorators, base references, and statically raised exception references. Public composition, examples, export, and interaction specifications retain behavioral authority. |
| `reflex_xy` | `python/reflex_xy/__init__.py`: explicit exports and lazy targets | Same declaration extraction; [integration design](../design/reflex-integration.md) and adapter fixtures retain registration, release, reconnect, and state-rebuild behavior. |
| `xyg.pyplot` | Its explicit `__all__` and local import targets | Same declarations, including exported Axes/Figure methods; [corpus compatibility](../matplotlib/compat.md) and `tests/pyplot/corpus/` define supported behavior, loud refusals, and differences. An accidental non-`__all__` module attribute is not promoted into a supported shim API. |
| Node | `packages/xy-node/package.json` export map, including every declared subpath | Compiler-resolved named exports and aliases, callable parameter/return types, declared class members, explicit defaults, and existing `.d.ts` declarations. Runtime JavaScript parameters and referenced literal default bindings are retained alongside `.d.ts` signatures where available. [Host parity](../design/host-parity.md) and the package README own loading errors, ownership, and supported-host behavior. |
| Browser | `js/src/60_entries.ts` and the browser package export map | Compiler-resolved value/type exports, typed signatures, defaults, class members, interfaces and aliases. [Browser API](../api/browser-wasm.md), [design](../design/browser-wasm.md), and WASM conformance own Worker ownership, cancellation, disposal, error codes, CSP, and offline requirements. Worker/WASM asset entrypoints are package exports, not invented JavaScript functions. |
| Native C ABI | Generated [JSON manifest](../abi/xyg-abi.json) and [C header](../abi/xyg.h) | Symbol inventory, ABI version, and the generator's signature digest reference the canonical signatures and pointer/return metadata without duplicating generated declarations. Run `scripts/gen_abi_manifest.py --check`; never hand-edit those authorities. These are internal exact-match contracts. |
| CLI and builds | `pyproject.toml` project scripts and Hatch hook mappings; documented repository operator scripts | Installed CLI entrypoints, hook source paths, and declared operator argument names/options/default expressions. The project currently declares no installed `[project.scripts]` CLI. Repository maintenance scripts are not silently advertised as installed product commands. |
| Environment configuration | Source environment lookups in shipped Python/Node/Rust code and `hatch_build.py` | Names, direct lookup defaults and source references; documented browser-discovery constants are included. `XYG_ABI_TRACE_*` diagnostics and `CODSPEED_ENV` benchmark controls remain internal; the Rust SIMD kill switch is included. Build/development/export controls retain their actual scope; a raw lookup default is not a claim about every downstream effective behavior. |

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
and Reflex posture is experimental. The Node README explicitly promises a
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
