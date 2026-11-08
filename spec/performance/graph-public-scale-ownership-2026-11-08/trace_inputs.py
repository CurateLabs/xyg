"""Frame all public commands for the independent requested-allocation ledger."""

import base64
import gzip
import json
import struct
import sys
from pathlib import Path


def main():
    source, output = map(Path, sys.argv[1:])
    data = source.read_bytes()
    if source.suffix == ".gz":
        data = gzip.decompress(data)
    report = json.loads(data)
    framed = bytearray(struct.pack("<Q", len(report["views"])))
    for view in report["views"]:
        framed.extend(struct.pack("<QQ", view["actualArena"], len(view["replay"])))
        for record in view["replay"]:
            request = base64.b64decode(record["request"], validate=True)
            framed.extend(struct.pack("<QQ", record["replyBytes"], len(request)))
            framed.extend(request)
    output.write_bytes(framed)


if __name__ == "__main__":
    main()
