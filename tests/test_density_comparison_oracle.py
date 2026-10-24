"""Source-to-payload goldens, independent of native aggregation expectations."""

from __future__ import annotations

import math

import numpy as np
import pytest
from benchmarks._ux_comparison_oracle import SourceOracle, compose, encode, histogram
from benchmarks._ux_comparison_source import create_source, load_source, window_counts


def decoded(wire, maximum):
    return (
        np.expm1(np.frombuffer(wire, dtype=np.uint8).astype(float) / 255 * math.log1p(maximum))
        .astype("<f4")
        .tobytes()
    )


def observation(out):
    d = out["density"]
    return {
        **out,
        "domain": [*d["x_range"], *d["y_range"]],
        "raster_shape": [d["h"], d["w"]],
        "reply_max": d["max"],
        "adopted_max": d["max"],
        "encoding": d["enc"],
    }


@pytest.mark.parametrize("pyramid", [False, True])
def test_actual_native_payload_matches_source_oracle(tmp_path, monkeypatch, pyramid):
    from scripts import verify_density_comparison_report as verifier

    import xyg
    from xyg import interaction, kernels

    n = 1_000_000
    meta = create_source(tmp_path / "source", n, "f64-memmap")
    x, y, _ = load_source(tmp_path / "source/source.json", n)
    if pyramid:
        # Eligibility only: native 2048 base, real mapped path, thresholds intact.
        monkeypatch.setattr(interaction, "PYRAMID_MIN_POINTS", n)

    def forbidden(*args, **kwargs):
        raise AssertionError("native aggregation answer used by oracle")

    with monkeypatch.context() as independent:
        for name in ("pyramid_count", "pyramid_compose", "bin_2d", "density_log_u8"):
            independent.setattr(kernels, name, forbidden)
        oracle = SourceOracle(x, y, meta, base_dim=2048 if pyramid else None)
    fig = xyg.scatter_chart(xyg.scatter(x, y, density=True)).figure()
    t = fig.traces[0]
    try:
        for item in meta["windows"]:
            reply, buffers = interaction.density_view(fig, t.id, *item["window"], 512, 512)
            out = observation(reply["traces"][0])
            wire = bytes(buffers[out["density"]["buf"]])
            proof = oracle.validate(out, wire, decoded(wire, out["reply_max"]))
            assert proof["passed"], (out, proof)
            # Pure verifier gate over a real numerical proof; injected HTTP
            # accounting is test metadata, not a browser measurement.
            proof.update(validation_wall_ms=0, validation_http_request_bytes=1)
            checked = dict(out, numerical_oracle=proof, exact_fallback=False)
            verifier.check_numerical(checked, item["window"], item["expected_count"])
            with pytest.raises(verifier.InvalidReport):
                verifier.check_numerical(
                    dict(checked, visible=out["visible"] + 1),
                    item["window"],
                    item["expected_count"],
                )
            assert proof["exact_source_count"] == item["expected_count"]
            if pyramid:
                assert out["binning"].startswith("pyramid-L")
                assert proof["count_exact"] is False
            else:
                assert out["binning"] == "bin2d-oversized"
        if pyramid:
            assert any(
                r["expected_visible"] != r["exact_source_count"]
                for (d, cold), r in oracle.records.items()
                if not cold
            )

        # The independent expected grid must not call back into native answers.
        for name in ("pyramid_count", "pyramid_compose", "bin_2d", "density_log_u8"):
            monkeypatch.setattr(kernels, name, forbidden)
        bad = dict(out, visible=out["visible"] + 1)
        assert not oracle.validate(bad, wire, decoded(wire, out["reply_max"]))["passed"]
        moved = np.roll(np.frombuffer(wire, dtype=np.uint8), 1).tobytes()
        assert not oracle.validate(out, moved, decoded(moved, out["reply_max"]))["passed"]
        assert not oracle.validate(out, wire, decoded(moved, out["reply_max"]))["passed"]
        assert not oracle.validate(
            dict(out, tier="direct", reduction="none"), wire, decoded(wire, out["reply_max"])
        )["passed"]
    finally:
        interaction._free_pyramid(t)


def test_upper_edges_are_not_removed_from_source_truth():
    from xyg import kernels

    x, y = np.array([0, 0.5, 1.0, 0.5]), np.array([0, 0.5, 0.5, 1.0])
    counts = window_counts(x, y, [0, 1, 0, 1], chunk=1)
    assert counts == {"inclusive": 4, "half_open": 2, "upper_boundary_excluded": 2}
    assert histogram(x, y, [0, 1, 0, 1], (16, 16)).sum() == 2
    assert kernels.bin_2d(x, y, 0, 1, 0, 1, 16, 16).sum() == 2
    assert len(kernels.range_indices(x, y, 0, 1, 0, 1)) == 4


@pytest.mark.parametrize(
    "domain", [[0.0, 1.0, 0.0, 1.0], [0.123, 0.813, 0.071, 0.739], [0.4, 0.42, 0.5, 0.52]]
)
def test_independent_compose_aligned_nonaligned_and_upsampled(domain):
    from xyg import kernels

    rng = np.random.default_rng(53)
    x, y = rng.random(8192), rng.random(8192)
    levels = [histogram(x, y, [0.0, 1.0, 0.0, 1.0], (64, 64))]
    while levels[-1].shape[0] > 1:
        a = levels[-1]
        levels.append(a[::2, ::2] + a[1::2, ::2] + a[::2, 1::2] + a[1::2, 1::2])
    handle = kernels.pyramid_build(x, y, 0, 1, 0, 1, 64)
    try:
        actual, level = kernels.pyramid_compose(handle, *domain, 16, 16, 1 << 30)
        expected, selected = compose(levels, [0.0, 1.0, 0.0, 1.0], domain, (16, 16))
        assert level == selected
        np.testing.assert_array_equal(actual, expected.ravel())
        encoded, maximum = kernels.density_log_u8(actual)
        assert encode(expected) == (encoded.tobytes(), maximum)
    finally:
        kernels.pyramid_free(handle)


def test_concentrated_boundary_has_source_mass_bound_not_percentage(tmp_path):
    from xyg import kernels

    meta = create_source(tmp_path / "source", 1000, "f64-memmap")
    x, y = np.full(1000, 0.508), np.full(1000, 0.508)
    x[:2], y[:2] = [0, 1], [0, 1]
    domain = [0, 0.5079, 0, 0.5079]
    meta["source_bounds"] = [0.0, 1.0, 0.0, 1.0]
    counts = window_counts(x, y, domain)
    meta["windows"] = [{"window": domain, "source_counts": counts}]
    oracle = SourceOracle(x, y, meta, base_dim=64)
    r = oracle.records[(tuple(domain), False)]
    assert r["exact_source_count"] == 1
    assert r["expected_visible"] == 999
    assert r["boundary_mass_bound"] >= 998
    handle = kernels.pyramid_build(x, y, *oracle.bounds, 64)
    try:
        assert kernels.pyramid_count(handle, *domain) == r["expected_visible"]
    finally:
        kernels.pyramid_free(handle)


def test_exact_fallback_keeps_gpu_count_and_padded_payload_distinct(tmp_path):
    meta = create_source(tmp_path / "source", 1000, "f32")
    x, y, _ = load_source(tmp_path / "source/source.json", 1000)
    oracle = SourceOracle(x, y, meta)
    step = meta["windows"][1]
    out = {
        "mode": "points",
        "tier": "direct",
        "reduction": "none",
        "visible": 1000,
        "domain": meta["extents"],
        "exact_count": step["expected_count"],
    }
    assert oracle.validate(out, target=step["window"])["passed"]
    assert not oracle.validate(
        dict(out, exact_count=step["expected_count"] + 1), target=step["window"]
    )["passed"]
