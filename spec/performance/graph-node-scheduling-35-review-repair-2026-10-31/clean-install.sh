#!/usr/bin/env bash
# Local Linux x64 exact-platform package check; offline, no publication.
set -euo pipefail
cd "$(dirname "$0")/../../.."
mkdir -p target/task-tmp
task_dir=$(mktemp -d "$PWD/target/task-tmp/node35-clean-install.XXXXXX")
uv build --wheel --out-dir "$task_dir/wheels"
uv run python scripts/stage_node_packages.py --version 0.0.0 --facade \
  --client packages/xy-client/dist/standalone.js --output "$task_dir/staged"
wheels=("$task_dir"/wheels/*.whl)
uv run python scripts/stage_node_packages.py --version 0.0.0 --platform linux-x64 \
  --wheel "${wheels[0]}" --output "$task_dir/staged"
mkdir -p "$task_dir/consumer/graphforge" "$task_dir/packs"
for package in "$task_dir/staged/xyg-node" "$task_dir/staged/xyg-node-linux-x64" \
  "$PWD/packages/xy-node/node_modules/koffi" "$PWD/packages/xy-node/node_modules/@koromix/koffi-linux-x64"; do
  npm pack "$package" --pack-destination "$task_dir/packs"
done
cp scripts/node_release_smoke.mjs "$task_dir/consumer/release-smoke.mjs"
cp tests/fixtures/graphforge/results/{manifest.json,base-cyclic-nodes.arrow,base-cyclic-edges.arrow,pagerank.arrow,node_similarity.arrow} "$task_dir/consumer/graphforge/"
cd "$task_dir/consumer"
npm init --yes
npm install --offline --no-audit --no-fund --ignore-scripts --omit=optional "$task_dir"/packs/*.tgz
env -u XYG_NATIVE_LIB XYG_EXPECTED_NODE_PLATFORM=linux-x64 XYG_EXPECTED_ABI=397 node release-smoke.mjs
