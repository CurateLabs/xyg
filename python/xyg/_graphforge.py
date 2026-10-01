"""GraphForge result compositions on the Python host (xyg#37).

GraphForge computes; XYG composes and renders. Rust owns recognition, UUID
joins, identity policy, composition, and the Scene
(spec/design/graphforge-compositions.md); this module only frames the
``XYGQ`` request, runs it through the native core, decodes the ``XYGF``
document, and paints the Rust planes with the ordinary chart components. It is
the Python twin of Node ``@curatelabs/xyg-node/graphforge``: the same request
produces byte-identical request and document bytes in both hosts and in
direct-browser WASM.
"""

from __future__ import annotations

import html
import math
import re
from collections.abc import Iterable, Mapping, Sequence
from functools import cached_property
from typing import Any

import numpy as np

from . import _native
from ._graphforge_container import (
    DOCUMENT_MAGIC,
    DTYPE,
    REQUEST_MAGIC,
    decode_container,
    encode_container,
)

__all__ = [
    "GRAPHFORGE_EXTRA_POLICIES",
    "GRAPHFORGE_INTENTS",
    "GRAPHFORGE_MISSING_POLICIES",
    "GraphForgeComposition",
    "GraphForgeCompositionError",
    "compose_graphforge",
    "compose_graphforge_request",
    "decode_graphforge_document",
    "encode_graphforge_request",
    "graphforge_chart",
    "graphforge_ledger",
    "graphforge_table_html",
]

GRAPHFORGE_INTENTS = (
    "graph",
    "table",
    "bar-chart",
    "embedding-coordinates",
    "parallel-coordinates",
)
GRAPHFORGE_MISSING_POLICIES = ("dim", "hide", "keep", "error")
GRAPHFORGE_EXTRA_POLICIES = ("error", "drop")
_NONE_U32 = 0xFFFFFFFF
_NONE_U64 = 0xFFFFFFFFFFFFFFFF
_UUID_TEXT = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
_SHAPES = ("circle", "square", "diamond", "triangle", "cross", "hexagon")


class GraphForgeCompositionError(ValueError):
    """A composition failure with Rust's stable ``code`` (value-free message)."""

    def __init__(
        self, code: str, message: str, *, layer: int | None = None, field: str | None = None
    ) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code
        self.layer = layer
        self.field = field


def _invalid(message: str) -> GraphForgeCompositionError:
    return GraphForgeCompositionError("GF_COMPOSE_REQUEST_INVALID", message)


def _uuid_bytes(text: Any, label: str) -> bytes:
    value = str(text).lower() if isinstance(text, str) else None
    if value is None or not _UUID_TEXT.match(value):
        raise _invalid(f"{label} must be a canonical UUID string")
    return bytes.fromhex(value.replace("-", ""))


def _uuid_text(data: bytes, at: int = 0) -> str:
    h = data[at : at + 16].hex()
    return f"{h[:8]}-{h[8:12]}-{h[12:16]}-{h[16:20]}-{h[20:]}"


def _uuid_plane(values: Any, label: str) -> bytes:
    if isinstance(values, (bytes, bytearray, memoryview)):
        return bytes(values)
    if isinstance(values, np.ndarray) and values.dtype == np.uint8:
        return values.tobytes()
    if isinstance(values, (str, bytes)) or not isinstance(values, Iterable):
        raise _invalid(f"{label} must be UUID strings or packed bytes")
    return b"".join(_uuid_bytes(v, label) for v in values)


def _ipc(value: Any, label: str) -> bytes:
    if isinstance(value, (bytes, bytearray, memoryview)):
        return bytes(value)
    if isinstance(value, np.ndarray) and value.dtype == np.uint8:
        return value.tobytes()
    to_py = getattr(value, "to_pybytes", None)  # pyarrow.Buffer
    if callable(to_py):
        return bytes(to_py())
    raise _invalid(f"{label} must be Arrow IPC bytes")


def encode_graphforge_request(
    *,
    layers: Sequence[Mapping[str, Any]],
    base: Mapping[str, Any] | None = None,
    select: Iterable[str] | None = None,
    render: Mapping[str, Any] | None = None,
) -> bytes:
    """Frame a composition request (``XYGQ``). Only representation is checked
    here; Rust validates every value, policy, and identity.

    ``base``: ``tables`` (GraphForge Arrow IPC bytes: Cypher entity results or
    flat node/edge tables) and/or packed planes ``node_uuid``, ``edge_uuid``,
    ``edge_source_uuid``, ``edge_target_uuid``; plus ``generation`` (UUID) and
    ``directed``. ``layers``: ``result`` (Arrow IPC bytes), ``intent``
    (required), ``result_id``, ``generation``, ``missing``, ``extra``,
    ``rows``, ``coordinates``. ``select``: node/relationship UUIDs painted
    selected. ``render``: ``{width, height, theme, title}`` also lowers a graph
    to the direct-tier canonical Scene.
    """
    if not layers:
        raise _invalid("layers must be a non-empty sequence")
    base = dict(base or {})
    sections: list[tuple[str, int, int, Any]] = []
    for index, table in enumerate(base.get("tables") or ()):
        sections.append(("base.table", index, DTYPE.BYTES, _ipc(table, "base.tables[]")))
    for key, name in (
        ("node_uuid", "base.node_uuid"),
        ("edge_uuid", "base.edge_uuid"),
        ("edge_source_uuid", "base.edge_source_uuid"),
        ("edge_target_uuid", "base.edge_target_uuid"),
    ):
        if base.get(key) is not None:
            sections.append((name, 0, DTYPE.UUID, _uuid_plane(base[key], f"base.{key}")))
    if base.get("generation") is not None:
        sections.append(
            ("base.generation", 0, DTYPE.UUID, _uuid_bytes(base["generation"], "base.generation"))
        )
    if base.get("directed") is not None:
        sections.append(("base.directed", 0, DTYPE.U8, [1 if base["directed"] else 0]))
    for index, layer in enumerate(layers):
        if not isinstance(layer, Mapping):
            raise _invalid("each layer must be a mapping")
        sections.append(
            (
                "layer.result",
                index,
                DTYPE.BYTES,
                _ipc(layer.get("result"), f"layers[{index}].result"),
            )
        )
        if layer.get("intent") is not None:
            sections.append(("layer.intent", index, DTYPE.UTF8, str(layer["intent"])))
        if layer.get("result_id") is not None:
            sections.append(("layer.result_id", index, DTYPE.UTF8, str(layer["result_id"])))
        if layer.get("generation") is not None:
            label = f"layers[{index}].generation"
            sections.append(
                ("layer.generation", index, DTYPE.UUID, _uuid_bytes(layer["generation"], label))
            )
        if layer.get("missing") is not None:
            sections.append(("layer.missing", index, DTYPE.UTF8, str(layer["missing"])))
        if layer.get("extra") is not None:
            sections.append(("layer.extra", index, DTYPE.UTF8, str(layer["extra"])))
        if layer.get("rows") is not None:
            rows = []
            for row in layer["rows"]:
                if isinstance(row, bool) or not isinstance(row, (int, np.integer)) or row < 0:
                    raise _invalid("rows must be non-negative integers")
                rows.append(int(row))
            sections.append(("layer.rows", index, DTYPE.U64, np.asarray(rows, dtype=np.uint64)))
        if layer.get("coordinates") is not None:
            sections.append(
                (
                    "layer.coordinates",
                    index,
                    DTYPE.BYTES,
                    _ipc(layer["coordinates"], f"layers[{index}].coordinates"),
                )
            )
    if select is not None:
        sections.append(("select.uuid", 0, DTYPE.UUID, _uuid_plane(list(select), "select")))
    if render is not None:
        sections.append(("render.width", 0, DTYPE.F64, [float(render["width"])]))
        sections.append(("render.height", 0, DTYPE.F64, [float(render["height"])]))
        if render.get("theme") is not None:
            sections.append(("render.theme", 0, DTYPE.UTF8, str(render["theme"])))
        if render.get("title") is not None:
            sections.append(("render.title", 0, DTYPE.UTF8, str(render["title"])))
    return encode_container(REQUEST_MAGIC, sections)


def compose_graphforge_request(request: bytes) -> bytes:
    """Run framed ``XYGQ`` bytes through Rust; the ``XYGF`` document bytes."""
    return _native.graphforge_compose(_ipc(request, "request"))


def compose_graphforge(
    *,
    layers: Sequence[Mapping[str, Any]],
    base: Mapping[str, Any] | None = None,
    select: Iterable[str] | None = None,
    render: Mapping[str, Any] | None = None,
) -> GraphForgeComposition:
    """Compose GraphForge results onto a base graph.

    Arguments are those of :func:`encode_graphforge_request`. Raises
    :class:`GraphForgeCompositionError` with Rust's stable ``code`` (for
    example ``GF_COMPOSE_GENERATION_STALE``) when a result cannot be composed.
    """
    request = encode_graphforge_request(layers=layers, base=base, select=select, render=render)
    return decode_graphforge_document(compose_graphforge_request(request))


def decode_graphforge_document(data: bytes) -> GraphForgeComposition:
    """Decode ``XYGF`` bytes (from any host); raises on an error document."""
    raw = _ipc(data, "XYGF bytes")
    try:
        sections = decode_container(raw, DOCUMENT_MAGIC)
    except ValueError as error:
        raise GraphForgeCompositionError("GF_COMPOSE_DOCUMENT_INVALID", str(error)) from None
    status = sections.get(("status", 0))
    if status is None or int(status[0]) != 0:
        layer = sections.get(("error.layer", 0))
        layer_index = None if layer is None or int(layer[0]) == _NONE_U32 else int(layer[0])
        raise GraphForgeCompositionError(
            sections.get(("error.code", 0)) or "GF_COMPOSE_NATIVE",
            sections.get(("error.message", 0)) or "composition failed",
            layer=layer_index,
            field=sections.get(("error.field", 0)),
        )
    return GraphForgeComposition(raw, sections)


def _uuid_list(data: bytes | None) -> list[str]:
    if data is None:
        return []
    return [_uuid_text(data, i * 16) for i in range(len(data) // 16)]


def _rgba_hex(rgba: np.ndarray, i: int) -> str:
    r, g, b, a = (int(v) for v in rgba[i * 4 : i * 4 + 4])
    return f"#{r:02x}{g:02x}{b:02x}" + ("" if a == 255 else f"{a:02x}")


class _Side:
    """Composed node or edge planes; UUID text is built on first use.

    Planes absent for a side (edge-only ``source``/``target``/``derived``/
    ``layer``/``order``/``path``) are ``None``.
    """

    base_row: Any
    name: Any
    type: Any
    class_: Any
    epistemic: Any
    status: Any
    metric: Any
    flags: Any
    label: Any
    label_priority: Any
    source: Any = None
    target: Any = None
    derived: Any = None
    layer: Any = None
    order: Any = None
    path: Any = None

    def __init__(self, planes: dict[str, Any], uuid_bytes: bytes, derived: Any) -> None:
        for key, value in planes.items():
            setattr(self, key, value)
        self.uuid_bytes = uuid_bytes
        self.count = len(uuid_bytes) // 16
        self._derived = derived

    @cached_property
    def uuid(self) -> list[str | None]:
        """UUID text by composed index (``None`` for derived edges)."""
        ids: list[str | None] = list(_uuid_list(self.uuid_bytes))
        if self._derived is not None:
            ids = [None if self._derived[i] else u for i, u in enumerate(ids)]
        return ids


class GraphForgeComposition:
    """A decoded composition: identity-preserving planes plus provenance."""

    def __init__(self, data: bytes, sections: dict[tuple[str, int], Any]) -> None:
        #: The exact ``XYGF`` bytes (identical from native and WASM hosts).
        self.bytes = data
        self.sections = sections

        def get(name: str, index: int = 0) -> Any:
            return sections.get((name, index))

        self.kind: str = get("kind")
        version = get("composition.version")
        self.version = int(version[0]) if version is not None else None
        ledger = get("ledger.version")
        self.ledger_version = int(ledger[0]) if ledger is not None else None
        directed = get("graph.directed")
        self.directed = directed is not None and int(directed[0]) == 1
        generation = get("base.generation")
        self.base_generation = _uuid_text(generation) if generation else None
        self.layers: list[dict[str, Any]] = []
        i = 0
        while ("layer.schema", i) in sections:
            counts = get("layer.counts", i)
            counts = [int(c) for c in counts] if counts is not None else [0, 0, 0, 0, 0]
            layer_generation = get("layer.generation", i)
            schema_version = get("layer.schema_version", i)
            self.layers.append(
                {
                    "index": i,
                    "schema": get("layer.schema", i),
                    "schema_version": int(schema_version[0])
                    if schema_version is not None
                    else None,
                    "verb": get("layer.verb", i),
                    "algorithm": get("layer.algorithm", i),
                    "disposition": get("layer.disposition", i),
                    "composition": get("layer.composition", i),
                    "intent": get("layer.intent", i),
                    "missing_policy": get("layer.missing_policy", i),
                    "extra_policy": get("layer.extra_policy", i),
                    "result_id": get("layer.result_id", i),
                    "generation": _uuid_text(layer_generation) if layer_generation else None,
                    "derived_type": get("layer.derived_type", i),
                    "counts": dict(
                        zip(
                            ("rows", "selected", "matched", "missing", "extra"),
                            counts,
                            strict=False,
                        )
                    ),
                    "value_names": get("layer.value_names", i) or [],
                    "text_names": get("layer.text_names", i) or [],
                    "node_texts": get("layer.node_texts", i),
                    "node_values": get("layer.node_values", i),
                    "node_rows": get("layer.node_rows", i),
                    "edge_values": get("layer.edge_values", i),
                    "edge_rows": get("layer.edge_rows", i),
                }
            )
            i += 1
        self.nodes: _Side | None = None
        self.edges: _Side | None = None
        self.paths: list[dict[str, Any]] = []
        self.table: dict[str, Any] | None = None
        self.chart: dict[str, Any] | None = None
        self.vectors: dict[str, Any] | None = None
        self.points: dict[str, Any] | None = None
        if self.kind == "graph":
            self.nodes = _Side(
                {
                    key: get(f"node.{name}")
                    for key, name in (
                        ("base_row", "base_row"),
                        ("name", "name"),
                        ("type", "type"),
                        ("class_", "class"),
                        ("epistemic", "epistemic"),
                        ("status", "status"),
                        ("metric", "metric"),
                        ("flags", "flags"),
                        ("label", "label"),
                        ("label_priority", "label_priority"),
                    )
                },
                get("node.uuid"),
                None,
            )
            derived = get("edge.derived")
            self.edges = _Side(
                {
                    key: get(f"edge.{name}")
                    for key, name in (
                        ("base_row", "base_row"),
                        ("source", "source"),
                        ("target", "target"),
                        ("type", "type"),
                        ("derived", "derived"),
                        ("layer", "layer"),
                        ("class_", "class"),
                        ("epistemic", "epistemic"),
                        ("status", "status"),
                        ("metric", "metric"),
                        ("flags", "flags"),
                        ("order", "order"),
                        ("path", "path"),
                        ("label", "label"),
                        ("label_priority", "label_priority"),
                    )
                },
                get("edge.uuid"),
                derived,
            )
            node_offsets = get("path.node_offsets")
            edge_offsets = get("path.edge_offsets")
            path_layer = get("path.layer")
            if path_layer is not None:
                for p in range(len(path_layer)):
                    self.paths.append(
                        {
                            "layer": int(path_layer[p]),
                            "row": int(get("path.row")[p]),
                            "rank": int(get("path.rank")[p]),
                            "cost": float(get("path.cost")[p]),
                            "nodes": [
                                int(v)
                                for v in get("path.nodes")[
                                    int(node_offsets[p]) : int(node_offsets[p + 1])
                                ]
                            ],
                            "edges": [
                                int(v)
                                for v in get("path.edges")[
                                    int(edge_offsets[p]) : int(edge_offsets[p + 1])
                                ]
                            ],
                        }
                    )
        elif self.kind == "table":
            columns, cells = get("table.columns"), get("table.cells")
            values, valid, rows = get("table.values"), get("table.valid"), get("table.rows")
            k = len(columns or ())
            if (
                not k
                or cells is None
                or rows is None
                or values is None
                or valid is None
                or len(cells) != len(rows) * k
                or len(values) != len(cells)
                or len(valid) != len(cells)
            ):
                raise GraphForgeCompositionError(
                    "GF_COMPOSE_DOCUMENT_INVALID", "table sections disagree on shape"
                )
            self.table = {
                "columns": list(columns),
                "kinds": get("table.kinds"),
                "result_rows": [int(r) for r in rows],
                "rows": [
                    [cells[r * k + c] if valid[r * k + c] else None for c in range(k)]
                    for r in range(len(rows))
                ],
                "values": [values[r * k : r * k + k].tolist() for r in range(len(rows))],
            }
        elif self.kind == "bar-chart":
            self.chart = {
                "category_name": get("chart.category_name"),
                "value_name": get("chart.value_name"),
                "categories": list(get("chart.category")),
                "values": get("chart.value"),
                # [x0, x1, y0, y1]: bar slots 0..k-1, zero-baseline value range (Rust).
                "domain": [float(v) for v in get("chart.domain")],
                "result_rows": [int(r) for r in get("chart.result_row")],
            }
        elif self.kind == "parallel-coordinates":
            self.vectors = {
                "dimensions": int(get("vector.dimensions")[0]),
                "uuid": _uuid_list(get("vector.uuid")),
                "name": list(get("vector.name")),
                "result_rows": [int(r) for r in get("vector.result_row")],
                "values": get("vector.values"),
                "domain": [float(v) for v in get("vector.domain")],
            }
        elif self.kind == "scatter":
            self.points = {
                "source": get("point.source"),
                "dimensions": int(get("vector.dimensions")[0]),
                "uuid": _uuid_list(get("point.uuid")),
                "name": list(get("point.name")),
                "result_rows": [int(r) for r in get("point.result_row")],
                "x": get("point.x"),
                "y": get("point.y"),
            }
        canonical = get("scene.canonical")
        bases = get("scene.stable_id_base")
        #: Direct-tier canonical Scene (``render`` requests).
        self.scene = (
            None
            if canonical is None
            else {
                "version": int(get("scene.version")[0]),
                "bytes": canonical,
                "x": get("scene.x"),
                "y": get("scene.y"),
                "node_stable_id_base": int(bases[0]),
                "edge_stable_id_base": int(bases[1]),
            }
        )
        side = get("legend.side")
        light, dark = get("legend.rgba_light"), get("legend.rgba_dark")
        self.legend = {
            "title": get("legend.title"),
            "rows": [
                {
                    "side": "node" if int(s) == 0 else "edge",
                    "field": int(get("legend.field")[r]),
                    "value": int(get("legend.value")[r]),
                    "text": get("legend.text")[r],
                    "shape": _SHAPES[int(get("legend.shape")[r]) % len(_SHAPES)],
                    "color_light": _rgba_hex(light, r),
                    "color_dark": _rgba_hex(dark, r),
                }
                for r, s in enumerate(side if side is not None else ())
            ],
        }
        codes = get("decision.code") or []
        decision_layers = get("decision.layer")
        decision_counts = get("decision.count")
        self.decisions = [
            {
                "code": code,
                "layer": None if int(decision_layers[d]) == _NONE_U32 else int(decision_layers[d]),
                "count": int(decision_counts[d]),
            }
            for d, code in enumerate(codes)
        ]

    @cached_property
    def _node_index(self) -> dict[str, int]:
        return {} if self.nodes is None else {u: i for i, u in enumerate(self.nodes.uuid) if u}

    @cached_property
    def _edge_index(self) -> dict[str, int]:
        return {} if self.edges is None else {u: i for i, u in enumerate(self.edges.uuid) if u}

    def node_index(self, uuid: str) -> int:
        """Dense node index for a UUID (or -1)."""
        return self._node_index.get(str(uuid).lower(), -1)

    def edge_index(self, uuid: str) -> int:
        """Dense edge index for a persisted relationship UUID (or -1)."""
        return self._edge_index.get(str(uuid).lower(), -1)

    def identify(self, kind: str, index: int) -> dict[str, Any]:
        """Identity of one composed element: its UUID (``None`` for derived
        edges) and, per layer, the caller's result id and result row."""
        side = self.nodes if kind == "node" else self.edges
        if side is None or not 0 <= int(index) < side.count:
            raise IndexError(f"no composed {kind} {index}")
        index = int(index)
        rows_key = "node_rows" if kind == "node" else "edge_rows"
        layers = []
        for layer in self.layers:
            rows = layer[rows_key]
            if rows is not None and int(rows[index]) != _NONE_U64:
                layers.append(
                    {
                        "layer": layer["index"],
                        "result_id": layer["result_id"],
                        "row": int(rows[index]),
                    }
                )
        out: dict[str, Any] = {
            "kind": kind,
            "index": index,
            "uuid": side.uuid[index],
            "layers": layers,
        }
        if kind == "edge":
            assert self.nodes is not None
            out["derived"] = bool(side.derived[index])
            out["type"] = side.type[index] or None
            order = side.order[index] if side.order is not None else -1
            if order >= 0:
                out["order"] = int(order)
                out["path"] = int(side.path[index])
            out["source"] = self.nodes.uuid[int(side.source[index])]
            out["target"] = self.nodes.uuid[int(side.target[index])]
        return out

    def select(self, uuids: Iterable[str]) -> dict[str, list[int]]:
        """UUIDs (nodes and/or relationships) → composed indices, for highlight."""
        nodes, edges = [], []
        for uuid in uuids:
            if (n := self.node_index(uuid)) >= 0:
                nodes.append(n)
            if (e := self.edge_index(uuid)) >= 0:
                edges.append(e)
        return {"nodes": nodes, "edges": edges}

    def diagnostics(self) -> dict[str, Any]:
        """Value-free summary for host logs: schema ids, counts, and codes only."""
        rows = None
        if self.table is not None:
            rows = len(self.table["rows"])
        elif self.chart is not None:
            rows = len(self.chart["categories"])
        elif self.vectors is not None:
            rows = len(self.vectors["uuid"])
        elif self.points is not None:
            rows = len(self.points["uuid"])
        return {
            "kind": self.kind,
            "composition_version": self.version,
            "rows": rows,
            "ledger_version": self.ledger_version,
            "nodes": self.nodes.count if self.nodes is not None else 0,
            "edges": self.edges.count if self.edges is not None else 0,
            "layers": [
                {
                    key: (dict(layer[key]) if key == "counts" else layer[key])
                    for key in (
                        "schema",
                        "schema_version",
                        "disposition",
                        "composition",
                        "intent",
                        "counts",
                    )
                }
                for layer in self.layers
            ],
            "decisions": [dict(d) for d in self.decisions],
        }


# -- painting ---------------------------------------------------------------------


def _graph_data(composition: GraphForgeComposition) -> Any:
    """``GraphData`` for a graph composition (identity is UUID text), as Node
    ``graphforgeGraphData`` builds it."""
    from ._graph import GraphData

    nodes, edges = composition.nodes, composition.edges
    assert nodes is not None and edges is not None
    node_attrs: dict[str, Any] = {
        "name": np.array([v or None for v in nodes.name], dtype=object),
        "type": np.array([v or None for v in nodes.type], dtype=object),
    }
    edge_attrs: dict[str, Any] = {"type": np.array([v or None for v in edges.type], dtype=object)}
    for layer in composition.layers:
        prefix = layer["algorithm"] or layer["verb"]
        if layer["node_texts"] is not None:
            t = len(layer["text_names"])
            for j, name in enumerate(layer["text_names"]):
                node_attrs[f"{prefix}.{name}"] = np.array(
                    [layer["node_texts"][i * t + j] or None for i in range(nodes.count)],
                    dtype=object,
                )
        for values, attrs, count in (
            (layer["node_values"], node_attrs, nodes.count),
            (layer["edge_values"], edge_attrs, edges.count),
        ):
            if values is None:
                continue
            k = len(layer["value_names"])
            for j, name in enumerate(layer["value_names"]):
                attrs[f"{prefix}.{name}"] = np.asarray(values[j::k][:count], dtype=np.float64)
    edge_ids: list[str] = []
    for i, uuid in enumerate(edges.uuid):
        if uuid is not None:
            edge_ids.append(uuid)
            continue
        layer = composition.layers[int(edges.layer[i])]
        step = (
            f":{int(edges.order[i])}"
            if edges.order is not None and int(edges.order[i]) >= 0
            else ""
        )
        edge_ids.append(f"derived:{int(edges.layer[i])}:{int(layer['edge_rows'][i])}{step}")
    if edges.order is not None:
        edge_attrs["step"] = np.array(
            [math.nan if int(v) < 0 else float(v) for v in edges.order], dtype=np.float64
        )
    return GraphData(
        list(nodes.uuid),
        edges.source,
        edges.target,
        node_attrs=node_attrs,
        edge_ids=edge_ids,
        edge_attrs=edge_attrs,
        node_uuid_bytes=np.frombuffer(nodes.uuid_bytes, dtype=np.uint8),
        edge_uuid_bytes=np.frombuffer(edges.uuid_bytes, dtype=np.uint8),
        node_provenance_rows=nodes.base_row,
        edge_provenance_rows=edges.base_row,
        directed=composition.directed,
    )


def _legend_items(composition: GraphForgeComposition, theme: str) -> list[dict[str, Any]]:
    return [
        {
            "kind": "scatter",
            "name": row["text"],
            "style": {
                "color": row["color_dark"] if theme == "dark" else row["color_light"],
                "symbol": row["shape"] if row["side"] == "node" and row["field"] == 0 else "circle",
            },
        }
        for row in composition.legend["rows"]
    ]


def _graph_chart(composition: GraphForgeComposition, props: dict[str, Any]) -> Any:
    from . import components as c

    theme = props.pop("theme", "light")
    nodes, edges = composition.nodes, composition.edges
    assert nodes is not None and edges is not None
    edge_labels = [v or None for v in edges.label] if edges.label is not None else None
    labelled = edge_labels is not None and any(edge_labels)
    mark = c.graph(
        _graph_data(composition),
        theme=theme,
        node_class=nodes.class_,
        node_epistemic=nodes.epistemic,
        node_status=nodes.status,
        node_metric=nodes.metric,
        visual_state_flags=nodes.flags,
        edge_class=edges.class_,
        edge_epistemic=edges.epistemic,
        edge_status=edges.status,
        edge_metric=edges.metric,
        edge_visual_state_flags=edges.flags,
        node_label=[v or None for v in nodes.label],
        label_priority=nodes.label_priority,
        edge_label=edge_labels if labelled else None,
        edge_label_priority=edges.label_priority if labelled else None,
        semantic_legend=False,
    )
    chart = c.graph_chart(mark, **props)
    items = _legend_items(composition, theme)
    if items:
        # The composition's Rust legend (layer-specific text), as Node passes it.
        fig = chart.figure()
        fig.legend_options = {
            "title": composition.legend["title"],
            **fig.legend_options,
            "items": items,
        }
    return chart


def _bar_chart(composition: GraphForgeComposition, props: dict[str, Any]) -> Any:
    from . import components as c

    chart_doc = composition.chart
    assert chart_doc is not None
    categories, values = chart_doc["categories"], chart_doc["values"]
    k = len(categories)
    slots = np.arange(k, dtype=np.float64)
    x0, x1, y0, y1 = chart_doc["domain"]
    props.pop("theme", None)
    chart = c.bar_chart(
        c.bar(slots, np.asarray(values, dtype=np.float64), name=chart_doc["value_name"]),
        # Bars sit on integer slots of a linear axis whose ticks carry the
        # category names (Rust domain), so browser and SVG/PNG label them alike.
        c.x_axis(
            label=chart_doc["category_name"],
            domain=(x0, x1),
            tick_values=list(slots),
            tick_labels=list(categories),
        ),
        c.y_axis(label=chart_doc["value_name"], domain=(y0, y1)),
        **props,
    )
    fig = chart.figure()
    fig.traces[-1].tooltip_rows = [
        {
            chart_doc["category_name"]: category,
            chart_doc["value_name"]: float(values[i]) if math.isfinite(values[i]) else None,
        }
        for i, category in enumerate(categories)
    ]
    return chart


def _parallel_chart(composition: GraphForgeComposition, props: dict[str, Any]) -> Any:
    from . import components as c

    vectors = composition.vectors
    assert vectors is not None
    dims, values, uuid, name = (
        vectors["dimensions"],
        vectors["values"],
        vectors["uuid"],
        vectors["name"],
    )
    dx0, dx1, dy0, dy1 = vectors["domain"]
    props.pop("theme", None)
    axes = (
        c.x_axis(label="dimension", domain=(dx0, dx1)),
        c.y_axis(label="value", domain=(dy0, dy1)),
    )
    if dims < 2:
        # One dimension has no polyline: each node is a point at dimension 0.
        chart = c.scatter_chart(
            c.scatter(np.zeros(len(uuid)), np.asarray(values, dtype=np.float64), name="embedding"),
            *axes,
            **props,
        )
        rows = [
            {"id": u, **({"name": name[i]} if name[i] else {}), "dimension": 0}
            for i, u in enumerate(uuid)
        ]
        chart.figure().traces[-1].tooltip_rows = rows
        return chart
    n = len(uuid)
    grid = np.asarray(values, dtype=np.float64).reshape(n, dims)
    d = np.tile(np.arange(dims - 1, dtype=np.float64), n)
    chart = c.chart(
        c.segments(d, grid[:, :-1].reshape(-1), d + 1, grid[:, 1:].reshape(-1), name="embedding"),
        *axes,
        **props,
    )
    # Every segment keeps its node identity (rows ship as typed tooltip columns).
    chart.figure().traces[-1].tooltip_rows = [
        {"id": uuid[r], **({"name": name[r]} if name[r] else {}), "dimension": dd}
        for r in range(n)
        for dd in range(dims - 1)
    ]
    return chart


def _scatter_chart(composition: GraphForgeComposition, props: dict[str, Any]) -> Any:
    from . import components as c

    points = composition.points
    assert points is not None
    props.pop("theme", None)
    children: list[Any] = [
        c.scatter(np.asarray(points["x"]), np.asarray(points["y"]), name="embedding")
    ]
    if points["source"] == "embedding":
        children += [c.x_axis(label="dimension 0"), c.y_axis(label="dimension 1")]
    chart = c.scatter_chart(*children, **props)
    chart.figure().traces[-1].tooltip_rows = [
        {"id": u, **({"name": points["name"][i]} if points["name"][i] else {})}
        for i, u in enumerate(points["uuid"])
    ]
    return chart


def graphforge_chart(composition: GraphForgeComposition, **props: Any) -> Any:
    """A chart of a composition, dispatched on its ``kind``.

    Graphs paint the base graph laid out by Rust from the composition's
    semantic planes and legend; bar charts put bars on category-labelled
    slots; parallel coordinates draw one polyline per node over the dimension
    index; embedding coordinates draw a scatter. Hover rows carry the UUIDs.
    ``props`` (``width``, ``height``, ``title``, ``theme``, …) pass through to
    the chart. Tables render with :func:`graphforge_table_html`.
    """
    kind = getattr(composition, "kind", None)
    props = dict(props)
    if kind == "graph":
        return _graph_chart(composition, props)
    if kind == "bar-chart":
        return _bar_chart(composition, props)
    if kind == "parallel-coordinates":
        return _parallel_chart(composition, props)
    if kind == "scatter":
        return _scatter_chart(composition, props)
    if kind == "table":
        raise TypeError(
            "table compositions render as tables: use graphforge_table_html(composition)"
        )
    raise TypeError(f"unknown composition kind {kind!r}")


def graphforge_table_html(composition: GraphForgeComposition) -> str:
    """A table composition as an escaped HTML ``<table>`` (cells are text only)."""
    if getattr(composition, "kind", None) != "table" or composition.table is None:
        raise TypeError("graphforge_table_html needs a table composition")
    esc = lambda text: html.escape(str(text), quote=True).replace("&#x27;", "&#39;")  # noqa: E731
    head = "".join(f'<th scope="col">{esc(col)}</th>' for col in composition.table["columns"])
    body = "".join(
        "<tr>" + "".join(f"<td>{'' if cell is None else esc(cell)}</td>" for cell in row) + "</tr>"
        for row in composition.table["rows"]
    )
    algorithm = composition.layers[0]["algorithm"] if composition.layers else None
    caption = f"<caption>{esc(algorithm)}</caption>" if algorithm else ""
    return (
        f'<table class="xyg-graphforge-table">{caption}<thead><tr>{head}</tr></thead>'
        f"<tbody>{body}</tbody></table>"
    )


def graphforge_ledger() -> list[dict[str, Any]]:
    """The Rust coverage ledger: one row per registered GraphForge result
    schema (``schema``, ``version``, ``disposition``, ``composition``,
    ``intents``, ``fields``), as Node ``graphforgeLedger`` returns it."""
    header, *lines = _native.graphforge_ledger_tsv().rstrip().split("\n")
    keys = header.split("\t")
    out = []
    for line in lines:
        cells = dict(zip(keys, line.split("\t"), strict=False))
        fields = []
        for field in cells.get("fields", "").split(",") if cells.get("fields") else []:
            name, _, kind = field.partition(":")
            fields.append({"name": name, "kind": kind})
        out.append(
            {
                "schema": cells["schema"],
                "version": int(cells["version"]),
                "disposition": cells["disposition"],
                "composition": cells["composition"],
                "intents": cells["intents"].split(",") if cells.get("intents") else [],
                "fields": fields,
                "algorithms": cells["algorithms"].split(",") if cells.get("algorithms") else [],
            }
        )
    return out
