# Late Python CI assertions and polar PNG snapshots

CI on prior immutable head 8d59d227 failed eleven tests that matched the old
Scene v12 annotation diagnostic and one historic polar PNG golden. The two
Node failures from the same CI cohort were already fixed in reviewed13c4cc16.
The Release surfaces failure aggregates those jobs; it is not another defect.
The eleven Python failures were reproduced locally before editing tests.

No product source changes are made here. Python annotations now assert complete
expected messages for all seven invalid-style and seven invalid-geometry cases,
matching the stable rejection contract already independently verified in R4.

The public rose/bar PNG snapshots were taken before the separately reviewed
#889 raster polar clipping/chrome changes. Old snapshots were rose
eaef5b30e2fa07399e0b837376fd57a3c3b91ee180b860e4a13c56d8934a8dbd
and bar c87d79ebb18af53d0a32402dd8ff27ec1cbcab39f2c25375b6e115000775212a.
New digests and an independent direct native probe are in arc-sidecar-probe.json.
They bind the same native artifact reviewed at13c4cc16; no renderer or artifact
was regenerated to satisfy this snapshot update.

The original test intended to prove exact vector arcs do not affect flattened
raster output. Four new controls now test that directly at scales1 and2 for
both rose and bar. Each removes exactly the bounded XYWA v1 sidecar before
XYPL from an otherwise byte-identical compiled Scene. Both forms must decode;
SVG output must differ while native raster command and PNG bytes must be
exactly equal. Existing vector arc geometry tests remain unchanged. Public
PNG digests separately pin the corrected polar chrome, rather than claiming
all historical renderer changes are forbidden by the XYWA contract. No masks,
resource-limit changes, pixel tolerance relaxation or host renderer is used.

Reproduce: uv run pytest -q tests/test_scene_ir.py tests/test_polar_wedge_svg_arcs.py
Result:99 passed,1 qualified xfailed. The required pyplot1196/163skip/26xfail,
host-parity1097 and Node131/1skip results from R4 remain applicable to unchanged
product source. This test/spec-only follow-up requires independent review and
current-head CI before merge. Complete hooks/Ruff results and source/artifact
hash bindings accompany the log receipts.
