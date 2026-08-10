# Host parity — Python and Node

**Status:** requirements / architecture intent for **graphforge-xy**, the
visualization extension of [core GraphForge](https://github.com/CurateLabs/graphforge)
([graphforge-extension.md](graphforge-extension.md)).

Core GraphForge already exposes one Rust engine to **Python and Node**. This
extension targets the same matrix: **semantic parity across all chart types**
from both hosts, over one viz Rust C ABI and one WebGL render client.

**Priority:** **graph visualization** is the core feature of this extension
([graph-fork-requirements.md](graph-fork-requirements.md)) and the first
surface that must prove dual-host end to end. **All other chart types** must
keep the same first-class API feel and speed (shared ABI, §29 wire, WebGL
client) — sequencing graph first is allowed; a degraded non-graph path is not
([graphforge-extension.md](graphforge-extension.md) §3).

Does not change runtime behavior until a Node host package lands.

Supersedes the upstream xy reading of dossier §32 (“Python-only forever”) for
*this* product line.

---

## 1. Goal

| Layer | Shared across Python and Node |
|---|---|
| Rust viz `cdylib` C ABI | All kernels (existing marks + `xy_graph_*`) |
| Wire / §29 buffers | Identical binary payloads for the same figure spec |
| JS render client | One bundled WebGL client |
| Public chart semantics | Same mark kinds, options, defaults, layout/LOD decisions |
| GraphForge integration | Same subgraph → chart path from both GraphForge bindings |

Host-only differences are idiomatic (NumPy/pandas/Arrow vs TypedArrays;
notebook/Reflex vs Node embed). Names and defaults match.

---

## 2. Placement rule

From [rust-engine.md](rust-engine.md) §1, applied to both hosts:

- **GraphForge Rust** — graph data, Cypher, storage, analysis (not duplicated
  here).
- **xy Rust** — O(N) / O(|V|+|E|) **viz** work that must be bit-identical
  across hosts (layouts for display, decimation, channel scans, screen LOD).
- **Host (Python *or* Node)** — API ergonomics, validation, spec assembly,
  policy; recorded decisions (§28) must not diverge.
- **JS client** — screen-bounded draw and gestures only.

Node must not reimplement layouts or mark geometry in TypeScript.

---

## 3. Requirements

- **REQ-HOSTPARITY-1 (MUST).** One xy Rust C ABI serves Python (`ctypes` today)
  and Node (N-API). `ABI_VERSION` bumps apply to both loaders.
- **REQ-HOSTPARITY-2 (MUST).** For every public chart type, Python and Node
  produce the same figure spec shape and §29 buffers for the same inputs.
  Graph is the core feature and first golden suite; other types MUST not ship
  on a slower or thinner host path.
- **REQ-HOSTPARITY-2b (MUST).** Non-graph marks retain upstream xy performance
  and composition quality (Rust kernels, binary transport, WebGL). Graph work
  MUST NOT regress them or leave them as second-class APIs.- **REQ-HOSTPARITY-3 (MUST).** The browser client is shared; hosts only differ
  in transport attachment.
- **REQ-HOSTPARITY-4 (MUST).** Graph viz is the **lead feature** for dual-host
  delivery in this extension ([graph-fork-requirements.md](graph-fork-requirements.md)).
- **REQ-HOSTPARITY-5 (MUST).** Dual-host parity mirrors core GraphForge’s
  Python + Node product surface ([graphforge-extension.md](graphforge-extension.md)).
- **REQ-HOSTPARITY-6 (SHOULD).** Document §32 divergence from upstream xy when
  the Node package ships.
- **REQ-HOSTPARITY-7 (SHOULD).** When bringing a mark to Node, prefer Rust for
  any remaining host-only layout (e.g. Sankey) so Node does not grow a parallel
  layout tree.

---

## 4. Delivery order

```mermaid
flowchart LR
  abi[Shared xy C ABI + loaders]
  graph[Graph mark MVP]
  gfIngest[GraphForge Arrow ingest]
  nodePkg[Node xy package]
  graphParity[Graph golden parity]
  rest[Remaining chart types on Node]
  abi --> graph
  graph --> gfIngest
  abi --> nodePkg
  gfIngest --> graphParity
  nodePkg --> graphParity
  graphParity --> rest
```

1. Extend the language-neutral viz C ABI.
2. Implement graph layout/render (**main need**).
3. Ingest from GraphForge (primary) + edge-list / NetworkX convenience.
4. Node loader; graph fixtures match Python.
5. Expose remaining chart types on Node.

---

## 5. Non-goals

- Separate Node-only renderers.
- Replacing GraphForge’s PyO3/N-API engine bindings with xy.
- Requiring Node for Python users or vice versa.
- Bit-identical *policy source* across languages — only identical recorded
  decisions and buffers.
