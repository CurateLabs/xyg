# Failed mounted temporal implementation attempt

Worktree /home/ubuntu/.t3/worktrees/xyg/t3-5af28b44, branch t3/5af28b44.
Implementation base/head unchanged: 7e720104f2d3f0508e6c93211980c09808f42bc6.
Ordered parents: bea7eab191e6ff54b1999087edf23b3d98695899, 43c35f67b95ae4e78e3e96f200a0e6be8642199c.
No commit, GitHub mutation, delivery, or acceptance claim.

Unqualified patch SHA256: 7621b72c1cb1bdb682a12c169e00d0de0322959d98e07a7d8c7683421c5e1549.
Draft paths: js/src/65_geo_host.ts, python/xyg/_geo_temporal.py,
python/xyg/widget.py, packages/xy-node/src/geo-temporal.js,
packages/xy-node/src/geo-webview.js. All restored after saving patch.

Draft introduced binary XYHT temporal intent, client ready notification,
mounted binders sharing snapshot source registries, stale temporal candidate
suppression, and notebook native RPC executor dispatch. It is NOT qualified.
Known unresolved cases: premount disposal waiter settlement; mounted remount
readiness reset; cancellation-safe source exclusivity through detach ACK;
widget close ordering with executor work; terminal webview waiter cleanup;
possible duplicate publication with camera/temporal races. Do not apply as a
review-ready candidate. No actual-host temporal acceptance was performed.

Executed:
- TMPDIR=/var/tmp uv sync --group dev: exit 0, Python 3.12.15.
- TMPDIR=/var/tmp npm ci: exit 0 (default Node 24.21.0, not requested Node22).
- TMPDIR=/var/tmp cargo build --release: exit 127 (cargo absent from PATH).
- TMPDIR=/var/tmp /home/ubuntu/.cargo/bin/cargo build --release: started separately.
- TMPDIR=/var/tmp node js/build.mjs (draft): exit 0, existing bundle warnings.
- TMPDIR=/var/tmp uv run ruff format python/xyg/widget.py python/xyg/_geo_temporal.py: exit 0.
- TMPDIR=/var/tmp uv run pytest tests/test_geo_host.py tests/test_geo_temporal_binding.py -q:
  exit 2, native library absent while build still running, two collection errors.
  This is a failed attempt, not test acceptance.
- Full pre-commit/Ruff checks not run; no commit attempted.
- Restored source client build log: restored-client-build.log.

All M6 mounted acceptance and broader full-issue gates remain unfulfilled by this
attempt. Historical evidence and source unchanged. Generated artifacts and local
dependency directories are untracked/ignored setup products.

Final setup results: own native release build exit 0 (2m12s); hash in
native-artifact.txt. Restored client build exit 0. Python/client ESM copies
both SHA256 279ac3767ee8b9dedf91698018f71441d143767ad940e887d3cc0fadbd29b056.
Final git status --short empty; git diff --quiet exit 0.
