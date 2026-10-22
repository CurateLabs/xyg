# Storage, temporary files, and mounted volumes

Audit record and normative guidance for what XYG writes to disk, where it
resolves those paths, and what holds on every supported host and on
container or mounted volumes (#1014). Related: [tier3-phase4-roadmap.md](tier3-phase4-roadmap.md)
(#5 tile spill), [host-parity.md](host-parity.md), [browser-wasm.md](browser-wasm.md).

## Contract

- **XYG has no durable store.** It owns no database, project directory, or
  recovery log. Everything it writes is either (a) a file the caller named,
  (b) a rebuildable derived cache beside a caller-owned file, or (c) a
  process-scoped temporary. Nothing is required to survive a restart, and any
  derived file may be deleted at any time and is rebuilt on demand (dossier §27).
- **No process-root, mount-point, or platform allowlist.** XYG never requires
  a fixed root (`/`, `/tmp`, the current directory, a home directory) and never
  probes filesystem type. Paths are resolved by the host runtime and the OS
  (`std::env::temp_dir`, Python `tempfile`, Node `path`). A project or data
  volume mounted anywhere (Docker/Podman bind mount, WSL `/mnt/c`, SMB/NFS
  share, external drive, a different drive letter on Windows) works as long as
  the OS can open, grow, and rename files on it. GraphForge's project-parent
  admission rules are not XYG rules and are not applied here.
- **Fail-closed or silent-degrade is per class, not blanket** (table below):
  explicit requests fail with an actionable error; implicit caches degrade to
  recomputation; caller-named writes raise the OS error and never leave a
  partial destination.
- **In-memory use needs no filesystem.** Default figures, `to_html`, notebook
  display, browser WASM, and Pyodide use no disk. See "Browser and Pyodide".

## Where temporary paths come from

| Host | Resolution | Override |
| --- | --- | --- |
| Rust core (`std::env::temp_dir`) | Unix and macOS: `$TMPDIR`, else `/tmp`. Windows: `GetTempPath` (`TMP`, `TEMP`, `USERPROFILE`, Windows directory). | `TMPDIR` / `TMP` / `TEMP` in the process environment **before the first spill**. |
| Python `tempfile` | `TMPDIR`, `TEMP`, `TMP`, then platform defaults; cached after first use. | Same variables, or `tempfile.tempdir` before first use. |
| Node `os.tmpdir()` | `TMPDIR`/`TMP`/`TEMP` (platform rules). | Same. |

`XDG_CACHE_HOME` and other XDG variables are **not read** anywhere; XYG keeps
no user cache directory. Setting them has no effect.

The Rust spill path and the Python `tempfile` path are resolved independently;
in one process they agree because both read the same environment, but a Python
program that assigns `tempfile.tempdir` changes only Python-created files. To
move the native tile spill, set `TMPDIR` (Unix) or `TMP`/`TEMP` (Windows) in
the process environment, not `tempfile.tempdir`.

## Evidence table

"Class": **D** durable caller-named output, **C** rebuildable cache beside a
caller file, **T** process-scoped temporary, **M** caller-owned out-of-core
data, **N** nothing on disk.

| Path (source) | What persists | Class | Location rule | Platform / volume behavior |
| --- | --- | --- | --- | --- |
| `<tmpdir>/xy-tiles-<pid>-<n>.xyts` (`crates/xyg-engine/src/tile_store.rs`, `xyg_pyramid_spill`) | Tier-3 pyramid tile spill, one file per pyramid (`create_new`, positioned reads/writes, native endianness) | T | `std::env::temp_dir()` | Deleted on `TileStore` drop (`xyg_tile_store_free`, trace GC finalizer). A crash leaves the file; it is never reopened (name carries the PID) and is safe to delete. Uses `FileExt` (Unix) / `seek_read` (Windows); no `mmap`, no locking, no `fsync`, so any filesystem that supports positioned I/O and sparse growth works (tmpfs, overlayfs, bind mounts, NFS, SMB). Size is `spilled_bytes` in `memory_report()` (`pyramid_spilled_bytes`). A tmpfs `/tmp` in a container counts against container memory; point `TMPDIR` at a disk volume for large spills. |
| Spill failure handling (`python/xyg/interaction.py` `_ensure_pyramid`; roadmap WP2) | none | n/a | n/a | `pyramid_spill=True` raises `RuntimeError` naming "temporary-directory space and permissions" and frees the RAM cache. Automatic spill (memmap, rows over `PYRAMID_NO_RESCAN_ROWS`, or resident bytes over `PYRAMID_RESIDENT_BYTES`) silently keeps the RAM pyramid. Covered by `tests/test_phase4_tile_spill_hosts.py`. Node mirrors the option as `pyramidSpill`. |
| `MemmapF64Builder(path)` and `open_f64(path)` (`python/xyg/_ooc.py`) | Canonical f64 column file; sparse pre-size, doubling growth, final truncate | M (caller-named, durable if the caller keeps it) | Exactly the caller's `path`; no default directory | Needs a filesystem with `mmap` and `ftruncate` (ext4, xfs, apfs, NTFS, overlayfs, bind mounts). Network and some FUSE or 9p shares may lack coherent `mmap` or sparse files; use a local volume for out-of-core columns. A zero-row column is a 0-byte file. |
| `<column path>.xyzones` (`python/xyg/columns.py` zone-map cache) | Zone-map fold of a memmapped column, validated by magic, chunk size, row count, source size and mtime | C | Beside the column file | Written via `<path>.<pid>.tmp` then `os.replace`. Read-only, full, or rename-refusing volumes: write failure is swallowed, the partial temp file is removed, and maps are recomputed per build. Stale sidecars self-invalidate (size or mtime). An mtime-coarse share (FAT 2 s, some SMB/NFS) can only cause a miss or, if a same-size edit lands in the same tick, a stale hit; delete the sidecar after rewriting a column in place on such a volume. |
| `<prefix>.idx`, `.lon.f32`, `.lat.f32` (`python/xyg/_spatial.py`) | Spatial index built by the external `osm-sort` tool; XYG only reads it with `np.memmap` | M | Caller-supplied prefix | Read-only mount is fine. Rebuildable derived buffer (§27). |
| XYGC chunked columns (`crates/xyg-engine/src/chunked_columns.rs`, `xyg_chunked_columns_open`) | `ChunkedColumns::create` writes a caller-named artifact; reads use positioned I/O | D (caller-named) | Caller path; **must be valid UTF-8**, else open returns handle 0 | Missing, partial, or corrupt artifacts return handle 0 (fail closed). Unix and Windows use separate `FileExt` implementations. Unavailable in Pyodide (fail-closed stubs, [host-parity.md](host-parity.md)). |
| `export.save/to_html/to_svg/...` destinations (`python/xyg/export.py` `_atomic_write_bytes`, `_atomic_write_text`; `_figure_export.py`; `_facets_grid.py`) | Caller-named export file | D | Caller path; temp file is created in the **destination directory** | Same-directory `mkstemp`, `fsync`, `os.replace`; failure removes the temp file and keeps the previous destination. Requires create and rename permission in the destination directory, so a write-only file or a mount that forbids rename fails with the OS error. `wasm_ticks=True` also writes Worker/WASM sidecars beside the destination. Node `toHtml(path)` uses a direct `writeFileSync` (not atomic). |
| `xy-export-*` temporary directory (`python/xyg/_chromium.py`, `export.py` browser PNG) | Page HTML, screenshot, Chromium stderr during browser-resolved export | T | `tempfile.TemporaryDirectory()` | Removed on close (retrying removal on Windows) or GC. Chromium also writes its own profile and `/dev/shm` data; `--disable-dev-shm-usage` is passed on the one-shot path, and containers with a small `/dev/shm` need `--shm-size` or the same flag. |
| `plt.show()` page (`python/xyg/pyplot/_mplfig.py`) | One HTML page opened in the default browser | T | `tempfile.NamedTemporaryFile(delete=False)` in the platform temp dir | Intentionally not deleted (the browser reads it after the call returns). URL is `Path.as_uri()`; it was previously `f"file://{name}"`, which is invalid on Windows drive paths and unescaped for spaces (fixed in #1014). |
| Reflex payload assets (`python/reflex_xy/payload_asset.py`) | `assets/xy/<digest>.xyf`, content-addressed | D (regenerated at each app compile) | `Path.cwd() / "assets" / "xy"`; skipped when `REFLEX_BACKEND_ONLY` | Follows the Reflex convention that the app is run from its app root. Written via a unique `.tmp` then replace. In a container mount the app root (or `assets/`) writable at build time; a backend-only runtime never writes. |
| Reflex figure registry, widget comm, notebook display | none | N | n/a | Per-process memory; rebuilt from Reflex state on miss. `XY_NOTEBOOK_DISPLAY` is a mode switch, not a path. |
| `XYG_ABI_TRACE_FILE` (`_abi_generated.py`, `_abi_generated.js`) | Test-only append-only JSONL of ABI calls | T (diagnostic) | Exact env value | Off unless set. Not part of the product contract. |
| `XYG_NATIVE_LIB` | none (read-only library path override) | n/a | Python accepts relative or absolute; Node requires **absolute** and throws `XYG_NATIVE_LIBRARY_PATH_INVALID` | Development override; packaged lookup is otherwise fixed. |
| Browser client (`js/src`, `@curatelabs/xyg`), browser WASM Worker | none | N | n/a | No IndexedDB, Cache Storage, OPFS, cookie, or `localStorage` use in the product path (only the opt-in `xy_debug` read in the Reflex wrapper). WASM modules and Workers are served from caller-chosen URLs; the browser HTTP cache is not an XYG store. |
| Pyodide / Emscripten | none | N | n/a | Tile spill and XYGC chunk reads are fail-closed stubs; in-memory kernels and Scene consumers work. |
| Build-time (`hatch_build.py`, `js/package-wasm.mjs`, `js/optimize-wasm.mjs`) | Packaged native library, bundles, WASM assets; `optimize-wasm` uses `mkdtemp(os.tmpdir())` | build only | Repository checkout / `tmpdir` | Not runtime storage. |

## Supported-host statements

- **Linux, macOS, Windows (native Python and Node):** temp and spill paths follow
  the OS temp dir for that platform; caller-named paths are used verbatim.
  Nothing is Linux-only. Distribution is a separate matter: published wheels
  and platform packages are listed in the README, and an unsupported platform
  fails at native load with `XYG_NATIVE_UNSUPPORTED_PLATFORM` or an
  `ImportError`, not at a storage path.
- **Containers and VMs:** a different root than the host (bind mounts, named
  volumes, WSL, VM shared folders) is fine for every row above. Guidance:
  1. Put `TMPDIR` on a disk-backed volume with room for the spill when large
     pyramids are expected (`memory_report()["pyramid_spilled_bytes"]`);
     tmpfs temp directories are RAM.
  2. Put out-of-core columns (`MemmapF64Builder`) and their `.xyzones`
     sidecars on a local volume that supports `mmap` and sparse files.
  3. Make export destination directories writable (not just the file) so the
     atomic replace can run.
  4. A read-only root filesystem is supported for in-memory use and for
     exports to a writable mount; only spill and sidecar writes need space.
- **Concurrency:** spill names embed PID and a counter and use `create_new`, so
  two processes never share a spill file. Two processes writing the same
  `.xyzones` sidecar publish whole-or-nothing via rename; the temp name
  includes the PID.

## Browser and Pyodide

The browser Worker, WASM host, and `@curatelabs/xyg` client hold all state in
memory and in the page's own caches. They do not persist chart data. Durable
output from a browser deployment is whatever the application saves.

## Known limits (documented, not defects)

- A crash can orphan `xy-tiles-<pid>-<n>.xyts` and `.<name>.<pid>.tmp` files.
  They are never read back; delete them freely.
- The native spill directory cannot be set per figure; it is the process temp
  directory. A per-figure `spill_dir` would be a new public option and is out
  of scope for this audit.
- The chunk artifact (XYGC) path crosses the C ABI as UTF-8; a non-UTF-8 Unix
  path is rejected with handle 0 rather than lossily converted.
- `Path.cwd()` in the Reflex asset writer is the Reflex app-root convention.

## Regression evidence

- `tests/test_phase4_tile_spill_hosts.py` — explicit spill failure is actionable
  and releases the RAM cache; spill output is bit-identical to RAM.
- `tests/test_ooc.py::test_zone_map_cache_failure_is_silent_and_leaves_no_temp_file`
  — a volume that refuses the sidecar publish neither fails ingest nor strands
  a temp file.
- `tests/pyplot/test_pyplot_state_management.py::test_pyplot_show_opens_valid_file_uri_from_platform_temp_dir`
  — `show()` honors `TMPDIR` and opens a valid `file:` URI.
- Cross-host conformance (#54) and the Phase 4 spill work (#5) are reused as
  existing evidence; this document adds no certification program.
