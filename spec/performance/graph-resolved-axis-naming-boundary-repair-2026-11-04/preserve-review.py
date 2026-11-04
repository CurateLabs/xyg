"""Preserve the supplied independent review request without altering old evidence."""

import gzip
import hashlib
import json
import sys
from pathlib import Path

out = Path(__file__).resolve().parent
source = Path(sys.argv[1])
raw = source.read_bytes()
packed = gzip.compress(raw, mtime=0)
log = out / "review-request.txt.gz"
record = out / "review-request.json"
assert not log.exists() and not record.exists()
log.write_bytes(packed)
record.write_text(
    json.dumps(
        {
            "reviewer": "s5a_final_review",
            "decision": "REQUEST_CHANGES",
            "priority": "P2",
            "candidate": "47d4d6514671b12c8f263a3d640416af1983621c",
            "reviewedSourceDiffSha256": "7598b93ec17f399a2b7dab33bdc291e95c5c99507630256e6d5482631be502e7",
            "provenance": "Exact user-forwarded review/repair request; terminal newline added by heredoc",
            "source": str(source),
            "log": log.name,
            "rawBytes": len(raw),
            "rawSha256": hashlib.sha256(raw).hexdigest(),
            "gzipSha256": hashlib.sha256(packed).hexdigest(),
            "newIndependentReviewStillRequired": True,
        },
        indent=2,
    )
    + "\n"
)
assert gzip.decompress(log.read_bytes()) == raw
print(record.read_text())
