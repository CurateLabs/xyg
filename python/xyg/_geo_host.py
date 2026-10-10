"""Native geographic host transport; numeric planes remain Rust-authored binary.

One adapter admits one mounted browser copy. Release follows browser buffer
teardown, never socket disappearance. Host and remote-browser accounting are
separate (spec/design/geographic-hosts.md).
"""

from __future__ import annotations

import struct
import threading
import weakref
from typing import Any

from ._geo_overview import request as _overview_request
from ._geo_overview_source import (
    GeoOverviewCleanupPending,
    GeoOverviewIndex,
)
from ._geo_overview_source import close_overview_owner as _close_overview_owner
from ._geo_overview_source import (
    is_native_overview_index as _native_overview_index,
)
from ._geo_overview_source import (
    overview_frame_authority as _overview_frame_authority,
)
from ._geo_overview_source import overview_frame_data as _overview_frame_data
from ._geo_overview_source import retain_overview_frame as _retain_overview_frame
from ._geo_overview_source import (
    update_overview_index as _update_overview_index,
)

_HEADER = struct.Struct("<4sIIIQQ")
_LANES = weakref.WeakKeyDictionary()
_LANE_LOCK = threading.Lock()
_OVERVIEW = weakref.WeakKeyDictionary()
_OVERVIEW_DATA = weakref.WeakKeyDictionary()
_OVERVIEW_BUDGET = GeoOverviewIndex.budget.fget


class GeoHostAdapter:
    """Private host-neutral facade used by notebook and Reflex transports."""

    def __init__(self, chart, *, frame=None, selected_scope=None, hierarchy_lane=None):
        overview = chart._overview_layer()
        if overview is not None:
            self._init_overview(chart, overview, frame, selected_scope, hierarchy_lane)
            return
        self._overview_mode = False
        from ._geo_retained import RetainedGeoSource

        layer = chart._retained_layer()
        if (
            layer is None
            or chart.tile_session is not None
            or not isinstance(layer.source, RetainedGeoSource)
            or (frame is None and type(layer.source) is not RetainedGeoSource)
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
        self._anchor = None
        if selected_scope is not None:
            from ._geo_selected import GeoSelectedScope

            if (
                not isinstance(selected_scope, GeoSelectedScope)
                or selected_scope._bridge is not layer.source._bridge
            ):
                raise TypeError("live selected scope requires matching issued transport authority")
        self._selected_scope = selected_scope
        self._hierarchy_lane = None
        self._hierarchy_authority = None
        if frame is not None:
            packet = frame.data.packet
            expected = bytearray(identity)
            actual = bytearray(frame._query_packet)
            actual_operation = struct.unpack_from("<I", actual, 8)[0]
            if actual_operation == 43:
                from ._geo_hierarchy import is_hierarchy_frame

                if not is_hierarchy_frame(frame):
                    raise ValueError("selected hierarchy frame requires private provenance")
            if actual_operation in (35, 36, 43):
                if (
                    len(actual) != 264
                    or struct.unpack_from("<Q", actual, 232)[0] != 8
                    or frame.data.selection is None
                ):
                    raise ValueError("selected frame requires exact issued query framing")
                actual = actual[:256]
                actual[232:240] = bytes(8)
            # Only operation and process-local source handle differ for indexed queries.
            actual[8:12] = expected[8:12]
            actual[16:24] = expected[16:24]
            if (
                frame._source is not layer.source
                or len(packet) < 256
                or packet[24:32] != expected[24:32]
                or packet[80:84] != expected[64:68]
                or packet[84:88] != expected[12:16]
                or packet[88:208] != expected[80:200]
                or packet[208:212] != expected[200:204]
                or packet[212:216] != expected[68:72]
                or packet[216:232] != expected[208:224]
                or bytes(layer.source.info["digest"]) != packet[144:152]
                or struct.pack("<Q", g._uint(layer.source.info["generation"])) != packet[152:160]
                or struct.pack(
                    "<QII",
                    g._uint(layer.source.info["rows"]),
                    g._uint(layer.source.info["geometry"], 32),
                    g._uint(layer.source.info["crs"], 32),
                )
                != packet[232:248]
                or actual != expected
                or frame._style != style
            ):
                raise ValueError("explicit frame does not match this geographic composition")
            if hierarchy_lane is not None:
                from ._geo_hierarchy import hierarchy_lane_authority, is_hierarchy_frame

                authority = hierarchy_lane_authority(hierarchy_lane)
                if (
                    authority is None
                    or authority[0] is not layer.source
                    or authority[1] is not layer.source._bridge
                    or not authority[3]
                    or selected_scope is None
                    or frame.data.selection is None
                    or not is_hierarchy_frame(frame)
                    or actual_operation != 43
                ):
                    raise ValueError("issued selected hierarchy lane must match this frame/source")
                hierarchy_lane._check()
                with _LANE_LOCK:
                    prior = _LANES.get(hierarchy_lane)
                    if prior is not None and prior() is not None:
                        raise RuntimeError("hierarchy lane already belongs to another live adapter")
                    _LANES[hierarchy_lane] = weakref.ref(self)
                self._hierarchy_lane, self._hierarchy_authority = hierarchy_lane, authority
            try:
                self._anchor = frame.retain()
            except BaseException:
                self._release_lane()
                raise
        elif hierarchy_lane is not None:
            raise ValueError("hierarchy live route requires an explicit selected frame")

        from ._geo_live_host import GeoLiveCandidate

        self._live_candidate = GeoLiveCandidate(self)

    def _init_overview(self, chart, layer, frame, selected_scope, hierarchy_lane):
        if selected_scope is not None or hierarchy_lane is not None:
            raise ValueError("Overview hosts do not accept selected or hierarchy authority")
        if not _native_overview_index(layer.source):
            raise ValueError("Overview host requires its genuine native issuing producer")
        query, sequence, identity = chart._overview_inputs(layer)
        time = query["time"]
        query = {
            **query,
            "camera": dict(query["camera"]),
            "time": {
                "kind": time["kind"],
                **(
                    {"instant": time["instant"]}
                    if time["kind"] == 1
                    else {"start": time["start"], "end": time["end"]}
                    if time["kind"] == 2
                    else {}
                ),
            },
            "source_digest": bytes(query["source_digest"]),
        }
        self._source, self._query, self._sequence, self._style = layer.source, query, sequence, b""
        self._budget, self._identity = chart.budget, identity
        self._lock = threading.RLock()
        self._frame = self._painter = self._mount = self._aux = self._anchor = None
        self._closing, self._overview_mode = False, True
        self._selected_scope = self._hierarchy_lane = self._hierarchy_authority = None
        _OVERVIEW[self] = (layer.source, _OVERVIEW_BUDGET(layer.source))
        _OVERVIEW_DATA[self] = weakref.WeakKeyDictionary()
        from ._geo_live_host import GeoLiveCandidate

        self._live_candidate = GeoLiveCandidate(self)
        if frame is not None:
            authority = _overview_frame_authority(frame)
            if (
                authority is None
                or authority[0] is not layer.source
                or authority[1] is not None
                or authority[2] != frame.handle
                or authority[3] != sequence
                or authority[4] != identity
            ):
                raise ValueError("Overview frame differs from its issued composition")
            self._anchor = self._retain_overview(frame)
            try:
                self._validate_overview_frame(self._anchor, query, sequence)
            except Exception:
                try:
                    self._close_owner(self._anchor)
                except Exception as error:
                    raise GeoOverviewCleanupPending(self._anchor) from error
                self._anchor = None
                self._live_candidate.cleanup_frame = None
                raise
            self._live_candidate.cleanup_frame = None

    def _retain_overview(self, frame):
        def issued(copy):
            self._live_candidate.cleanup_operation = copy

        owned = _retain_overview_frame(frame, on_issued=issued)
        # Successful26 now has exact Data authority; preserve it on validation failure.
        self._live_candidate.cleanup_frame = owned
        self._live_candidate.cleanup_operation = None
        return owned

    def _owner_data(self, frame):
        if not self._overview_mode:
            return frame.data
        cache = _OVERVIEW_DATA[self]
        if frame not in cache:
            cache[frame] = _overview_frame_data(frame)
        return cache[frame]

    def _close_owner(self, owner):
        if not self._overview_mode:
            return owner.close()
        _OVERVIEW_DATA[self].pop(owner, None)
        return _close_overview_owner(owner)

    def _overview_source(self):
        authority = _OVERVIEW.get(self)
        source = authority[0] if authority is not None else None
        if source is None or source is not self._source:
            raise ValueError("Overview issuing source changed")
        return source

    def _overview_budget(self):
        return _OVERVIEW[self][1]

    def _validate_overview_frame(self, frame, query, sequence):
        source = _OVERVIEW[self][0]
        authority = _overview_frame_authority(frame)
        expected = _overview_request(
            28, source.handle, sequence, budget=self._overview_budget(), query=query
        )
        if (
            authority is None
            or authority[0] is not source
            or authority[1] is not None
            or authority[2] != frame.handle
            or authority[3] != sequence
            or authority[4] != expected
            or bytes(self._owner_data(frame).packet[:2304]) != authority[5]
        ):
            raise ValueError("Overview private frame authority changed")

    def _prepare_overview(self, query, sequence):
        source = self._overview_source()

        def issued(operation):
            self._live_candidate.cleanup_operation = operation

        try:
            frame = _update_overview_index(source, query, sequence=sequence, on_issued=issued)
            self._live_candidate.cleanup_frame = frame
            self._validate_overview_frame(frame, query, sequence)
            return frame
        finally:
            self._live_candidate._settle_operation()

    def build_payload_split(self, px=None):
        return {"geo_host": True}, []

    def build_payload(self, px=None):
        if self._identity is None:
            raise RuntimeError("geographic host authoring disposed")
        return {"geo_host": True}, self._identity

    def dom_class_strings(self):
        return ()

    def _open(self, mount):
        from . import _native

        if self._closing or self._mount is not None:
            raise RuntimeError("geographic host admits one mount; release it before reopening")
        self._live_candidate.begin_mount()
        source, query, sequence, style = self._source, self._query, self._sequence, self._style
        if source is None:
            raise RuntimeError("geographic host authoring disposed")
        if self._anchor is not None:
            frame = self._anchor
        elif self._overview_mode:
            current = self._overview_source().current
            authority = _overview_frame_authority(current) if current is not None else None
            if (
                authority is not None
                and authority[0] is source
                and authority[3] == sequence
                and authority[4] == self._identity
            ):
                frame = self._retain_overview(current)
            else:
                frame = self._prepare_overview(query, sequence)
        else:
            frame = self._prepare_source(source, query, sequence, style)
        try:
            if self._overview_mode:
                self._validate_overview_frame(frame, query, sequence)
            data = self._owner_data(frame)
            painter = _native.scene_browser_painter(bytes(data.scene), self._budget)
            copies = 3 if self._overview_mode else 2
            processor_bytes = (self._overview_budget() if self._overview_mode else source.budget)[
                "processor_bytes"
            ]
            if len(data.packet) * copies + len(painter) > processor_bytes:
                raise ValueError("native geographic host packet and painter exceed transfer budget")
            outgoing = data.packet.obj
            if not isinstance(outgoing, bytes) or len(outgoing) != len(data.packet):
                raise ValueError("native frame must have exact immutable packet backing")
        except BaseException:
            if self._overview_mode:
                self._anchor = frame
                self._live_candidate.cleanup_frame = None
            elif frame is not self._anchor:
                frame.close()
            raise
        if self._overview_mode:
            self._anchor = frame
            self._live_candidate.cleanup_frame = None
        self._frame, self._painter, self._mount = frame, painter, mount
        return [_HEADER.pack(b"XYGH", 1, 1, 0, frame.handle, sequence), outgoing, painter]

    @staticmethod
    def _prepare_source(source, query, sequence, style):
        from . import _geoscale as g
        from ._geo_retained import _attach_frame

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
        return frame

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
                raw = bytes(raw)
                magic, version, op, reserved, owner, sequence = _HEADER.unpack_from(raw)
                if (
                    magic != b"XYGH"
                    or reserved
                    or (version, op)
                    not in ((1, 1), (1, 2), (1, 3), (1, 4), (1, 5), (2, 6), (2, 7), (2, 8), (2, 9))
                ):
                    raise ValueError("invalid geographic host request header")
                if version == 2:
                    live = self._live_candidate
                    closing_replay = (
                        op == 7
                        and len(raw) == 64
                        and not any(raw[56:64])
                        and live.repeated(7, (owner, sequence, *struct.unpack_from("<3Q", raw, 32)))
                    )
                    if (
                        mount != self._mount
                        or self._frame is None
                        or (
                            self._closing
                            and (
                                (op == 6 and not live.replay_prepare(raw))
                                or (op == 7 and not closing_replay)
                            )
                        )
                    ):
                        raise ValueError("unowned live geographic mount")
                    if op == 8:
                        if len(raw) != 64 or any(raw[56:64]):
                            raise ValueError("invalid retirement ACK")
                        live.acknowledge(owner, sequence, *struct.unpack_from("<3Q", raw, 32))
                        outgoing = []
                    else:
                        receipt = (
                            (owner, sequence, *struct.unpack_from("<3Q", raw, 32))
                            if len(raw) == 64
                            else None
                        )
                        if (
                            op == 9
                            and len(raw) == 64
                            and not any(raw[56:64])
                            and live.repeated(9, receipt)
                        ):
                            return reply, []
                        if op != 7 and (owner != self._frame.handle or sequence != self._sequence):
                            raise ValueError("stale geographic candidate baseline")
                        if self._aux is not None:
                            raise ValueError("release auxiliary before geographic replacement")
                        if op == 6:
                            packet, painter = live.prepare(raw)
                            candidate = live.frame
                            if candidate is None:
                                raise RuntimeError("Missing prepared candidate")
                            nonce = struct.unpack_from("<Q", raw, 32)[0]
                            tag = _HEADER.pack(b"XYGH", 2, op, 0, owner, sequence) + struct.pack(
                                "<3Q8x", nonce, candidate.handle, live.sequence
                            )
                            outgoing = [tag, packet, painter]
                        else:
                            if len(raw) != 64 or any(raw[56:64]):
                                raise ValueError("invalid live geographic acknowledgment")
                            nonce, candidate, candidate_sequence = struct.unpack_from(
                                "<3Q", raw, 32
                            )
                            if op == 7:
                                live.commit(owner, sequence, nonce, candidate, candidate_sequence)
                                outgoing = [
                                    _HEADER.pack(b"XYGH", 2, op, 0, owner, sequence)
                                    + bytes(raw[32:64])
                                ]
                            else:
                                live.abort(owner, sequence, nonce, candidate, candidate_sequence)
                                outgoing = []
                    return reply, outgoing
                if op == 1:
                    if len(raw) != 32 or owner or sequence:
                        raise ValueError("invalid open request")
                    outgoing = self._open(mount)
                else:
                    if mount != self._mount or self._frame is None:
                        raise ValueError("unowned geographic mount")
                    frame = self._frame
                    if sequence != self._owner_data(frame).identity["sequence"]:
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
                            if (
                                len(raw) != 32
                                or self._aux is not None
                                or self._live_candidate.frame is not None
                                or self._live_candidate.cleanup_frame is not None
                                or self._live_candidate.cleanup_operation is not None
                                or self._live_candidate.cleanup_state is not None
                                or self._live_candidate.cleanup_allocation is not None
                            ):
                                raise ValueError("drop auxiliary packets before releasing frame")
                            self._painter = None
                            if frame is not self._anchor:
                                self._close_owner(frame)
                            self._frame = self._mount = None
                            if self._closing:
                                self._release_anchor()
                            outgoing = []
                        elif self._overview_mode:
                            raise ValueError(
                                "Overview has domain counts, not source feature picking/membership"
                            )
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
            except Exception as error:
                return {
                    **reply,
                    "error": str(error),
                    **(
                        {"prepareAbsent": True}
                        if locals().get("version") == 2
                        and locals().get("op") == 6
                        and self._live_candidate.frame is None
                        and self._live_candidate.cleanup_frame is None
                        and self._live_candidate.cleanup_operation is None
                        and self._live_candidate.cleanup_state is None
                        and self._live_candidate.cleanup_allocation is None
                        else {}
                    ),
                }, []

    def close(self):
        """Retire authoring; a mounted immutable frame stays leased until ACK."""
        with self._lock:
            self._closing = True
            self._query = self._identity = self._source = self._style = None
            if not self.mounted:
                self._release_anchor()

    def _release_lane(self):
        lane = self._hierarchy_lane
        if lane is not None:
            with _LANE_LOCK:
                prior = _LANES.get(lane)
                if prior is not None and prior() is self:
                    del _LANES[lane]
            self._hierarchy_lane = self._hierarchy_authority = None

    def _release_anchor(self):
        if self._overview_mode:
            self._live_candidate._settle_operation()
            if self._live_candidate.cleanup_frame is not None:
                self._close_owner(self._live_candidate.cleanup_frame)
                self._live_candidate.cleanup_frame = None
        anchor = self._anchor
        if anchor is not None:
            self._close_owner(anchor)
            self._anchor = None
        self._release_lane()
        if self._closing:
            _OVERVIEW.pop(self, None)
            _OVERVIEW_DATA.pop(self, None)

    @property
    def mounted(self):
        return self._mount is not None
