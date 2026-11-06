"""Replay captured public browser commands through the existing native transport."""

import base64
import json
from pathlib import Path

import numpy as np

from xyg._graph_session import GraphSession
from xyg._graphforge_container import decode_container

capture = json.loads(Path(__file__).with_name("progressive.json.replay.json").read_text())
opening = base64.b64decode(capture[0]["request"])
fields = decode_container(opening, "XYGI")
instance_id, group_id, _ = fields["header.u64", 0]
reports = []
with GraphSession(
    fields["document.bytes", 0], opening, instance_id=int(instance_id), group_id=int(group_id)
) as session:
    for command in capture[1:]:
        request = base64.b64decode(command["request"])
        expected = decode_container(base64.b64decode(command["reply"]), "XYGR")
        actual = decode_container(
            session.render(request) if command["operation"] == 21 else session.interact(request),
            "XYGR",
        )
        for name in ["relayout.steps.u64", "relayout.alpha.f64", "relayout.done.u8"]:
            np.testing.assert_array_equal(actual[name, 0], expected[name, 0])
        np.testing.assert_allclose(
            actual["paint.node.center.f64", 0],
            expected["paint.node.center.f64", 0],
            rtol=0,
            atol=1e-9,
        )
        reports.append(int(actual["relayout.steps.u64", 0][0]))
print(
    f"PASS native/WASM public checkpoint replay: {len(reports)} publications, ticks {reports[0]}..{reports[-1]}"
)
