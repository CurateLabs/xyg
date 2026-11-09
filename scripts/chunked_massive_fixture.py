"""Manual, bounded-memory materialized XYGC fixture and independent full scan.

This authors synthetic canonical rows x=i, y=(17*i)%65521. It is not a product
reader or an alternative index. No huge fixture runs in ordinary CI.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import resource
import struct
import sys
import time
from pathlib import Path

import numpy as np
import numpy.typing as npt

PERIOD = 65521
DTYPE = np.dtype("<f8")


def memory() -> dict:
    fields = {}
    for line in Path("/proc/meminfo").read_text().splitlines():
        key, value = line.split(":", 1)
        if key in ("MemTotal", "MemAvailable"):
            fields[key] = int(value.split()[0]) * 1024
    limit = Path("/sys/fs/cgroup/memory.max")
    fields["cgroupMemoryMax"] = limit.read_text().strip() if limit.exists() else None
    fields["processPeakRssBytes"] = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024
    return fields


def pairs(start: int, count: int) -> npt.NDArray[np.float64]:
    ids = np.arange(start, start + count, dtype=np.uint64)
    out = np.empty((count, 2), dtype=DTYPE)
    out[:, 0] = ids
    out[:, 1] = (ids * 17) % PERIOD
    return out


def overview_oracle(rows: int) -> list[tuple[int, float, float]]:
    """Independent arithmetic oracle; never uses the generator's running buckets."""
    width = max(1, (rows + 511) // 512)
    result = []
    for start in range(0, rows, width):
        stop = min(rows, start + width)
        if stop - start >= PERIOD:
            lo = start + (-start) % PERIOD
            residue = ((PERIOD - 1) * pow(17, -1, PERIOD)) % PERIOD
            hi = start + (residue - start) % PERIOD
        else:
            values = [(17 * i) % PERIOD for i in range(start, stop)]
            lo = start + values.index(min(values))
            hi = start + values.index(max(values))
        result.extend(
            (i, float(i), float((17 * i) % PERIOD)) for i in sorted({start, lo, hi, stop - 1})
        )
    return result


def generate(path: Path, rows: int, chunk_rows: int) -> dict:
    if not 0 < rows <= 1 << 53 or not 0 < chunk_rows <= 1 << 20:
        raise ValueError("fixture rows must be in [1,2^53], chunk_rows in [1,2^20]")
    partial = path.with_name(path.name + ".partial")
    if path.exists() or partial.exists():
        raise FileExistsError("refusing to overwrite an existing fixture or partial")
    path.parent.mkdir(parents=True, exist_ok=True)
    before = memory()
    chunks = (rows + chunk_rows - 1) // chunk_rows
    if chunks > (1 << 32) - 1 or chunks * 48 > 16 << 20:
        raise ValueError("manual fixture metadata exceeds 16 MiB; choose larger chunks")
    data_offset = 64 + chunks * 48
    overview_offset = data_offset + rows * 16
    bucket_rows = (rows + 511) // 512
    overview = []
    bucket = None
    metadata = []
    written_since_sync = 0
    sync_start = data_offset
    started = time.perf_counter()
    with partial.open("xb", buffering=1 << 20) as f:
        f.write(bytes(data_offset))
        for start in range(0, rows, chunk_rows):
            data = pairs(start, min(chunk_rows, rows - start))
            ys = data[:, 1]
            metadata.append(
                struct.pack(
                    "<QII4d",
                    start,
                    len(data),
                    0,
                    float(start),
                    float(start + len(data) - 1),
                    float(np.min(ys)),
                    float(np.max(ys)),
                )
            )
            f.write(data.tobytes())
            pos = 0
            while pos < len(data):
                row = start + pos
                end = min(rows, ((row // bucket_rows) + 1) * bucket_rows)
                size = min(end - row, len(data) - pos)
                segment = data[pos : pos + size]
                low = int(np.argmin(segment[:, 1]))
                high = int(np.argmax(segment[:, 1]))
                first = (row, float(segment[0, 0]), float(segment[0, 1]))
                last = (row + size - 1, float(segment[-1, 0]), float(segment[-1, 1]))
                lo = (row + low, float(segment[low, 0]), float(segment[low, 1]))
                hi = (row + high, float(segment[high, 0]), float(segment[high, 1]))
                if bucket is None:
                    bucket = [first, lo, hi, last]
                else:
                    if lo[2] < bucket[1][2]:
                        bucket[1] = lo
                    if hi[2] > bucket[2][2]:
                        bucket[2] = hi
                    bucket[3] = last
                pos += size
                if row + size == end:
                    overview.extend(sorted(set(bucket)))
                    bucket = None
            written_since_sync += data.nbytes
            if written_since_sync >= 256 << 20:
                f.flush()
                os.fdatasync(f.fileno())
                if hasattr(os, "posix_fadvise"):
                    os.posix_fadvise(
                        f.fileno(), sync_start, written_since_sync, os.POSIX_FADV_DONTNEED
                    )
                sync_start += written_since_sync
                written_since_sync = 0
                print(
                    json.dumps(
                        {
                            "writtenRows": start + len(data),
                            "sourceRows": rows,
                            "processPeakRssBytes": memory()["processPeakRssBytes"],
                        }
                    ),
                    flush=True,
                )
        assert bucket is None and len(metadata) == chunks
        assert overview == overview_oracle(rows)
        f.seek(overview_offset)
        for point in overview:
            f.write(struct.pack("<Q2d", *point))
        f.seek(64)
        for record in metadata:
            f.write(record)
        header = bytearray(64)
        struct.pack_into(
            "<4sIQIIQQI",
            header,
            0,
            b"XYGC",
            2,
            rows,
            chunk_rows,
            chunks,
            data_offset,
            overview_offset,
            len(overview),
        )
        f.seek(0)
        f.write(header)
        f.flush()
        os.fsync(f.fileno())
        if hasattr(os, "posix_fadvise"):
            os.posix_fadvise(f.fileno(), 0, 0, os.POSIX_FADV_DONTNEED)
    # Atomic no-clobber installation even if another writer creates path
    # during a long generation. Both names are on the same filesystem.
    os.link(partial, path)
    partial.unlink()
    st = path.stat()
    result = {
        "schemaVersion": 1,
        "kind": "materialized synthetic canonical XYGC v2",
        "rows": rows,
        "chunkRows": chunk_rows,
        "chunks": chunks,
        "overviewPoints": len(overview),
        "bytes": st.st_size,
        "allocatedBytes": st.st_blocks * 512,
        "before": before,
        "after": memory(),
        "elapsedSecondsDiagnostic": time.perf_counter() - started,
        "pattern": {"x": "row ordinal", "y": "(17*row)%65521"},
        "platform": platform.platform(),
        "python": sys.version,
        "command": sys.argv,
        "performanceQualification": False,
    }
    assert st.st_size == overview_offset + len(overview) * 24
    assert st.st_blocks * 512 >= rows * 16, (
        "sparse or compressed storage is not a materialized fixture"
    )
    path.with_name(path.name + ".generation.json").write_text(json.dumps(result, indent=2) + "\n")
    return result


def verify(path: Path, ranges: list[dict]) -> dict:
    started = time.perf_counter()
    before = memory()
    digest = hashlib.sha256()
    selected = [[] for _ in ranges]
    with path.open("rb", buffering=1 << 20) as f:
        header = f.read(64)
        digest.update(header)
        magic, version, rows, chunk_rows, chunks, data_offset, overview_offset, points = (
            struct.unpack_from("<4sIQIIQQI", header)
        )
        assert magic == b"XYGC" and version == 2
        assert data_offset == 64 + chunks * 48 and overview_offset == data_offset + 16 * rows
        metadata = f.read(chunks * 48)
        digest.update(metadata)
        count = 0
        # Read EVERY detail row, without zone-map pruning. This also computes
        # the complete file SHA256 and checks the authored independent formula.
        for chunk in range(chunks):
            start, size, reserved, xmin, xmax, ymin, ymax = struct.unpack_from(
                "<QII4d", metadata, chunk * 48
            )
            assert start == count and 0 < size <= chunk_rows and reserved == 0
            raw = f.read(size * 16)
            assert len(raw) == size * 16
            digest.update(raw)
            data = np.frombuffer(raw, dtype=DTYPE).reshape(-1, 2)
            ids = np.arange(start, start + size, dtype=np.uint64)
            assert np.array_equal(data[:, 0], ids.astype(np.float64))
            # Independent scalar definition vectorized for the full-scan oracle.
            values = ((ids % PERIOD) * 17) % PERIOD
            assert np.array_equal(data[:, 1], values.astype(np.float64))
            assert (xmin, xmax, ymin, ymax) == (
                np.min(data[:, 0]),
                np.max(data[:, 0]),
                np.min(data[:, 1]),
                np.max(data[:, 1]),
            )
            for index, query in enumerate(ranges):
                lo, hi = query["x"]
                mask = (data[:, 0] >= lo) & (data[:, 0] <= hi)
                if query.get("y") is not None:
                    bottom, top = query["y"]
                    mask &= (data[:, 1] >= bottom) & (data[:, 1] <= top)
                if mask.any():
                    selected[index].extend(
                        (int(i), float(x), float(y))
                        for i, (x, y) in zip(ids[mask], data[mask], strict=True)
                    )
            count += size
            if chunk % 1024 == 0:
                print(json.dumps({"verifiedRows": count, "sourceRows": rows}), flush=True)
        assert count == rows
        raw = f.read(points * 24)
        digest.update(raw)
        actual = [struct.unpack_from("<Q2d", raw, i * 24) for i in range(points)]
        assert actual == overview_oracle(rows) and not f.read(1)
        if hasattr(os, "posix_fadvise"):
            os.posix_fadvise(f.fileno(), 0, 0, os.POSIX_FADV_DONTNEED)
    result = {
        "schemaVersion": 1,
        "rowsScanned": rows,
        "everyDetailRowVerified": True,
        "sha256": digest.hexdigest(),
        "bytes": path.stat().st_size,
        "allocatedBytes": path.stat().st_blocks * 512,
        "before": before,
        "after": memory(),
        "ranges": [
            {"query": bounds, "rows": entries}
            for bounds, entries in zip(ranges, selected, strict=True)
        ],
        "overview": actual,
        "elapsedSecondsDiagnostic": time.perf_counter() - started,
        "performanceQualification": False,
    }
    path.with_name(path.name + ".oracle.json").write_text(json.dumps(result, indent=2) + "\n")
    return result


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("mode", choices=["generate", "verify"])
    p.add_argument("--path", required=True, type=Path)
    p.add_argument("--rows", type=int, default=4_500_000_000)
    p.add_argument("--chunk-rows", type=int, default=65536)
    p.add_argument("--range", action="append", default=[])
    p.add_argument("--requests", type=Path)
    args = p.parse_args()
    if args.mode == "generate":
        generate(args.path, args.rows, args.chunk_rows)
    else:
        verify(
            args.path,
            json.loads(args.requests.read_text())
            if args.requests
            else [{"x": tuple(map(float, r.split(":"))), "y": None} for r in args.range],
        )
