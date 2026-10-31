# Parent integration notes

This child implements only the independent Node/VS Code scheduling slice of
#35, on parent local `dee3ea37540a7126c3082ae59624bb02881bb00f`.
No remotes, PRs, tags, issue states, hardware or paid resources were changed.
No Rust, generated ABI, browser controller/shader or shared normative file was
edited. Independent final review remains the parent's responsibility.

## Shared normative edits proposed for the parent

Apply after combining S4 work, before a PR. These are proposals, not edits made
by this child:

1. `spec/design/graph-mark.md` §4, the paragraph beginning **Remaining for #35**:
   replace the claim that default Node/VS Code payloads compose synchronously
   and bypass `runForceTicks` with: “Node/VS Code live payloads now require a
   per-view `GraphForgeLayoutController` and use the existing native scheduler
   plus worker preset packing; see graphforge-node-scheduling.md. The bounded
   four-node native/painter receipt proves pixels, changed later positions,
   pick and pan through full view replacement. Render-based first paint and
   interactivity across the large-data ladder, retained S5 updates, and Python
   notebook attachment remain open.” Preserve the historical ladder language
   and all receipts; it measures checkpoints, not paint.

2. `spec/design/graphforge-compositions.md` §6.2: replace the synchronous
   `graphforgeWebviewPayload(composition, opts)` paragraph with a link to the
   new normative scheduling doc and the new signature
   `await graphforgeWebviewPayload(owner, input, options)`. Name
   `graphforgeStaticPayload` as the explicit former synchronous API, including
   Figure and static preset reuse. Live `positions` seed force; explicit
   `layout: "preset"` is needed to reuse without ticks, and incomplete source
   UUID coverage rejects instead of silently restarting. Static
   `graphforgeChart` and its documented reuse timings stay historical/static.
   Update the pick paragraph to accept either live payload or static Figure;
   remove its existing duplicated first line. In §6.4, require one owner per
   webview and await `dispose()` on reload/teardown; UI/message routing and
   retained controller ownership stay outside this slice.

3. `spec/design/host-parity.md` §0: note that the Node host's live graph owner
   performs asynchronous composition/layout/preset packing with two workers:
   the narrow bridge and existing force scheduler. This adds no engine/runtime
   surface or layout/LOD/style policy. Native library loading at module import,
   structured cloning and callbacks still have caller costs; no zero-copy or
   large-scale responsiveness claim is supported by this local proof.

4. `spec/design/application-consumers.md`: add the independent
   `examples/vanilla-ts/graphforge-live.mjs` functional fixture and new receipt.
   It uses local native ABI 397 and generated paint assets, no shipping WASM
   qualification, no packaged consumer qualification, and full replacement
   resets viewport. Existing application and packaged consumer receipts remain
   unchanged. This does not implement an editor adapter or S5 controller.

5. `spec/releases/0.6.0-api-inventory.json`: regenerate with
   `uv run python scripts/check_release_inventory.py --write` after reviewing
   the combined diff. Account for `GraphForgeLayoutController` (revision,
   render/cancel/dispose), the owner-required asynchronous
   `graphforgeWebviewPayload`, new `graphforgeStaticPayload`, the live payload
   form accepted by `graphforgePick`, and added composition parent planes.
   The child deliberately did not regenerate this shared inventory.

## Existing boundary failure requiring parent disposition

`node --test packages/xy-node/test/no_browser_globals.test.mjs` fails because
its regex matches `document` in the generated native FFI declaration string
for `xyg_graphforge_session_create`. `baseline-contract-finding.json` binds
identical base/current generated ABI hashes and the exact declaration;
`baseline-contract-failure.log` records the failure. Generated ABI files are
outside this child's ownership. Repair the generator/source parameter naming
or make the guard distinguish FFI signature text from executable browser-global
use; do not manually edit generated output or silently waive the gate.

The current real S4 WASM package gate remains failed per parent evidence.
This child built only the local native core and painter bundles and makes no
WASM release claim. No acceptance status for #35/#1015/#36/M4 is closed here.

## API/ownership/review handoff

- Default live callers now own one controller per view. Synchronous metadata
  composition is still available; raw live input moves it to the bridge.
- Repository payload tests are explicit static readers; the new browser
  consumer exercises the new async live path. Package-root/GraphForge/VS Code
  exports and the integration recipe are updated. Generic docs referring to
  static `graphforgePick(Figure, ...)` remain valid.
- The bridge calls existing `runForceTicks` in worker mode; its Rust force
  handle, tick ACK, destruction and worker-exit authority are unchanged.
  Presentations retain initial and final, coalescing only pending updates.
- Native errors/codes/layer/field and active callback failures remain observable;
  revisions/jobs, cancellation/supersession/disposal and late ACK refusal are
  owned per view. Rollback reverts this pre-v1 API and migrated readers together.
- The raw receipt binds exact source/native/client/screenshot hashes. The
  canonical final full-index binary diff hash is supplied in the child handoff
  after committing, avoiding a self-referential in-diff hash.
