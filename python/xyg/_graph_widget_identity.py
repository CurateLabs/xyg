"""Notebook identity transport over the existing Rust session projection.

The session's painter output is deliberately unused: Figure remains the renderer.
Source/render joins below copy the original compiler's Rust membership planes.
"""

from __future__ import annotations

import secrets
import struct
import uuid
import weakref

import numpy as np

from ._graph_session import GraphSession
from ._graphforge_container import DTYPE as D
from ._graphforge_container import decode_container, encode_container


class NotebookGraphIdentity:
    def __init__(self, composition, meta, figure, x, y):
        self.composition = composition
        self.meta = meta
        self.figure = weakref.proxy(figure)
        self.instance = secrets.randbits(63) or 1
        self.sequence = 1
        self.revision = 0
        opening = self._request(
            19,
            [
                ("document.bytes", 0, D.BYTES, composition.bytes),
                ("load.x.f64", 0, D.F64, x),
                ("load.y.f64", 0, D.F64, y),
            ],
        )
        self.session = GraphSession(
            composition.bytes, opening, instance_id=self.instance, group_id=0
        )
        weakref.finalize(self, self.session.close)
        self._decode(self.session.render(self._request(21)))

    def _request(self, operation, extra=()):
        sequence = self.sequence
        self.sequence += 1
        return encode_container(
            "XYGI",
            [
                ("header.u64", 0, D.U64, [self.instance, 0, sequence]),
                ("header.u32", 0, D.U32, [self.revision, operation, 0, 0, 0, 0, 0, 0, 0]),
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
            out.append(
                {
                    "kind": "node" if kind == 0 else "edge",
                    "uuid": str(uuid.UUID(bytes=refs[start + 8 : start + 24]))
                    if kind < 2
                    else None,
                    "index": int(result["selection.indices.u64", 0][i]),
                    "layers": [
                        {
                            "layer": int(layers[j]),
                            "result_id": names[int(layers[j])] if valid[int(layers[j])] else None,
                            "row": int(rows[j]),
                        }
                        for j in range(int(offsets[i]), int(offsets[i + 1]))
                    ],
                }
            )
        return out

    def select(self, uuids):
        data = b"".join(uuid.UUID(value).bytes for value in uuids)
        return self._decode(
            self.session.interact(self._request(10, [("uuids.uuid", 0, D.UUID, data)]))
        )

    def source_rows(self, trace, index):
        m = self.meta
        if m["tier_name"] == "aggregate":
            return []  # aggregate membership is not an individual identity
        if trace == m["node_trace"]:
            return [("node", i) for i, render in enumerate(m["member_of"]) if render == index][:1]
        if trace == m["edge_trace"]:
            identity = self.figure._graph_edge_identity[trace]
            if 0 <= index < len(identity.render_edge_index):
                return [
                    ("edge", int(i))
                    for i in identity.members_of(int(identity.render_edge_index[index]))
                ]
        return []

    def project(self, per_trace):
        sources = sorted(
            {
                item
                for trace, indices in per_trace.items()
                for index in indices
                for item in self.source_rows(trace, int(index))
            }
        )
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
                    self.session.interact(
                        self._request(17, [("companion.u32", 0, D.U32, [page, 1])])
                    ),
                    "XYGR",
                )
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
        return self._decode(
            self.session.interact(self._request(11, [("refs.bytes", 0, D.BYTES, refs)]))
        )

    def render_rows(self, identities):
        m = self.meta
        if m["tier_name"] == "aggregate":
            raise ValueError("UUID highlights require exact graph LOD")
        nodes = {row["index"] for row in identities if row["kind"] == "node"}
        edges = {row["index"] for row in identities if row["kind"] == "edge"}
        identity = self.figure._graph_edge_identity[m["edge_trace"]]
        selected_nodes = {m["member_of"][i] for i in nodes}
        if any(
            render >= m["n_nodes"] or sum(value == render for value in m["member_of"]) != 1
            for render in selected_nodes
        ):
            raise ValueError("UUID highlights require individually rendered nodes")
        if any(
            len(identity.members_of(int(render))) != 1
            and edges.intersection(map(int, identity.members_of(int(render))))
            for render in identity.render_edge_index
        ):
            raise ValueError("UUID highlights require individually rendered edges")
        return {
            m["node_trace"]: np.array(sorted(selected_nodes), dtype=np.uint64),
            m["edge_trace"]: np.array(
                [
                    i
                    for i, render in enumerate(identity.render_edge_index)
                    if len(identity.members_of(int(render))) == 1
                    and int(identity.members_of(int(render))[0]) in edges
                ],
                dtype=np.uint64,
            ),
        }
