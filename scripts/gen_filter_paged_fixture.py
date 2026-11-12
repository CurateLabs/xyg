#!/usr/bin/env python3
"""Materialize and fully verify the deterministic five-dimension XYGC fixture.

This is evidence authoring, not a product reader or filtering fallback. NumPy
keeps generation bounded to one chunk; the native/browser count oracle is separate.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import struct
from pathlib import Path

import numpy as np

FEATURES = (("b", 17, 65521), ("c", 29, 65519), ("d", 43, 65497), ("e", 71, 65479))
FIRST = (1 << 63) + 17
MAX_METADATA = 16 << 20


def require(condition, detail):
    if not condition:
        raise ValueError(detail)


def overview(rows, multiplier, period):
    bucket = max(1, (rows + 511) // 512)
    points = []
    for start in range(0, rows, bucket):
        stop = min(rows, start + bucket)
        if stop - start >= period:
            low = start + (-start) % period
            residue = ((period - 1) * pow(multiplier, -1, period)) % period
            high = start + (residue - start) % period
        else:
            values = [(i * multiplier) % period for i in range(start, stop)]
            low = start + values.index(min(values))
            high = start + values.index(max(values))
        points.extend(
            (i, float(i), float(i * multiplier % period))
            for i in sorted({start, low, high, stop - 1})
        )
    return points


def sync(handle):
    handle.flush()
    os.fsync(handle.fileno())


def write_new_json(path, value):
    # Preserve failed partials and never replace an existing evidence record.
    temporary = path.with_name(path.name + ".partial")
    with temporary.open("x", encoding="utf-8") as output:
        output.write(json.dumps(value, indent=2) + "\n")
        sync(output)
    os.link(temporary, path)
    temporary.unlink()


def generate(directory, rows=100_000_000, chunk=65536):
    require(type(rows) is int and 0 < rows <= (1 << 32) - 1, "invalid rows")
    require(type(chunk) is int and 0 < chunk <= 1 << 20, "invalid chunk rows")
    count = (rows + chunk - 1) // chunk
    require(count * 48 <= MAX_METADATA, "metadata exceeds XYGC admission")
    require(all(math.gcd(a, p) == 1 for _, a, p in FEATURES), "invalid fixture periods")
    directory.mkdir(parents=True, exist_ok=False)
    offset, results = 64 + count * 48, []
    end = offset + rows * 16
    # Serial files keep authoring memory independent of the number of dimensions.
    for name, multiplier, period in FEATURES:
        temporary = directory / ("time-" + name + ".xygc.partial")
        metadata = bytearray(count * 48)
        with temporary.open("xb", buffering=1 << 20) as output:
            output.write(bytes(offset))
            for k, start in enumerate(range(0, rows, chunk)):
                n = min(chunk, rows - start)
                ids = np.arange(start, start + n, dtype=np.uint64)
                pairs = np.empty((n, 2), dtype="<f8")
                pairs[:, 0], pairs[:, 1] = ids, (ids * multiplier) % period
                struct.pack_into(
                    "<QII4d",
                    metadata,
                    k * 48,
                    start,
                    n,
                    0,
                    float(start),
                    float(start + n - 1),
                    float(pairs[:, 1].min()),
                    float(pairs[:, 1].max()),
                )
                output.write(pairs.tobytes())
            require(output.tell() == end, "incomplete canonical output")
            points = overview(rows, multiplier, period)
            for point in points:
                output.write(struct.pack("<Q2d", *point))
            output.seek(64)
            output.write(metadata)
            header = bytearray(64)
            struct.pack_into(
                "<4sIQIIQQI",
                header,
                0,
                b"XYGC",
                2,
                rows,
                chunk,
                count,
                offset,
                end,
                len(points),
            )
            output.seek(0)
            output.write(header)
            sync(output)
        final = temporary.with_suffix("")
        os.link(temporary, final)
        temporary.unlink()
        size = final.stat().st_size
        require(size == end + len(points) * 24, "incomplete fixture")
        results.append(
            {
                "path": str(final.resolve()),
                "dimension": name,
                "multiplier": multiplier,
                "period": period,
                "bytes": size,
                "overviewPoints": len(points),
            }
        )
    result = {
        "schemaVersion": 1,
        "rows": rows,
        "chunkRows": chunk,
        "firstRow": str(FIRST),
        "dimensions": ["time", "b", "c", "d", "e"],
        "files": results,
        "correspondence": "Every file row i is canonical firstRow+i; time is exactly i",
        "generatorSha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "performanceQualification": False,
    }
    write_new_json(directory / "manifest.json", result)
    return result


def verify(directory):
    manifest = json.loads((directory / "manifest.json").read_text())
    rows, chunk = manifest["rows"], manifest["chunkRows"]
    require(type(rows) is int and 0 < rows <= (1 << 32) - 1, "invalid rows")
    require(type(chunk) is int and 0 < chunk <= 1 << 20, "invalid chunk rows")
    require(manifest["dimensions"] == ["time", "b", "c", "d", "e"], "fixture schema")
    require(manifest["firstRow"] == str(FIRST) and len(manifest["files"]) == 4, "fixture identity")
    count = (rows + chunk - 1) // chunk
    require(count * 48 <= MAX_METADATA, "metadata exceeds XYGC admission")
    results = []
    for record, (name, multiplier, period) in zip(manifest["files"], FEATURES, strict=True):
        require(
            (record["dimension"], record["multiplier"], record["period"])
            == (name, multiplier, period),
            "fixture formula",
        )
        digest = hashlib.sha256()
        with Path(record["path"]).open("rb", buffering=1 << 20) as source:
            header = source.read(64)
            require(len(header) == 64, "truncated header")
            offset, end = 64 + count * 48, 64 + count * 48 + rows * 16
            points = overview(rows, multiplier, period)
            expected = bytearray(64)
            struct.pack_into(
                "<4sIQIIQQI", expected, 0, b"XYGC", 2, rows, chunk, count, offset, end, len(points)
            )
            require(header == expected, "invalid fixture header")
            require(os.fstat(source.fileno()).st_size == end + len(points) * 24, "fixture extent")
            digest.update(header)
            metadata = source.read(count * 48)
            digest.update(metadata)
            for k, start in enumerate(range(0, rows, chunk)):
                n = min(chunk, rows - start)
                raw = source.read(n * 16)
                require(len(raw) == n * 16, "truncated canonical page")
                digest.update(raw)
                pairs = np.frombuffer(raw, dtype="<f8").reshape(n, 2)
                ids = np.arange(start, start + n, dtype=np.uint64)
                require(np.array_equal(pairs[:, 0], ids.astype(np.float64)), "time plane")
                values = ((ids % period) * multiplier) % period
                require(np.array_equal(pairs[:, 1], values.astype(np.float64)), "dimension plane")
                expected_meta = (
                    start,
                    n,
                    0,
                    pairs[:, 0].min(),
                    pairs[:, 0].max(),
                    pairs[:, 1].min(),
                    pairs[:, 1].max(),
                )
                require(
                    struct.unpack_from("<QII4d", metadata, k * 48) == expected_meta,
                    "chunk metadata",
                )
            raw = source.read(len(points) * 24)
            digest.update(raw)
            require(raw == b"".join(struct.pack("<Q2d", *p) for p in points), "overview")
            require(not source.read(1), "trailing bytes")
        results.append(
            {"dimension": name, "sha256": digest.hexdigest(), "completeRowsVerified": rows}
        )
    return {
        "rowsPerFile": rows,
        "physicalFiles": 4,
        "distinctDimensions": 5,
        "results": results,
        "fullCanonicalScan": True,
        "performanceQualification": False,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["generate", "verify"])
    parser.add_argument("directory", type=Path)
    parser.add_argument("--rows", type=int, default=100_000_000)
    parser.add_argument("--chunk", type=int, default=65536)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    result = (
        generate(args.directory, args.rows, args.chunk)
        if args.action == "generate"
        else verify(args.directory)
    )
    if args.report:
        write_new_json(args.report, result)
    print(json.dumps(result), flush=True)
