# Honor the declared Python annotation floor

Hosted run42348870857 failed before tests because the annotated _geo_temporal module lacked the repository-required future annotations import. The existing whole-repository Python-floor checker reproduces the exact failure. Adding the standard future import makes that unchanged checker pass; no gate, signature, lifecycle body, Rust/ABI, or artifact changes occur.

Fresh affected lifecycle/retained-source/controller batch passes112 tests on actual Python3.11.17 with the candidate source path and explicitly verified native library. The interpreter/dependencies come from the existing read-only311 environment; PYTHONPATH selects this worktree and the printed xyg.__file__ confirms it. Root uv remains the tool launcher. Current Core/inventory/realGitCRLF and floor-module tests are rerun with successor bindings. Native and all11 artifacts remain unchanged; prior independent finalR11 production approval at4b026baa is inherited only for unchanged code.

Before/after floor logs, actual311 run and source/artifact bindings are retained. Reproduction: uv run python scripts/check_python_floor.py; the311 command and exact environment are in checks.json. Independent correction review and new-head hosted CI/queue remain required. All broader #50/#39/M6 acceptance gaps remain open.
