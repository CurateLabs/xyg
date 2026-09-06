# Spec: issue #33 — Render directed multigraph edges with routes, arrows, loops, labels, and stable identity

Source: https://github.com/CurateLabs/xyg/issues/33

## Acceptance

## Relationships

- Parent: #31
- Depends on: #32 canonical GraphForge UUID ingestion (completed)
- Related: #30 (edge channels/tooltips)
- Non-goals: Cytoscape API compatibility; editor/mutation tools

## Problem

XYG currently paints graph edges as straight source-target segments. Self-loops collapse, parallel and reciprocal edges overlap, directedness lacks visible arrowheads, `edge_curve` is metadata only, and edge identity is not carried through every interaction and LOD path.

These are correctness failures for GraphForge's directed property multigraph, not optional styling.

## Objective

Provide deterministic, scale-aware directed multigraph geometry that preserves every edge's identity through layout, paint, interaction, LOD, and export.

## Requirements

- Visible self-loop geometry.
- Deterministic separation for parallel and reciprocal edges.
- Straight and curved/routed edge programs, including Bezier-class routing.
- Source/target arrowheads with border-aware endpoints.
- First-class edge labels with placement and collision/zoom policy.
- Stable `edge_uuid` through segment generation, hover/click, selection, tooltips, highlights, export, and aggregate LOD provenance.
- Correct hit-testing for routed geometry.
- Explicit behavior when an LOD aggregate represents multiple original edges.
- Rust owns routing and deterministic geometry; hosts remain thin.
- Reuse inherited HTML/PNG/SVG/file export infrastructure and verify these graph programs in it.

## Acceptance Criteria

- Fixtures cover self-loops, reciprocal pairs, multiple parallel edges, arrows, curves, and edge labels.
- Node borders and arrow tips meet without visible overlap across supported node shapes.
- Selecting an edge returns the exact GraphForge edge UUID at direct LOD.
- Aggregate tiers expose deterministic membership rather than inventing one source edge.
- Interaction and render cost are measured across small, medium, large, and massive graph cases.
- Python, Node, browser, and exported output agree.

## BDD Completion Scenarios

### Scenario: Directed multigraph structure remains legible

Given two nodes with reciprocal edges, parallel relationships, and a self-loop
When XYG renders the GraphForge graph
Then every edge is visibly distinguishable and correctly directed
And selecting it returns its stable edge UUID.

### Scenario: Edge identity survives scale policy

Given a graph that enters sampled or aggregate LOD
When an analyst hovers or selects visible edge geometry
Then XYG reports either the exact edge or deterministic aggregate membership
And never reports an unrelated edge.

## Testing

Add native geometry goldens, browser hit-testing, host parity, export pixel/vector checks, and bounded scale evidence.

## Documentation

Update graph mark, graph fork requirements, dossier sections governing offsets/LOD/export, capability matrix, and visual examples.

## Rust/WASM Architecture Amendment

- Routing, clipping, curve/arrow/label geometry, LOD membership, pick geometry, and export-scene primitives are canonical Rust behavior and must run equivalently through native and WASM hosts.
- TypeScript paints and dispatches browser input against Rust-produced scene and pick structures; it does not independently route or flatten graph edges.
- Add native-versus-WASM geometry/identity goldens and browser Worker lifecycle evidence.

This section is authoritative over any earlier host-ownership wording in this issue. It does not broaden third-party payload compatibility or legacy-reader scope.

## Verification

Follow #108's shared lean CI policy: bounded correctness and affected integration checks in the existing Release surfaces aggregate; hosted performance/100M+ runs scheduled/manual, full platform evidence at release. Reuse hash-linked evidence; no duplicate gate or repeated-green-run requirement.

## Coordinator notes

- Deliver with a commit containing `Coordinated-By: <assignmentId>`.
- Do not claim done without that trailer.
