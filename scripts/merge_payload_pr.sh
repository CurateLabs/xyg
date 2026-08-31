#!/usr/bin/env bash
# Merge one payload-stack PR: cherry-pick tip, resolve ABI conflicts, test, push, gh merge.
set -euo pipefail
cd /workspace

COMMIT=$1
ABI=$2
BRANCH=$3
PR=$4
FEATURE_NOTE=${5:-}

resolve_standard() {
  # lib.rs ABI — replace conflict block, never delete the const
  python3 - <<PY
import re, pathlib
p = pathlib.Path("crates/xyg-core/src/lib.rs")
t = p.read_text()
t = re.sub(r"<<<<<<<[^\n]*\n.*?>>>>>>>[^\n]*\n?", "", t, flags=re.S)
t = re.sub(r"pub const ABI_VERSION: u32 = \d+;", f"pub const ABI_VERSION: u32 = ${ABI};", t)
if "pub const ABI_VERSION" not in t:
    t = t.replace(
        "rule, applied to the in-process boundary).\n",
        f"rule, applied to the in-process boundary).\npub const ABI_VERSION: u32 = ${ABI};\n",
        1,
    )
p.write_text(t)
PY

  # test_abi_parity.py
  python3 - <<PY
import re, pathlib
p = pathlib.Path("tests/test_abi_parity.py")
t = p.read_text()
t = re.sub(r"<<<<<<<.*?>>>>>>>\n", "", t, flags=re.S)
t = re.sub(r"def test_abi_version_is_\d+\(\)", f"def test_abi_version_is_${ABI}()", t)
t = re.sub(r'assert manifest\["abi_version"\] == \d+', f'assert manifest["abi_version"] == ${ABI}', t)
p.write_text(t)
PY

  # native-path.test.mjs
  python3 - <<PY
import re, pathlib
p = pathlib.Path("packages/xy-node/test/native-path.test.mjs")
t = p.read_text()
t = re.sub(r"<<<<<<<.*?>>>>>>>\n?", "", t, flags=re.S)
lines = []
seen = False
for line in t.splitlines(True):
    if re.search(r"assert\.equal\(ABI_VERSION,\s*\d+\)", line):
        if seen:
            continue
        lines.append(f"  assert.equal(ABI_VERSION, ${ABI});\n")
        seen = True
    else:
        lines.append(line)
p.write_text("".join(lines))
PY

  # encode.js import: keep HEAD side, union in new xy* symbols from incoming side
  if grep -q '<<<<<<<' packages/xy-node/src/encode.js; then
    python3 - <<'PY'
import re, pathlib
p = pathlib.Path("packages/xy-node/src/encode.js")
t = p.read_text()
m = re.search(r"<<<<<<<[^\n]*\n(.*?)=======\n(.*?)>>>>>>>[^\n]*", t, re.S)
if m:
    head, inc = m.group(1), m.group(2)
    hm = re.search(r"import \{([^}]+)\}", head)
    im = re.search(r"import \{([^}]+)\}", inc)
    symbols = []
    seen = set()
    for part in (hm.group(1) if hm else "", im.group(1) if im else ""):
        for sym in part.split(","):
            sym = sym.strip()
            if sym and sym not in seen:
                seen.add(sym)
                symbols.append(sym)
    merged = "import { " + ", ".join(symbols) + ' } from "./native.js";'
    t = t[:m.start()] + merged + "\n" + t[m.end():]
    p.write_text(t)
PY
  fi

  # ownership-audit: take HEAD block, append feature note if provided
  if grep -q '<<<<<<<' spec/design/ownership-audit.md; then
    python3 - <<PY
import re, pathlib
p = pathlib.Path("spec/design/ownership-audit.md")
t = p.read_text()
note = "${FEATURE_NOTE}"
while "<<<<<<<" in t:
    m = re.search(r"<<<<<<<[^\n]*\n(.*?)=======\n(.*?)>>>>>>>[^\n]*\n?", t, re.S)
    if not m:
        break
    head, inc = m.group(1).strip(), m.group(2).strip()
    chosen = head
    if note and note not in chosen:
        if chosen.endswith("."):
            chosen = chosen[:-1]
        if "; density " in inc and "ABI" in inc:
            chosen = chosen + "; " + note
    t = t[:m.start()] + chosen + "\n" + t[m.end():]
p.write_text(t)
PY
  fi

  # union-merge any remaining conflict files (e.g. density_emit.rs)
  while IFS= read -r f; do
    [[ -z "$f" ]] && continue
    [[ "$f" == *"_abi_generated"* ]] && continue
    [[ "$f" == spec/abi/* ]] && continue
    python3 - <<PY
import re, pathlib
p = pathlib.Path("$f")
t = p.read_text()
while "<<<<<<<" in t:
    m = re.search(r"<<<<<<<[^\n]*\n(.*?)=======\n(.*?)>>>>>>>[^\n]*\n?", t, re.S)
    if not m:
        break
    h, i = m.group(1), m.group(2)
    merged = h if h.strip()==i.strip() else (h.rstrip("\\n")+"\\n"+i if h.strip() and i.strip() else (h or i))
    t = t[:m.start()] + merged + t[m.end():]
p.write_text(t)
PY
  done < <(git diff --name-only --diff-filter=U)

  git checkout --ours packages/xy-node/src/_abi_generated.js python/xyg/_abi_generated.py spec/abi/xyg-abi.json spec/abi/xyg.h 2>/dev/null || true
}

echo "=== PR #${PR} ABI ${ABI} ${COMMIT} ==="
git fetch origin main
git checkout main
git reset --hard origin/main

if ! git cherry-pick "$COMMIT"; then
  resolve_standard
  git add -A
fi

resolve_standard
cargo build --release
python3 scripts/gen_abi_manifest.py --write
git add -A
if git rev-parse -q --verify CHERRY_PICK_HEAD >/dev/null 2>&1; then
  git cherry-pick --continue --no-edit
else
  git commit --amend --no-edit 2>/dev/null || git commit -m "Merge payload PR #${PR} at ABI ${ABI}"
fi

python3 scripts/abi_smoke.py
git push -u origin "main:${BRANCH}" --force-with-lease
gh pr ready "$PR"
gh pr merge "$PR" --merge --admin
git fetch origin main
git reset --hard origin/main
echo "Merged PR #${PR} at ABI ${ABI}"
