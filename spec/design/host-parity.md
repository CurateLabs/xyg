# Host parity — Python and Node

**Status:** requirements / architecture intent. Supersedes the “bindings are
Python-only forever” reading of dossier §32 for *new* work: XY targets
**semantic parity across all chart types** from Python and Node hosts over one
Rust C ABI and one WebGL render client.

**Priority:** the first product surface that *must* exercise this contract end
to end is **graph visualization**
([graph-fork-requirements.md](graph-fork-requirements.md)). Other chart
families already ship in Python; Node parity for them follows the same binding
and wire rules, not a second implementation.

Does not change runtime behavior until a Node host package lands.

---

## 1. Goal

| Layer | Shared across Python and Node |
|---|---|
| Rust `cdylib` C ABI | All kernels (existing marks + future `xy_graph_*`) |
| Wire / §29 buffers | Identical binary payloads for the same figure spec |
| JS render client | One `static/index.js` / `standalone.js` |
| Public chart semantics | Same mark kinds, options, defaults, layout/LOD decisions |

Host-only differences are idiomatic: Python lists/NumPy/pandas vs TypedArrays;
`show()` / anywidget / Reflex vs Node embedding APIs. Names and defaults match.

---

## 2. Placement rule (unchanged, dual-loaded)

From [rust-engine.md](rust-engine.md) §1:

- **Rust** — O(N) / O(|V|+|E|) work and anything that must be bit-identical
  across hosts (layouts, decimation, channel scans, graph store).
- **Host (Python *or* Node)** — API ergonomics, validation messages, spec
  assembly, policy (tier choice). Policy code may start in one host and be
  ported; it must not diverge on recorded decisions (§28).
- **JS client** — screen-bounded draw and gestures only.

Node must **not** reimplement layouts or mark geometry in TypeScript.

---

## 3. Requirements

- **REQ-HOSTPARITY-1 (MUST).** One Rust C ABI serves Python (`ctypes` today)
  and Node (N-API / napi-rs). `ABI_VERSION` bumps apply to both loaders.
- **REQ-HOSTPARITY-2 (MUST).** For every public chart type, Python and Node
  produce the same figure spec shape and §29 buffers for the same inputs
  (golden fixtures). Graph is the first new type held to this; existing types
  gain Node coverage as the host package lands.
- **REQ-HOSTPARITY-3 (MUST).** The browser client is shared; hosts only differ
  in how they attach transport (widget comm, Reflex `/_xy`, Node-served page,
  etc.).
- **REQ-HOSTPARITY-4 (MUST).** Graph viz ([graph-fork-requirements.md](graph-fork-requirements.md))
  is the **lead feature** for dual-host delivery: ship `graph_chart` with
  Python + Node parity in the same program of work.
- **REQ-HOSTPARITY-5 (SHOULD).** Amend dossier §32 and distribution docs when
  the Node package ships, replacing “Python-only binding surface” with
  “Python and Node hosts over one cdylib.”
- **REQ-HOSTPARITY-6 (SHOULD).** Prefer moving host-only layout leftovers (e.g.
  Sankey’s Python `_sankey.py`) into Rust when touching those marks for Node
  parity, so Node does not grow a parallel layout tree.

---

## 4. Delivery order

```mermaid
flowchart LR
  abi[Shared C ABI + loaders]
  graph[Graph mark MVP]
  nodePkg[Node xy package]
  graphParity[Graph golden parity]
  rest[Remaining chart types on Node]
  abi --> graph
  abi --> nodePkg
  graph --> graphParity
  nodePkg --> graphParity
  graphParity --> rest
```

1. Keep / extend the language-neutral C ABI (already the Python path).
2. Implement graph store/layout/render (main product need).
3. Add Node loader + thin chart API; prove graph fixtures match Python.
4. Expose existing chart types through the same Node API (scatter, line, …)
   without rewriting the Rust/JS core.

---

## 5. Non-goals

- Separate Node-only renderers or canvas stacks.
- PyO3 / per-CPython extension wheels (stay on plain C ABI + `py3-none-*`).
- Requiring Node for Python users, or Python for Node users.
- Bit-identical *policy source code* across languages — only identical
  recorded decisions and buffers.
