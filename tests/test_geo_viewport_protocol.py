"""Native camera semantics and no-write C ABI failures (#48)."""

from __future__ import annotations

import ctypes

import numpy as np
import pytest

from xyg import _geoviewport as host
from xyg import _native

CAMERA = dict(
    crs=4326, center_x=0.0, center_y=0.0, zoom=2.0, width=800.0, height=600.0, world_wrap=True
)


def test_native_project_inverse_and_transactional_snapshot() -> None:
    projected = host.geo_viewport(CAMERA, host.OPERATIONS["project"], (10.0, 20.0))
    restored = host.geo_viewport(
        projected["camera"], host.OPERATIONS["inverse"], projected["result"]
    )
    np.testing.assert_allclose(restored["result"], (10.0, 20.0), rtol=0, atol=1e-9)
    normalized = host.geo_viewport({**CAMERA, "bearing": 720.0})
    assert normalized["camera"]["bearing"] == 0.0
    assert len(normalized["rebuild_key"]) == 64
    assert normalized["bounds"] is not None
    assert normalized["bounds"][0] < 0 < normalized["bounds"][2]
    assert normalized["bounds"][1] < 0 < normalized["bounds"][3]
    with pytest.raises(_native.GeoNativeError) as error:
        host.geo_viewport(CAMERA, host.OPERATIONS["zoom"], (25.0,))
    assert error.value.status == -1
    assert CAMERA["zoom"] == 2.0


def test_cabi_output_failure_leaves_every_destination_untouched() -> None:
    request = ctypes.create_string_buffer(host.encode_request(CAMERA))
    out = ctypes.create_string_buffer(b"x" * 255, 255)
    length = ctypes.c_size_t(12345)
    code = _native._lib.xyg_geo_viewport_execute(
        request, 128, 65536, out, 255, ctypes.byref(length)
    )
    assert code == -13
    assert out.raw == b"x" * 255
    assert length.value == 12345
    code = _native._lib.xyg_geo_viewport_execute(
        None, 1 << 40, 65536, out, 255, ctypes.byref(length)
    )
    assert code == -9
    assert length.value == 12345


def test_response_reserved_padding_and_trailing_bytes_are_rejected() -> None:
    data = host.execute(host.encode_request(CAMERA))
    for offset in (172, 232):
        bad = bytearray(data)
        bad[offset] = 1
        with pytest.raises(ValueError):
            host.decode_response(bytes(bad))
    with pytest.raises(ValueError):
        host.decode_response(data + b"\0" * 8)


def test_overbudget_input_fails_before_host_allocation(monkeypatch: pytest.MonkeyPatch) -> None:
    request = host.encode_request(CAMERA)

    def forbidden(*args: object, **kwargs: object) -> None:
        raise AssertionError("allocator/native processor must not be invoked")

    monkeypatch.setattr(ctypes, "create_string_buffer", forbidden)
    monkeypatch.setattr(_native._lib, "xyg_geo_viewport_execute", forbidden)
    with pytest.raises(_native.GeoNativeError) as error:
        host.execute(request, budget=127)
    assert error.value.status == -9
    with pytest.raises(_native.GeoNativeError) as error:
        host.execute(b"short")
    assert error.value.status == -1


@pytest.mark.parametrize("value", ["false", 2, None])
def test_wrap_requires_explicit_boolean(value: object) -> None:
    with pytest.raises(TypeError):
        host.encode_request({**CAMERA, "world_wrap": value})
    assert not host.geo_viewport({**CAMERA, "world_wrap": False})["camera"]["world_wrap"]


def test_typed_geoarrow_descriptor_prefix_preserves_source_bits_and_identity() -> None:
    import pyarrow as pa

    from xyg import _geoarrow

    storage = pa.struct([("x", pa.float64()), ("y", pa.float64())])
    field = pa.field(
        "geometry",
        storage,
        metadata={
            b"ARROW:extension:name": b"geoarrow.point",
            b"ARROW:extension:metadata": b'{"crs":"EPSG:4326"}',
        },
    )
    column = pa.array([{"x": 0.0, "y": 0.0}], type=storage)
    descriptor = _geoarrow.descriptor_from_geoarrow(
        column, field, np.array([2**64 - 1], dtype=np.uint64)
    )
    before = descriptor["xy"].tobytes()
    response = host.decode_response(host.execute(host.encode_column_request(CAMERA, descriptor)))
    assert response["visible_feature_ids"].tolist() == [2**64 - 1]
    assert descriptor["xy"].tobytes() == before
    assert response["bounds"] == (400.0, 300.0, 400.0, 300.0)
    with pytest.raises(TypeError):
        host.encode_column_request(
            CAMERA, {**descriptor, "xy": descriptor["xy"].astype(np.float32)}
        )
