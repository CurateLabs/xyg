"""Verify immutable inherited evidence and disjoint source integration."""

import json
import subprocess
from pathlib import Path

receipt = Path(__file__).resolve().parent
prior = "24ab68045c98ea50055061191759c25479ddedcd"
main = "5e00c6b9147b67f20046cdfa6bd77aa413c18474"
reviewed = "2bb6a0c3841d5cba19f6ed74b41524274d0a1ce7"


def git(*args):
    return subprocess.check_output(["git", *args])


def tree(ref):
    result = {}
    for row in git("ls-tree", "-r", "-z", ref).split(b"\0"):
        if row:
            meta, path = row.split(b"\t", 1)
            result[path.decode()] = meta.decode()
    return result


assert git("rev-parse", main + "^{tree}") == git("rev-parse", reviewed + "^{tree}")
old, accepted = tree(prior), tree(main)
paths = sorted(set(old) | set(accepted))
actual = dict(
    zip(
        paths,
        subprocess.check_output(
            ["git", "hash-object", "--stdin-paths"], input=("\n".join(paths) + "\n").encode()
        )
        .decode()
        .splitlines(),
        strict=True,
    )
)
counts = {}
for label, source in [("R10", old), ("accepted-main", accepted)]:
    protected = {
        p: identity
        for p, identity in source.items()
        if p.startswith(("spec/performance/", "spec/matplotlib/evidence/"))
    }
    for path, identity in protected.items():
        assert actual[path] == identity.split()[-1], path
    counts[label] = len(protected)
# All accepted product/build/test bytes remain main-exact except the explicit
# existing picked-target changes; those stay R10-exact.
base = git("merge-base", main, prior).decode().strip()
changed = set(
    git(
        "diff",
        "--name-only",
        base,
        prior,
        "--",
        "crates",
        "python",
        "js",
        "packages",
        "scripts",
        ".github",
    )
    .decode()
    .splitlines()
)
source_counts = {"R10": 0, "accepted-main": 0}
for path in sorted(set(accepted) | set(old)):
    identity = accepted.get(path)
    if path.startswith(("crates/", "python/", "js/", "packages/", "scripts/", ".github/")):
        reference = old[path] if path in changed else identity
        assert actual[path] == reference.split()[-1], path
        source_counts["R10" if path in changed else "accepted-main"] += 1
record = {
    "prior": prior,
    "accepted_main": main,
    "accepted_main_tree_exact_reviewed": reviewed,
    "protected_file_counts": counts,
    "source_file_counts": source_counts,
    "R10_source_paths": sorted(changed),
    "no_new_external_review_claim": True,
}
output = receipt / "protection-final.json"
with output.open("x") as stream:
    stream.write(json.dumps(record, indent=2) + "\n")
print(json.dumps(record, indent=2))
