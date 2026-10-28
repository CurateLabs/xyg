# Accepted-main hardware attempt — failed renderer preflight

**Run 40639793475 failed before any canonical source allocation.** This receipt
retains that failure; it supplies no accepted M4 acceleration, owned-resource
chart journey, normal-RAF 100M proof, whole-#11/#108 acceptance or publication
permission. No execution was retried, rerun, canceled or dispatched here.

The already-dispatched [actual run](https://github.com/CurateLabs/xyg/actions/runs/40639793475),
attempt 1, used accepted main `fe7d2ae71d316fd96b9851f3ce6232f76dd19134`
(#1077), tree `4fd8722a09fc92b3f9a5f0b8167ec1fdb57bc9a7`, created
2026-10-28 05:45:05 UTC. Job `122655020139` ran 05:45:41–05:47:12 UTC,
conclusion `failure`; the sweep step failed at 05:47:08 UTC with exit 1.
Terminal `run.json`, `attempt-1.json`, `jobs.json` and `job.json` retain exact
timestamps and all step outcomes. The sole job used existing label
`blacksmith-12vcpu-macos-15`, runner
`blacksmith-12vcpu-macos-15-y2dz3gvea6jfo6cs`. M4/12-vCPU/48-GiB is the
configured lane, not independently measured capacity in this artifact. Actual
logs identify macOS 15.7.4 and an Apple arm64 host. No runner/capacity,
credentials, budgets, product, test or workflow code changed.

The log records `INPUT_EXPERIMENT: colored-browser-hardware` and
`INPUT_HARDWARE_GL: true`. The exact main SHA, manual event and clean-checkout
guards precede preflight in the retained accepted workflow. The preflight records
the matching repository, workflow ref and workflow SHA. Reaching it also follows
the existing Darwin/arm64 context guard. `environment.json` preserves actual
logged inputs/versions, recorded renderer/GPU features and explicit missing
binary identities. No locally exported Actions capability or fabricated ambient
execution context was used. Default ladder sizes, repetitions, timeout and
memory inputs appear in the log but do not control this experiment's fixed caps.

## Actual failed phase and cleanup

Native/package/environment/client/Chromium setup all succeeded. The installed
interpreter was CPython 3.12.10, NumPy 2.4.6; native import reported `native`.
The browser reported Chrome 149.0.7827.55, protocol 1.3. Its preflight obtained:

- WebGL `WebGL 2.0 (OpenGL ES 3.0 Chromium)` and readback `[64,128,191,255]`.
- Unmasked vendor `Google Inc. (Apple)` and renderer
  `ANGLE (Apple, ANGLE Metal Renderer: Apple Paravirtual device, Unspecified Version)`.
- Browser GPU device `ANGLE (Apple, ANGLE Metal Renderer: Apple Paravirtual device, Version 15.7.4 (Build 24G517))`;
  driver vendor Apple, driver version 15.7.4, display implementation Metal.
- GPU feature `webgl: enabled`; Chromium supplied no separate `webgl2` feature.
  All other reported features and driver workarounds remain in the raw report.
- `contextLost: false`, PID 1656 / process group 519, `process_reaped: true`
  and `profile_removed: true`.

The unchanged renderer guard requires actual **Apple M4** and Metal in the
unmasked renderer. It raised:

```text
hardware requires actual Apple M4 Metal accelerated WebGL: ANGLE (Apple, ANGLE Metal Renderer: Apple Paravirtual device, Unspecified Version)
```

This is an actual identification/admission failure. It does not establish
SwiftShader fallback, physical Apple M4 identity, total driver VRAM, acceleration
acceptance or a benchmark result. No guard was relaxed to reinterpret it.

The 16,384-row control, its two verifiers, the 100M production/base-4096 worker
and its two verifiers **never started**. There are zero chart journeys, pan/zoom
windows, framebuffer comparisons, adjacent transitions and accepted host/browser
verifier pairs from this run. Canonical x/y/color hashes, source mappings, spill,
owned texture/buffer inventories, sampled RSS/disk and worker cleanup are absent,
not zero-valued measurements. Only browser/profile preflight cleanup is observed.
No host or browser companion report exists. Host/browser success validators have
no applicable report to validate; the archival inspector instead reproduces
the actual renderer refusal over saved observations.

Configured limits remain **30 s preflight**, **180 s / 4 GiB RSS / 1 GiB disk
control**, **3600 s / 12 GiB RSS / 4 GiB disk 100M worker**, and **720 min outer
job**. Setup-to-sweep timestamps do not substitute for sampled resource usage.
Accelerated owned-allocation/normal-RAF 100M evidence, massive canonical drill
localization/scale proof, comparative evidence, larger-than-RAM and final
candidate acceptance remain outstanding. #11 remains open; this receipt does
not complete #108. Historical receipts are unchanged. Parent independent review
and integration remain required.

## Exact retained bytes and provenance limits

Artifact `12794149653` (`ceiling-benchmark`, 3,057 bytes) contains only
`_temp/colored-browser-preflight-fe7d2ae71d316fd96b9851f3ce6232f76dd19134.json`.
ZIP SHA-256 matches both GitHub's artifact digest and the upload log:
`64dbf69c6bd1a9471099c3c19750bf5dd7986fe68479dc1c7b9a929e29f062e9`.
The sole member is 7,913 bytes, CRC32 `9ce160bd`, SHA-256
`a491ac8fe4b925c1e3c1bfdebd70a1e761aa993644a039a5ceb044752bcf6ade`.
`preflight.json.gz` decodes to those exact original JSON bytes.

`logs.zip` retains all 21 full/step/system log members (47,416 bytes), SHA-256
`65eeab881572fef40d0f092e5b7263d403a2c46d08ea3121460752ef2e994b03`.
`job-122655020139.log.gz` decodes to the exact 86,364-byte full-job member,
SHA-256 `29dc91cfaceb4ca749679175a0828917c6d6ab150e5fb0315f39356db2ee5acb`.
Both ZIPs pass all member CRC checks. Gzip copies use mtime zero and no filename.
No original report/log bytes were rewritten. `retention.json` inventories ZIP
members and decoded hashes; `manifest.json` and `SHA256SUMS` seal receipt files.

`source-commit.json` and `source-commit.git.txt.gz` retain the accepted commit.
`source-bindings.json` binds 432 source/build/lock/workflow files to Git blob
IDs and SHA-256; `source-files.tar.gz` retains their exact bytes. These include
Python, Rust, TypeScript, the producers, both success verifiers, the workflow
guard, build configuration and locks. Accepted workflow blob:
`591e3d20c313cda7b909ea7a4c843e7b69215512`, SHA-256
`e34f6e28c2bd9743f7ad1040f7912443dacdcf80884d487264a360cc96be627c`.
These are archival source bindings, not a producer-generated product manifest.

The native and render-client builds succeeded in logs, but the preflight-only
report contains **no measured native, generated-client or Chromium executable
SHA-256**, and those binaries were not uploaded. Source hashes, build success
and a local rebuild cannot supply missing measured binary identity. This limit
is retained explicitly rather than attaching identities from a different run.

From the repository root:

```bash
python3 benchmarks/results/colored-browser-hardware-2026-10-28/hosted-main-fe7d2ae7/inspect_evidence.py
(cd benchmarks/results/colored-browser-hardware-2026-10-28/hosted-main-fe7d2ae7 && sha256sum -c SHA256SUMS)
```

The stdlib inspector verifies terminal metadata, actual source/context/runner,
artifact digest, both ZIPs' CRC/member hashes, exact report/log copies and all
432 historical Git source blobs. It evaluates only the accepted pure renderer
guard with saved observations, without importing the harness, launching Chrome,
generating source arrays or setting authority variables. `commands.txt` records
read-only retrieval and local verification commands. `validation.txt` records
actual local checks; they do not convert this failed run into success.
