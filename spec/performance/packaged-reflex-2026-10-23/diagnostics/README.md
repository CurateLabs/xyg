# Diagnostic history

The first frozen-wheel public HTML invocation stopped with the observed tool
error `export never completed a live presentation`. That harness version did
not yet persist failure-state JSON/PNG, so no GL-state cause can be established
from the original error. Enhanced failure diagnostics were then added; the
same generated export bytes passed both cases with unchanged pixel assertions
and presentation bound. `diagnostic.export.json` and its two screenshots retain
that diagnostic replay, not the original failure.

`strict-null-oracle/` retains a later combined red run against the same frozen
wheel. Four real Reflex journeys and both HTML cases passed before the new
tick-failure assertion rejected an unset handle slot. Initial attachment only
installs `_wasmTicks` after Rust admission, so initialization failure leaves it
undefined. The final green report explicitly records that absent/unowned state
and preserves exact error, empty positions, Worker termination, and strict-null
post-destruction checks. No production change resulted from this oracle fix.

The separate `baseline/` directory retains the actual original-wheel product
regression: a supplied DOM id remained in the live view map after unmount. The
stable-key production fix addresses that independently of these test
diagnostics. All raw reports retain their original statuses and hashes.
