# Host-neutral architecture — implementation plan

**Status:** plan locked for execution. Product invariant: **Python exists
only when the user is using Python.** Rust core + a thin Python host *or* a
thin Node host + one shared TypeScript WebGL paint client. Not a mandatory
three-stack. Embedding the paint client in the Python wheel for notebooks,
`to_html()`, and Reflex is required and stays.

**Tracking issue:** [#24](https://github.com/CurateLabs/xyg/issues/24).
In-repo pointer: [`issues/host-neutral-architecture.md`](issues/host-neutral-architecture.md).

This plan sequences existing issues. It does not replace
[tier3-phase4-roadmap.md](tier3-phase4-roadmap.md) (#5) or the fork-hygiene
epic (#12). Those stay their own epics; this document is the cross-cutting
host / identity / store / client-packaging graph.

---

## 1. Product invariant

| User | What they install | What they must not need |
| --- | --- | --- |
| Python (notebooks, pyplot, Reflex, `to_html`) | Python distribution (`pip install`; name in #13/#18) | Node, npm, or a CDN at install/export time |
| JS / browser | `@curatelabs/xyg` | Python runtime or `python/xy/` as the ship vehicle |
| Node / VS Code | `@curatelabs/xyg-node` (loads the same `libxyg_core`) plus the paint client for HTML/webview | Python package tree |

Three **runtime surfaces** remain ([host-parity.md](host-parity.md) §0). The
bug is treating the Python wheel as the only way to obtain the shared client
or the native engine.

### What stays Python forever

- Composition API (`python/xy/components.py`) and the matplotlib shim
  (`python/xy/pyplot/`).
- Reflex integration (`python/reflex_xy/`) — may keep linking
  `xy/static/index.js` from the *installed Python package*.
- Notebook / anywidget / `Chart.to_html()` embedding a **copy** of the paint
  client inside the wheel.
- Host ergonomics: ingest coercion, error-message text, transport attach.

### What must not stay Python-owned

- Canonical f64 column store and streaming append → Rust `stream.rs` (#22).
- Paint-client *ship vehicle* → host-neutral artifact that Python copies
  into the wheel (#23).
- Layout / LOD / encode / recorded §28 decisions → already Rust
  ([host-parity.md](host-parity.md) REQ-HOSTPARITY-1b).

Host leftovers such as facet composition and polar-bar *assembly* are
called out in [dual-host-parity-matrix.md](dual-host-parity-matrix.md) /
[rust-engine.md](rust-engine.md) but have **no dedicated issues**; they are
out of this plan until filed.

---

## 2. Locked public names (CurateLabs / XYG)

Do **not** publish `@xy/node`. That name is upstream-adjacent and is not
this product. Public names follow the org + product the repository already
chose: **Curate Labs** and **XYG**.

| Surface | Public name | Owner issue | Notes |
| --- | --- | --- | --- |
| Paint client (npm) | **`@curatelabs/xyg`** | #23 (publish the artifact); #13 (npm org / registry) | JS/browser front door: `npm install @curatelabs/xyg`. ESM `render` + IIFE `standalone.js` / `window.xy` (global rename is #18 if the product global becomes `xyg`). |
| Node host (npm) | **`@curatelabs/xyg-node`** | #13 / #18 (identity + native packaging); #23 (toHtml consumes `@curatelabs/xyg`, does not own native `.so` lookup) | Replaces in-tree `"name": "@xy/node"`; never publish `@xy/node`. Thin koffi host; must not import browser APIs. |
| Safe Rust crate | `xyg-engine` | #18 | Algorithms and deterministic policy. |
| C ABI crate / artifact | `xyg-core` / `libxyg_core` | #18 | One cdylib for Python and Node. |
| Python distribution | **`xyg`** | #13 / #18 | `pip install xyg`. Not upstream `xy`. Import remains `xy` until the staged `python/xyg/` cutover. |
| Python import | `xy` or `xyg` | #13 / #18 open question | Time-bounded alias vs clean break; does not change the product name XYG. |

**Why two npm packages.** Isolation in host-parity §0: the Node package must
not import `window` / WebGL / DOM; the browser client must not import
`koffi` / `node:fs`. One TypeScript source tree (`js/src`) still builds the
paint client; the Node host stays a separate package that *depends on* or
*inlines* `@curatelabs/xyg` for `toHtml` / VS Code webviews.

**Why `@curatelabs/xyg` is the paint client.** That is the JS product door
matching `pip install xyg` on the Python side. `@curatelabs/xyg-node` is the
Node-shaped host (native ABI + composition), the owned replacement for
`@xy/node`.

**Operational prerequisite (not a product-name question):** Curate Labs must
own the npm scope `@curatelabs` before a real publish. Record that under #13;
do not invent `@xy/*` as a fallback.

In-repo directories (`packages/xy-node`, `js/src`, `python/xy/`) may keep
current paths until #18’s mechanical rename; **published** `package.json`
`name` fields must use the table above.

---

## 3. Issue clusters (no duplicates)

Searched open + recently closed issues. No merge/close: overlapping work is
related, not the same acceptance criteria.

| Cluster | Issues | Job |
| --- | --- | --- |
| Identity / crate split | **#18** | XYG name, `xyg-engine` / `xyg-core`, one ABI, Node `.so`/`.dylib`/`.dll` lookup |
| Publish identity | **#13** (parent #12) | PyPI/npm names, tag line, publish guards (guards already in #20). **Names** here; **shipping packages** in #18/#23 |
| Docs / branding links | **#14** (parent #12) | Retarget `reflex-dev/xy` URLs. Overlaps README with #23’s npm door — different job |
| Canonical store | **#22** | Rust `stream.rs` + `xyg_stream_*`. Not npm, not crate split, not tile spill |
| Host-neutral client | **#23** | Paint-client artifact + npm `@curatelabs/xyg` + Node `toHtml` + spec/README doors |
| Ownership enforcement | **#56** | Exhaustive file ledger + stdlib-only CI gate; no language-ratio target |
| Generated host bindings | **#57** | Typed ABI contract generates ctypes and Koffi declarations; retains one cdylib rather than PyO3/napi-rs artifacts |
| Canonical scene/export | **#58** | Move shared scene, layout, tick, geometry, and static-export construction into Rust; keep host API shells |
| Direct browser engine | **#59** | Compile the same Rust engine to WASM in a Worker; keep TypeScript paint/pick/gesture/lifecycle |
| Phase-4 tile spill | **#5** → #7 (done), **#8**, **#9**, #10, #11 | Derived cache spill. Append = dirty *tiles*, not owning the f64 store |
| Fork CI hygiene | #12, #15, #16, #21 | Not on this architecture critical path |

Draft PR **#19** is the paused WP1 implementation of #8 against today’s
`src/` layout. It must be re-landed inside `crates/xyg-engine` after #18.
It does not close #8 until that re-land.

---

## 4. Dependency order (why)

```text
#13 remaining names ──coordinates──► #18 crate split + XYG identity
        │                              │
        │ npm scope / names            │ blocks re-land of PR #19 / #8
        ▼                              ▼
#23 @curatelabs/xyg artifact      #8 WP1 tile store ──► #9 WP2 hosts
   (in-repo + toHtml now;            (parallel with #22 after #18)
    npm publish after names)                    │
                                                ▼
#22 stream.rs  (not blocked by #18;             #10 WP3 (optional)
 prefer after #18 to avoid a double             #11 WP4 (alongside #8/#9)
 move of src/). Node owning the same
 f64 store needs this. #23 does not.
```

### Hard blocks (GitHub `blocked by`)

| Issue | Blocked by | Why |
| --- | --- | --- |
| #8 WP1 re-land | **#18** | PR #19 is paused: the crate split moves the whole Rust tree. Re-land inside `xyg-engine`, do not merge #19 onto pre-split `src/`. |
| #9 WP2 hosts | **#8** | Spill engagement binds the WP1 ABI ([tier3-phase4-roadmap.md](tier3-phase4-roadmap.md) WP0 → WP1 → WP2). |
| #10 WP3 client cache | **#8** | Tile-keyed cache needs `(level, tx, ty)` on the wire from WP1. Optional after that. |

### Not hard blocks (do not mash)

| Pair | Relationship | Why |
| --- | --- | --- |
| **#8 vs #22** | Parallel after #18 | Spec: #22 is the canonical f64 store (rust-engine.md §5). #8 is derived pyramid *spill* (Phase-4 D1–D7). Dirty-tile on #8 is the spill-store consumer; dirty-tile on #22 is in-RAM pyramid + stream handle. Prefer #22 first when both are free so WP1 fetch can read through the stream handle; **do not** delay re-landing #19/#8 on #22 — #19 already implements spill against host-owned buffers. |
| **#23 vs #22** | Unrelated | Packaging vs column store. npm client path must not wait on `stream.rs`. |
| **#23 vs #18** | Related | #23 owns the *client path*. Native `@curatelabs/xyg-node` `.so`/`.dylib`/`.dll` packaging is #18. In-repo host-neutral artifact + `toHtml` can land before the crate split. |
| **#23 vs #13** | Related | #13 owns *whether/under what name* a real npm publish is allowed. #23 implements the artifact and may use the locked names in-repo immediately. A registry publish waits on `@curatelabs` scope + #13 guards. |
| **#13 vs #18** | Coordinate, don’t cycle | Remaining #13 identity (Python dist name `xyg`, tag re-baseline) moves with #18’s naming matrix. Publish *guards* already landed (#20). |
| **#13 vs npm publish of packages** | Naming vs shipping | #13 does not implement `@curatelabs/xyg` or `@curatelabs/xyg-node`. #23 ships the paint client; #18 ships native Node lookup under `@curatelabs/xyg-node`. |

### Git coordination (not a semantic block)

#18 and #22 both rewrite `src/`. Prefer **#18 then #22** so `stream.rs` is
born inside `crates/xyg-engine`. #22’s own non-goal stands: the crate split
must not *block* stream.rs if #18 is stalled — land in current `src/` and
let #18 absorb the module.

---

## 5. Execution phases (issue = unit of work)

### Architecture conformance and completion

1. **#56** — classify every production source and enforce the ownership
   ledger. This is the gate for new architecture work, not a line-count quota.
2. **#57** — typed ABI manifest and generated low-level ctypes/Koffi/C-header
   declarations while preserving one shared C ABI artifact. **Implemented:**
   generated artifacts are byte-for-byte gated and loaders validate the
   version before binding the complete surface.
3. **#58** — move canonical scene/layout/export behavior into Rust in bounded
   slices; Python/Node retain ergonomic wrappers.
4. **#59** — add direct browser execution using the same Rust engine compiled
   to WebAssembly; the existing TypeScript client remains the painter and
   interaction layer.

These issues are native children of #24. They supersede the old assumption
that completing the crate split and paint artifact alone proved thin hosts.

### Phase 0 — Names (documentation + #13)

Lock the table in §2 on #13 / #18 / #23 (this document). Create or verify
the npm `@curatelabs` org. Do not publish `@xy/node`.

### Phase 1 — First unblocked slices (parallel)

1. **#23** — host-neutral paint client: `js/build.mjs` writes a non-Python
   artifact; Python wheel *copies* it; Node `toHtml` + demos + VS Code
   contract stop reading `python/xy/static`; README/`docs/overview/installation.md`
   document `npm install @curatelabs/xyg` beside `pip install`. Package
   `name` is `@curatelabs/xyg` even before a registry publish.
2. **#18** — crate split + XYG identity, including renaming
   `packages/xy-node`’s public name to `@curatelabs/xyg-node` and native
   library lookup. Do not start #22 on the same `src/` tree in parallel.
3. **#14 / #15 / #16 / #21** — fork docs and CI; not required for Phase 1
   architecture, but #14 should not fight #23 on README install snippets
   (npm door is #23; upstream-link retarget is #14).

**First recommended execution issue:** **#23** — independent of `stream.rs`
and of the crate split for the client artifact; makes the product invariant
true for JS users. If the immediate goal is unblocking Phase-4 WP1 instead,
execute **#18** first.

### Phase 2 — Canonical store

**#22** — `crates/xyg-engine/src/stream.rs` / `xyg_stream_*`, thin hosts,
in-RAM dirty tiles. After #18 (this branch); still future — do not land here.

### Phase 3 — Phase-4 spill (existing epic #5)

1. **#8** — re-land PR #19 inside `xyg-engine` (blocked on #18).
2. **#9** — Python + Node thin spill hosts (blocked on #8). Prefer the
   stream handle from #22 when it exists; do not expand #9 into owning
   `stream.rs`.
3. **#10** — optional tile-keyed client cache (blocked on #8). Uses the
   host-neutral client from #23; does not own packaging.
4. **#11** — evidence; runs alongside WP1–WP2; gates Phase-4 exit.

---

## 6. Spec files each phase must keep current

A change is incomplete while its spec is stale.

| Phase | Spec |
| --- | --- |
| Names / #23 | This file; [host-parity.md](host-parity.md) §0 location table + §5; dossier §33; [wire-protocol.md](wire-protocol.md); [dual-host-parity-matrix.md](dual-host-parity-matrix.md); README + `docs/overview/installation.md` |
| #18 | [rust-engine.md](rust-engine.md); dossier identity; [bazel-ci.md](bazel-ci.md); [production-readiness.md](../process/production-readiness.md) |
| #22 | [rust-engine.md](rust-engine.md) §2 / §5 / §6 (drop “still future”) |
| #56–#59 | [ownership-audit.md](ownership-audit.md); [rust-engine.md](rust-engine.md); [host-parity.md](host-parity.md); dossier browser/scene sections as each vertical slice lands |
| #8–#11 | [tier3-phase4-roadmap.md](tier3-phase4-roadmap.md); [lod-architecture.md](lod-architecture.md) |

---

## 7. Non-goals for this plan

- Implementing the refactor in the same change as this document.
- Closing #13 because publish guards landed — identity/rename remains.
- Merging #23 into #18 or #13.
- Promoting facet / polar-bar host leftovers (no issues filed).
- CDN-hosted paint JS, WASM-as-the-shipped-client, or a second renderer.
- Publishing under `@xy/*`.
