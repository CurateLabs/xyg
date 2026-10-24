# Bounded owned-resource and normal-RAF proof, 2026-10-24

This is one local 1M-row software-renderer control of the schema-2 colored
browser harness. It is neither main-run authority nor proof of M4 acceleration,
100M normal cadence, production FPS, competitive performance or release acceptance.
The original environment identifies base `8185de790ea4699ffc93701f5b4b55fb5d838d72`
plus dirty file hashes; its completed runtime implementation is retained in
`a41274b2d29bcb8889fee01034d7c24f55343e3b`. Original reports are not rewritten.

`host.json.gz` and `browser.json.gz` preserve the exact decoded original bytes.
They contain environment/versions, source and per-file hashes, the loaded native
and generated client identities, every request/frame, allocation events,
normal-clock observations, original embedded captures and process/cleanup facts.
Decoded host SHA256 is `292fa42483b8a1cdd55ae4f07e393cde0ca2fc5253bc31c3760dcb4b08905424`;
decoded companion SHA256 is `dda013421de8cdf9d34de087ef8ba5c7476b1ca29542832e24899a761cb9a1f1`.
`handoff.json` retains the implementation/diff fingerprint and summary.
`path-fingerprints.sha256` binds its original fifteen implementation paths.
The three PNGs here are decoded from the final companion's embedded captures
and match its `capture_sha256`; earlier scratch PNG siblings are not retained.

The control made 99 binary requests, obtained 33 cached/fetch-all framebuffer
matches, zero maximum seam error and eight adjacent normal-clock transitions
in 61 observed product RAF draws. It explicitly deleted all 48/227/15 textures
and four buffers per chart. Keyed texture peak was 3,461,328 bytes under 8 MiB;
CPU tile residency remains separately capped at 16 MiB. Observed group RSS was
1,993,695,232 bytes, owned disk 111,313,980 bytes and elapsed time 22.123995571862906
seconds. These sampled/instrumented observations include validation overhead.

Both original report verifiers passed with the implementation checkout as
`--artifact-root`; exact invocations/output are in `validation.txt`.
A separate tiny `--gl hardware --preflight-only` request on this Linux host
obtained SwiftShader and failed closed before source generation. Its raw JSON
and stderr are retained as failure evidence, not accelerated success.

Reproduce the bounded workload after normal source/native/client setup:

```bash
mkdir -p target/task-tmp
TMPDIR="$PWD/target/task-tmp" uv run python benchmarks/bench_density_e2e.py \
  --workload colored-spill --points 1000000 --chunk-points 262144 \
  --timeout 600 --max-rss-gib 8 --max-disk-gib 2 \
  --chrome /home/ubuntu/.cache/ms-playwright/chromium-1248/chrome-linux64/chrome \
  --temp-root target/task-tmp --output target/owned-host.json \
  --colored-browser-report target/owned-browser.json
uv run python scripts/verify_density_spill_report.py target/owned-host.json --artifact-root "$PWD"
uv run python scripts/verify_density_spill_browser_report.py target/owned-browser.json \
  --host-report target/owned-host.json --artifact-root "$PWD"
```

To inspect retained bytes without rerunning a browser, check `SHA256SUMS` and
losslessly decompress the two reports. Verifying them without `--artifact-root`
checks recorded structure and bindings only; it does not establish current-file
identity. Historical source/native/client hashes must not be replaced with
current bytes. The actual main Mac hardware execution remains outstanding.
