# Release a held native reply before test failure teardown

Base: `ea19bdb0f622faace721b68a59c3c80431439555`.
Independent review found a P2 in the new VS Code application test. Its synthetic
transport gate held an actual native prepared reply. An assertion failure or
invalidation deadline before the success-path `releasePrepared()` entered
`finally`, which awaited `host.dispose()` while the admitted transport was still
held. Remaining native-owner cleanup could never run. A late prepare could also
enter the still-armed hold during failure cleanup.

The test now owns the hold flag and resolver in outer cleanup scope. Every exit
disarms future holds and releases any admitted held reply before disposing the
actual panel and awaiting the host/binding. This preserves the real native
transport, realm teardown and acknowledgement rules. It does not synthesize a
completion or relax the45-second action/native-gate deadlines. Cleanup checks
actual mount/anchor release, closed source/lane and retired Scope ownership.

`XYG_GEO_VSCODE_FAIL_HELD_PREPARE=1` injects a failure immediately after the actual
prepared reply reaches its hold. The existing application operator **must exit1**
with the intentional error still recorded, while `report.json.cleanup.json`
confirms completed native-owner cleanup. The normal actual VS Code journey must
still exit0 with its exact sequence, camera, selected ID and full-RGBA assertions.

```bash
# Explicit native library, checkout PYTHONPATH, installed VS Code/display and
# ordinary application dependencies are the same as the parent receipt.
XYG_GEO_HIERARCHY=1 XYG_GEO_VSCODE_FAIL_HELD_PREPARE=1 \
  python scripts/geo_vscode_mounted_temporal_smoke.py \
  --code /path/to/code --output /path/to/negative-output
# Expected: exit1, report.ok=false, intentional held-reply error, cleanupComplete=true.

XYG_GEO_HIERARCHY=1 python scripts/geo_vscode_mounted_temporal_smoke.py \
  --code /path/to/code --output /path/to/normal-output
# Expected: exit0, report.ok=true and cleanupComplete=true.
```

The reviewer control is also retained and rerun: with the actual native fixture
and host facade, disposal stays pending while a transport reply is held and
settles only after explicit release. That focused dependency control stubs the
reply delivery; it is distinct from the actual VS Code failure-injection run.
No original failed run or review result is converted to a pass.

`checks.json` binds normal and injected actual-application commands, reports,
cleanup receipts, logs/captures and source/artifact identities. The append-only
successor preserves all parent source history and prior receipts. This changes
only the test, its specification and provenance. Production, all324 compiled
inputs, eight shipping artifacts and six Python static copies remain unchanged.
The parent actual Jupyter proof is inherited only through unchanged source and
artifact equality; it was not rerun for this harness-only correction.

Earlier startup/Worker/timer failures remain unresolved. Five automatic bindings,
mixed tiles, installed-XYG-wheel, global budgets, full accessibility, scale and
competitor qualification remain open. No shipping, hosted-CI, queue, issue or
milestone-completion claim follows. Independent re-review is required before
delivery of this correction.
