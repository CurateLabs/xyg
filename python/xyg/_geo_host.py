"""Native geographic host transport; numeric planes remain Rust-authored binary.

One adapter admits one mounted browser copy. Release follows browser buffer
teardown, never socket disappearance. Host and remote-browser accounting are
separate (spec/design/geographic-hosts.md).
"""

from __future__ import annotations

import struct
import threading
from typing import Any

_HEADER = struct.Struct("<4sIIIQQ")


class GeoHostAdapter:
    """Private host-neutral facade used by notebook and Reflex transports."""

    def __init__(self, chart):
        from ._geo_retained import RetainedGeoSource

        layer = chart._retained_layer()
        if (
            layer is None
            or chart.tile_session is not None
            or not isinstance(layer.source, RetainedGeoSource)
        ):
            raise ValueError(
                "live native hosts require one canonical RetainedGeoSource; indexed hosts are pending"
            )
        if layer.source._bridge is not None:
            raise ValueError("live native hosts currently require a synchronous native reader")
        from . import _geoscale as g

        query, sequence, style = chart._retained_inputs(layer)
        query = {
            **query,
            "camera": dict(query["camera"]),
            "time": dict(query["time"]),
            "source_digest": bytes(query["source_digest"]),
        }
        self._source, self._query, self._sequence, self._style = (
            layer.source,
            query,
            sequence,
            style,
        )
        self._budget = chart.budget
        identity = bytearray(
            g.encode_request(
                dict(command=5, sequence=sequence, budget=layer.source.budget, query=query)
            )
        )
        self._identity = bytes(identity) + style
        self._lock = threading.RLock()
        self._frame = None
        self._painter = None
        self._mount = None
        self._aux = None
        self._closing = False

    def build_payload_split(self, px=None):
        return {"geo_host": True}, []

    def build_payload(self, px=None):
        if self._identity is None:
            raise RuntimeError("geographic host authoring disposed")
        return {"geo_host": True}, self._identity

    def dom_class_strings(self):
        return ()

    def _open(self, mount):
        from . import _geoscale as g
        from . import _native
        from ._geo_retained import _attach_frame

        if self._closing or self._mount is not None:
            raise RuntimeError("geographic host admits one mount; release it before reopening")
        source, query, sequence, style = self._source, self._query, self._sequence, self._style
        if source is None:
            raise RuntimeError("geographic host authoring disposed")
        packet = g.encode_request(
            dict(
                command=5,
                handle=source.handle,
                sequence=sequence,
                budget=source.budget,
                query=query,
            )
        )
        current = source.current
        if current is not None and source._sequence == sequence:
            if current._query_packet != packet or current._style != style:
                raise ValueError("published query does not match this geographic composition")
            frame = source._prepare(11, source.handle, sequence, style)
            _attach_frame(source, frame, sequence, packet, style)
        else:
            frame = source.update(query, sequence=sequence, style=style)
        try:
            painter = _native.scene_browser_painter(bytes(frame.data.scene), self._budget)
            if len(frame.data.packet) * 2 + len(painter) > source.budget["processor_bytes"]:
                raise ValueError("native geographic host packet and painter exceed transfer budget")
            # One frontend packet copy. The native frame owns the first read.
            outgoing = frame.data.packet.obj
            if not isinstance(outgoing, bytes) or len(outgoing) != len(frame.data.packet):
                raise ValueError("native frame must have exact immutable packet backing")
        except BaseException:
            frame.close()
            raise
        self._frame, self._painter, self._mount = frame, painter, mount
        return [_HEADER.pack(b"XYGH", 1, 1, 0, frame.handle, sequence), outgoing, painter]

    def handle_host_message(self, content: Any, buffers=None):
        if not isinstance(content, dict) or content.get("type") != "geo_host":
            return None
        request, mount = content.get("request"), content.get("mount")
        if not isinstance(request, str) or not 1 <= len(request) <= 96:
            return None
        reply = {"type": "geo_host", "request": request}
        with self._lock:
            try:
                if not isinstance(mount, str) or not 1 <= len(mount) <= 96:
                    raise ValueError("invalid mount identity")
                incoming = list(buffers or ())
                if not incoming and isinstance(
                    content.get("buffer"), (bytes, bytearray, memoryview)
                ):
                    incoming = [content["buffer"]]
                if len(incoming) != 1:
                    raise ValueError("one binary request attachment required")
                raw = memoryview(incoming[0]).cast("B")
                if len(raw) < _HEADER.size or len(raw) > 256:
                    raise ValueError("invalid geographic host request length")
                magic, version, op, reserved, owner, sequence = _HEADER.unpack_from(raw)
                if magic != b"XYGH" or version != 1 or reserved or op not in (1, 2, 3, 4, 5):
                    raise ValueError("invalid geographic host request header")
                if op == 1:
                    if len(raw) != 32 or owner or sequence:
                        raise ValueError("invalid open request")
                    outgoing = self._open(mount)
                else:
                    if mount != self._mount or self._frame is None:
                        raise ValueError("unowned geographic mount")
                    frame = self._frame
                    if sequence != frame.data.identity["sequence"]:
                        raise ValueError("stale geographic frame")
                    if op == 5:
                        if len(raw) != 32 or self._aux is None or owner != self._aux.handle:
                            raise ValueError("unowned auxiliary release")
                        self._aux.close()
                        self._aux = None
                        outgoing = []
                    else:
                        if owner != frame.handle:
                            raise ValueError("unowned geographic frame")
                        if op == 4:
                            if len(raw) != 32 or self._aux is not None:
                                raise ValueError("drop auxiliary packets before releasing frame")
                            self._painter = None
                            frame.close()
                            self._frame = self._mount = None
                            outgoing = []
                        elif op == 2:
                            if len(raw) != 64 or self._aux is not None:
                                raise ValueError("invalid or concurrent pick request")
                            x, y, tolerance, mode, max_hits = struct.unpack_from("<3dII", raw, 32)
                            aux = frame.pick(
                                style=frame._style,
                                x=x,
                                y=y,
                                tolerance=tolerance,
                                mode=mode,
                                max_hits=max_hits,
                            )
                            self._aux = aux
                            outgoing = [
                                _HEADER.pack(b"XYGH", 1, op, 0, aux.handle, sequence),
                                aux.data["packet"].obj,
                            ]
                        else:
                            if len(raw) not in (48, 256) or self._aux is not None:
                                raise ValueError("invalid or concurrent membership request")
                            cell, has_cursor, budget = struct.unpack_from("<IIQ", raw, 32)
                            if budget > struct.unpack_from("<Q", frame._query_packet, 224)[0]:
                                raise ValueError("membership exceeds committed frame work bound")
                            if has_cursor != (len(raw) == 256):
                                raise ValueError("invalid membership cursor framing")
                            aux = frame.membership(
                                cell,
                                max_projected_vertices=budget,
                                cursor=bytes(raw[48:]) if has_cursor else None,
                            )
                            self._aux = aux
                            outgoing = [
                                _HEADER.pack(b"XYGH", 1, op, 0, aux.handle, sequence),
                                aux.data["packet"].obj,
                            ]
                return reply, outgoing
            except (ValueError, TypeError, RuntimeError, OverflowError) as error:
                return {**reply, "error": str(error)}, []

    def close(self):
        """Retire authoring; a mounted immutable frame stays leased until ACK."""
        with self._lock:
            self._closing = True
            self._query = self._identity = self._source = self._style = None

    @property
    def mounted(self):
        return self._mount is not None
