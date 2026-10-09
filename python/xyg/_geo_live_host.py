"""XYGH v2 candidate ownership; camera and selected policy remain Rust-owned.

Dossier §27/§29/§34. A process admits one staged replacement until retirement
ACK. Remote renderer storage remains outside the native engine ledger.
"""

from __future__ import annotations

import struct
import threading

from . import _geoscale as g
from . import _geoviewport as viewport
from ._geo_retained import _attach_frame

_SLOT = threading.Lock()


class GeoLiveCandidate:
    """Private per-adapter candidate and retired owner, never caller paint."""

    def __init__(self, adapter):
        self.adapter = adapter
        self.nonce = 0
        self.frame = self.retired = None
        self.cleanup_frame = None
        self.cleanup_operation = None
        self.cleanup_state = None
        self.cleanup_allocation = None
        self.query = None
        self._owns_slot = False
        self.committed = False
        self.receipts = {}

    def begin_mount(self):
        if (
            self.frame is not None
            or self.retired is not None
            or self.cleanup_frame is not None
            or self.cleanup_operation is not None
            or self.cleanup_state is not None
            or self.cleanup_allocation is not None
        ):
            raise RuntimeError("Outstanding geographic candidate")
        self.nonce = 0
        self.receipts.clear()

    def _release_slot(self):
        if self._owns_slot:
            self._owns_slot = False
            _SLOT.release()

    def replay_prepare(self, raw):
        return (
            (self.frame is not None and not self.committed)
            or self.cleanup_frame is not None
            or self.cleanup_operation is not None
            or self.cleanup_state is not None
            or self.cleanup_allocation is not None
        ) and getattr(self, "prepare_request", None) == bytes(raw)

    def prepare(self, raw):
        if (
            self.cleanup_frame is not None
            or self.cleanup_operation is not None
            or self.cleanup_state is not None
            or self.cleanup_allocation is not None
        ):
            if not self.replay_prepare(raw):
                raise RuntimeError("Candidate cleanup requires exact preparation retry")
            self._settle_operation()
            if self.cleanup_frame is not None:
                self.cleanup_frame.close()
                self.cleanup_frame = None
            self._release_slot()
            raise RuntimeError("Geographic preparation cancelled")
        if self.replay_prepare(raw):
            frame = self.frame
            if frame is None:
                raise RuntimeError("Missing prepared candidate")
            return frame.data.packet.obj, self.painter
        a = self.adapter
        from ._geo_hierarchy import is_hierarchy_frame

        if is_hierarchy_frame(a._frame) and a._hierarchy_lane is None:
            raise RuntimeError("Hierarchy live updates require an explicit hierarchy route")
        if len(raw) != 256 or any(raw[76:80]) or any(raw[224:256]):
            raise ValueError("invalid live prepare framing")
        nonce, sequence, camera_rev, time_rev, state_rev = struct.unpack_from("<5Q", raw, 32)
        time_kind = struct.unpack_from("<I", raw, 72)[0]
        start, end = struct.unpack_from("<2q", raw, 80)
        if not nonce or nonce <= self.nonce or self.frame is not None or self.retired is not None:
            raise ValueError("stale or outstanding geographic candidate")
        if (
            sequence <= a._sequence
            or camera_rev < a._query["camera_revision"]
            or time_rev < a._query["time_revision"]
            or state_rev != a._query["state_revision"]
        ):
            raise ValueError("stale geographic desired snapshot")
        if (
            time_kind not in (0, 1, 2)
            or (time_kind == 0 and (start or end))
            or (time_kind == 1 and end)
        ):
            raise ValueError("invalid signed time framing")
        camera_request = bytes(raw[96:224])
        operation = struct.unpack_from("<I", camera_request, 8)[0]
        if (
            operation > 9
            or camera_request[:8] != b"XYVC\x01\0\0\0"
            or any(camera_request[20:24])
            or any(camera_request[120:128])
        ):
            raise ValueError("invalid camera delta framing")
        accepted_camera = a._frame.data.identity["camera"]
        baseline = viewport.encode_request(accepted_camera, operation)
        if camera_request[:8] != baseline[:8] or camera_request[12:80] != baseline[12:80]:
            raise ValueError("camera delta does not name accepted camera")
        if not _SLOT.acquire(blocking=False):
            raise RuntimeError("another geographic replacement awaits retirement ACK")
        self._owns_slot = True
        self.prepare_request = bytes(raw)
        frame = None
        try:
            camera = viewport.decode_response(viewport.execute(camera_request, 1 << 20))["camera"]
            query = {
                **a._query,
                "camera": camera,
                "camera_revision": camera_rev,
                "time_revision": time_rev,
                "state_revision": state_rev,
                "time": {
                    "kind": time_kind,
                    **(
                        {"instant": start}
                        if time_kind == 1
                        else {"start": start, "end": end}
                        if time_kind == 2
                        else {}
                    ),
                },
            }
            if camera != accepted_camera and camera_rev == a._query["camera_revision"]:
                raise ValueError("camera change requires new revision")
            if query["time"] != a._query["time"] and time_rev == a._query["time_revision"]:
                raise ValueError("time change requires new revision")
            source = a._source
            frame = self._build(source, query, sequence, a._style)
            self.cleanup_frame = None
            from . import _native

            painter = _native.scene_browser_painter(bytes(frame.data.scene), a._budget)
            if 2 * len(frame.data.packet) + len(painter) > source.budget["processor_bytes"]:
                raise ValueError("candidate exceeds geographic transfer ceiling")
            packet = frame.data.packet.obj
            if not isinstance(packet, bytes) or len(packet) != len(frame.data.packet):
                raise ValueError("candidate requires exact immutable packet backing")
            self.frame, self.query, self.painter = frame, query, painter
            self.nonce, self.sequence, self.committed = nonce, sequence, False
            self.prepare_request = bytes(raw)
            self.old_owner, self.old_sequence = a._frame.handle, a._sequence
            return packet, painter
        except BaseException:
            self._settle_operation()
            if frame is not None:
                self.cleanup_frame = frame
            if self.cleanup_frame is not None:
                self.cleanup_frame.close()
                self.cleanup_frame = None
            self._release_slot()
            raise

    def _allocate_state(self, scope, query, selection, budget):
        self.cleanup_allocation = scope.begin_state(
            revision=query["state_revision"],
            ids=selection["ids"],
            fill=selection["fill"],
            budget=budget,
        )
        state = self.cleanup_allocation.recover()
        self.cleanup_state = state
        return state

    def _settle_operation(self):
        if self.cleanup_operation is not None:
            self.cleanup_operation.close()
            self.cleanup_operation = None
        if self.cleanup_allocation is not None:
            self.cleanup_allocation.close()
            self.cleanup_allocation = None
        if self.cleanup_state is not None:
            self.cleanup_state.close()
            self.cleanup_state = None

    def _build_hierarchy(self, lane, query, sequence, style):
        from ._geo_hierarchy import hierarchy_lane_authority

        if hierarchy_lane_authority(lane) != self.adapter._hierarchy_authority:
            raise ValueError("hierarchy lane authority changed")
        lane._check()
        generation = lane.cancel_generation
        selection = self.adapter._frame.data.selection
        state = self._allocate_state(self.adapter._selected_scope, query, selection, lane.budget)
        operation = None
        try:
            if lane._closed or generation != lane.cancel_generation:
                raise RuntimeError("Geographic preparation cancelled")
            operation = lane.begin_selected(state, query, sequence=sequence)
            self.cleanup_operation = operation
            operation.drive()
            frame = operation.prepare(style)
            self.cleanup_frame = frame
            if lane._closed or generation != lane.cancel_generation:
                frame.close()
                self.cleanup_frame = None
                raise RuntimeError("Geographic preparation cancelled")
            return frame
        finally:
            self.cleanup_operation = operation or lane.pending_operation
            # Successful44 owns Data and its operation is closed. An uncertain
            # 43/44 attempt owns its exact cleanup guard until disposal confirms.
            self._settle_operation()

    def _build(self, source, query, sequence, style):
        if self.adapter._hierarchy_lane is not None:
            return self._build_hierarchy(self.adapter._hierarchy_lane, query, sequence, style)
        from ._geo_spatial import GeoSpatialFullScanRequired, GeoSpatialIndex, drive_index

        generation = source._cancel_generation
        selection = self.adapter._frame.data.selection
        if selection is not None:
            scope = self.adapter._selected_scope
            if scope is None:
                raise ValueError("selected live frames require an explicit selected scope")
            state = self._allocate_state(scope, query, selection, source.budget)
            operation = None
            try:
                operation = state.begin(
                    source, query, sequence=sequence, indexed=isinstance(source, GeoSpatialIndex)
                )
                if isinstance(operation, dict):
                    raise GeoSpatialFullScanRequired(operation["reason"])
                if operation.indexed:
                    self.cleanup_operation = operation
                operation.drive()
                frame = operation.prepare(style)
                self.cleanup_frame = frame
                if source._closed or generation != source._cancel_generation:
                    self.cleanup_frame = frame
                    frame.close()
                    self.cleanup_frame = None
                    raise RuntimeError("Geographic preparation cancelled")
                return frame
            finally:
                self._settle_operation()
        source._check()
        indexed = isinstance(source, GeoSpatialIndex)
        request = g.encode_request(
            dict(
                command=18 if indexed else 5,
                handle=source.handle,
                sequence=sequence,
                budget=source.budget,
                query=query,
            )
        )
        handle = source.handle
        source._busy = True
        try:
            reply = g.decode_reply(g.execute(request))
            if reply["code"] == 10:
                raise GeoSpatialFullScanRequired(reply["fallback_reason_code"])
            handle = reply["handle"]
            source._sequence = sequence
            if indexed:
                drive_index(
                    handle,
                    sequence,
                    source.budget,
                    source._reader,
                    source._read_page,
                    source._write_page,
                )
            else:
                source._drive(sequence, 4)

            frame = source._prepare(19 if indexed else 11, handle, sequence, style)
            self.cleanup_frame = frame
            if source._closed or generation != source._cancel_generation:
                self.cleanup_frame = frame
                frame.close()
                self.cleanup_frame = None
                raise RuntimeError("Geographic preparation cancelled")
            _attach_frame(source, frame, sequence, request, style)
            return frame
        finally:
            source._busy = False
            if indexed and handle != source.handle:
                g.execute(g.encode_request(dict(command=10, handle=handle)))

    def repeated(self, op, receipt):
        return op in self.receipts and self.receipts[op] == receipt

    def commit(self, old_owner, old_sequence, nonce, owner, sequence):
        a = self.adapter
        receipt = (old_owner, old_sequence, nonce, owner, sequence)
        if self.repeated(7, receipt) and (a._frame.handle, a._sequence) == (owner, sequence):
            return
        if (old_owner, old_sequence) != (a._frame.handle, a._sequence):
            raise ValueError("stale geographic commit baseline")
        if (
            self.committed
            or self.frame is None
            or (nonce, owner, sequence) != (self.nonce, self.frame.handle, self.sequence)
        ):
            raise ValueError("unowned geographic commit")
        if a._aux is not None:
            raise ValueError("release geographic auxiliary before commit")
        self.retired = a._frame
        self.retired_sequence = a._sequence
        a._frame, a._painter, a._query, a._sequence = (
            self.frame,
            self.painter,
            self.query,
            self.sequence,
        )
        self.committed = True
        self.receipts[7] = receipt

    def acknowledge(self, old_owner, old_sequence, nonce, new_owner, new_sequence):
        a = self.adapter
        receipt = (old_owner, old_sequence, nonce, new_owner, new_sequence)
        if self.repeated(8, receipt):
            return
        if (
            not self.committed
            or self.retired is None
            or self.frame is None
            or (old_owner, old_sequence, nonce, new_owner, new_sequence)
            != (
                self.retired.handle,
                self.retired_sequence,
                self.nonce,
                self.frame.handle,
                self.sequence,
            )
        ):
            raise ValueError("unowned geographic retirement ACK")
        retired = self.retired
        retired.close()
        a._anchor = self.frame
        self.receipts[8] = receipt
        self.retired = self.frame = self.query = self.painter = None
        self._release_slot()

    def abort(self, old_owner, old_sequence, nonce, owner, sequence):
        receipt = (old_owner, old_sequence, nonce, owner, sequence)
        if self.repeated(9, receipt):
            return
        if (old_owner, old_sequence) != (self.old_owner, self.old_sequence):
            raise ValueError("stale candidate abort baseline")
        if (
            self.committed
            or self.frame is None
            or (nonce, owner, sequence) != (self.nonce, self.frame.handle, self.sequence)
        ):
            raise ValueError("unowned geographic candidate abort ACK")
        self.frame.close()
        self.receipts[9] = receipt
        self.frame = self.query = self.painter = None
        self._release_slot()
