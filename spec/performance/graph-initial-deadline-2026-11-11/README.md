# Initial graph recovery transaction deadline

Source parent: `530345c80334f7cea3369317660d57767b74f9e7`.

Independent review found that the initial recovery deadline only aborted a
restoration waiter. Once restoration resolved that waiter, expiry during the
retry's Worker reply could still install and publish the first frame. The real
Worker control reproduced fulfilled readiness, one publication and painted
pixels after the expiry callback. The parent remains **REQUEST_CHANGES**;
its nine-case and full-foundation passes do not supersede that finding.

Expiry now reports a terminal timeout for the whole initial transaction. The
controller checks the expired lifetime before installation and after a render
returns without publication, preserving the original timeout instead of a
later stale/disposal error. One deadline spans coalesced temporal intents;
superseding an unpainted frame cannot renew it. Successful initial publication
or disposal clears the timer. The generated 30-second limit is unchanged.

The real Worker gate now has twelve cases. Added controls expire the active
deadline at the second render reply, before its production listener, for both
temporal and ordinary attachments. Another expires it at the successor
membership reply after a newer intent supersedes the first. The private test
clock honors clearTimeout, so it cannot resurrect an already cancelled timer.
Expired work must reject with the exact first timeout message and publish no
frame; cleanup still retires every Worker. The prior nine lifecycle, malformed
input, mid-allocation loss and same-Worker reuse controls remain intact.

`checks.json` binds the final commands/results, predecessor failures, external
review record, raw archives, source history and matching runtime artifacts.
The first correction refused publication but returned a generic disposal error
for the superseded temporal reply; that failed run remains preserved. A sealed
intermediate client with per-intent deadlines fails the successor-expiry
control. The parent client fails the restored-reply control. No failed run is
credited as a pass.

The parent generation-insensitive density upload assertion also failed a new
broad attempt before graph tests. Its original cause remains unclassified.
A controlled prior review separately proves that legitimate post-paint context
recovery uploads an unchanged grid and image. The density oracle now retains
strict identity/zero-upload checks within each GL generation. Across a verified
restoration it additionally requires the old texture invalid, a live new
texture and byte-identical canonical Rust upload (including dimensions and
normalization); no non-recovery upload is allowed. A new post-paint forced-loss
case joins the ESM/IIFE matrix, yielding ten cases. Ownership facts are sampled
synchronously before hashing, avoiding mixed-generation comparisons. Pixel
assertions remain single-shot and unchanged; no blank-image retry is added.

Only the browser controller and regression/spec/provenance change. Rust, the
324 compiled inputs, native405/WASM38, all 551 native declarations and 68 WASM
exports, optimizer, budgets, defaults and package caps remain unchanged. The
main ESM/IIFE artifacts and their Python copies are rebuilt from matching
source. This is not a timing, reliability or global-memory qualification.

Original spontaneous context-loss and notebook failures remain unresolved.
Whole issue/milestone acceptance, final independent review, final-head hosted
CI and the required merge queue remain separate requirements. Milestones 4–7
remain open.
