"""Read-only before/after proof; run from the checkout being inspected."""

import hashlib
import importlib.util
import json
import struct
import sys
from pathlib import Path

from xyg import _native
from xyg._graphforge import compose_graphforge_request

root = Path.cwd()
spec = importlib.util.spec_from_file_location(
    "cross_host", root / "scripts/gen_graphforge_cross_host.py"
)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def sections(data):
    count = struct.unpack_from("<I", data, 8)[0]
    names = 32 + count * 40
    result = {}
    for i in range(count):
        name_offset, name_length, dtype, index, offset, size, rows = struct.unpack_from(
            "<IIIIQQQ", data, 32 + i * 40
        )
        name = data[names + name_offset : names + name_offset + name_length].decode()
        result[f"{name}:{index}"] = {
            "dtype": dtype,
            "rows": rows,
            "sha256": sha(data[offset : offset + size]),
        }
    return result


result = {"native_abi": _native._lib.xyg_abi_version(), "cases": {}}
for case in module.cases():
    request = module.build_request(case)
    document = compose_graphforge_request(request)
    result["cases"][case["name"]] = {
        "request": sha(request),
        "document": sha(document),
        "sections": sections(document),
    }
Path(sys.argv[1]).write_text(json.dumps(result, indent=2) + "\n")
print(f"inspected {len(result['cases'])} cases, native ABI {result['native_abi']}")
