"""Sankey layout — name resolution and host error text around the Rust ABI.

A Sankey is not a new primitive so much as a *placement*: given nodes, weighted
links and a box, decide where every node rectangle and every ribbon endpoint
goes. That decision is what the roadmap means by "requires layout work"
(spec/api/chart-roadmap.md item 30). Placement math lives in the native core
(`xyg_sankey_layout` / `_native.sankey_layout`) so both hosts stay bit-identical;
this module only resolves names to dense indices and maps return codes to
error *text*.

The output is in **data space**: x runs 0..1 across the layers and y runs 0..1
down the diagram, so the caller maps it through ordinary axes and every
renderer inherits the placement unchanged. Nothing here knows about pixels.
"""

from __future__ import annotations

import math
from collections import Counter
from dataclasses import dataclass, field
from typing import Any, Optional

import numpy as np

from . import _native

_ALIGNMENTS = frozenset({"justify", "left", "right", "center"})


@dataclass
class SankeyNode:
    """One placed node. `x0/x1/y0/y1` are in the 0..1 layout box."""

    name: str
    index: int
    layer: int = 0
    order: int = 0
    value: float = 0.0
    x0: float = 0.0
    x1: float = 0.0
    y0: float = 0.0
    y1: float = 0.0
    incoming: list[int] = field(default_factory=list)
    outgoing: list[int] = field(default_factory=list)


@dataclass
class SankeyLink:
    """One placed link. The two endpoints are vertical spans, not points."""

    source: int
    target: int
    value: float
    index: int = 0
    source_y0: float = 0.0
    source_y1: float = 0.0
    target_y0: float = 0.0
    target_y1: float = 0.0
    label: Optional[str] = None


@dataclass
class SankeyLayout:
    nodes: list[SankeyNode]
    links: list[SankeyLink]
    layers: int


def _resolve_nodes(
    nodes: Optional[list[Any]], links: list[tuple[Any, Any, float]]
) -> tuple[list[str], dict[str, int]]:
    """Node names in a stable order, plus their index.

    When `nodes` is omitted the order is first-appearance across the links,
    which keeps a diagram's column order predictable from the source data
    rather than from a set's iteration order.
    """
    if nodes is not None:
        names = [str(n) for n in nodes]
        duplicates = sorted(name for name, count in Counter(names).items() if count > 1)
        if duplicates:
            raise ValueError(f"sankey nodes must be unique; repeated: {duplicates}")
    else:
        names = []
        seen: set[str] = set()
        for source, target, _value in links:
            for endpoint in (str(source), str(target)):
                if endpoint not in seen:
                    seen.add(endpoint)
                    names.append(endpoint)
    return names, {name: i for i, name in enumerate(names)}


def compute_layout(
    links: list[tuple[Any, Any, float]],
    *,
    nodes: Optional[list[Any]] = None,
    node_width: float = 0.02,
    node_padding: float = 0.02,
    align: str = "justify",
    iterations: int = 6,
) -> SankeyLayout:
    """Place a Sankey in a 0..1 x 0..1 box.

    Args:
        links: ``(source, target, value)`` triples. Endpoints are node names.
        nodes: Explicit node order. Defaults to first appearance in `links`.
        node_width: Node rectangle width, as a fraction of the box.
        node_padding: Vertical gap between nodes in a layer, as a fraction.
        align: ``"justify"`` (default) flushes sinks to the last layer.
        iterations: Barycentre sweeps for crossing minimisation.

    Returns:
        A `SankeyLayout` whose coordinates are all in 0..1.
    """
    if align not in _ALIGNMENTS:
        raise ValueError(f"sankey align must be one of {sorted(_ALIGNMENTS)}")
    if not links:
        raise ValueError("sankey needs at least one link")
    if not 0.0 < node_width < 1.0:
        raise ValueError("sankey node_width must be between 0 and 1")
    if not 0.0 <= node_padding < 1.0:
        raise ValueError("sankey node_padding must be between 0 and 1")

    names, index_of = _resolve_nodes(nodes, links)
    placed_nodes = [SankeyNode(name=name, index=i) for i, name in enumerate(names)]
    placed_links: list[SankeyLink] = []
    sources: list[int] = []
    targets: list[int] = []
    values: list[float] = []
    seen: set[tuple[int, int]] = set()
    for position, (source, target, value) in enumerate(links):
        source_name, target_name = str(source), str(target)
        for endpoint in (source_name, target_name):
            if endpoint not in index_of:
                raise ValueError(
                    f"sankey link {position} references unknown node {endpoint!r}; "
                    f"known nodes are {names}"
                )
        si, ti = index_of[source_name], index_of[target_name]
        if si == ti:
            raise ValueError(
                f"sankey link {position} connects {source_name!r} to itself; "
                "a self-link has no width to draw and no direction to flow in"
            )
        weight = float(value)
        if not math.isfinite(weight) or weight < 0.0:
            raise ValueError(
                f"sankey link {position} ({source_name} -> {target_name}) has value {value!r}; "
                "link values must be finite and non-negative"
            )
        if (si, ti) in seen:
            raise ValueError(
                f"sankey has duplicate link {source_name!r} -> {target_name!r}; "
                "sum the values into one link"
            )
        seen.add((si, ti))
        link = SankeyLink(source=si, target=ti, value=weight, index=len(placed_links))
        placed_nodes[si].outgoing.append(link.index)
        placed_nodes[ti].incoming.append(link.index)
        placed_links.append(link)
        sources.append(si)
        targets.append(ti)
        values.append(weight)

    try:
        native = _native.sankey_layout(
            np.asarray(sources, dtype=np.uint64),
            np.asarray(targets, dtype=np.uint64),
            np.asarray(values, dtype=np.float64),
            n_nodes=len(placed_nodes),
            node_width=node_width,
            node_padding=node_padding,
            align=align,
            iterations=iterations,
        )
    except _native.SankeyLayoutError as exc:
        if exc.code == -2:
            cyclic = sorted(names[int(i)] for i in exc.err_nodes)
            raise ValueError(
                f"sankey links form a cycle through {cyclic}; a Sankey flows left to right, "
                "so every link must point to a later stage. Break the cycle or aggregate "
                "the nodes involved."
            ) from None
        if exc.code == -3 and len(exc.err_nodes) >= 2:
            layer = int(exc.err_nodes[0])
            count = int(exc.err_nodes[1])
            raise ValueError(
                f"sankey node_padding {node_padding:g} leaves no room for nodes: "
                f"layer {layer} holds {count} of them, so node_padding must "
                f"stay below {1.0 / (count - 1):g}"
            ) from None
        raise ValueError(str(exc)) from None

    for i, node in enumerate(placed_nodes):
        node.layer = int(native["layer"][i])
        node.value = float(native["value"][i])
        node.x0 = float(native["x0"][i])
        node.y0 = float(native["y0"][i])
        node.x1 = float(native["x1"][i])
        node.y1 = float(native["y1"][i])
    for i, link in enumerate(placed_links):
        link.source_y0 = float(native["source_y0"][i])
        link.source_y1 = float(native["source_y1"][i])
        link.target_y0 = float(native["target_y0"][i])
        link.target_y1 = float(native["target_y1"][i])
    return SankeyLayout(nodes=placed_nodes, links=placed_links, layers=int(native["layers"]))
