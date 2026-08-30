#!/usr/bin/env python3
"""Cherry-pick stay-host commits; resolve spec/coverage/figure conflicts."""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

SPEC = (
    "spec/design/ownership-audit.md",
    "spec/design/host-parity.md",
    "spec/design-dossier.md",
)
HOST_FILES = (
    "packages/xy-node/src/figure.js",
    "packages/xy-node/src/scene.js",
    "packages/xy-node/src/marks/scatter.js",
)
COVERAGE = "packages/xy-node/test/coverage.test.mjs"


def run(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, text=True, capture_output=True, check=check)


def show(rev: str, path: str) -> str:
    return run("git", "show", f"{rev}:{path}").stdout


def patch_row(head: str, inc: str) -> str:
    hk = set(re.findall(r"emit-[a-z0-9-]+|next-trace-id-base|scene-[a-z0-9-]+", head))
    ik = set(re.findall(r"emit-[a-z0-9-]+|next-trace-id-base|scene-[a-z0-9-]+", inc))
    return inc if ik - hk else head


def merge_spec(head_rev: str, inc_rev: str) -> None:
    for path in SPEC:
        head = show(head_rev, path)
        inc = show(inc_rev, path)
        if path.endswith("host-parity.md"):
            out = head
            for line in inc.splitlines(True):
                if line.startswith("  Node ") and line not in out:
                    out = out.replace("---\n", line + "---\n", 1)
            Path(path).write_text(out)
            continue
        out_lines: list[str] = []
        for hline in head.splitlines():
            replaced = False
            prefix = None
            if hline.startswith("| `"):
                parts = hline.split("`")
                if len(parts) >= 2:
                    prefix = "| `" + parts[1] + "`"
            for iline in inc.splitlines():
                if prefix and iline.startswith(prefix):
                    pl = patch_row(hline, iline)
                    if pl != hline:
                        out_lines.append(pl)
                        replaced = True
                        break
                if hline.startswith(("eligibility", "ABI")) and iline.startswith(hline[:12]):
                    pl = patch_row(hline, iline)
                    if pl != hline:
                        out_lines.append(pl)
                        replaced = True
                        break
            if not replaced:
                out_lines.append(hline)
        Path(path).write_text("\n".join(out_lines) + "\n")


def strip_conflict_markers(text: str) -> str:
    text = re.sub(r"<<<<<<<[^\n]*", "", text)
    text = re.sub(r"=======[^\n]*\n?", "", text)
    text = re.sub(r">>>>>>>[^\n]*\n?", "", text)
    return "".join(
        line
        for line in text.splitlines(True)
        if not line.startswith(("<<<<<<<", "=======", ">>>>>>>"))
    )


def added_comment_hunks(inc_rev: str, path: str) -> list[tuple[list[str], list[str]]]:
    """Return (context_before, added_lines) for each diff hunk."""
    diff = run("git", "show", inc_rev, "--", path).stdout
    hunks: list[tuple[list[str], list[str]]] = []
    ctx: list[str] = []
    added: list[str] = []
    in_hunk = False
    for line in diff.splitlines():
        if line.startswith("@@"):
            if added:
                hunks.append((ctx, added))
            ctx = []
            added = []
            in_hunk = True
            continue
        if not in_hunk:
            continue
        if line.startswith(" ") and not line.startswith("+++") and not line.startswith("---"):
            ctx.append(line[1:])
        elif line.startswith("+") and not line.startswith("+++"):
            line = line[1:]
            if line.startswith(("<<<<<<<", "=======", ">>>>>>>")):
                continue
            added.append(line)
        elif line.startswith("-") and not line.startswith("---"):
            continue
    if added:
        hunks.append((ctx, added))
    return hunks


def stay_host_tag(inc_rev: str) -> str | None:
    msg = run("git", "log", "-1", "--format=%B", inc_rev).stdout
    m = re.search(r"Recorded\s+([a-z0-9-]+)\s+stay-host", msg, flags=re.DOTALL)
    return m.group(1) if m else None


def filter_added_for_tag(added: list[str], tag: str | None) -> list[str]:
    if not tag:
        return added
    return [line for line in added if tag in line]


def apply_added_comment_hunks(head_rev: str, inc_rev: str, path: str) -> None:
    tag = stay_host_tag(inc_rev)
    out = strip_conflict_markers(show(head_rev, path))
    for ctx, added in added_comment_hunks(inc_rev, path):
        added = filter_added_for_tag(added, tag)
        if not added:
            continue
        block = "".join(f"{line}\n" for line in added)
        if tag and tag in out:
            continue
        if ctx:
            needle = ctx[-1]
            if needle in out and block.strip() not in out:
                out = out.replace(needle, needle + block, 1)
                continue
        anchor = "      view: { ranges"
        if anchor in out and block.strip() not in out:
            out = out.replace(anchor, block + anchor, 1)
    Path(path).write_text(out)


def merge_figure_js(head_rev: str, inc_rev: str) -> None:
    path = "packages/xy-node/src/figure.js"
    tag = stay_host_tag(inc_rev)
    out = strip_conflict_markers(show(head_rev, path))
    for ctx, added in added_comment_hunks(inc_rev, path):
        added = filter_added_for_tag(added, tag)
        if not added:
            continue
        block = "".join(f"{line}\n" for line in added)
        if tag and tag in out:
            continue
        if all(line.lstrip().startswith("//") for line in added):
            spec_hunk = (
                any('backend: "native"' in c or "view: { ranges" in c for c in ctx) or not ctx
            )
            if spec_hunk:
                anchor = "      view: { ranges"
                if anchor in out and block.strip() not in out:
                    out = out.replace(anchor, block + anchor, 1)
                continue
            if ctx:
                needle = ctx[-1]
                if needle in out and block.strip() not in out:
                    out = out.replace(needle, needle + block, 1)
                continue
        if ctx:
            needle = ctx[-1]
            if needle in out and block.strip() not in out:
                out = out.replace(needle, needle + block, 1)
    Path(path).write_text(out)


def extract_test_blocks(text: str) -> dict[str, str]:
    blocks: dict[str, str] = {}
    for m in re.finditer(r'test\("([^"]+)"', text):
        name = m.group(1)
        start = m.start()
        i = start
        depth = 0
        started = False
        while i < len(text):
            ch = text[i]
            if ch == "{":
                depth += 1
                started = True
            elif ch == "}":
                depth -= 1
                if started and depth == 0:
                    end = text.index("});", i) + 3
                    blocks[name] = text[start:end] + "\n"
                    break
            i += 1
    return blocks


def merge_coverage(head_rev: str, inc_rev: str) -> None:
    head = strip_conflict_markers(show(head_rev, COVERAGE))
    inc = strip_conflict_markers(show(inc_rev, COVERAGE))
    head_blocks = extract_test_blocks(head)
    cov = head.rstrip()
    for name, block in extract_test_blocks(inc).items():
        if name not in head_blocks:
            cov = cov + "\n\n" + block
    Path(COVERAGE).write_text(cov + "\n")


def pick(sha: str) -> None:
    head = run("git", "rev-parse", "HEAD").stdout.strip()
    msg = run("git", "log", "-1", "--format=%B", sha).stdout.strip()
    cp = run("git", "cherry-pick", "-n", sha, check=False)
    if cp.returncode != 0:
        merge_spec(head, sha)
    merge_coverage(head, sha)
    for path in HOST_FILES:
        if run("git", "cat-file", "-e", f"{sha}:{path}", check=False).returncode != 0:
            continue
        if path.endswith("figure.js"):
            merge_figure_js(head, sha)
        else:
            apply_added_comment_hunks(head, sha, path)
    to_add = [p for p in (*HOST_FILES, COVERAGE, *SPEC) if Path(p).exists()]
    run("git", "add", *to_add)
    status = run("git", "diff", "--cached", "--stat", check=False).stdout.strip()
    if not status:
        run("git", "reset", "--hard", head, check=False)
        return
    run("git", "commit", "-m", msg)


def main() -> int:
    for sha in sys.argv[1:]:
        print(
            "pick",
            sha[:8],
            run("git", "log", "-1", "--format=%s", sha).stdout.strip()[:50],
        )
        pick(sha)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
