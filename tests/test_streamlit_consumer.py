"""Public-package consumption through stock Streamlit; no XYG runtime adapter."""

from __future__ import annotations

import runpy
from pathlib import Path

import pytest

# The Python-floor lane deliberately installs only XYG + pytest. The required
# application gate installs the locked dev group and starts real Streamlit apps.
AppTest = pytest.importorskip("streamlit.testing.v1").AppTest

APP = Path(__file__).resolve().parents[1] / "examples" / "streamlit" / "app.py"


@pytest.mark.parametrize("kind", ("scatter", "line", "bar", "graph"))
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
