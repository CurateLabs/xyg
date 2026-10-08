"""Typed catalog host framing and atomic native seam."""

import ctypes
import struct

import numpy as np
import pytest

from xyg import _geocatalog as host
from xyg import _native

CAMERA = dict(crs=4326, center_x=0.0, center_y=0.0, zoom=0.0, width=800.0, height=600.0)
SOURCE = dict(
    geometry=1,
    crs=4326,
    xy=np.array([0.0, 0.0], dtype="<f8"),
    validity=np.array([1, 0], dtype="u1"),
    feature_ids=np.array([2**64 - 1, 2**63], dtype="<u8"),
)


def request():
    return host.encode_request(
        dict(
            camera=CAMERA,
            layers=[
                dict(
                    layer_id=2**64 - 1,
                    kind=1,
                    source=SOURCE,
                    state_flags=np.array([2, 4], dtype="u1"),
                    legend_label="unicode λ",
                    labels=[
                        dict(
                            feature_index=0,
                            anchor=0,
                            font_size=12.0,
                            coordinate=[0.0, 0.0],
                            rgba=bytes([255, 0, 0, 255]),
                            text="label λ",
                        )
                    ],
                )
            ],
            legend=dict(title="catalog", location=0, font_size=12.0),
        )
    )


def test_source_metadata_scene_and_labels():
    out = host.decode_response(host.execute(request()))
    layer = out["layers"][0]
    assert layer["layer_id"] == 2**64 - 1
    np.testing.assert_array_equal(layer["feature_ids"], SOURCE["feature_ids"])
    np.testing.assert_array_equal(layer["validity"], [1, 0])
    np.testing.assert_array_equal(layer["state_flags"], [2, 4])
    np.testing.assert_array_equal(layer["visible_feature_indices"], [0])
    assert out["scene"][:4] == b"XYGS"
    assert len(out["rebuild_key"]) == 64
    np.testing.assert_array_equal(SOURCE["xy"], [0.0, 0.0])


def test_cabi_capacity_and_excess_length_preserve_destinations():
    raw = request()
    source = ctypes.create_string_buffer(raw)
    out = ctypes.create_string_buffer(b"x" * 16, 16)
    length = ctypes.c_size_t(12345)
    fn = _native._lib.xyg_geo_catalog_compile
    assert fn(source, len(raw), host.MAX_BYTES, out, 16, ctypes.byref(length)) == -13
    assert out.raw == b"x" * 16 and length.value == 12345
    assert fn(None, 1 << 40, host.MAX_BYTES, out, 16, ctypes.byref(length)) == -9
    assert out.raw == b"x" * 16 and length.value == 12345


def test_framing_and_recovery():
    raw = request()
    for offset in [96, 128 + 8 + 328]:
        bad = bytearray(raw)
        bad[offset] = 1
        with pytest.raises(_native.GeoNativeError):
            host.execute(bytes(bad))
    out = host.execute(raw)
    for offset in [96, 127]:
        bad = bytearray(out)
        bad[offset] = 1
        with pytest.raises(ValueError):
            host.decode_response(bytes(bad))
    with pytest.raises(ValueError):
        host.decode_response(out + b"\0")
    bad = bytearray(raw)
    struct.pack_into("<Q", bad, 128 + 8 + 264, 2**64 - 1)
    with pytest.raises(_native.GeoNativeError):
        host.execute(bytes(bad))


def test_precopy_budget(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("allocator/native must not run")

    monkeypatch.setattr(ctypes, "create_string_buffer", forbidden)
    monkeypatch.setattr(_native._lib, "xyg_geo_catalog_compile", forbidden)
    with pytest.raises(_native.GeoNativeError) as error:
        host.execute(b"x" * 65537, 65536)
    assert error.value.status == -9
    with pytest.raises(_native.GeoNativeError):
        host.execute(b"short")


@pytest.mark.parametrize("world_wrap", ["false", 2, None])
def test_boolean_and_no_narrowing(world_wrap):
    with pytest.raises(TypeError):
        host.encode_request(dict(camera={**CAMERA, "world_wrap": world_wrap}, layers=[]))
    with pytest.raises(TypeError):
        host.encode_request(
            dict(
                camera=CAMERA,
                layers=[
                    dict(layer_id=1, kind=1, source={**SOURCE, "xy": np.zeros(4, dtype="<f4")})
                ],
            )
        )


@pytest.mark.parametrize("operation", [1, 2, 3, 4, 5, 6, 7])
def test_interaction_full_u64_state_and_hits(operation):
    event = dict(operation=operation)
    if operation in (1, 2):
        event["coordinates"] = [400.0, 300.0]
    if operation == 3:
        event["coordinates"] = [390.0, 290.0, 410.0, 310.0]
    if operation == 5:
        event["delta"] = 1
    if operation in (6, 7):
        event.update(layer_id=2**64 - 1, feature_id=2**64 - 1)
    raw = host.encode_request(
        dict(camera=CAMERA, layers=[dict(layer_id=2**64 - 1, kind=1, source=SOURCE)], event=event)
    )
    out = host.decode_response(host.execute(raw))
    if operation != 4:
        assert out["hits"][0]["feature_id"] == 2**64 - 1
        np.testing.assert_array_equal(out["hits"][0]["feature_indices"], [0])
    if operation in (5, 6):
        assert out["focus"]["layer_id"] == 2**64 - 1
        np.testing.assert_array_equal(out["layers"][0]["state_flags"], [8, 0])
    if operation in (2, 3, 7):
        np.testing.assert_array_equal(out["layers"][0]["state_flags"], [2, 0])


def test_compile_only_focus_is_normalized_without_geometry_index():
    raw = host.encode_request(
        dict(
            camera=CAMERA,
            layers=[
                dict(layer_id=1, kind=1, source=SOURCE, state_flags=np.array([8, 8], dtype="u1"))
            ],
        )
    )
    out = host.decode_response(host.execute(raw))
    assert out["focus"] == dict(layer_id=1, feature_id=2**64 - 1)
    np.testing.assert_array_equal(out["layers"][0]["state_flags"], [8, 0])
    assert out["hits"] == []


def test_multipoint_density_counts_vertices_and_deduplicates_source_membership():
    source = dict(
        geometry=4,
        crs=4326,
        xy=np.array([0.0, 0.0, 0.0, 0.0], dtype="<f8"),
        validity=np.array([1], dtype="u1"),
        feature_ids=np.array([2**64 - 1], dtype="<u8"),
        offsets0=np.array([0, 2], dtype="<u4"),
    )
    raw = host.encode_request(
        dict(
            camera=CAMERA,
            layers=[dict(layer_id=9, kind=7, source=source, density=dict(columns=1, rows=1))],
        )
    )
    out = host.decode_response(host.execute(raw))
    bins = out["layers"][0]["density"]
    np.testing.assert_array_equal(bins["counts"], [2])
    np.testing.assert_array_equal(bins["offsets"], [0, 1])
    np.testing.assert_array_equal(bins["feature_indices"], [0])
