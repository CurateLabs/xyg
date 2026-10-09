"""Thin immutable mixed-frame transport; Rust owns composition and publication."""

from __future__ import annotations

import math
import struct
import traceback

from . import _geo_tiles as tiles
from . import _geoscale as scale

HEADER = 256
MAX_PACKET = 32 << 20
MAX_BUDGET = 128 << 20


def request(
    command: int,
    handle: int = 0,
    *,
    nonce: int = 0,
    budget: int = 0,
    authorities: tuple[int, ...] | list[int] | None = None,
    snapshot: bytes | bytearray | memoryview | None = None,
    stamps: bytes | bytearray | memoryview | None = None,
) -> bytes:
    command, handle, nonce, budget = (
        scale._uint(command, 32),
        scale._uint(handle),
        scale._uint(nonce),
        scale._uint(budget),
    )
    if (
        command not in (1, 2, 3, 4, 5, 6, 20)
        or budget > MAX_BUDGET
        or (command in (1, 3, 4, 5) and budget)
        or (command in (2, 6, 20) and budget < 65536)
        or (command in (1, 2, 5) and nonce)
        or (command != 2 and any(v is not None for v in (authorities, snapshot, stamps)))
    ):
        raise ValueError("field does not belong to mixed command")
    payload = b""
    encoded_authorities = None
    count = 0
    if command == 2:
        if snapshot is None or stamps is None:
            raise TypeError("exact mixed snapshot/stamps required")
        snapshot, stamps = scale._bytes(snapshot), scale._bytes(stamps)
        if len(snapshot) != 160 or len(stamps) % 96 or len(stamps) > 64 * 96:
            raise ValueError("exact mixed snapshot/stamps required")
        if not isinstance(authorities, (tuple, list)) or len(authorities) != 7:
            raise TypeError("six exact authority IDs and explicit tile time required")
        if authorities[6] not in (0, 1):
            raise ValueError("unsupported mixed tile temporal guarantee")
        encoded_authorities = tuple(scale._uint(n) for n in authorities)
        count = len(stamps) // 96
        payload = bytes(snapshot) + bytes(stamps)
    b = bytearray(HEADER + len(payload))
    struct.pack_into("<4sII", b, 0, b"XYMX", 1, command)
    struct.pack_into("<4Q", b, 16, handle, nonce, budget, len(payload))
    if encoded_authorities is not None:
        struct.pack_into("<6QII", b, 64, *encoded_authorities, count)
    b[HEADER:] = payload
    return bytes(b)


def reply(packet):
    b = scale._bytes(packet)
    if len(b) != HEADER or b[:4] != b"XYMY" or struct.unpack_from("<I", b, 4)[0] != 1:
        raise ValueError("invalid fixed mixed reply")
    kind = struct.unpack_from("<I", b, 8)[0]
    if kind > 2 or any(b[12:16]) or any(b[48:]):
        raise ValueError("invalid mixed reply fields")
    handle, nonce, coordinator, length = struct.unpack_from("<4Q", b, 16)
    if length > MAX_PACKET:
        raise ValueError("mixed packet exceeds bound")
    return dict(kind=kind, handle=handle, nonce=nonce, coordinator=coordinator, length=length)


class MixedData:
    """Planes borrow one bounded receipt; drop every external view before close."""

    def __init__(self, packet):
        self.packet = packet
        b = scale._bytes(packet)
        if not HEADER <= len(b) <= MAX_PACKET or b[:4] != b"XYMF":
            raise ValueError("invalid mixed data framing")
        version, flags = struct.unpack_from("<II", b, 4)
        self.coordinator, self.nonce, scene_length, tile_length = struct.unpack_from("<4Q", b, 16)
        ranges = struct.unpack_from("<4Q", b, 48)
        self.source_handle, self.source_sequence, self.tile_handle, self.tile_epoch, cache, view = (
            struct.unpack_from("<6Q", b, 80)
        )
        self.tile_time = struct.unpack_from("<I", b, 128)[0]
        if (
            version != 1
            or flags
            or any(b[12:16])
            or any(b[132:136])
            or any(b[160:256])
            or self.tile_time > 1
            or struct.unpack_from("<Q", b, 136)[0] != len(b)
            or HEADER + scene_length + tile_length + 208 != len(b)
            or scene_length < 160
            or tile_length < 384
        ):
            raise ValueError("invalid mixed data planes")
        self.scene = b[HEADER : HEADER + scene_length]
        self.tile = b[HEADER + scene_length : HEADER + scene_length + tile_length]
        if (
            self.scene[:4] != b"XYGS"
            or struct.unpack_from("<II", self.scene, 4) != (32, 160)
            or self.tile[:4] != b"XYGU"
            or struct.unpack_from("<II", self.tile, 4) != (1, 1)
            or struct.unpack_from("<3Q", self.tile, 16) != (cache, self.tile_epoch, view)
        ):
            raise ValueError("invalid embedded mixed authority")
        records, styles = struct.unpack_from("<2Q", self.scene, 16)
        if (
            records > 2_000_000
            or styles > 2_000_000
            or not 0 <= ranges[0] <= ranges[1] <= records
            or not 0 <= ranges[2] <= ranges[3] <= styles
        ):
            raise ValueError("invalid retained record/style ranges")
        self.retained_records, self.retained_styles = ranges[:2], ranges[2:]
        self.snapshot, self.style = b[-208:-48], b[-48:]
        if any(self.snapshot[132:136]) or any(self.snapshot[152:160]) or any(self.style[33:]):
            raise ValueError("nonzero mixed snapshot/style reserved bytes")
        crs, wrap = struct.unpack_from("<2I", self.snapshot)
        time_kind = struct.unpack_from("<I", self.snapshot, 128)[0]
        start, end = struct.unpack_from("<2q", self.snapshot, 136)
        if (
            crs not in (4326, 3857)
            or wrap > 1
            or time_kind > 2
            or (time_kind == 0 and (start or end))
            or (time_kind == 1 and end)
            or (time_kind == 2 and start >= end)
        ):
            raise ValueError("invalid mixed camera/time framing")
        if not all(
            math.isfinite(n) for n in struct.unpack_from("<7d", self.snapshot, 8)
        ) or not all(math.isfinite(n) for n in struct.unpack_from("<3d", self.style, 8)):
            raise ValueError("nonfinite mixed camera/style")
        if self.snapshot[:8] != self.tile[72:80] or self.snapshot[8:64] != self.tile[80:136]:
            raise ValueError("mismatched mixed camera")
        self.visible_vertices, self.projected_vertices = struct.unpack_from("<2Q", b, 144)


class MixedCandidate:
    _freeze_command = 5
    _bridge = None

    def __init__(self, handle, nonce, data):
        self.handle, self.nonce, self._data = handle, nonce, data
        self._closed = False

    @property
    def data(self):
        if self._data is None:
            raise RuntimeError("mixed frame disposed")
        return self._data

    def commit(self):
        _ = self.data
        tiles.execute(request(3, self.handle, nonce=self.nonce))

    def cancel(self):
        _ = self.data
        tiles.execute(request(4, self.handle, nonce=self.nonce))

    def retain_source_authority(self, *, budget):
        _ = self.data
        return reply(tiles.execute(request(6, self.handle, nonce=self.nonce, budget=budget)))

    def export(self, format="png", **options):
        from ._geo_snapshot import export_frame

        _ = self.data
        return export_frame(self, self.nonce, format, **options)

    def close(self):
        self._data = None
        if not self._closed:
            tiles.execute(request(5, self.handle))
            self._closed = True


def prepare(packet, *, budget):
    if (
        not isinstance(packet, bytes)
        or len(packet) < HEADER
        or packet[:4] != b"XYMX"
        or struct.unpack_from("<I", packet, 8)[0] != 2
    ):
        raise ValueError("mixed prepare requires command2")
    fixed = reply(tiles.execute(packet))
    data = raw = None
    try:
        if (
            fixed["kind"] != 1
            or fixed["coordinator"] != struct.unpack_from("<Q", packet, 16)[0]
            or fixed["nonce"] == 0
            or 2 * fixed["length"] > budget
        ):
            raise ValueError("invalid mixed candidate admission")
        raw = tiles.read(request(20, fixed["handle"], nonce=fixed["nonce"], budget=budget), budget)
        if len(raw) != fixed["length"]:
            raise ValueError("mixed candidate size changed")
        data = MixedData(raw)
        if (
            data.coordinator != fixed["coordinator"]
            or data.nonce != fixed["nonce"]
            or (data.source_handle, data.source_sequence, data.tile_handle, data.tile_epoch)
            != struct.unpack_from("<4Q", packet, 64)
        ):
            raise ValueError("mixed candidate identity changed")
        return MixedCandidate(fixed["handle"], fixed["nonce"], data)
    except BaseException as error:
        data = raw = None
        traceback.clear_frames(error.__traceback__)
        tiles.execute(request(5, fixed["handle"]))
        raise


def tile_descriptor(packet):
    """Borrow the trusted frame's bounded stamps; no configuration hashing here."""
    b = scale._bytes(packet)
    if not 256 <= len(b) <= 6400 or b[:4] != b"XYUP" or struct.unpack_from("<I", b, 4)[0] != 1:
        raise ValueError("invalid tile provenance framing")
    handle, epoch, cache, view, count, length = struct.unpack_from("<6Q", b, 16)
    if (
        count > 64
        or length != len(b)
        or len(b) != 256 + 96 * count
        or any(b[8:16])
        or any(b[64:256])
    ):
        raise ValueError("invalid tile provenance planes")
    for at in range(256, len(b), 96):
        present, kind, z, x, y, padding = struct.unpack_from("<6I", b, at + 56)
        start, end = struct.unpack_from("<2q", b, at + 40)
        if (
            present > 1
            or kind > 1
            or z > 25
            or x >= 1 << z
            or y >= 1 << z
            or padding
            or (not present and (start or end))
            or (present and start >= end)
        ):
            raise ValueError("invalid tile provenance key")
    return dict(packet=packet, handle=handle, epoch=epoch, cache=cache, view=view, stamps=b[256:])
