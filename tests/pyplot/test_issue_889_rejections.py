"""Active exact diagnostics for deferred #889 native-export journeys.

The original future-rendering tests remain xfailed. Invoking their bodies here
retains their pre-export authoring assertions and proves the actual rejection;
a changed diagnostic or unexpected successful export fails this active test.
"""

from __future__ import annotations

import importlib.util
import json
from functools import cache
from pathlib import Path

import pytest

from xyg._static_document import UnsupportedStaticExport

ROOT = Path(__file__).resolve().parents[2]
CASES = json.loads(Path(__file__).with_name("issue_889_rejections.json").read_text())


@cache
def _module(path: str):
    spec = importlib.util.spec_from_file_location(Path(path).stem, ROOT / path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("case", CASES, ids=lambda case: case["test"])
def test_deferred_journey_has_exact_native_rejection(case):
    with pytest.raises(UnsupportedStaticExport) as error:
        getattr(_module(case["path"]), case["test"])()
    assert str(error.value) == case["reason"]


@pytest.mark.parametrize(
    "kind,key",
    [
        ("callout", key)
        for key in (
            "gap_start",
            "gap_end",
            "head_size",
            "head_style",
            "label_clear",
            "label_color",
            "start_offset",
        )
    ]
    + [("arrow", "head_size"), ("rule", "span_start"), ("rule", "span_end")],
)
def test_each_deferred_annotation_style_key_has_exact_reason(kind, key):
    from xyg._scene_annotations import pack_xyaf_bulk
    from xyg._scene_observations import UnsupportedSceneV3

    annotation = {"kind": kind, "style": {key: 8}}
    with pytest.raises(UnsupportedSceneV3) as error:
        pack_xyaf_bulk([annotation])
    assert str(error.value) == (
        f"XYG_SCENE_UNSUPPORTED_ANNOTATION_STYLE: {kind} unsupported keys {key}"
    )


def test_arrow_head_style_outside_the_native_vocabulary_has_stable_reason():
    from xyg._scene_annotations import ARROW_STYLE_UNSUPPORTED, pack_xyaf_bulk
    from xyg._scene_observations import UnsupportedSceneV3

    with pytest.raises(UnsupportedSceneV3) as error:
        pack_xyaf_bulk(
            [
                {
                    "kind": "arrow",
                    "x0": 0,
                    "y0": 0,
                    "x1": 1,
                    "y1": 1,
                    "style": {"head_style": "fancy"},
                }
            ]
        )
    assert str(error.value) == ARROW_STYLE_UNSUPPORTED
