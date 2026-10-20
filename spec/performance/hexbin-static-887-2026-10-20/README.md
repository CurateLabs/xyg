# Static hexbin export beyond the 1,024 painter-group limit (#887)

Reproduce (from the repository root, after `cargo build --release`):

```bash
uv pip install matplotlib==3.11.0
uv run python scripts/bench_hexbin_static.py --out after.json
```

`before.json` is the same command on `origin/main` (`59d7e58e`) behaviour (the
Rust admission change reverted and rebuilt). Raw results: `before.json`,
`after.json`. Each row is a fresh subprocess; time is the median of
3 `savefig` calls, size is output bytes, memory is the
subprocess peak RSS (includes interpreter and imports).

Environment: Linux-7.0.0-34-generic-x86_64-with-glibc2.43, Python 3.13.12, NumPy 2.5.1,
Matplotlib 3.11.0, Model name:                              AMD Ryzen 7 3800X 8-Core Processor. After-commit: `930878e6598722cd5f48a08668f1f29ba8d51032`.

Data: the `hexbin_demo.py` gallery cloud (100,000 rows, seed 19680801,
`bins="log"`, inferno, colorbar). Cell **counts differ by engine** by design:
Matplotlib always draws the full lattice including empty cells, while the XYG
log-count lattice ships only populated cells, so cell counts are reported next
to every row and rows are not like-for-like work.

| gridsize | format | XYG cells | XYG before (main) | XYG after | Matplotlib cells | Matplotlib 3.11.0 |
|---|---|---|---|---|---|---|
| 25 | svg | 377 | 4.5 ms / 88 KiB / 61 MiB | 4.3 ms / 88 KiB / 61 MiB | 740 | 85.3 ms / 127 KiB / 91 MiB |
| 25 | png | 377 | 11.0 ms / 56 KiB / 61 MiB | 9.7 ms / 56 KiB / 61 MiB | 740 | 75.9 ms / 47 KiB / 90 MiB |
| 50 | svg | 1,226 | fail-closed LOD | 5.6 ms / 263 KiB / 61 MiB | 2,879 | 138.3 ms / 429 KiB / 91 MiB |
| 50 | png | 1,226 | fail-closed LOD | 11.9 ms / 80 KiB / 61 MiB | 2,879 | 94.0 ms / 61 KiB / 91 MiB |
| 100 | svg | 3,946 | fail-closed LOD | 20.7 ms / 824 KiB / 70 MiB | 11,558 | 357.7 ms / 1643 KiB / 94 MiB |
| 100 | png | 3,946 | fail-closed LOD | 25.0 ms / 112 KiB / 70 MiB | 11,558 | 114.0 ms / 84 KiB / 92 MiB |
| 200 | svg | 11,843 | fail-closed LOD | 55.5 ms / 2448 KiB / 98 MiB | 46,316 | 1249.9 ms / 6455 KiB / 132 MiB |
| 200 | png | 11,843 | fail-closed LOD | 55.4 ms / 112 KiB / 94 MiB | 46,316 | 265.7 ms / 92 KiB / 98 MiB |
| 300 | svg | 21,449 | fail-closed LOD | 103.5 ms / 4423 KiB / 133 MiB | 104,274 | 2617.7 ms / 14408 KiB / 197 MiB |
| 300 | png | 21,449 | fail-closed LOD | 98.0 ms / 106 KiB / 129 MiB | 104,274 | 522.3 ms / 95 KiB / 108 MiB |
| 400 | svg | 31,488 | fail-closed LOD | 161.2 ms / 6453 KiB / 156 MiB | 184,631 | 4467.2 ms / 25376 KiB / 286 MiB |
| 400 | png | 31,488 | fail-closed LOD | 139.4 ms / 101 KiB / 158 MiB | 184,631 | 856.9 ms / 97 KiB / 127 MiB |
| 600 | svg | 50,166 | fail-closed LOD | fail-closed LOD | 416,147 | 9834.0 ms / 56762 KiB / 546 MiB |
| 600 | png | 50,166 | fail-closed LOD | fail-closed LOD | 416,147 | 1889.2 ms / 96 KiB / 175 MiB |

Reading: before this change every XYG export above 1,024 cells failed closed;
now all populated lattices up to the documented 50,000-cell ceiling export with
every cell retained, and the first gridsize above the ceiling (600 → 50,166
cells) still fails closed with `XYG_SCENE_UNSUPPORTED_PUBLIC_LOD`. Below 1,024
cells, before/after are unchanged within noise. Wall time and memory grow
roughly linearly with cells (~5 µs/cell SVG, ~160 MiB at 31k cells). Per cell
XYG SVG is larger than Matplotlib's (~210 B vs ~140 B per cell, no path
interning), and XYG PNGs are ~20–30% larger than Matplotlib's; the XYG
wall-time lead partly reflects drawing fewer cells, so this is evidence that
the route works and scales, not a like-for-like speed claim. Single machine,
single chart; no multi-chart or interaction measurement.
