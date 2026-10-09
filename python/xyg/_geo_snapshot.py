"""Typed native frozen-frame export; Rust owns provenance and rendering policy."""

from __future__ import annotations

import asyncio
import ctypes
import math
import struct
import traceback

from . import _geoscale as g

HEADER = 256
MAX_BYTES = 64 << 20
MAX_BUDGET = 384 << 20
FORMATS = {"svg": 0, "png": 1, "pdf": 2, "jpeg": 3, "webp": 4, "html": 5}


class GeoSnapshotError(RuntimeError):
    def __init__(self, status):
        self.status = status
        self.code = {
            -1: "XYG_GEO_SNAPSHOT_INVALID",
            -9: "XYG_GEO_SNAPSHOT_LIMIT",
            -10: "XYG_GEO_SNAPSHOT_STALE",
            -13: "XYG_GEO_SNAPSHOT_OUTPUT_CAPACITY",
            -15: "XYG_GEO_SNAPSHOT_UNSUPPORTED",
        }.get(status, "XYG_GEO_SNAPSHOT_ERROR")
        super().__init__(self.code)


def request(command, handle, *, sequence=0, budget=0, format="png", scale=1.0, quality=90):
    command = g._uint(command, 32)
    if (
        command not in (1, 2, 3, 4, 5, 6, 20, 21, 22)
        or (command not in (1, 4, 5, 6) and sequence != 0)
        or (command not in (1, 2, 4, 5, 6) and budget != 0)
    ):
        raise ValueError("field does not belong to snapshot command")
    if command == 2 and (isinstance(scale, bool) or not isinstance(scale, (int, float))):
        raise TypeError("expected numeric f64 scale")
    b = bytearray(HEADER)
    struct.pack_into("<4sII", b, 0, b"XYGJ", 1, command)
    struct.pack_into("<QQQ", b, 16, g._uint(handle), g._uint(sequence), g._uint(budget))
    if command == 2:
        struct.pack_into("<IId", b, 40, FORMATS[format], g._uint(quality, 32), scale)
    return bytes(b)


def reply(packet):
    b = g._bytes(packet)
    if (
        len(b) != HEADER
        or bytes(b[:4]) != b"XYGW"
        or struct.unpack_from("<I", b, 4)[0] != 1
        or any(b[12:16])
        or any(b[64:])
    ):
        raise ValueError("invalid frozen export reply")
    kind = struct.unpack_from("<I", b, 8)[0]
    handle, sequence, length, companion = struct.unpack_from("<4Q", b, 16)
    if (
        kind > 1
        or handle == 0
        or length > MAX_BYTES
        or companion > 32 << 20
        or (kind == 0 and (companion or any(b[48:64])))
    ):
        raise ValueError("invalid frozen export planes")
    if kind == 1:
        format, quality, scale = struct.unpack_from("<IId", b, 48)
        if format > 5 or not 1 <= quality <= 100 or not math.isfinite(scale) or scale <= 0:
            raise ValueError("invalid typed artifact reply")
    return dict(handle=handle, sequence=sequence, length=length, companion=companion, kind=kind)


def execute(packet):
    from . import _native

    if not isinstance(packet, bytes) or len(packet) != HEADER:
        raise ValueError("snapshot command must have 256 bytes")
    source, out = ctypes.create_string_buffer(packet), ctypes.create_string_buffer(HEADER)
    status = _native._lib.xyg_geo_snapshot_execute(source, HEADER, out, HEADER)
    if status:
        raise GeoSnapshotError(status)
    return out.raw


def read(packet, budget):
    from . import _native

    if not isinstance(packet, bytes) or len(packet) != HEADER or not HEADER <= budget <= MAX_BUDGET:
        raise ValueError("invalid snapshot read framing")
    source, length = ctypes.create_string_buffer(packet), ctypes.c_size_t()
    fn = _native._lib.xyg_geo_snapshot_read
    status = fn(source, HEADER, budget, None, 0, ctypes.byref(length))
    if status:
        raise GeoSnapshotError(status)
    if length.value > MAX_BYTES or 4 * length.value + HEADER > budget:
        raise GeoSnapshotError(-9)
    out = ctypes.create_string_buffer(length.value)
    status = fn(source, HEADER, budget, out, len(out), ctypes.byref(length))
    if status:
        raise GeoSnapshotError(status)
    if length.value != len(out):
        raise ValueError("snapshot read length changed")
    return out.raw


class NativeSnapshotBridge:
    def __init__(self, budget):
        self.budget = budget

    async def execute(self, packet):
        return execute(packet)

    async def read(self, packet):
        return read(packet, self.budget)


class OwnedGeoArtifact:
    """Drop all exported bytes/snapshot views before releasing this lease."""

    def __init__(self, handle, data, snapshot, format, bridge=None):
        self.handle, self.format = handle, format
        self._bytes, self._snapshot, self._bridge = data, snapshot, bridge
        self._closed, self._disposal = False, None

    @property
    def bytes(self):
        if self._closed or self._bytes is None:
            raise RuntimeError("geographic artifact disposed")
        return self._bytes

    @property
    def snapshot(self):
        if self._closed or self._snapshot is None:
            raise RuntimeError("geographic artifact disposed")
        return self._snapshot

    def close(self):
        if self._bridge is not None:
            raise RuntimeError("use aclose for an asynchronous artifact")
        if not self._closed:
            self._bytes = self._snapshot = None
            execute(request(3, self.handle))
            self._closed = True

    async def aclose(self):
        if self._bridge is None:
            self.close()
        elif not self._closed:
            self._bytes = self._snapshot = None
            if self._disposal is None:
                self._disposal = asyncio.create_task(self._bridge.execute(request(3, self.handle)))
            _, interrupted = await g._settle(self._disposal)
            self._closed = True
            if interrupted:
                raise asyncio.CancelledError

    async def dispose(self):
        await self.aclose()


def export_frame(frame, sequence, format="png", *, scale=1.0, quality=90, budget=MAX_BUDGET):
    _ = frame.data
    if frame._bridge is not None:
        raise RuntimeError("use export_async for an asynchronous frame")
    if (
        not isinstance(budget, int)
        or isinstance(budget, bool)
        or not HEADER <= budget <= MAX_BUDGET
    ):
        raise ValueError("invalid frozen export budget")
    frozen = artifact = owner = None
    data = companion = None
    try:
        fixed = reply(
            execute(
                request(
                    getattr(frame, "_freeze_command", 1),
                    frame.handle,
                    sequence=sequence,
                    budget=min(budget, 128 << 20),
                )
            )
        )
        frozen = fixed["handle"]
        if fixed["kind"] != 0 or fixed["sequence"] != sequence:
            raise ValueError("mismatched frozen frame identity")
        result = reply(
            execute(request(2, frozen, budget=budget, format=format, scale=scale, quality=quality))
        )
        artifact = result["handle"]
        if result["kind"] != 1 or result["sequence"] != sequence:
            raise ValueError("mismatched artifact identity")
        data, companion = read(request(22, artifact), budget), read(request(21, artifact), budget)
        if len(data) != result["length"] or len(companion) != result["companion"]:
            raise ValueError("mismatched frozen export lengths")
        owner = OwnedGeoArtifact(artifact, data, companion, format)
        artifact = None
        return owner
    except BaseException as error:
        data = companion = None
        traceback.clear_frames(error.__traceback__)
        raise
    finally:
        try:
            if artifact is not None:
                execute(request(3, artifact))
            if frozen is not None:
                execute(request(3, frozen))
        except BaseException:
            if owner is not None:
                owner.close()
            raise


async def export_frame_async(
    frame, sequence, format="png", *, scale=1.0, quality=90, budget=MAX_BUDGET, bridge=None
):
    _ = frame.data
    if (
        not isinstance(budget, int)
        or isinstance(budget, bool)
        or not HEADER <= budget <= MAX_BUDGET
    ):
        raise ValueError("invalid frozen export budget")
    if bridge is None:
        if frame._bridge is not None and not isinstance(frame._bridge, g.NativeGeoScaleBridge):
            raise ValueError("remote frame requires its matching snapshot bridge")
        bridge = NativeSnapshotBridge(budget)
    frozen = artifact = owner = None
    data = companion = None
    interrupted = False

    async def settled(awaitable):
        nonlocal interrupted
        value, cancelled = await g._settle(asyncio.create_task(awaitable))
        interrupted |= cancelled
        return value

    try:
        fixed = reply(
            await settled(
                bridge.execute(
                    request(
                        getattr(frame, "_freeze_command", 1),
                        frame.handle,
                        sequence=sequence,
                        budget=min(budget, 128 << 20),
                    )
                )
            )
        )
        frozen = fixed["handle"]
        if fixed["kind"] != 0 or fixed["sequence"] != sequence:
            raise ValueError("mismatched frozen frame identity")
        if interrupted:
            raise asyncio.CancelledError
        result = reply(
            await settled(
                bridge.execute(
                    request(2, frozen, budget=budget, format=format, scale=scale, quality=quality)
                )
            )
        )
        artifact = result["handle"]
        if result["kind"] != 1 or result["sequence"] != sequence:
            raise ValueError("mismatched artifact identity")
        if interrupted:
            raise asyncio.CancelledError
        data = await settled(bridge.read(request(22, artifact)))
        if interrupted:
            raise asyncio.CancelledError
        companion = await settled(bridge.read(request(21, artifact)))
        if interrupted:
            raise asyncio.CancelledError
        if len(data) != result["length"] or len(companion) != result["companion"]:
            raise ValueError("mismatched frozen export lengths")
        owner = OwnedGeoArtifact(artifact, data, companion, format, bridge)
        artifact = None
    except BaseException as error:
        data = companion = None
        traceback.clear_frames(error.__traceback__)
        raise
    finally:
        try:
            if artifact is not None:
                await settled(bridge.execute(request(3, artifact)))
            if frozen is not None:
                await settled(bridge.execute(request(3, frozen)))
        except BaseException:
            if owner is not None:
                await owner.aclose()
            raise
        if interrupted and owner is not None:
            await owner.aclose()
            raise asyncio.CancelledError
    return owner
