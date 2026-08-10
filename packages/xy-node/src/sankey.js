/**
 * Thin Sankey composition over `xy_sankey_layout` (host-parity.md).
 * Emits link + node ribbons (Python parity): gradient flow bands, not midlines.
 */

import { sankeyLayout } from "./abi.js";
import { DEFAULT_PALETTE } from "./encode.js";
import { composeRibbon } from "./marks/ribbon.js";

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

  const palette = opts.colors ?? DEFAULT_PALETTE;
  if (opts.colors != null && opts.colors.length !== ids.length) {
    throw new RangeError(
      `sankey colors must have one entry per node (${ids.length}); got ${opts.colors.length}`,
    );
  }
  const nodeCss = ids.map((_, i) => palette[i % palette.length]);
  const linkOpacity = opts.linkOpacity ?? 0.4;
  if (!(linkOpacity > 0 && linkOpacity <= 1)) {
    throw new RangeError("sankey linkOpacity must be in (0, 1]");
  }

  const traces = [];
  const nLinks = sources.length;
  if (nLinks > 0) {
    const linkX0 = new Float64Array(nLinks);
    const linkX1 = new Float64Array(nLinks);
    const sourceLo = new Float64Array(nLinks);
    const sourceHi = new Float64Array(nLinks);
    const targetLo = new Float64Array(nLinks);
    const targetHi = new Float64Array(nLinks);
    const linkColors = [];
    const linkTargets = [];
    const tooltipRows = [];
    for (let i = 0; i < nLinks; i += 1) {
      const s = Number(sources[i]);
      const t = Number(targets[i]);
      linkX0[i] = layout.x1[s];
      linkX1[i] = layout.x0[t];
      sourceLo[i] = layout.sourceY0[i];
      sourceHi[i] = layout.sourceY1[i];
      targetLo[i] = layout.targetY0[i];
      targetHi[i] = layout.targetY1[i];
      linkColors.push(nodeCss[s]);
      linkTargets.push(nodeCss[t]);
      tooltipRows.push({
        source: ids[s],
        target: ids[t],
        value: values[i],
      });
    }
    const linkRibbon = composeRibbon(linkX0, linkX1, sourceLo, sourceHi, targetLo, targetHi, {
      color: linkColors,
      colorTarget: linkTargets,
      opacity: linkOpacity,
      name: opts.name == null ? null : `${opts.name}:links`,
      style: opts.style,
      tooltipRows,
    });
    traces.push(...linkRibbon.traces);
  }

  // Nodes: equal-span ribbons are axis-aligned rectangles (Python parity).
  const nodeRibbon = composeRibbon(
    layout.x0,
    layout.x1,
    layout.y0,
    layout.y1,
    layout.y0,
    layout.y1,
    {
      color: nodeCss,
      opacity: 1.0,
      name: opts.name == null ? null : `${opts.name}:nodes`,
      tooltipRows: ids.map((id, i) => ({ node: id, value: layout.value[i] })),
    },
  );
  traces.push(...nodeRibbon.traces);

  return {
    layout,
    ids,
    traces,
  };
}
