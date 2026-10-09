"""Explicit geographic tile data owners; selection and publication are Rust-owned."""

from __future__ import annotations

import ctypes
import hashlib
import inspect
import struct
import traceback
from dataclasses import dataclass

HEADER = 128
REPLY = 256
MAX_PACKET = 32 << 20
MAX_PROCESSOR = 128 << 20


def _uint(value, bits=64):
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value < 1 << bits:
        raise TypeError(f"expected u{bits}")
    return value


def _bytes(value):
    if not isinstance(value, (bytes, bytearray, memoryview)):
        raise TypeError("expected raw bytes")
    b = memoryview(value)
    if not b.c_contiguous:
        raise TypeError("contiguous bytes required")
    return b.cast("B")


def _budget(value):
    if isinstance(value, bool) or not isinstance(value, int) or not REPLY <= value <= MAX_PROCESSOR:
        raise ValueError("invalid tile processor budget")
    return value


def encode_request(command, handle=0, *, epoch=0, view=0, budget=0, payload=b""):
    command = _uint(command, 32)
    if command not in (*range(1, 11), 21, 22, 23):
        raise ValueError("unknown tile command")
    data = _bytes(payload)
    if len(data) + HEADER > MAX_PACKET or (budget and len(data) + HEADER > _budget(budget)):
        raise ValueError("tile command exceeds framing budget")
    b = bytearray(HEADER + len(data))
    struct.pack_into("<4sII", b, 0, b"XYGT", 1, command)
    struct.pack_into(
        "<5Q", b, 16, _uint(handle), _uint(epoch), _uint(view), _uint(budget), len(data)
    )
    b[HEADER:] = data
    return bytes(b)


def execute(packet):
    from . import _native

    if not isinstance(packet, bytes) or not HEADER <= len(packet) <= MAX_PACKET:
        raise ValueError("invalid tile request size")
    source, out = ctypes.create_string_buffer(packet), ctypes.create_string_buffer(REPLY)
    status = _native._lib.xyg_geo_tile_execute(source, len(packet), out, REPLY)
    if status:
        raise _native.GeoNativeError(status)
    return out.raw


def read(packet, budget):
    from . import _native

    _budget(budget)
    if not isinstance(packet, bytes) or not HEADER <= len(packet) <= min(MAX_PACKET, budget):
        raise ValueError("invalid tile read size")
    source, length = ctypes.create_string_buffer(packet), ctypes.c_size_t()
    fn = _native._lib.xyg_geo_tile_read
    status = fn(source, len(packet), budget, None, 0, ctypes.byref(length))
    if status:
        raise _native.GeoNativeError(status)
    if length.value > MAX_PACKET or length.value * 2 > budget:
        raise _native.GeoNativeError(-9)
    out = ctypes.create_string_buffer(length.value)
    status = fn(source, len(packet), budget, out, len(out), ctypes.byref(length))
    if status:
        raise _native.GeoNativeError(status)
    if length.value != len(out):
        raise ValueError("tile read length changed")
    return out.raw


def _reply(packet):
    b = _bytes(packet)
    if (
        len(b) < REPLY
        or b[:4] != b"XYGU"
        or struct.unpack_from("<I", b, 4)[0] != 1
        or any(b[12:16])
    ):
        raise ValueError("invalid tile receipt")
    return b


def _fixed(packet):
    b = _reply(packet)
    if len(b) != REPLY:
        raise ValueError("fixed tile reply required")
    return dict(
        kind=struct.unpack_from("<I", b, 8)[0],
        handle=struct.unpack_from("<Q", b, 16)[0],
        epoch=struct.unpack_from("<Q", b, 24)[0],
        count=struct.unpack_from("<Q", b, 32)[0],
    )


def _key(b):
    if len(b) != 80 or any(b[76:80]):
        raise ValueError("invalid tile key")
    values = struct.unpack_from("<5Q2q5I", b)
    if (
        values[7] > 1
        or values[8] > 1
        or values[9] > 25
        or (not values[7] and (values[5] or values[6]))
    ):
        raise ValueError("invalid typed tile key")
    return dict(
        zip(
            (
                "source_id",
                "generation",
                "layer_id",
                "layer_revision",
                "style_revision",
                "start",
                "end",
                "time_present",
                "kind",
                "z",
                "x",
                "y",
            ),
            values,
            strict=True,
        )
    )


def decode_read_receipt(packet, handle, epoch):
    b = _reply(packet)
    location, locator_length, attr_length = struct.unpack_from("<3I", b, 48)
    if (
        len(b) != REPLY + locator_length + attr_length
        or location > 1
        or locator_length > 4096
        or attr_length > 4096
        or any(b[60:64])
        or any(b[168:256])
        or struct.unpack_from("<QQ", b, 16) != (handle, epoch)
        or struct.unpack_from("<I", b, 8)[0] != 2
        or any(b[84:88])
        or not 0 < struct.unpack_from("<Q", b, 32)[0] <= 8 << 20
    ):
        raise ValueError("invalid tile read receipt planes")
    key = _key(b[88:168])
    return dict(
        packet=b,
        handle=handle,
        epoch=epoch,
        max_bytes=struct.unpack_from("<Q", b, 32)[0],
        ticket=bytes(b[64:168]),
        key=key,
        location=location,
        locator=bytes(b[256 : 256 + locator_length]).decode("utf-8"),
        attribution=bytes(b[256 + locator_length :]).decode("utf-8"),
    )


@dataclass(frozen=True)
class GeoTileSource:
    source_id: int
    generation: int
    layer_id: int
    layer_revision: int
    style_revision: int
    kind: int
    min_zoom: int
    max_zoom: int
    max_bytes: int
    max_features: int
    max_vertices: int
    locator: str
    attribution: str
    network: bool
    time: tuple[int, int] | None = None

    def encode(self):
        if not isinstance(self.network, bool):
            raise TypeError("network must be an explicit boolean")
        locator, attr = self.locator.encode("utf-8"), self.attribution.encode("utf-8")
        if len(locator) > 4096 or len(attr) > 4096:
            raise ValueError("tile source text exceeds framing")
        b = bytearray(112 + len(locator) + len(attr))
        struct.pack_into(
            "<5Q",
            b,
            0,
            *(
                _uint(n)
                for n in (
                    self.source_id,
                    self.generation,
                    self.layer_id,
                    self.layer_revision,
                    self.style_revision,
                )
            ),
        )
        if self.time is not None:
            if len(self.time) != 2 or any(
                isinstance(n, bool) or not isinstance(n, int) or not -(1 << 63) <= n < 1 << 63
                for n in self.time
            ):
                raise TypeError("time requires two i64 endpoints")
            struct.pack_into("<2qI", b, 40, *self.time, 1)
        struct.pack_into(
            "<IBB", b, 60, _uint(self.kind, 32), _uint(self.min_zoom, 8), _uint(self.max_zoom, 8)
        )
        struct.pack_into(
            "<3Q3I",
            b,
            72,
            *(_uint(n) for n in (self.max_bytes, self.max_features, self.max_vertices)),
            len(locator),
            len(attr),
            self.network,
        )
        b[112:] = locator + attr
        return bytes(b)


def encode_begin(camera, sources):
    from ._geoviewport import encode_request as encode_camera_request

    wire = encode_camera_request(camera)
    camera_bytes = wire[12:20] + wire[24:80]
    encoded = [source.encode() for source in sources]
    size = 80 + sum(map(len, encoded))
    if len(encoded) > 16 or size + HEADER > MAX_PACKET:
        raise ValueError("tile sources exceed framing")
    b = bytearray(size)
    b[:64] = camera_bytes
    struct.pack_into("<I", b, 64, len(encoded))
    at = 80
    for source in encoded:
        b[at : at + len(source)] = source
        at += len(source)
    return bytes(b)


def encode_prepare(catalog, vector_styles, image_id):
    from . import _geoscale as g

    catalog = _bytes(catalog)
    if len(vector_styles) > 64 or len(catalog) + 32 + 64 * len(vector_styles) + HEADER > MAX_PACKET:
        raise ValueError("tile scene exceeds framing")
    b = bytearray(32 + 64 * len(vector_styles) + len(catalog))
    struct.pack_into("<QI", b, 0, _uint(image_id), len(vector_styles))
    struct.pack_into("<Q", b, 16, len(catalog))
    for i, item in enumerate(vector_styles):
        at = 32 + 64 * i
        struct.pack_into("<QI", b, at, _uint(item["layer_id"]), _uint(item["kind"], 32))
        style = item["style"] if isinstance(item["style"], bytes) else g.encode_style(item["style"])
        if len(style) != 48 or any(style[33:]):
            raise ValueError("style must have exact48 bytes and zero reserved fields")
        b[at + 16 : at + 49] = style[:33]
    b[32 + 64 * len(vector_styles) :] = catalog
    return bytes(b)


def decode_frame(packet):
    from . import _geocatalog

    b = _reply(packet)
    view, catalog_length, keys, attrs, attr_bytes = struct.unpack_from("<5Q", b, 32)
    padded = (catalog_length + 7) & ~7
    if (
        keys > 64
        or attrs > 16
        or len(b) != REPLY + padded + keys * 80 + attr_bytes
        or any(b[144:256])
        or any(b[REPLY + catalog_length : REPLY + padded])
    ):
        raise ValueError("invalid tile frame planes")
    catalog = _geocatalog.decode_response(b[REPLY : REPLY + catalog_length])
    at = REPLY + padded
    tile_keys = [_key(b[at + i * 80 : at + (i + 1) * 80]) for i in range(keys)]
    at += keys * 80
    attributions = []
    for _ in range(attrs):
        if at + 8 > len(b) or any(b[at + 4 : at + 8]):
            raise ValueError("invalid attribution record")
        length = struct.unpack_from("<I", b, at)[0]
        end, padded_end = at + 8 + length, at + ((8 + length + 7) & ~7)
        if length > 4096 or padded_end > len(b) or any(b[end:padded_end]):
            raise ValueError("invalid attribution plane")
        attributions.append(bytes(b[at + 8 : end]).decode("utf-8"))
        at = padded_end
    if at != len(b):
        raise ValueError("trailing tile frame data")
    return dict(
        packet=b,
        view=view,
        epoch=struct.unpack_from("<Q", b, 24)[0],
        cache=struct.unpack_from("<Q", b, 16)[0],
        catalog=catalog,
        scene=catalog["scene"],
        keys=tile_keys,
        attributions=attributions,
    )


class OwnedTileFrame:
    """Drop receipt/Scene views and target painters before close releases the lease."""

    def __init__(self, handle, data, session):
        self.handle, self._data, self._session = handle, data, session
        self._bridge, self._freeze_command = None, 4
        self.epoch, self._committed, self._closed = data["epoch"], False, False
        self._camera_packet = None
        self._prepare_digest = None

    @property
    def data(self):
        if self._closed:
            raise RuntimeError("tile frame disposed")
        return self._data

    def export(self, format="png", **options):
        from ._geo_snapshot import export_frame

        return export_frame(self, self.epoch, format, **options)

    def commit(self):
        _ = self.data
        execute(encode_request(7, self.handle, epoch=self.epoch))
        self._committed = True
        self._session.current = self

    def close(self):
        if not self._closed:
            self._data = None
            if not self._committed and not self._session._closed:
                execute(encode_request(9, self._session.handle, epoch=self.epoch))
            execute(encode_request(10, self.handle))
            self._closed = True


class GeoTileSession:
    """Explicit synchronous native tile I/O; staged candidates commit atomically."""

    def __init__(self, sources, read_tile, *, view_id, budget):
        if (
            not isinstance(sources, (list, tuple))
            or len(sources) > 16
            or not callable(read_tile)
            or not all(isinstance(s, GeoTileSource) for s in sources)
        ):
            raise TypeError("explicit tile sources and reader required")
        self.sources, self._reader = tuple(sources), read_tile
        self.view_id, self.budget = _uint(view_id), _budget(budget)
        self.handle = _fixed(execute(encode_request(1)))["handle"]
        self.current, self._closed, self._busy = None, False, False

    def prepare(self, camera, *, catalog, vector_styles, image_id):
        if self._closed or self._busy:
            raise RuntimeError("tile session unavailable")
        payload = encode_begin(camera, self.sources)
        preparation = encode_prepare(catalog, vector_styles, image_id)
        self._busy = True
        epoch = None
        frame_handle = None
        frame = None
        try:
            epoch = _fixed(
                execute(
                    encode_request(
                        2, self.handle, view=self.view_id, budget=self.budget, payload=payload
                    )
                )
            )["epoch"]
            while True:
                issued = _fixed(execute(encode_request(3, self.handle, epoch=epoch)))
                read_handle = issued["handle"]
                if read_handle == 0:
                    break
                receipt = data = view = None
                try:
                    receipt = decode_read_receipt(
                        read(
                            encode_request(21, read_handle, epoch=epoch, budget=self.budget),
                            self.budget,
                        ),
                        read_handle,
                        epoch,
                    )
                    authorized_max = receipt["max_bytes"]
                    data = self._reader(receipt)
                    if inspect.isawaitable(data):
                        if inspect.iscoroutine(data):
                            data.close()
                        raise TypeError("native synchronous tile reader must return bytes")
                    view = _bytes(data)
                    if view.nbytes > authorized_max or memoryview(view.obj).nbytes > authorized_max:
                        raise ValueError("tile read exceeds authorized capacity")
                    execute(encode_request(4, read_handle, epoch=epoch, payload=view))
                    view = None
                except BaseException as error:
                    view = data = receipt = None
                    traceback.clear_frames(error.__traceback__)
                    raise
                finally:
                    view = data = receipt = None
                    execute(encode_request(5, read_handle, epoch=epoch))
            fixed = _fixed(
                execute(
                    encode_request(
                        6, self.handle, epoch=epoch, budget=self.budget, payload=preparation
                    )
                )
            )
            frame_handle = fixed["handle"]
            data = decode_frame(
                read(encode_request(22, frame_handle, epoch=epoch, budget=self.budget), self.budget)
            )
            if (
                data["epoch"] != epoch
                or data["cache"] != self.handle
                or data["view"] != self.view_id
            ):
                raise ValueError("mismatched tile frame authority")
            frame = OwnedTileFrame(frame_handle, data, self)
            frame._camera_packet = payload[:64]
            frame._prepare_digest = hashlib.sha256(preparation).digest()
            frame_handle = None
            return frame
        except BaseException as error:
            data = None
            traceback.clear_frames(error.__traceback__)
            if frame_handle is not None:
                execute(encode_request(10, frame_handle))
            if epoch is not None:
                execute(encode_request(9, self.handle, epoch=epoch))
            raise
        finally:
            self._busy = False

    def update(self, camera, *, catalog, vector_styles, image_id, stage):
        if not callable(stage):
            raise TypeError("an explicit target staging callback is required")
        frame = self.prepare(
            camera, catalog=catalog, vector_styles=vector_styles, image_id=image_id
        )
        self._busy = True
        try:
            staged = stage(frame)
            if inspect.isawaitable(staged):
                if inspect.iscoroutine(staged):
                    staged.close()
                raise TypeError("native synchronous staging callback cannot be async")
            frame.commit()
            return frame
        except BaseException:
            execute(encode_request(9, self.handle, epoch=frame.epoch))
            frame.close()
            raise
        finally:
            self._busy = False

    def close(self):
        if self._busy:
            raise RuntimeError("tile session operation is active")
        if not self._closed:
            execute(encode_request(10, self.handle))
            self._closed = True


def http_tile_loader(receipt):
    """Explicit opt-in loader for configured HTTP(S) raw RGBA/XYGD payloads."""
    from urllib.parse import urlsplit
    from urllib.request import urlopen

    if receipt["location"] != 1 or not receipt["attribution"]:
        raise ValueError("configured attributed network tile required")
    key = receipt["key"]
    url = receipt["locator"]
    for name in ("z", "x", "y"):
        url = url.replace("{" + name + "}", str(key[name]))
    if urlsplit(url).scheme not in ("http", "https"):
        raise ValueError("HTTP(S) tile URL required")
    with urlopen(url) as response:
        if urlsplit(response.url).scheme not in ("http", "https"):
            raise ValueError("HTTP(S) response required")
        data = response.read(receipt["max_bytes"] + 1)
    if len(data) > receipt["max_bytes"]:
        raise ValueError("network tile exceeds authorized capacity")
    return data
