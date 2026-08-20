"""Graph ingest helpers — id maps and thin adapters (graph-mark.md).

Layout math lives in the Rust ABI (`_native.graph_layout`); this module only
coerces xyg-native inputs and optional NetworkX / GraphForge tables into dense
u64 indices + columns.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any
from uuid import UUID

import numpy as np

from . import _native

__all__ = [
    "DEFAULT_LAYOUT",
    "GraphData",
    "GraphProjectionError",
    "from_graphforge_tables",
    "from_networkx",
    "looks_like_graphforge_tables",
    "normalize_graph_inputs",
    "projection_tooltip_rows",
    "resolve_encoding_values",
    "resolve_graph_data",
]

DEFAULT_LAYOUT = "force"


class GraphData:
    """Dense graph ready for layout + segments/scatter emit."""

    __slots__ = (
        "directed",
        "edge_attrs",
        "edge_ids",
        "edge_provenance_rows",
        "edge_uuid_bytes",
        "ids",
        "node_attrs",
        "node_provenance_rows",
        "node_uuid_bytes",
        "parent_indices",
        "parent_validity",
        "sources",
        "targets",
        "x",
        "y",
    )

    def __init__(
        self,
        ids: list[Any],
        sources: np.ndarray,
        targets: np.ndarray,
        *,
        x: np.ndarray | None = None,
        y: np.ndarray | None = None,
        node_attrs: Mapping[str, np.ndarray] | None = None,
        edge_ids: list[Any] | None = None,
        edge_attrs: Mapping[str, np.ndarray] | None = None,
        node_uuid_bytes: np.ndarray | None = None,
        edge_uuid_bytes: np.ndarray | None = None,
        node_provenance_rows: np.ndarray | None = None,
        edge_provenance_rows: np.ndarray | None = None,
        parent_indices: np.ndarray | None = None,
        parent_validity: np.ndarray | None = None,
        directed: bool = True,
    ) -> None:
        self.ids = list(ids)
        self.sources = np.ascontiguousarray(sources, dtype=np.uint64)
        self.targets = np.ascontiguousarray(targets, dtype=np.uint64)
        self.x = None if x is None else np.ascontiguousarray(x, dtype=np.float64)
        self.y = None if y is None else np.ascontiguousarray(y, dtype=np.float64)
        self.node_attrs = dict(node_attrs or {})
        self.edge_ids = list(edge_ids or [])
        self.edge_attrs = dict(edge_attrs or {})
        self.node_uuid_bytes = node_uuid_bytes
        self.edge_uuid_bytes = edge_uuid_bytes
        self.node_provenance_rows = node_provenance_rows
        self.edge_provenance_rows = edge_provenance_rows
        self.parent_indices = parent_indices
        self.parent_validity = parent_validity
        self.directed = bool(directed)

    @property
    def n_nodes(self) -> int:
        return len(self.ids)

    @property
    def n_edges(self) -> int:
        return int(len(self.sources))


class GraphProjectionError(ValueError):
    """Stable GraphForge projection validation failure."""

    def __init__(
        self, code: str, message: str, *, field: str | None = None, row: int | None = None
    ):
        self.code = code
        self.field = field
        self.row = row
        context = "".join(
            part
            for part in (
                f" field={field}" if field is not None else "",
                f" row={row}" if row is not None else "",
            )
        )
        super().__init__(f"{code}:{context} {message}".strip())


def looks_like_graphforge_tables(
    nodes: Any,
    edges: Any,
    mapping: Mapping[str, str] | None = None,
) -> bool:
    """True when both tables expose GraphForge UUID identity columns.

    Honors the same ``mapping`` overrides as ``from_graphforge_tables``.
    """
    try:
        node_names = set(_table_column_names(nodes))
        edge_names = set(_table_column_names(edges))
    except (GraphProjectionError, TypeError, ValueError, AttributeError):
        return False
    mapping = mapping or {}
    node_id_field = mapping.get("node_uuid", "node_uuid")
    edge_id_field = mapping.get("edge_uuid", "edge_uuid")
    return node_id_field in node_names and edge_id_field in edge_names


def resolve_graph_data(
    nodes: Any,
    edges: Any = None,
    *,
    x: Any = None,
    y: Any = None,
    directed: bool = True,
    mapping: Mapping[str, str] | None = None,
) -> GraphData:
    """Resolve xyg-native pairs, a ready ``GraphData``, or GraphForge tables.

    GraphForge tables (canonical ``node_uuid`` / ``edge_uuid`` columns, or the
    same fields via ``mapping``) route through Rust identity validation.
    Generic id/source/target inputs keep the xyg-native path (REQ-API-3).
    """
    if isinstance(nodes, GraphData):
        if edges is not None:
            raise TypeError(
                "when nodes is GraphData, edges must be omitted "
                "(pass GraphData alone or pass table/sequence pairs)"
            )
        return nodes
    if edges is None:
        raise TypeError("graph edges are required unless nodes is GraphData")
    if looks_like_graphforge_tables(nodes, edges, mapping):
        data = from_graphforge_tables(nodes, edges, mapping=mapping, directed=directed)
        if x is not None or y is not None:
            xs = None if x is None else np.ascontiguousarray(_as_1d(x, "x"), dtype=np.float64)
            ys = None if y is None else np.ascontiguousarray(_as_1d(y, "y"), dtype=np.float64)
            if (xs is None) ^ (ys is None):
                raise ValueError("x and y must both be provided or both omitted")
            if xs is not None and (
                len(xs) != data.n_nodes or (ys is not None and len(ys) != data.n_nodes)
            ):
                raise ValueError("x/y must match node count")
            data.x = xs
            data.y = ys
        return data
    return normalize_graph_inputs(nodes, edges, x=x, y=y, directed=directed)


def _json_scalar(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, np.generic):
        value = value.item()
    if isinstance(value, (bytes, bytearray)):
        return value.decode("utf-8", errors="replace")
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value
    if isinstance(value, int):
        # Preserve integers beyond JSON/JS safe range as decimal strings.
        if abs(value) > (2**53 - 1):
            return str(value)
        return value
    if isinstance(value, float):
        return value
    return str(value)


def projection_tooltip_rows(
    data: GraphData,
) -> tuple[list[dict[str, Any]] | None, list[dict[str, Any]] | None]:
    """Build node/edge semantic hover rows from a validated projection.

    Returns ``(None, None)`` for generic xyg-native graphs with no attrs. Rows
    are source-indexed; callers attach them only when render LOD did not drop
    nodes/edges.
    """
    has_projection = (
        data.node_uuid_bytes is not None
        or data.edge_uuid_bytes is not None
        or bool(data.node_attrs)
        or bool(data.edge_attrs)
        or data.node_provenance_rows is not None
        or data.edge_provenance_rows is not None
    )
    if not has_projection:
        return None, None

    node_rows: list[dict[str, Any]] = []
    for i in range(data.n_nodes):
        row: dict[str, Any] = {"id": str(data.ids[i])}
        if data.node_provenance_rows is not None:
            row["provenance_row"] = int(data.node_provenance_rows[i])
        for key, col in data.node_attrs.items():
            row[str(key)] = _json_scalar(col[i])
        node_rows.append(row)

    edge_rows: list[dict[str, Any]] = []
    for i in range(data.n_edges):
        src = int(data.sources[i])
        tgt = int(data.targets[i])
        row = {
            "source": str(data.ids[src]),
            "target": str(data.ids[tgt]),
        }
        if data.edge_ids:
            row["edge_id"] = str(data.edge_ids[i])
        if data.edge_provenance_rows is not None:
            row["provenance_row"] = int(data.edge_provenance_rows[i])
        for key, col in data.edge_attrs.items():
            row[str(key)] = _json_scalar(col[i])
        edge_rows.append(row)
    return node_rows, edge_rows


def resolve_encoding_values(
    data: GraphData,
    values: Any,
    *,
    where: str = "node",
) -> Any:
    """Resolve ``color=`` / ``size=`` when the value names a projection column."""
    if not isinstance(values, str):
        return values
    attrs = data.node_attrs if where == "node" else data.edge_attrs
    if values in attrs:
        return attrs[values]
    return values


def _as_1d(values: Any, name: str) -> np.ndarray:
    arr = np.asarray(values)
    if arr.ndim != 1:
        raise ValueError(f"{name} must be 1-D")
    return arr


def _table_column_names(table: Any) -> list[str]:
    if isinstance(table, Mapping):
        return [str(name) for name in table]
    names = getattr(table, "column_names", None)
    if names is not None:
        return [str(name) for name in names]
    columns = getattr(table, "columns", None)
    if columns is not None and all(isinstance(name, str) for name in columns):
        return list(columns)
    schema = getattr(table, "schema", None)
    if schema is not None and getattr(schema, "names", None) is not None:
        return [str(name) for name in schema.names]
    raise GraphProjectionError(
        "GF_GRAPH_TABLE",
        "expected a mapping or Arrow/table-like object with named columns",
    )


def _table_column(table: Any, name: str) -> Any:
    try:
        column = table[name]
    except (KeyError, IndexError, TypeError):
        getter = getattr(table, "column", None)
        if not callable(getter):
            raise GraphProjectionError(
                "GF_GRAPH_FIELD_MISSING", f"required column {name!r} is absent", field=name
            ) from None
        column = getter(name)
    combine_chunks = getattr(column, "combine_chunks", None)
    if callable(combine_chunks):
        column = combine_chunks()
    to_numpy = getattr(column, "to_numpy", None)
    if callable(to_numpy):
        try:
            return to_numpy(zero_copy_only=False)
        except TypeError:
            return to_numpy()
    to_pylist = getattr(column, "to_pylist", None)
    if callable(to_pylist):
        return to_pylist()
    return column


def _uuid_bytes(values: Any, field: str) -> tuple[list[str], np.ndarray]:
    raw = list(values)
    out = np.empty((len(raw), 16), dtype=np.uint8)
    text: list[str] = []
    for row, value in enumerate(raw):
        if value is None:
            raise GraphProjectionError(
                "GF_GRAPH_UUID_NULL", "UUID values cannot be null", field=field, row=row
            )
        try:
            if isinstance(value, UUID):
                parsed = value
            elif isinstance(value, (bytes, bytearray, memoryview)):
                data = bytes(value)
                if len(data) != 16:
                    raise ValueError("binary UUID must contain exactly 16 bytes")
                parsed = UUID(bytes=data)
            else:
                parsed = UUID(str(value))
        except (TypeError, ValueError, AttributeError) as exc:
            raise GraphProjectionError(
                "GF_GRAPH_UUID_INVALID", str(exc), field=field, row=row
            ) from exc
        text.append(str(parsed))
        out[row] = np.frombuffer(parsed.bytes, dtype=np.uint8)
    return text, np.ascontiguousarray(out)


def _resolve_column(
    names: list[str],
    explicit: str | None,
    candidates: tuple[str, ...],
    semantic: str,
) -> str:
    if explicit is not None:
        if explicit not in names:
            raise GraphProjectionError(
                "GF_GRAPH_FIELD_MISSING",
                f"configured {semantic} column {explicit!r} is absent",
                field=explicit,
            )
        return explicit
    matches = [name for name in candidates if name in names]
    if len(matches) == 1:
        return matches[0]
    if not matches:
        raise GraphProjectionError(
            "GF_GRAPH_FIELD_MISSING",
            f"no {semantic} column found; expected one of {candidates!r}",
        )
    raise GraphProjectionError(
        "GF_GRAPH_FIELD_AMBIGUOUS",
        f"multiple {semantic} columns are present: {matches!r}; provide mapping=",
    )


def _attrs(
    table: Any, names: list[str], excluded: set[str], expected: int
) -> dict[str, np.ndarray]:
    attrs: dict[str, np.ndarray] = {}
    for name in names:
        if name in excluded:
            continue
        values = np.asarray(_table_column(table, name))
        if values.ndim != 1 or len(values) != expected:
            raise GraphProjectionError(
                "GF_GRAPH_COLUMN_SHAPE",
                f"attribute columns must be one-dimensional with {expected} rows",
                field=name,
            )
        attrs[name] = values
    return attrs


def normalize_graph_inputs(
    nodes: Any,
    edges: Any,
    *,
    x: Any = None,
    y: Any = None,
    directed: bool = True,
) -> GraphData:
    """Accept ids + edge pairs/columns (xyg-native formats)."""
    if isinstance(nodes, Mapping) and "id" in nodes:
        ids = list(_as_1d(nodes["id"], "nodes.id"))
        attrs = {
            key: np.asarray(val) for key, val in nodes.items() if key != "id" and not callable(val)
        }
    elif hasattr(nodes, "columns") and "id" in getattr(nodes, "columns", []):
        ids = list(nodes["id"])
        attrs = {col: np.asarray(nodes[col]) for col in nodes.columns if col != "id"}
    else:
        ids = list(_as_1d(nodes, "nodes"))
        attrs = {}

    id_to_index = {node_id: i for i, node_id in enumerate(ids)}
    if len(id_to_index) != len(ids):
        raise ValueError("graph node ids must be unique")

    if isinstance(edges, Mapping) and "source" in edges and "target" in edges:
        src_ids = _as_1d(edges["source"], "edges.source")
        tgt_ids = _as_1d(edges["target"], "edges.target")
    elif hasattr(edges, "columns"):
        cols = list(edges.columns)
        if "source" not in cols or "target" not in cols:
            raise ValueError("edge table requires source and target columns")
        src_ids = np.asarray(edges["source"])
        tgt_ids = np.asarray(edges["target"])
    else:
        pairs = np.asarray(edges, dtype=object)
        if pairs.ndim == 2 and pairs.shape[1] == 2:
            src_ids = pairs[:, 0]
            tgt_ids = pairs[:, 1]
        elif isinstance(edges, Sequence) and edges and isinstance(edges[0], (tuple, list)):
            src_ids = np.asarray([e[0] for e in edges], dtype=object)
            tgt_ids = np.asarray([e[1] for e in edges], dtype=object)
        else:
            raise ValueError(
                "edges must be (source, target) pairs, or a mapping/table with "
                "source and target columns"
            )

    if len(src_ids) != len(tgt_ids):
        raise ValueError("edge source/target lengths differ")

    sources = np.empty(len(src_ids), dtype=np.uint64)
    targets = np.empty(len(tgt_ids), dtype=np.uint64)
    for i, (s, t) in enumerate(zip(src_ids, tgt_ids, strict=True)):
        if s not in id_to_index or t not in id_to_index:
            raise ValueError(f"edge endpoints {(s, t)!r} are not in nodes")
        sources[i] = id_to_index[s]
        targets[i] = id_to_index[t]

    xs = None if x is None else np.ascontiguousarray(_as_1d(x, "x"), dtype=np.float64)
    ys = None if y is None else np.ascontiguousarray(_as_1d(y, "y"), dtype=np.float64)
    if (xs is None) ^ (ys is None):
        raise ValueError("x and y must both be provided or both omitted")
    if xs is not None and len(xs) != len(ids):
        raise ValueError("x/y must match node count")

    return GraphData(
        ids,
        sources,
        targets,
        x=xs,
        y=ys,
        node_attrs=attrs,
        directed=directed,
    )


def from_networkx(graph: Any, *, pos: Mapping[Any, Sequence[float]] | None = None) -> GraphData:
    """Thin NetworkX adapter — optional convenience, not required."""
    try:
        nodes = list(graph.nodes())
    except Exception as exc:  # noqa: BLE001 — surface adapter errors clearly
        raise TypeError("from_networkx expects a NetworkX-like graph") from exc
    edges = list(graph.edges())
    x = y = None
    if pos is not None:
        x = np.asarray([float(pos[n][0]) for n in nodes], dtype=np.float64)
        y = np.asarray([float(pos[n][1]) for n in nodes], dtype=np.float64)
    directed = bool(getattr(graph, "is_directed", lambda: False)())
    return normalize_graph_inputs(nodes, edges, x=x, y=y, directed=directed)


def from_graphforge_tables(
    nodes: Any,
    edges: Any,
    *,
    mapping: Mapping[str, str] | None = None,
    directed: bool = True,
) -> GraphData:
    """Build identity-preserving graph data from canonical GraphForge tables.

    The canonical fields are ``node_uuid``, ``edge_uuid``, ``src_uuid`` and
    ``dst_uuid``. ``source_uuid``/``target_uuid`` are accepted for canonical
    algorithm-result projections. An explicit ``mapping`` resolves tables that
    contain more than one candidate; inference never guesses between matches.
    """
    mapping = dict(mapping or {})
    node_names = _table_column_names(nodes)
    edge_names = _table_column_names(edges)
    node_id_field = _resolve_column(
        node_names, mapping.get("node_uuid"), ("node_uuid",), "node UUID"
    )
    edge_id_field = _resolve_column(
        edge_names, mapping.get("edge_uuid"), ("edge_uuid",), "edge UUID"
    )
    source_field = _resolve_column(
        edge_names,
        mapping.get("source_uuid"),
        ("src_uuid", "source_uuid"),
        "edge source UUID",
    )
    target_field = _resolve_column(
        edge_names,
        mapping.get("target_uuid"),
        ("dst_uuid", "target_uuid"),
        "edge target UUID",
    )

    ids, node_uuid_bytes = _uuid_bytes(_table_column(nodes, node_id_field), node_id_field)
    edge_ids, edge_uuid_bytes = _uuid_bytes(_table_column(edges, edge_id_field), edge_id_field)
    source_ids, source_uuid_bytes = _uuid_bytes(_table_column(edges, source_field), source_field)
    target_ids, target_uuid_bytes = _uuid_bytes(_table_column(edges, target_field), target_field)

    parent_field = mapping.get("parent_uuid", "parent_uuid")
    parent_uuid_bytes: np.ndarray | None = None
    parent_validity: np.ndarray | None = None
    if parent_field in node_names:
        raw_parents = list(_table_column(nodes, parent_field))
        parent_uuid_bytes = np.zeros((len(raw_parents), 16), dtype=np.uint8)
        parent_validity = np.zeros(len(raw_parents), dtype=np.uint8)
        for row, value in enumerate(raw_parents):
            if value is None:
                continue
            _, encoded = _uuid_bytes([value], parent_field)
            parent_uuid_bytes[row] = encoded[0]
            parent_validity[row] = 1

    try:
        handle = _native.graph_projection_create(
            node_uuid_bytes,
            edge_uuid_bytes,
            source_uuid_bytes,
            target_uuid_bytes,
            parent_ids=parent_uuid_bytes,
            parent_validity=parent_validity,
            directed=directed,
        )
    except _native.GraphProjectionNativeError as exc:
        code = {
            -1: "GF_GRAPH_ARGUMENT",
            -2: "GF_GRAPH_CAPACITY",
            -3: "GF_GRAPH_UUID_INVALID",
            -4: "GF_GRAPH_NODE_DUPLICATE",
            -5: "GF_GRAPH_EDGE_DUPLICATE",
            -6: "GF_GRAPH_ENDPOINT_MISSING",
            -7: "GF_GRAPH_HANDLE_STALE",
            -8: "GF_GRAPH_OUTPUT_CAPACITY",
        }.get(exc.status, "GF_GRAPH_NATIVE")
        field = None
        row = None
        if exc.status == -6:
            known = set(ids)
            for candidate_field, candidate_values in (
                (source_field, source_ids),
                (target_field, target_ids),
            ):
                missing = next(
                    (i for i, value in enumerate(candidate_values) if value not in known), None
                )
                if missing is not None:
                    field, row = candidate_field, missing
                    break
        raise GraphProjectionError(code, str(exc), field=field, row=row) from exc
    try:
        (
            node_uuid_bytes,
            edge_uuid_bytes,
            sources,
            targets,
            parent_indices,
            parent_validity_out,
            native_directed,
        ) = _native.graph_projection_copy(handle)
    finally:
        _native.graph_projection_destroy(handle)

    node_provenance_field = mapping.get("node_provenance_row", "provenance_row")
    edge_provenance_field = mapping.get("edge_provenance_row", "provenance_row")
    node_provenance = (
        np.ascontiguousarray(_table_column(nodes, node_provenance_field), dtype=np.uint64)
        if node_provenance_field in node_names
        else np.arange(len(ids), dtype=np.uint64)
    )
    edge_provenance = (
        np.ascontiguousarray(_table_column(edges, edge_provenance_field), dtype=np.uint64)
        if edge_provenance_field in edge_names
        else np.arange(len(edge_ids), dtype=np.uint64)
    )
    if len(node_provenance) != len(ids) or len(edge_provenance) != len(edge_ids):
        raise GraphProjectionError(
            "GF_GRAPH_PROVENANCE_LENGTH", "provenance columns must match their table row counts"
        )

    node_excluded = {node_id_field, node_provenance_field, parent_field}
    edge_excluded = {
        edge_id_field,
        source_field,
        target_field,
        edge_provenance_field,
    }
    return GraphData(
        ids,
        sources,
        targets,
        node_attrs=_attrs(nodes, node_names, node_excluded, len(ids)),
        edge_ids=edge_ids,
        edge_attrs=_attrs(edges, edge_names, edge_excluded, len(edge_ids)),
        node_uuid_bytes=node_uuid_bytes,
        edge_uuid_bytes=edge_uuid_bytes,
        node_provenance_rows=node_provenance,
        edge_provenance_rows=edge_provenance,
        parent_indices=parent_indices,
        parent_validity=parent_validity_out,
        directed=native_directed,
    )


def run_layout(
    data: GraphData,
    layout: str = DEFAULT_LAYOUT,
    *,
    seed: int = 0,
    iterations: int = 300,
    node_budget: int = 200_000,
    edge_budget: int = 500_000,
    viewport: tuple[float, float, float, float] | None = None,
) -> tuple[np.ndarray, np.ndarray, dict[str, Any]]:
    """Layout via Rust ABI, then emit a perceptually bounded render graph.

    Layout runs on the **full** source graph (Barnes–Hut repulsion when
    ``n > 500``). LOD reduction happens once via ``graph_build_render`` —
    hosts must not double-sample edges for draw.
    """
    layout_name = str(layout or DEFAULT_LAYOUT).strip().lower()
    n = data.n_nodes
    e = data.n_edges
    sources = data.sources
    targets = data.targets
    alpha = None
    layout_id = _native.graph_layout_id(layout_name)
    use_progressive = iterations > 0 and layout_id in _native._GRAPH_PROGRESSIVE_FORCE
    if use_progressive:
        handle = _native.graph_force_create(
            n,
            sources,
            targets,
            x=data.x,
            y=data.y,
            seed=seed,
            algorithm=layout_id,
        )
        try:
            x, y, alpha = _native.graph_force_tick(handle, n, max(1, int(iterations)))
        finally:
            _native.graph_force_destroy(handle)
    else:
        if layout_name == "preset" and (data.x is None or data.y is None):
            raise ValueError("layout='preset' requires x and y")
        x, y = _native.graph_layout(
            layout_name,
            n,
            sources,
            targets,
            x=data.x,
            y=data.y,
            seed=seed,
        )

    rx, ry, member_of, edge_s, edge_t, tier, edges_kept = _native.graph_build_render(
        x,
        y,
        sources,
        targets,
        node_budget=int(node_budget),
        edge_budget=int(edge_budget),
        viewport=viewport,
    )
    meta: dict[str, Any] = {
        "layout": layout_name,
        "seed": int(seed),
        "lod_tier": int(tier),
        "edges_kept": int(edges_kept),
        "nodes_kept": int(len(rx)),
        "n_nodes": int(len(rx)),
        "n_edges": int(len(edge_s)),
        "source_n_nodes": int(n),
        "source_n_edges": int(e),
        "member_of": member_of,
        "render_sources": edge_s,
        "render_targets": edge_t,
        "node_budget": int(node_budget),
        "edge_budget": int(edge_budget),
    }
    if use_progressive:
        meta["iterations"] = int(iterations)
        meta["alpha"] = float(alpha) if alpha is not None else None
    return rx, ry, meta
