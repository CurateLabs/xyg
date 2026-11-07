# PR1113 current-main integration

Local history-preserving integration of accepted main
`084b3c1b7c393e135476aab9610bf8334767b2ac` (including PR1109 / accepted
`33baef7134f9bd5c8f298a4a348714685e1d8e5a` proof) and reviewed resource candidate
`b1491f9848f9e6e13d63adc81435f1f9ba1da243`, using `git merge --no-ff --no-commit`.
The two design-note conflicts retain the resource candidate wording: the old
10k refusal describes its historical receipt, while the new admission receipt
has its own bounded scope. All pre-existing candidate files equal that parent
byte-for-byte except the officially regenerated release inventory. Its contract
hash is unchanged; only baseCommit and the current host-parity source hash change.
No product algorithm, ABI, cap, tolerance, compiler or package policy changes.

The candidate was independently approved for its full 60-path implementation
against `581f4682c4079d1604eb3186df7d5ac92c125e66`, canonical binary/full-index diff
SHA256 `aa1de0a0672fc8c901467d4b0448b5b717d29bd425d5bbfae5733752e8154486`,
and full 180-path union against `80e841542462eaf5509ac90e1f17a80cae974164`,
SHA256 `b01bb2b6a545a7292f630197269a217b588ca191a43cd96fdaae3720f5cef8d3`.
The independent review is retained at
`/home/ubuntu/.t3/worktrees/xyg/t3-9f0f81b3/target/review-public10k/review.md`.
Root still requires independent review of this final integration diff and fresh
CI / merge queue before delivery. This local merge neither opens nor merges a PR.

Fresh checks all exit zero: eight native/WASM wire/resource cases; sixteen
camera controls; 38 Python transport/ABI cases; 33 Core/inventory cases including
real Git autocrlf checkout with a converting unpinned control; asset verification;
official inventory regeneration/check; full source-dist foundation including
ESM/IIFE density cases, strict CSP/Worker lifecycle, and the accepted two-view 1k
unheld unfinished selection, camera continuity, isolation and cleanup journey.
The foundation observation records default-16MiB 1k refusal and explicit-384MiB
10k opening. It asserts the former and observes the latter; its historical
"refusals" case name is not a requirement that current 10k admission fail.
All functional controls and wall limits remain unchanged.

Full-worktree hooks, Ruff check and Ruff format check passed before committing.
The receipt archives their first successful run; the same mandatory commands
are repeated after staging the final evidence. Commands, environment, logs,
source and artifact hashes are in `bindings.json`. Reports identify the
pre-merge HEAD because checks execute before the integration commit; the exact
input hashes and final handoff diff bind this tested tree. Compressed files are
lossless deterministic gzip; PNGs retain original bytes.

Exact producer inputs were verified before copying generated artifacts from
`/home/ubuntu/.t3/worktrees/xyg/t3-3c28a8ac`; that checkout was read only.
All 15 source, nine artifact, 52 receipt and decompressed receipt bindings match.
Entire Rust/client/host input trees equal the reviewed resource parent. Native
SHA256 is `40a94cd7c043b675b8ccbaa622937e952d76f67625cf0adf52fa3e2111cc73e7`
from the committed producer binding; shipping WASM SHA256 is
`06938b014a74528eb95a279971cb884b41a9dbcb094d3530a49a633ffd1e9792`.
Node 22.23.4 raw/gzip6 remains 1,927,066 / 786,154 bytes under unchanged
1,927,168 / 786,432 caps. Native/WASM/client builds and prior actual 10k+1k
cold/warm/full-reply replays are inherited after exact verification, not rerun.
Dependency symlinks are used read only with `UV_NO_SYNC=1`; generated assets are
local copies. A short disk-backed task TMPDIR avoids exhausted `/tmp` and long
Chrome socket paths.

`parent-protection.json.gz` records blob IDs and SHA256 for all 12,041 accepted
main and 12,094 resource-parent performance/release evidence paths (inventory
excluded), with exact equality verified against both parent trees. It also
records the integrated changed paths before this additive receipt. No historical
receipt was rewritten, and recorded refusals, package failures, quota failures
and two-10k timeout attempts retain their bytes and failed status. Existing
current Core binding and its LF pins still match all current sources, so no
replacement binding or additional Core pin is needed. This receipt is additive.

This establishes current-main integration and bounded functional gates. It does
not establish default 1k admission, reliable two-10k completion, a latency win,
100k/1M coverage, notebook/export/accessibility acceptance, closure of #35/#36/
#1015, or M4 completion. Parent owns delivery; no push or GitHub mutation occurred.
