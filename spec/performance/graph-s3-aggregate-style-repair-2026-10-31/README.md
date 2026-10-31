# S3 tier-wide aggregate style repair

Greptile review on #1082 identified singleton Aggregate nodes and edges that
retained source semantics. The prior implementation chose styles using the
aggregate state flag or edge member count. Those describe state and membership,
not the tier-wide omission contract in graph-interaction §2.3 and graph-mark
§7.1.3. The new regression fails against the previous production code: a graph
at x = [0, 10, 100] with node budget two contains both singleton and multi-member
render nodes and edges, whose paint differs from neutral-source input.

The repair uses the published Aggregate tier for both style and semantic-layer
selection. It retains projected interaction flags and emphasis, and preserves
the global directed fallback for arrowheads when edge status is absent.
Direct and EdgeSample still retain source semantics, including a collapsed
representative and an explicitly authored aggregate state flag. Tests compare
whole published paint and picks, then prove selection/focus republish at the
same revision. They also cover default directed heads in the exact tiers.

This directory records the focused before/after proof, nearest interaction and
workspace gates, fresh native/WASM builds and real package verification. Exact
commands, exits, timings and raw/compressed log hashes are in the command JSON
files. Reproduce each recorded argv from the checkout root with the environment
in `environment.json`; logs are deterministic gzip (`mtime=0`). The failed
before run is expected and is not a passing gate. Source hashes bind the final
inputs. Full-worktree hooks and Ruff run before commit and again before push.

The earlier [package/foundation receipt](../graph-s3-package-budget-2026-10-31/README.md)
remains immutable. Matching packaged bytes reuse that full strict-CSP foundation
proof; this typed session geometry still has no exported native/WASM session
boundary. There is no new ABI, package-size allowance, runtime speed claim,
hardware run or host acceptance. Independent review and CI remain required.
S4–S7, #36, M4 and #108 are not completed by this repair.
