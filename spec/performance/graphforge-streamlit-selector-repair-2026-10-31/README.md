# Streamlit selector qualification repair (#1081)

This follow-up preserves the original [#1016 receipt](../graphforge-streamlit-1016/README.md)
unchanged. It repairs repository browser automation only; the example,
package implementation, dependencies, exports and lifecycle contract do not
change. #1016, #36 and milestone 4 remain open for broader acceptance.

## Observed failure and repair

CI run [41225069267](https://github.com/CurateLabs/xyg/actions/runs/41225069267),
test job 124607772828, failed while waiting for `line · 8 rows` during the
first property-graph switch-away. Its 13 installed AppTests passed. The
Release surfaces aggregate failed because this test failed and wheels were
consequently skipped; it exposed no separate product failure.

The original [failure screenshot](ci-failure.png) and [body/stack](ci-failure.txt)
show `line` typed into the selector while the committed caption and iframe
still show `graphforge-property`. There is no Rows control. This establishes
a failure to commit selection, not a row-count mismatch or failed iframe
retirement. The source artifact ID and downloaded ZIP digest are retained in
[results.json](results.json); only the relevant original members are copied.

An initial filtered-click candidate retained `fill(kind)` and clicked the
exact option. It still failed on locked Streamlit 1.66.1 with CI's cached
Chromium 149.0.7827.55: the exact `line` option appeared, then detached before
the click committed. It passed on Streamlit 1.56.0. Its raw failed full-gate
log, failure screenshot/text and passing floor report remain here as a
negative control. These observations do not establish the precise scheduling
of the frontend's filtering/focus effects.

The final repair uses the same ordinary interaction as the established
baseline consumer journey: scroll the selector into view before opening its
portal, click it, then click the exact visible option. It removes filtering
and keyboard-highlight dependence. There is no forced click, scripted
selection, added retry, timeout increase or relaxed assertion. Caption,
settled-script/iframe, paint, exports, remount and retirement checks remain.

## Executed proof

- The full existing installed-consumer gate passed on Streamlit **1.66.1**,
  actual Node **22.23.4**, and cached Chromium **149.0.7827.55** (the same
  browser build as CI). Its 13 AppTest/package-boundary tests passed.
- The separate **1.56.0** installed-wheel floor passed all 13 tests and the
  complete GraphForge browser journey on the same Chromium build.
- Each of the two graph fixtures exercised previews, byte-exact direct-host
  HTML/PNG/SVG comparisons, trusted brush/zoom and two line/graph switch
  cycles. Every outgoing iframe context retired, every remount painted, and
  each remounted document was identical. No page errors, CSP violations or
  external requests were observed.
- Normal JavaScript syntax checking passed. Required worktree hooks and Ruff
  run before commit and again before push; final review/CI are separate gates.

The exact previously verified local wheel was reused because the change
touches only the repository harness and specification. Its digest, installed
paths, floor provenance and commands are recorded in `results.json` and the
complete `installed-consumers.json`. The report's commit field identifies the
baseline `2fc467a8`; the 14 working-tree hashes in `source.json` identify the
repaired harness/spec inputs. It is not a final release cohort.

Raw command logs are lossless `*.txt.gz`. The locked/floor browser reports,
AppTest JUnit results and independent direct-host oracle are retained here.
Reproduce the full gate with `results.json`'s command and an actual Node 22
PATH; the original receipt documents the separate floor setup/journey.

Selection remains browser-local. This proves snapshot execution-context
retirement, not application-driven live-view/Worker/GPU destruction, UUID
callbacks, graph accessibility, scale or complete milestone acceptance.
