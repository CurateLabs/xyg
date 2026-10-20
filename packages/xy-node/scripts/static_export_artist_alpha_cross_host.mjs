#!/usr/bin/env node
/**
 * Cross-host artist-alpha matrix (#1006): role (fill, stroke) x source
 * (constant/scalar, per-item) x paint (keyword transparent, explicit #00000000, opaque,
 * translucent) with a per-item artist-alpha channel. Prints one entry per case:
 * the encoded Scene, or the rejection text, so Python can compare bytes.
 */

import { Figure, sceneExportSupportReason } from "../src/index.js";

const PAINTS = { keyword: "transparent", hex0: "#00000000", opaque: "#ff0000", translucent: "#ff000080" };
// A per-item array has no keyword form: the keyword and an explicit #00000000 are the same row.
const ROWS = { keyword: [0, 0, 0, 0], hex0: [0, 0, 0, 0], opaque: [1, 0, 0, 1], translucent: [1, 0, 0, 128 / 255] };

function build(role, source, paint) {
  const f = new Figure({ width: 320, height: 240 });
  f.setAxisDomain("x", [0, 1]);
  f.setAxisDomain("y", [0, 1]);
  const css = PAINTS[paint];
  const value = source === "per_item" ? [ROWS[paint], ROWS[paint]] : css;
  const opts = { style: { opacity: 1 } };
  if (role === "fill") {
    opts.color = value;
  } else {
    opts.color = "#00ff00";
    opts.stroke = value;
    opts.style.stroke_width = 4;
  }
  f.scatter([0.3, 0.7], [0.5, 0.5], opts);
  f.traces[0].id = 0;
  f.traces[0].style_channels = { ...(f.traces[0].style_channels ?? {}), artist_alpha: { values: Float64Array.of(0.5, 0.5) } };
  return f;
}

const out = {};
for (const role of ["fill", "stroke"]) {
  for (const source of ["constant", "per_item"]) {
    for (const paint of Object.keys(PAINTS)) {
      const key = `${role}/${source}/${paint}`;
      try {
        const figure = build(role, source, paint);
        const reason = sceneExportSupportReason(figure);
        out[key] = reason ? { error: reason } : { scene_b64: Buffer.from(figure.toScene()).toString("base64") };
      } catch (error) {
        out[key] = { error: String(error?.message ?? error) };
      }
    }
  }
}
process.stdout.write(`${JSON.stringify(out)}\n`);
