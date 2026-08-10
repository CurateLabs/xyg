/**
 * Thin Sankey composition over `xy_sankey_layout` (host-parity.md).
 * Emits node rectangles as scatter centers + link bands as segments — enough
 * for layout goldens; full band polygons remain a follow-up on both hosts.
 */

import { sankeyLayout } from "./abi.js";

/**
 * @param {Iterable|object} nodes — id list or `{id: [...]}`
 * @param {Iterable|object} links — `{source, target, value}` columns or triples
 * @param {object} [opts]
 */
export function composeSankey(nodes, links, opts = {}) {
  let ids;
  if (nodes != null && typeof nodes === "object" && !Array.isArray(nodes) && "id" in nodes) {
    ids = [...nodes.id];
  } else {
    ids = [...(nodes ?? [])];
  }
  const idToIndex = new Map(ids.map((id, i) => [id, i]));
  if (idToIndex.size !== ids.length) {
    throw new Error("sankey node ids must be unique");
  }

  let srcIds;
  let tgtIds;
  let values;
  if (
    links != null &&
    typeof links === "object" &&
    !Array.isArray(links) &&
    "source" in links &&
    "target" in links
  ) {
    srcIds = [...links.source];
    tgtIds = [...links.target];
    values = Float64Array.from(links.value ?? links.values ?? [], Number);
  } else {
    const rows = [...(links ?? [])];
    srcIds = [];
    tgtIds = [];
    const vals = [];
    for (const row of rows) {
      if (Array.isArray(row)) {
        srcIds.push(row[0]);
        tgtIds.push(row[1]);
        vals.push(Number(row[2] ?? 1));
      } else if (row && typeof row === "object") {
        srcIds.push(row.source);
        tgtIds.push(row.target);
        vals.push(Number(row.value ?? 1));
      } else {
        throw new Error("sankey links must be triples or {source,target,value}");
      }
    }
    values = Float64Array.from(vals);
  }

  const sources = BigUint64Array.from(srcIds, (s) => {
    if (!idToIndex.has(s)) throw new Error(`unknown sankey source ${String(s)}`);
    return BigInt(idToIndex.get(s));
  });
  const targets = BigUint64Array.from(tgtIds, (t) => {
    if (!idToIndex.has(t)) throw new Error(`unknown sankey target ${String(t)}`);
    return BigInt(idToIndex.get(t));
  });

  const layout = sankeyLayout(ids.length, sources, targets, values, {
    nodeWidth: opts.nodeWidth,
    nodePadding: opts.nodePadding,
    align: opts.align,
    iterations: opts.iterations,
  });

  // Node centers for a scatter placeholder; link midlines as segments.
  const cx = new Float64Array(ids.length);
  const cy = new Float64Array(ids.length);
  for (let i = 0; i < ids.length; i += 1) {
    cx[i] = (layout.x0[i] + layout.x1[i]) / 2;
    cy[i] = (layout.y0[i] + layout.y1[i]) / 2;
  }

  const nLinks = sources.length;
  const x0 = new Float64Array(nLinks);
  const y0 = new Float64Array(nLinks);
  const x1 = new Float64Array(nLinks);
  const y1 = new Float64Array(nLinks);
  for (let i = 0; i < nLinks; i += 1) {
    const s = Number(sources[i]);
    const t = Number(targets[i]);
    x0[i] = layout.x1[s];
    y0[i] = (layout.sourceY0[i] + layout.sourceY1[i]) / 2;
    x1[i] = layout.x0[t];
    y1[i] = (layout.targetY0[i] + layout.targetY1[i]) / 2;
  }

  return {
    layout,
    ids,
    traces: [
      {
        kind: "segments",
        name: opts.name == null ? null : `${opts.name}:links`,
        x0,
        y0,
        x1,
        y1,
        style: { color: opts.linkColor ?? "#888888", ...(opts.style ?? {}) },
      },
      {
        kind: "scatter",
        name: opts.name == null ? null : `${opts.name}:nodes`,
        x: cx,
        y: cy,
        style: {
          color: opts.color ?? "#3987e5",
          size: opts.size ?? 10,
          ...(opts.style ?? {}),
        },
      },
    ],
  };
}
