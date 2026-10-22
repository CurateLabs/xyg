"""Static triangle-mesh tiers (#1006, dossier §28).

The Scene keeps every face. Raster formats (PNG/JPEG/WebP) paint them
directly at the requested scale. SVG/PDF write one vector path per face up to
``MAX_PUBLIC_TRIANGLE_MESH_FACES`` (50,000) faces aggregate; above that each
mesh trace is one embedded raster image of its own faces at the default PNG
scale (2) — the dense-fill tier. Above 1,024 faces, raster-work admission
bounds the faces' overdraw; pure vector SVG/PDF bypass that raster cost bound. Meshes at or
below 1,024 faces are byte-identical to before. Hexbin keeps its own budget
(#1023).
"""

from __future__ import annotations

import hashlib
import re
import struct
import zlib

import numpy as np
import pytest

import xyg
from xyg._scene_v3 import figure_scene, scene_export_support_reason
from xyg._static_document import UnsupportedStaticExport

WIDTH = 640
HEIGHT = 420
_IMAGE = re.compile(r"<image [^>]*>")


def _quad_mesh(cols: int, rows: int) -> tuple[np.ndarray, ...]:
    """`cols x rows` unit-square quads as 2*cols*rows triangles plus a value each."""
    index = np.arange(cols * rows, dtype=np.float64)
    gx = (index % cols) / cols
    gy = np.floor(index / cols) / rows
    sx, sy = 1.0 / cols, 1.0 / rows
    value = ((index * 7919.0) % 101.0) / 100.0
    return (
        np.concatenate([gx, gx + sx]),
        np.concatenate([gy, gy]),
        np.concatenate([gx + sx, gx + sx]),
        np.concatenate([gy, gy + sy]),
        np.concatenate([gx, gx]),
        np.concatenate([gy + sy, gy + sy]),
        np.concatenate([value, 1.0 - value]),
    )


def _mesh_chart(columns: tuple[np.ndarray, ...], *, stroke: bool = True) -> xyg.Chart:
    x0, y0, x1, y1, x2, y2, value = columns
    style = {"stroke": "#111827", "stroke_width": 0.5} if stroke else {}
    return xyg.chart(
        xyg.triangle_mesh(x0=x0, y0=y0, x1=x1, y1=y1, x2=x2, y2=y2, color=value, **style),
        xyg.x_axis(domain=(0.0, 1.0)),
        xyg.y_axis(domain=(0.0, 1.0)),
        width=WIDTH,
        height=HEIGHT,
    )


def _exports(chart: xyg.Chart) -> dict[str, bytes]:
    figure = chart.figure()
    return {
        "svg": figure.to_svg().encode(),
        "png": figure.to_png(),
        "png1": figure.to_png(scale=1.0),
        "pdf": figure.to_image("pdf"),
    }


def _decode_png(encoded: bytes) -> np.ndarray:
    """Decode the engine's 8-bit non-interlaced RGB/RGBA PNG to an HxWxC array."""
    assert encoded[:8] == b"\x89PNG\r\n\x1a\n"
    pos, width, height, channels, idat = 8, 0, 0, 0, b""
    while pos < len(encoded):
        (length,) = struct.unpack(">I", encoded[pos : pos + 4])
        kind, body = encoded[pos + 4 : pos + 8], encoded[pos + 8 : pos + 8 + length]
        pos += 12 + length
        if kind == b"IHDR":
            width, height, depth, color, _, _, interlace = struct.unpack(">IIBBBBB", body)
            assert depth == 8 and not interlace
            channels = {2: 3, 6: 4}[color]
        elif kind == b"IDAT":
            idat += body
    raw = np.frombuffer(zlib.decompress(idat), dtype=np.uint8).reshape(height, -1)
    stride = width * channels
    out = np.zeros((height, stride), dtype=np.int32)
    previous = np.zeros(stride, dtype=np.int32)
    for row in range(height):
        kind, line = raw[row, 0], raw[row, 1:].astype(np.int32)
        if kind == 1:
            for i in range(channels, stride):
                line[i] = (line[i] + line[i - channels]) & 0xFF
        elif kind == 2:
            line = (line + previous) & 0xFF
        elif kind == 3:
            for i in range(stride):
                left = line[i - channels] if i >= channels else 0
                line[i] = (line[i] + ((left + previous[i]) >> 1)) & 0xFF
        elif kind == 4:
            for i in range(stride):
                a = line[i - channels] if i >= channels else 0
                b, c = previous[i], previous[i - channels] if i >= channels else 0
                p = a + b - c
                pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
                line[i] = (line[i] + (a if pa <= pb and pa <= pc else b if pb <= pc else c)) & 0xFF
        else:
            assert kind == 0
        out[row], previous = line, line
    return out.reshape(height, width, channels)


def _plot_rect(scene: bytes) -> tuple[float, float, float, float]:
    """Plot rectangle (CSS px) from the canonical Scene header."""
    assert scene[:4] == b"XYGS"
    return struct.unpack_from("<4d", scene, 48)


# Recorded from the pre-change main (8ce49667) native core: a stroked mesh at
# the 1,024-face budget exports byte-identically on the per-polygon path.
_MAIN_AT_BUDGET = {
    "svg": "566b3427135cb39330720fee2a707ae396a8b8d6451fb5396a139763a2bb15bc",
    "png": "b3275663651b7ee9d6587c2cb7e9bc0070f125c5ce0b178f458f2235dbb74582",
    "png1": "ba0d64c05219d591e0656e98e77d8628493899292e429e14772a6c87fc6e25b0",
    "pdf": "22ea33d403827720629466d5583313752caed11e126bd77fbb40c2a12d20a750",
}
_LOD = "XYG_SCENE_UNSUPPORTED_PUBLIC_LOD"


def test_mesh_at_budget_is_byte_identical_and_keeps_per_polygon_records() -> None:
    columns = _quad_mesh(32, 16)
    assert len(columns[0]) == 1_024
    exports = _exports(_mesh_chart(columns))
    assert b"<image" not in exports["svg"]
    assert exports["svg"].count(b"<path") >= 1_024
    digests = {key: hashlib.sha256(value).hexdigest() for key, value in exports.items()}
    assert digests == _MAIN_AT_BUDGET


def test_meshes_stay_vector_up_to_the_public_face_ceiling() -> None:
    """1,250 faces (formerly over the painter's 1,024 budget) export as paths."""
    figure = _mesh_chart(_quad_mesh(25, 25)).figure()
    assert scene_export_support_reason(figure) is None
    svg = figure.to_svg()
    assert "<image" not in svg
    assert svg.count('<path d="M') >= 1_250 // 7


def test_dense_mesh_exports_one_smooth_image_in_svg_and_pdf() -> None:
    figure = _mesh_chart(_quad_mesh(160, 160)).figure()  # 51,200 faces
    assert scene_export_support_reason(figure) is None
    svg = figure.to_svg()
    (image,) = _IMAGE.findall(svg)
    assert 'data-xy-dense-fill="true"' in image
    assert "pixelated" not in image
    assert svg.count("<path") < 50  # chrome only: no per-face polygons
    pdf = figure.to_image("pdf")
    assert pdf.startswith(b"%PDF") and b"/Interpolate true" in pdf
    png = _decode_png(figure.to_png())
    assert png.shape[:2] == (HEIGHT * 2, WIDTH * 2)
    left, top, right, bottom = _plot_rect(figure_scene(figure))
    plot = png[int(top * 2) + 4 : int(bottom * 2) - 4, int(left * 2) + 4 : int(right * 2) - 4]
    # Colormapped faces paint (not the white plot background) everywhere.
    assert (plot[..., :3].sum(axis=-1) < 700).mean() > 0.9
    assert figure.to_image("jpeg")[:2] == b"\xff\xd8"
    assert figure.to_image("webp")[8:12] == b"WEBP"


@pytest.mark.parametrize("scale", [1.0, 2.0, 3.0, 4.0])
def test_dense_mesh_raster_matches_the_per_polygon_raster_at_every_scale(scale: float) -> None:
    """Raster formats paint the faces themselves at the requested scale.

    The 160x160 quad mesh (51,200 faces) is above the vector ceiling; its left
    80 columns and right 80 columns (25,600 faces each) are below it. Away from
    the seam every pixel of the dense PNG equals the half that owns it, at
    scales 1 to 4 (the dense-fill image exists only in SVG/PDF).
    """
    columns = _quad_mesh(160, 160)
    dense = _mesh_chart(columns).figure()
    left_faces = np.concatenate([np.arange(160 * 160) % 160 < 80] * 2)
    halves = [
        _mesh_chart(tuple(column[mask] for column in columns)).figure()
        for mask in (left_faces, ~left_faces)
    ]
    dense_png = _decode_png(dense.to_png(scale=scale))
    left_png, right_png = (_decode_png(half.to_png(scale=scale)) for half in halves)
    left, top, right, bottom = _plot_rect(figure_scene(dense))
    seam = scale * (left + (right - left) * 0.5)
    y0, y1 = int(np.ceil(top * scale)) + 2, int(bottom * scale) - 2
    for reference, x0, x1 in (
        (left_png, int(np.ceil(left * scale)) + 2, int(seam) - 2),
        (right_png, int(seam) + 3, int(right * scale) - 2),
    ):
        delta = np.abs(dense_png[y0:y1, x0:x1] - reference[y0:y1, x0:x1])
        assert delta.max() <= 3, (scale, delta.max())


def test_dense_mesh_consumes_the_shared_rust_autorange() -> None:
    """Without authored domains a mesh exports on Rust's figure autorange."""
    x0, y0, x1, y1, x2, y2, value = _quad_mesh(40, 40)
    style = {"stroke": "#111827", "stroke_width": 0.5}
    mesh = xyg.triangle_mesh(x0=x0, y0=y0, x1=x1, y1=y1, x2=x2, y2=y2, color=value, **style)
    figure = xyg.chart(mesh, width=WIDTH, height=HEIGHT).figure()
    domains = [tuple(float(v) for v in figure._range(axis)) for axis in ("x", "y")]
    authored = xyg.chart(
        mesh,
        xyg.x_axis(domain=domains[0]),
        xyg.y_axis(domain=domains[1]),
        width=WIDTH,
        height=HEIGHT,
    ).figure()
    assert scene_export_support_reason(figure) is None
    assert figure.to_svg() == authored.to_svg()
    assert figure.to_png() == authored.to_png()


def test_mesh_overdraw_above_the_group_budget_fails_closed() -> None:
    """1,100 full-plot faces would paint ~1,100 plots of pixels: refused.

    Painting cost is the faces' covered pixels; above 1,024 faces raster admission
    charges each face its plot-clipped bounding box and refuses more than 64
    plot rectangles, so overlapping faces cannot make export quadratic. At or
    below 1,024 faces nothing changes.
    """
    for n, expected in ((1_000, None), (1_100, _LOD)):
        zeros = np.zeros(n)
        figure = xyg.chart(
            xyg.triangle_mesh(x0=zeros, y0=zeros, x1=zeros + 1, y1=zeros, x2=zeros, y2=zeros + 1),
            xyg.x_axis(domain=(0.0, 1.0)),
            xyg.y_axis(domain=(0.0, 1.0)),
            width=WIDTH,
            height=HEIGHT,
        ).figure()
        assert scene_export_support_reason(figure) == expected, n
        if expected:
            with pytest.raises(UnsupportedStaticExport, match=_LOD):
                figure.to_png()
            assert scene_export_support_reason(figure, format="svg") is None
            assert scene_export_support_reason(figure, format="pdf") is None
            assert "<image" not in figure.to_svg()
            assert figure.to_image("pdf").startswith(b"%PDF")


def test_dense_mesh_above_the_scene_image_ceiling_fails_closed() -> None:
    # A 1,700 x 1,400 chart's plot rectangle exceeds 2,000,000 pixels even at
    # scale 1, so the SVG/PDF dense image cannot be bounded: the LOD reason.
    x0, y0, x1, y1, x2, y2, value = _quad_mesh(160, 160)
    figure = xyg.chart(
        xyg.triangle_mesh(x0=x0, y0=y0, x1=x1, y1=y1, x2=x2, y2=y2),
        width=1_700,
        height=1_400,
    ).figure()
    assert scene_export_support_reason(figure, format="svg") == _LOD
    with pytest.raises(UnsupportedStaticExport, match=_LOD):
        figure.to_svg()


def test_dense_mesh_beyond_the_scene_mark_ceiling_fails_closed() -> None:
    """3 expanded records per face share MAX_SCENE_MARKS (counted only)."""
    n = 700_000  # 2,100,000 expanded records
    zeros = np.zeros(n)
    ones = np.ones(n)
    figure = xyg.chart(
        xyg.triangle_mesh(x0=zeros, y0=zeros, x1=ones, y1=zeros, x2=zeros, y2=ones),
        xyg.x_axis(domain=(0.0, 1.0)),
        xyg.y_axis(domain=(0.0, 1.0)),
    ).figure()
    assert scene_export_support_reason(figure) == _LOD


def test_thick_mesh_outlines_are_charged_and_fail_closed_fast() -> None:
    """Outline painting is charged its padded stroke bounds (#1006).

    2,000 sub-pixel faces with a 100 px outline paint ~2,000 x 4 boxes of
    ~200 x 200 px; before the outline charge they passed the bound and a
    50,000-face version took 12.6 s to PNG. The same faces with an ordinary
    0.5 px outline still export.
    """
    import time

    n = 2_000
    i = np.arange(n, dtype=np.float64)
    gx, gy = (i % 50) / 50.0, np.floor(i / 50) / 40.0
    d = 0.0002

    def chart(width: float) -> xyg.Chart:
        return xyg.chart(
            xyg.triangle_mesh(
                x0=gx,
                y0=gy,
                x1=gx + d,
                y1=gy,
                x2=gx,
                y2=gy + d,
                stroke="#111827",
                stroke_width=width,
            ),
            xyg.x_axis(domain=(0.0, 1.0)),
            xyg.y_axis(domain=(0.0, 1.0)),
            width=WIDTH,
            height=HEIGHT,
        )

    thick = chart(100.0).figure()
    started = time.perf_counter()
    assert scene_export_support_reason(thick) == _LOD
    with pytest.raises(UnsupportedStaticExport, match=_LOD):
        thick.to_png()
    assert time.perf_counter() - started < 1.0
    thin = chart(0.5).figure()
    assert scene_export_support_reason(thin) is None
    assert thin.to_png().startswith(b"\x89PNG")


def _radial_fan(n: int) -> xyg.Chart:
    angle = np.arange(n + 1, dtype=np.float64) * (2 * np.pi / n)
    zeros = np.zeros(n)
    return xyg.chart(
        xyg.triangle_mesh(
            x0=zeros,
            y0=zeros,
            x1=np.cos(angle[:-1]),
            y1=np.sin(angle[:-1]),
            x2=np.cos(angle[1:]),
            y2=np.sin(angle[1:]),
        ),
        xyg.x_axis(domain=(-1.0, 1.0)),
        xyg.y_axis(domain=(-1.0, 1.0)),
        width=WIDTH,
        height=HEIGHT,
    )


@pytest.mark.parametrize("faces", [5_000, 50_000])
def test_radial_fan_is_vector_only_through_the_inclusive_ceiling(faces: int) -> None:
    """#1042: non-overlapping fan boxes exceed the raster cost bound."""
    figure = _radial_fan(faces).figure()
    for format in ("svg", "pdf"):
        assert scene_export_support_reason(figure, format=format) is None
    svg = figure.to_svg()
    assert "<image" not in svg
    assert svg.count(" Z") >= faces
    pdf = figure.to_image("pdf")
    assert pdf.startswith(b"%PDF") and b"/Subtype /Image" not in pdf
    for format in ("png", "jpeg", "webp"):
        assert scene_export_support_reason(figure, format=format) == _LOD
        with pytest.raises(UnsupportedStaticExport, match=_LOD):
            figure.to_image(format)


def test_radial_fan_above_vector_ceiling_keeps_dense_image_bound() -> None:
    figure = _radial_fan(50_001).figure()
    for format in ("svg", "pdf", "png"):
        assert scene_export_support_reason(figure, format=format) == _LOD
        with pytest.raises(UnsupportedStaticExport, match=_LOD):
            figure.to_image(format)


def test_multi_panel_xyst_cannot_bypass_raster_mesh_work_admission() -> None:
    from xyg import _native, _static_document

    scene = figure_scene(_radial_fan(5_000).figure())
    document = _static_document.encode(
        [_static_document.Panel(scene, offset, 0, WIDTH, HEIGHT) for offset in (0, WIDTH)],
        width=WIDTH * 2,
        height=HEIGHT,
    )
    assert b"<image" not in _native.static_document_export(document, "svg")
    with pytest.raises(_native.StaticDocumentRejected) as rejected:
        _native.static_document_export(document, "png")
    assert rejected.value.code == _LOD


def test_format_support_query_preserves_the_c_byte_buffer_contract() -> None:
    import ctypes

    from xyg import _native

    encoded = figure_scene(_radial_fan(5_000).figure())
    source = ctypes.create_string_buffer(encoded)
    query = _native._lib.xyg_scene_static_export_reason
    sentinel = ctypes.c_size_t(-1).value
    expected = _LOD.encode()
    assert query(source, len(encoded), 1, None, 0) == len(expected)
    short = ctypes.create_string_buffer(b"zz")
    assert query(source, len(encoded), 1, short, 2) == len(expected)
    assert short.raw == b"zz\0"  # No partial diagnostic or NUL is written.
    output = ctypes.create_string_buffer(b"z" * (len(expected) + 1))
    assert query(source, len(encoded), 1, output, len(expected)) == len(expected)
    assert output.raw[: len(expected)] == expected
    assert output.raw[len(expected)] == ord("z")  # Diagnostic has no NUL terminator.
    for code in (0, 2):
        assert query(source, len(encoded), code, short, 2) == 0
        assert short.raw == b"zz\0"
    malformed = ctypes.create_string_buffer(b"XYGS")
    assert query(malformed, 4, 0, short, 2) == sentinel
    assert query(source, len(encoded), 99, short, 2) == sentinel
    assert query(None, 0, 0, short, 2) == sentinel
    assert query(source, len(encoded), 1, None, 1) == sentinel
    assert short.raw == b"zz\0"


def test_large_scene_support_queries_allocate_only_diagnostic_buffers(monkeypatch) -> None:
    import ctypes

    from xyg import _native

    figure = _radial_fan(50_000).figure()
    scene = figure_scene(figure)
    assert len(scene) > 8_000_000
    query = _native._lib.xyg_scene_static_export_reason
    buffers = []

    def record_query(source, length, format, output, capacity):
        buffers.append((length, ctypes.sizeof(output), capacity))
        return query(source, length, format, output, capacity)

    monkeypatch.setattr(_native._lib, "xyg_scene_static_export_reason", record_query)
    assert _native.scene_static_export_reason(scene, "svg") == ""
    assert _native.scene_static_export_reason(scene, "png") == _LOD
    assert scene_export_support_reason(figure, format="svg") is None
    with pytest.raises(ValueError, match=_LOD):
        _native.scene_static_export(scene, "png")
    # Both query results fit in one call; their output scratch space must not
    # scale with the 8 MB Scene, including either caller's preflight path.
    assert len(buffers) == 4
    assert all(length > 8_000_000 for length, _, _ in buffers)
    assert all(size == capacity and size <= 256 for _, size, capacity in buffers), buffers

    # Keep the ABI's required-size retry if a future diagnostic exceeds the
    # initial scratch buffer; the first call must not truncate its payload.
    diagnostic = b"XYG_TEST_" + b"x" * 300
    capacities = []

    def long_diagnostic(source, length, format, output, capacity):
        capacities.append(capacity)
        if capacity >= len(diagnostic):
            ctypes.memmove(output, diagnostic, len(diagnostic))
        return len(diagnostic)

    monkeypatch.setattr(_native._lib, "xyg_scene_static_export_reason", long_diagnostic)
    assert _native.scene_static_export_reason(scene, "svg") == diagnostic.decode()
    assert capacities == [256, len(diagnostic)]
