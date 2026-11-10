# Notebook graph history admission correction

Independent review of 0e19fea7580b611716e2935ed76b2752f84b1fca found two P2s:
one mixed public range/selection patch made two undo entries, and native refusal
of Back left the camera changed while neither stack moved. The original review
and failing controls are preserved; the original receipt is unchanged.

Deferred intents now retain the existing interaction ID. History queries its
stored data-space predicate in the accepted picture; only accepted navigation
commits the stored ranges and stack movement through the existing state engine.
A later range write or changed history target supersedes pending navigation
without rolling back newer state. Opaque-row history retains its synchronous
non-reselecting behavior. Obsolete axis schemas refuse through the shared state
validator before query or stack mutation. Ordinary transports and API range-facet behavior are
unchanged. No Rust, ABI, worker, native or WASM product code changes.

The transport fixture now exercises actual range mutation, validation and
history instead of stubbing the mutation. Final assertions fail on the exact
parent host. New coverage checks mixed updates, refused Back/Next, complete
accepted roundtrips, pending navigation superseded by a non-history range write,
and opaque-row navigation. The actual notebook adds a labeled seeded-history
control under real native Capacity refusal, complete camera/mask/RGBA retention,
and public mixed applyState/Back/Forward roundtrips at both DPRs. The new notebook
guard rejects the parent's packaged client. All existing region oracles remain.

Commands, exact exits, current/predecessor source identities, runtime archives
and capture hashes are in checks.json and current-bindings.json. The unchanged
shipping module remains **1,885,379 raw / 786,379 Node22 gzip6 bytes**, with **53
gzip bytes spare** under unchanged caps. Native ABI405/551 and WASM38/68 remain.
Original whole-scope qualification is inherited only over unchanged identities;
fresh correction checks are distinguished from prior and failed runs.

Full-foundation GPU-context failures remain unexplained. The final client run
failed the density presentation context-loss guard; the same focused failure
reproduces using the exact accepted-main f75d2560 artifacts and parent 0e19fea7
artifacts. Earlier quiet complete passes and an instrumented diagnostic pass
are recorded separately and do not establish a reliability repair or a green
final full invocation. No assertion, renderer setting or deadline was changed.
Independent re-review, final-head hosted checks and the main
merge queue remain delivery gates. Whole #1015, #36 and milestones 4–7 remain
open for the previously documented frontend, changed-LOD/aggregate/categorical,
scale, export, accessibility, latency/competitor and global-memory acceptance.
