"""Notebook identity transport over the existing Rust session projection.

The session's painter output is deliberately unused: Figure remains the renderer.
Source/render joins below copy the original compiler's Rust membership planes.
"""

from __future__ import annotations

import hashlib
import heapq
import secrets
import struct
import uuid
import weakref

import numpy as np

from ._graph_session import GraphSession, GraphSessionError, GraphSessionStatus
from ._graphforge_container import DTYPE as D
from ._graphforge_container import decode_container, encode_container

_BATCH_SIZE = 1000  # Transport batch; Rust's unchanged selection cap remains authoritative.


class NotebookGraphIdentity:
    def __init__(self, composition, meta, figure, x, y, *, prepare=True):
        self.composition = composition
        self.meta = meta
        self.figure = weakref.proxy(figure)
        self.instance = secrets.randbits(63) or 1
        self.sequence = 1
        self.revision = 0
        self.session = None
        self._error = None
        self._closed = False
        self._positions = x, y
        self._node_sources = None
        self._shared_node_rows = set()
        if prepare:
            self.prepare()

    def prepare(self):
        if self._closed:
            raise GraphSessionError("notebook graph identity is closed")
        if self._error is not None:
            raise GraphSessionError("notebook graph identity resource limit", status=self._error)
        if self.session is not None:
            return self.session
        x, y = self._positions
        opening = self._request(
            19,
            [
                ("document.bytes", 0, D.BYTES, self.composition.bytes),
                ("load.x.f64", 0, D.F64, x),
                ("load.y.f64", 0, D.F64, y),
            ],
        )
        try:
            self.session = GraphSession(
                self.composition.bytes, opening, instance_id=self.instance, group_id=0
            )
        except GraphSessionError as error:
            if error.status == GraphSessionStatus.BUDGET:
                self._error = error.status
            raise
        weakref.finalize(self, self.session.close)
        return self.session

    def close(self):
        self._closed = True
        if self.session is not None:
            self.session.close()

    def row_space(self):
        """Opaque transport equality stamp; every input is a compiler fact.

        No coordinates, style decisions or host-derived edge membership enter
        this stamp. It only prevents cached row masks crossing different
        ordered source identities or native membership/route planes.
        """
        digest = hashlib.sha256(b"XYG notebook graph rows v1")
        digest.update(struct.pack("<qq", self.meta["node_trace"], self.meta["edge_trace"]))
        for values in (self.meta["ids"], self.meta.get("source_edge_ids", ())):
            digest.update(struct.pack("<Q", len(values)))
            for value in values:
                if value is None:
                    digest.update(b"\x00")
                else:
                    encoded = value.encode("utf-8")
                    digest.update(b"\x01" + struct.pack("<Q", len(encoded)))
                    digest.update(encoded)
        edges = self.figure._graph_edge_identity[self.meta["edge_trace"]]
        for values in (
            self.meta["member_of"],
            edges.render_edge_index,
            edges.offsets,
            edges.members,
        ):
            array = np.ascontiguousarray(values, dtype="<u8")
            digest.update(struct.pack("<Q", array.size))
            digest.update(memoryview(array).cast("B"))
        for trace in (self.meta["node_trace"], self.meta["edge_trace"]):
            values = self.figure.traces[trace].shipped_sel
            digest.update(b"\x00" if values is None else b"\x01")
            if values is not None:
                array = np.ascontiguousarray(values, dtype="<u8")
                digest.update(struct.pack("<Q", array.size))
                digest.update(memoryview(array).cast("B"))
        return digest.hexdigest()

    def _request(self, operation, extra=(), *, policy=0):
        sequence = self.sequence
        self.sequence += 1
        return encode_container(
            "XYGI",
            [
                ("header.u64", 0, D.U64, [self.instance, 0, sequence]),
                ("header.u32", 0, D.U32, [self.revision, operation, 0, policy, 0, 0, 0, 0, 0]),
                *extra,
            ],
        )

    def _decode(self, payload):
        result = decode_container(payload, "XYGR")
        self.revision = int(result["header.u32", 0][0])
        refs = result["selection.refs.bytes", 0]
        count = struct.unpack_from("<I", refs)[0]
        offsets = result["selection.layer_offsets.u64", 0]
        layers = result["selection.layers.u32", 0]
        rows = result["selection.rows.u64", 0]
        names = result["selection.result_ids.texts", 0]
        valid = result["selection.result_ids.valid.u8", 0]
        out = []
        for i in range(count):
            start = 8 + 56 * i
            kind = struct.unpack_from("<I", refs, start)[0]
            # Merge keys copy Rust's emitted ElementSet order, not source rows.
            # Derived pool offsets are local to a reply: use their exact bytes.
            if kind < 2:
                key = (kind, refs[start + 8 : start + 24])
            elif kind == 2:
                offset, length = struct.unpack_from("<II", refs, start + 48)
                pool = 8 + 56 * count
                key = (
                    kind,
                    offset != 0xFFFFFFFF,
                    refs[pool + offset : pool + offset + length] if offset != 0xFFFFFFFF else b"",
                    struct.unpack_from("<I", refs, start + 24)[0],
                    *struct.unpack_from("<QQ", refs, start + 32),
                )
            else:
                raise GraphSessionError("unsupported notebook identity reference")
            out.append(
                (
                    key,
                    {
                        "kind": "node" if kind == 0 else "edge",
                        "uuid": str(uuid.UUID(bytes=refs[start + 8 : start + 24]))
                        if kind < 2
                        else None,
                        "index": int(result["selection.indices.u64", 0][i]),
                        "layers": [
                            {
                                "layer": int(layers[j]),
                                "result_id": names[int(layers[j])]
                                if valid[int(layers[j])]
                                else None,
                                "row": int(rows[j]),
                            }
                            for j in range(int(offsets[i]), int(offsets[i + 1]))
                        ],
                    },
                )
            )
        return out

    @staticmethod
    def _merge(batches):
        # Each reply is already canonically ordered by Rust. Merge transport
        # runs and remove repeated references without re-resolving identities.
        out, previous = [], None
        for key, row in heapq.merge(*batches, key=lambda item: item[0]):
            if key != previous:
                out.append(row)
                previous = key
        return out

    def select(self, uuids):
        # Validate the complete caller input before issuing any native request.
        values = [uuid.UUID(value).bytes for value in uuids]
        if not values:
            return []
        session = self.prepare()
        # This is one user intent, not metadata lookup: the native aggregate
        # cap must admit the complete UUID set before any highlight is sent.
        data = b"".join(values)
        return self._merge(
            [self._decode(session.interact(self._request(10, [("uuids.uuid", 0, D.UUID, data)])))]
        )

    def source_rows(self, trace, index):
        m = self.meta
        if m["tier_name"] == "aggregate":
            return []  # aggregate membership is not an individual identity
        if trace == m["node_trace"]:
            source = self._index_node_rows().get(index)
            return [] if source is None else [("node", source)]
        if trace == m["edge_trace"]:
            identity = self.figure._graph_edge_identity[trace]
            if 0 <= index < len(identity.render_edge_index):
                return [
                    ("edge", int(i))
                    for i in identity.members_of(int(identity.render_edge_index[index]))
                ]
        return []

    def _index_node_rows(self) -> dict[int, int]:
        if self._node_sources is not None:
            return self._node_sources
        self._node_sources = {}
        for source, render in enumerate(self.meta["member_of"]):
            render = int(render)
            if render in self._node_sources:
                self._shared_node_rows.add(render)
            else:
                self._node_sources[render] = source
        return self._node_sources

    def project(self, per_trace):
        sources = sorted(
            {
                item
                for trace, indices in per_trace.items()
                for index in indices
                for item in self.source_rows(trace, int(index))
            },
            key=lambda item: (item[0] == "edge", item[1]),
        )
        if not sources:
            return []
        session = self.prepare()
        return self._merge(
            self._project_batch(session, sources[start : start + _BATCH_SIZE])
            for start in range(0, len(sources), _BATCH_SIZE)
        )

    def _project_batch(self, session, sources):
        # Encode canonical refs; only Rust resolves identity and provenance.
        records, pool = [], bytearray()
        for kind, index in sources:
            side = self.composition.nodes if kind == "node" else self.composition.edges
            value = side.uuid[index]
            if value is None:
                # Ask Rust for this canonical candidate ref. In particular,
                # derived pair-vs-path key policy must stay inside Rust.
                page = self.composition.nodes.count + index
                reply = decode_container(
                    session.interact(self._request(17, [("companion.u32", 0, D.U32, [page, 1])])),
                    "XYGR",
                )
                self.revision = int(reply["header.u32", 0][0])
                canonical = reply["candidates.bytes", 0]
                record = bytearray(canonical[8:64])
                offset, length = struct.unpack_from("<II", record, 48)
                if offset != 0xFFFFFFFF:
                    struct.pack_into("<I", record, 48, len(pool))
                    pool.extend(canonical[64 + offset : 64 + offset + length])
                records.append(record)
            else:
                records.append(
                    struct.pack(
                        "<II16sIIQQII",
                        int(kind == "edge"),
                        0,
                        uuid.UUID(value).bytes,
                        0,
                        0,
                        0,
                        0,
                        0,
                        0,
                    )
                )
        refs = struct.pack("<II", len(records), len(pool)) + b"".join(records) + pool
        return self._decode(session.interact(self._request(11, [("refs.bytes", 0, D.BYTES, refs)])))

    def select_region(self, indices, *, include_edges=True):
        """Frame native scatter candidates against this exact Rust publication.

        Comparing the existing compiler's positions and membership is admission,
        not an alternative layout or a host implementation of induced edges.
        """
        meta = self.meta
        node_ids, expected_nodes = meta["ids"], self.composition.nodes.uuid
        if len(node_ids) != len(expected_nodes) or any(
            actual != expected for actual, expected in zip(node_ids, expected_nodes, strict=True)
        ):
            raise ValueError("graph region source identities differ from displayed membership")
        edge_ids = meta.get("source_edge_ids", ())
        if len(edge_ids) != self.composition.edges.count or any(
            expected is not None and actual != expected
            for actual, expected in zip(edge_ids, self.composition.edges.uuid, strict=True)
        ):
            raise ValueError("graph region source identities differ from displayed membership")
        session = self.prepare()
        published = decode_container(session.render(self._request(21)), "XYGR")
        self.revision = int(published["header.u32", 0][0])
        trace = self.figure.traces[meta["node_trace"]]
        edges = self.figure._graph_edge_identity[meta["edge_trace"]]
        planes = {
            "render.node_x.f64": trace.x.values,
            "render.node_y.f64": trace.y.values,
            "render.member_of.u64": meta["member_of"],
            "render.edge_source.u64": meta["sources"],
            "render.edge_target.u64": meta["targets"],
            "render.edge_member_offsets.u64": edges.offsets,
            "render.edge_members.u64": edges.members,
        }
        for name, expected in planes.items():
            dtype = "<f8" if name.endswith("f64") else "<u8"
            actual = np.asarray(published[name, 0], dtype=dtype)
            wanted = np.asarray(expected, dtype=dtype)
            if actual.shape != wanted.shape or actual.tobytes() != wanted.tobytes():
                raise ValueError("graph region publication differs from displayed membership")
        if include_edges:
            extra = [("region.nodes.u32", 0, D.U32, indices)]
        else:
            records = [
                struct.pack("<II16sIIQQII", 3, 0, bytes(16), int(index), self.revision, 0, 0, 0, 0)
                for index in indices
            ]
            refs = struct.pack("<II", len(records), 0) + b"".join(records)
            extra = [("refs.bytes", 0, D.BYTES, refs)]
        result = session.interact(self._request(11, extra, policy=2 if include_edges else 0))
        return self._merge([self._decode(result)])

    def render_rows(self, identities, *, whole_groups=False):
        m = self.meta
        if m["tier_name"] == "aggregate" and not whole_groups:
            raise ValueError("UUID highlights require exact graph LOD")
        nodes = {row["index"] for row in identities if row["kind"] == "node"}
        edges = {row["index"] for row in identities if row["kind"] == "edge"}
        identity = self.figure._graph_edge_identity[m["edge_trace"]]
        selected_nodes = {m["member_of"][i] for i in nodes}
        self._index_node_rows()
        if any(render >= m["n_nodes"] for render in selected_nodes) or (
            not whole_groups and any(render in self._shared_node_rows for render in selected_nodes)
        ):
            raise ValueError("UUID highlights require individually rendered nodes")
        if (
            whole_groups
            and {source for source, render in enumerate(m["member_of"]) if render in selected_nodes}
            != nodes
        ):
            raise ValueError("graph region must contain complete published node membership")
        if any(
            edges.intersection(map(int, identity.members_of(int(render))))
            and (
                not set(map(int, identity.members_of(int(render)))) <= edges
                if whole_groups
                else len(identity.members_of(int(render))) != 1
            )
            for render in identity.render_edge_index
        ):
            raise ValueError("UUID highlights require individually rendered edges")
        return {
            m["node_trace"]: np.array(sorted(selected_nodes), dtype=np.uint64),
            m["edge_trace"]: np.array(
                [
                    i
                    for i, render in enumerate(identity.render_edge_index)
                    if len(identity.members_of(int(render)))
                    and set(map(int, identity.members_of(int(render)))) <= edges
                ],
                dtype=np.uint64,
            ),
        }
