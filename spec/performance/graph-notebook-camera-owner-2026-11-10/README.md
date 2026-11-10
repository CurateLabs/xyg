# Camera-write ownership during native graph history

Independent re-review of 55e4d1f7 found that current-coordinate equality could
not detect a newer animation before its first frame, or writes returning to the
same coordinates. An accepted older Back reply could then overwrite the newer
camera and move both history stacks. The earlier mixed-patch and refused-Back
findings remain resolved; all preceding receipts and reviews are preserved.

The common viewport writer now replaces one opaque token for each validated
write intent, before animation or same-value early returns. Native history
captures that token and commits only while it still owns the camera facet.
An empty ranges merge-patch does not call the writer, preserving its no-op
semantics and avoiding self-supersession by the staged history query. The token
is transient, never serialized, has no numeric wraparound, and retains no map
or unbounded request history. Clamping, drawing, events and range calculations
keep their existing implementations.

Regressions use the actual mutation methods and cover pre-frame animation,
non-history writes returning to prior coordinates, explicit same-value writes,
empty patches, and rejected invalid patches. Original history and native-wire
controls remain. Actual notebook DPR1/2 journeys retain every UUID, mask,
refusal, complete-camera/RGBA and public history assertion. Exact parent-source
controls distinguish the correction from the failing implementation.

Fresh results, original failures, artifact/source bindings and reproduction
commands are in checks.json. No Rust, ABI, Worker, native or WASM code changes;
the module remains 1,885,379 raw /786,379 Node22 gzip6 bytes, with 53 gzip bytes
spare under unchanged caps. Earlier Rust/ABI/CI results are inherited only over
unchanged identities. All previous full-foundation context-loss failures and
matching accepted-main/parent controls remain recorded; the current invocation
is reported separately without a reliability-repair claim. No oracle, renderer
setting, resource cap or deadline changes.

Independent final re-review, hosted checks and the required main merge queue
remain delivery gates. Whole #1015, #36 and milestones 4–7 remain open with the
previously documented frontend, changed-LOD/aggregate/categorical, scale,
export, accessibility, latency/competitor and global-memory requirements.
