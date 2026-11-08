"""Verify complete native planes/pixels against a full source scan and syscall trace.

This consumes the independent oracle from chunked_massive_fixture.py, not a
sample. The syscall trace must filter the source path and include pread64 with
timestamps, fd paths and suppressed buffer strings (strace -f -ttt -yy -s 0).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import struct
from pathlib import Path

from PIL import Image


def verify(source: Path, oracle: Path, browser: Path, trace: Path) -> dict:
    expected = json.loads(oracle.read_text())
    report = json.loads((browser / "report.json").read_text())
    stat = source.stat()
    assert expected["everyDetailRowVerified"]
    assert expected["rowsScanned"] == int(report["source"]["rows"])
    assert expected["bytes"] == report["source"]["bytes"] == stat.st_size
    assert stat.st_size > report["source"]["physicalRamBytes"]
    assert stat.st_blocks * 512 >= expected["rowsScanned"] * 16
    files = {}
    for scanned, snapshot in zip(expected["ranges"], report["snapshots"], strict=True):
        assert scanned["query"] == snapshot["ranges"]
        path = browser / snapshot["nativeData"]["file"]
        data = path.read_bytes()
        assert hashlib.sha256(data).hexdigest() == snapshot["nativeData"]["sha256"]
        magic, version, n = struct.unpack_from("<4sIQ", data)
        assert magic == b"XYBO" and version == 1 and len(data) == 16 + n * 24
        ids = struct.unpack_from("<" + "Q" * n, data, 16)
        xs = struct.unpack_from("<" + "d" * n, data, 16 + n * 8)
        ys = struct.unpack_from("<" + "d" * n, data, 16 + n * 16)
        assert list(zip(ids, xs, ys, strict=True)) == [tuple(row) for row in scanned["rows"]]
        assert [str(i) for i in ids] == snapshot["ids"]
        images = [browser / (snapshot["name"] + suffix) for suffix in (".png", "-oracle.png")]
        with Image.open(images[0]) as a, Image.open(images[1]) as b:
            a, b = a.convert("RGBA"), b.convert("RGBA")
            assert a.size == b.size and a.tobytes() == b.tobytes()
            pixel_hash = hashlib.sha256(a.tobytes()).hexdigest()
        files[snapshot["name"]] = {
            "rows": n,
            "nativePlanesSha256": hashlib.sha256(data).hexdigest(),
            "decodedRgbaSha256": pixel_hash,
            "pngSha256": {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in images},
        }
    assert report["trustedEvents"] and all(event["trusted"] for event in report["trustedEvents"])
    assert report["errors"] == report["external"] == []
    with source.open("rb") as f:
        header = f.read(64)
    rows = struct.unpack_from("<Q", header, 8)[0]
    chunk_rows = struct.unpack_from("<I", header, 16)[0]
    data_offset = struct.unpack_from("<Q", header, 24)[0]
    chunk_bytes = chunk_rows * 16
    allowed = set()
    for request in report["wire"]:
        lo, hi = request["ranges"]["x"]
        first = max(0, math.ceil(lo)) // chunk_rows
        last = min(rows - 1, math.floor(hi)) // chunk_rows
        allowed.update(range(first, last + 1))
    calls, pending = [], {}
    for line in trace.read_text().splitlines():
        if "<unfinished ...>" in line and "pread64(" in line:
            pending[line.split()[0]] = line.replace(" <unfinished ...>", "")
            continue
        if "<... pread64 resumed>" in line:
            tid = line.split()[0]
            line = pending.pop(tid) + line.split("<... pread64 resumed>", 1)[1]
        if "pread64(" not in line:
            continue
        match = re.search(
            r"^(\d+)\s+([\d.]+)\s+pread64\(.*?,\s*(\d+),\s*(\d+)\)\s*=\s*(\d+)$",
            line,
        )
        assert match, line
        tid, at, requested, offset, returned = match.groups()
        requested, offset, returned = int(requested), int(offset), int(returned)
        chunk = (offset - data_offset) // chunk_bytes
        assert chunk in allowed and 0 < requested <= chunk_bytes
        assert 0 < returned <= requested
        assert offset + requested <= data_offset + (chunk + 1) * chunk_bytes
        calls.append(
            {
                "tid": int(tid),
                "epochSeconds": float(at),
                "offset": offset,
                "bytes": returned,
                "chunk": chunk,
            }
        )
    assert not pending and calls
    warm_start = report["snapshots"][-2]["observedAtEpochMs"] / 1000
    assert not [call for call in calls if call["epochSeconds"] > warm_start]
    return {
        "sourceSha256FromCompleteScan": expected["sha256"],
        "everyDetailRowVerified": True,
        "rowsScanned": expected["rowsScanned"],
        "sourceBytes": stat.st_size,
        "sourceAllocatedBytes": stat.st_blocks * 512,
        "physicalRamBytes": report["source"]["physicalRamBytes"],
        "nativeAndPixelOracles": files,
        "positionedDetailReadsIncludingSupersededCalls": calls,
        "totalPositionedDetailBytes": sum(call["bytes"] for call in calls),
        "warmPositionedReads": 0,
        "metadataOverviewBytesPerOpenAdditional": data_offset
        + struct.unpack_from("<I", header, 40)[0] * 24,
        "scope": "Functional native Node overview/axis-wheel/pan/revisit; not a performance or global CPU/WASM/GPU-budget qualification",
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("source", "oracle", "browser", "trace", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    result = verify(args.source, args.oracle, args.browser, args.trace)
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))
