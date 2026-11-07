# Reentrant Python controller close and terminal delivery

Independent review of `8ad02db8e0e775178dadbcf3dae53ae06769b4a0` found one remaining lifecycle defect: a Python observer could close its controller during an active notification, queue a terminal snapshot, then clear the subscriptions before that snapshot drained. The geographic binding retained its private frame and source registration.

Closure now clears the public handle before publishing its captured terminal state, making nested close idempotent. The publisher preserves subscriptions until terminal delivery completes and lets a queued terminal snapshot supersede the remaining nonterminal callbacks. No Rust policy or wire change is involved. Real-controller regressions cover ordinary and nested-terminal closure, automatic private-owner and registration cleanup, retained caller lease survival, and source rebinding with an explicitly newer query sequence. Both variants failed before the repair and pass afterward.

The previous complete final review independently passed 157 Python and 39 Node tests and verified all historical/current source and artifact bindings. This successor changes only the Python controller, regressions, normative text, successor binding pointer and append-only receipts. Fresh focused Python lifecycle/Core/checkout/inventory checks, types, and mandatory hooks/Ruff are recorded. Native, WASM and browser artifacts remain identical by digest. Node and browser behavior are inherited after source equality; no new browser capture or rebuild is claimed.

Independent re-review, PR/CI and queue delivery remain pending. Mounted native replacement, mixed tiles, broader exports/accessibility, scale/five-view/competitor acceptance, and #50/#39/M6 completion remain open.
