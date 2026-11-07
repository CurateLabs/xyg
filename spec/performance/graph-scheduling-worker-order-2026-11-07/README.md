# Stable attachment identity under reverse Worker arrival

PR #1109 review identified an ordering assumption in the two-view scheduling proof: fixture entries arrive when Workers become ready, but picking, pan polling and final assertions used positional indexes. A valid reversed Worker completion order could fail the required gate.

All setup, pick coordinates, progress polling, cleanup and assertions now find views by explicit IDs 7101 and 7102. The fixture deterministically places 7102 before 7101 after both real Workers initialize, making every normal 1k probe exercise the adverse storage order. The report records this as fixtureStorageOrder, not actual startup completion order. With the new permutation but the original positional assertions the actual browser run fails; with ID lookup the same live case passes. It still requires exact trusted unfinished pick, host-button +12 camera retention, untouched second-view state, advancing paints and cleanup. No shipping code or artifact changes.

The current live probe, sixteen camera unit controls and full normal foundation pass. Reports, six captures and lossless logs are retained here, with source/artifact hashes. Prior independent approval of the exact camera oracle is inherited only for unchanged helper bytes; this ordering correction requires its own final review. Old receipts remain immutable.

Both Workers explicitly use 384 MiB. Default-arena 1k and ceiling-arena 10k remain recorded refusals. The proof covers trusted host-button camera input, not canvas dragging, and cleanup follows completion. Cold startup, 1k keyboard, larger scale ladder, notebook/frontends/exports/accessibility and full #35/#36/#1015/M4 acceptance remain open. No latency or competitor win is claimed; page heap excludes Worker/WASM/GPU memory.
