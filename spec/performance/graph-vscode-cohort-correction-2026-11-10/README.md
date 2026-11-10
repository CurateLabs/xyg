# Complete desktop cohort admission correction

Independent review of 0ea5338e found two P2 provenance gaps: duplicate
extension IDs overwrote earlier directories, and the driver rehashed only the
Electron executable. The real frontend journey and strict report passed, but
that did not establish the claimed complete installed cohort recheck. The
original review and its private adversarial controls are retained unchanged.

The installer and driver now reject duplicate IDs before building the payload
map. Extension-directory links are also refused. Before any server or app
process starts, the driver hashes the complete installed application file and
directory map against a new pin independently derived from the unchanged
official archive. All 3,192 entries are bound by path, kind, file length, file
hash and executable status. This exact archive has no symbolic/hard links or
special entries; substitutions are refused. The installation sidecar carries
the complete canonical map, and the strict report verifier recomputes its
digest and requires the exact installed ID/version list. Download/executable
pins, stock app/extension versions and runtime product artifacts are unchanged.

New helper regressions cover duplicate-ID overwrite, changed and missing app
resources, extra files/directories, executable status and links. Adversarial
report controls reject changed application maps and installed sets. Fresh
normal and intentional-failure runs use a new installer output and preserve
the original qualification directory and all earlier reports/receipts.

Reproduce with the same commands as the preceding desktop README, selecting
a new installer/output directory and this successor fixture manifest. The
original archive may be supplied through --cache; complete bytes are rehashed
before reuse. No app, extension, kernel, renderer or production JS/Rust patch
is used. No global memory, offline, all-host, generic startup/Worker, whole
#1015 or milestone acceptance follows. Current-head hosted CI and required
merge queue remain separate delivery requirements.

The first corrected ordinary-display run failed before the notebook opened:
Xvfb could not write its fixed /tmp PID locks, and a direct write probe returned
errno122 there while /var/tmp succeeded. That run and xdpyinfo exit1 remain
unqualified. Fresh Python3.11/3.12 runs use the already documented private
TCP/-nolock display route. The hosted ordinary xvfb-run command is unchanged;
its new-head result remains required. No shared X server or quota cleanup was
performed, and this is not a product reliability repair.
