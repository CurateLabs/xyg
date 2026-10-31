"""Public-package consumption through stock Streamlit; no XYG runtime adapter."""

from __future__ import annotations

import importlib.util
import json
import runpy
from pathlib import Path

import pytest

import xyg

# The Python-floor lane deliberately installs only XYG + pytest. The required
# application gate installs the locked consumer group and runs these AppTests
# against the installed wheel before starting real Streamlit apps.
if importlib.util.find_spec("streamlit") is None:
    pytest.skip("optional Streamlit framework is not installed", allow_module_level=True)

from streamlit.testing.v1 import AppTest  # noqa: E402

APP = Path(__file__).resolve().parents[1] / "examples" / "streamlit" / "app.py"


@pytest.mark.parametrize(
    "kind", ("scatter", "line", "bar", "graph", "graphforge-property", "graphforge-pagerank")
)
def test_streamlit_public_charts_export_deterministically(kind: str) -> None:
    build = runpy.run_path(str(APP))["build_chart"]
    first = build(kind, 8)
    second = build(kind, 8)
    assert first.to_svg() == second.to_svg()
    assert first.to_png().startswith(b"\x89PNG\r\n\x1a\n")
    spec, blob = first.figure().build_payload()
    other_spec, other_blob = second.figure().build_payload()
    assert spec == other_spec
    assert bytes(blob) == bytes(other_blob)
    assert "connect-src 'none'" in first.to_html()


@pytest.mark.parametrize("kind", ("graphforge-property", "graphforge-pagerank"))
def test_graphforge_streamlit_matches_direct_public_host(kind: str) -> None:
    example = runpy.run_path(str(APP))
    results = example["RESULTS"]
    bases = json.loads((results / "manifest.json").read_text())["bases"]
    base = bases["property" if kind == "graphforge-property" else "cyclic"]
    kwargs = {
        "base": {
            "tables": [(results / f"{base[key]}.arrow").read_bytes() for key in ("nodes", "edges")],
            "generation": base["generation"],
        }
    }
    if kind == "graphforge-pagerank":
        kwargs["layers"] = [
            {
                "result": (results / "pagerank.arrow").read_bytes(),
                "intent": "graph",
                "result_id": "pagerank",
                "generation": base["generation"],
            }
        ]
    direct = xyg.compose_graphforge(**kwargs)
    actual = example["build_graphforge_composition"](kind)
    assert actual.nodes.uuid == direct.nodes.uuid
    assert actual.edges.uuid == direct.edges.uuid
    if kind == "graphforge-property":
        assert actual.layers == []
        assert list(actual.nodes.label) == ["ada", "Prof", "Acme", "00000004", "00000005"]
        assert [row["text"] for row in actual.legend["rows"]] == [
            "no label",
            "Company",
            "Person",
            "directed relationship",
        ]
        assert list(actual.edges.label) == list(actual.edges.type)
    else:
        assert len(actual.layers) == 1
        assert actual.identify("node", 0)["uuid"] == direct.nodes.uuid[0]
    expected = xyg.graphforge_chart(direct, title=kind, width=720, height=360)
    chart = example["build_chart"](kind)
    assert chart.to_svg() == expected.to_svg()
    assert chart.to_png() == expected.to_png()
    assert chart.to_html() == expected.to_html()


def test_graphforge_script_reruns_restore_identical_documents() -> None:
    app = AppTest.from_file(str(APP), default_timeout=30).run()
    for kind in ("graphforge-property", "graphforge-pagerank"):
        app.selectbox[0].select(kind).run()
        assert not app.exception
        assert app.caption[1].value == kind
        assert "Selection stays in the browser" in app.caption[0].value
        assert not app.select_slider
        first = app.get("iframe")[0].proto.srcdoc
        # 1.56 exposes image protos as "imgs"; newer AppTest names them "image".
        images = app.get("image") or app.get("imgs")
        assert [image.proto.imgs[0].caption for image in images] == [
            "Native PNG export",
            "Native SVG export",
        ]
        assert len(app.get("download_button")) == 2
        app.run()
        assert not app.exception
        assert len(app.get("iframe")) == 1
        assert app.get("iframe")[0].proto.srcdoc == first
        app.selectbox[0].select("line").run()
        app.selectbox[0].select(kind).run()
        assert not app.exception
        assert app.get("iframe")[0].proto.srcdoc == first


def test_streamlit_rerun_changes_chart_without_adapter() -> None:
    app = AppTest.from_file(str(APP), default_timeout=30).run()
    assert not app.exception
    assert app.caption[1].value == "scatter · 8 rows"
    assert len(app.get("iframe")) == 1
    app.selectbox[0].select("line").run()
    app.select_slider[0].set_value(16).run()
    assert not app.exception
    assert app.caption[1].value == "line · 16 rows"
    assert len(app.get("iframe")) == 1
    assert len(app.get("download_button")) == 2
    app.selectbox[0].select("graph").run()
    assert not app.exception
    assert app.caption[1].value == "graph · 16 rows"


def test_streamlit_example_bounds_fixture_inputs() -> None:
    build = runpy.run_path(str(APP))["build_chart"]
    for kind, count in (("unknown", 8), ("scatter", 10)):
        with pytest.raises(ValueError):
            build(kind, count)
    with pytest.raises(ValueError):
        runpy.run_path(str(APP))["build_graphforge_composition"]("unknown")
