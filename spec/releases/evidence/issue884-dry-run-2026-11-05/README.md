# Manual release branch fixture repair

Greptile P1 discussion4484700049 on PR1097 correctly found that all three branch
staging callers still passed 0.0.0-dryrun.RUN_NUMBER after canonical parser
admission rejected that label. Two new controls using workflow-extracted values
and run numbers1/42 failed before repair. They now stage native, facade and
browser package manifests plus exact facade pins successfully.

All three callers use 0.0.0-rc.${GITHUB_RUN_NUMBER}, an unreserved fixture version.
Tag-derived versions and every upload gate remain unchanged. The shared parser
is not loosened. No workflow dispatch, tag, registry write or publication occurs.
The reproduction test uses minimal native/WASM fixture bytes and does not claim
to qualify actual candidate binaries. Existing real packaging evidence remains
in the preceding issue884 receipt.

Commands: uv run --with dunamai pytest -q [the same nine test modules listed in
the preceding receipt]; make check-ci; full-worktree hooks and Ruff. Results:
219 focused tests passed and make check-ci passed757 tests plus workflow gates.
This is a scoped repair on approved1ad4ac47; independent re-review and new-head
CI still gate merge. #884 and108 remain incomplete on selected-Core and broader
product/package acceptance. Logs are lossless archives with raw/archive hashes.
