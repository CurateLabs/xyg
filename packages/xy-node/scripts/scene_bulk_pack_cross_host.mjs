import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import { sceneChromePack, sceneFigureSupportMaterialize, sceneXyafBulkPack } from "../src/sceneBulkNative.js";
import { createHash } from "node:crypto";

const root = join(dirname(fileURLToPath(import.meta.url)), "../../..");
const fixture = JSON.parse(
  readFileSync(join(root, "tests/fixtures/scene_bulk_pack_minimal.json"), "utf8"),
);

const sha = (buf) => createHash("sha256").update(buf).digest("hex");
const chrome = fixture.chrome;
const support = fixture.figure_support;

const xycf = sceneChromePack(chrome);
const fs = sceneFigureSupportMaterialize({
  polar: support.polar,
  colorbarUnsupported: support.colorbar_unsupported,
  hasColorbar: support.has_colorbar,
  hasCustomFont: support.has_custom_font,
  hasBrowserCss: support.has_browser_css,
  hasExtraLegends: support.has_extra_legends,
  annotations: support.annotations,
  axes: support.axes,
  traces: support.traces,
});
const xyaf = sceneXyafBulkPack([
  {
    kind: "text",
    text: "hello",
    x: 0.5,
    y: 0.25,
    style: { color: "#667085" },
  },
]);

// #1006: an axes-fraction text row (XYAF byte 26 = 1, routed through XYAW)
// and the bulk-pack rejection of any other coordinate space (code -14).
const fractionRow = (coordinateSpace) => ({
  kind: "text",
  text: "cell",
  x: 0.25,
  y: 0,
  dy: 8,
  anchor: "middle",
  style: { color: "#667085", label_background: "#dbeafe", coordinate_space: coordinateSpace },
});
const xyafFraction = sceneXyafBulkPack([fractionRow("axes_fraction")]);
let figureFractionCode = null;
try {
  sceneXyafBulkPack([fractionRow("figure_fraction")]);
} catch (error) {
  figureFractionCode = error.code ?? null;
}

process.stdout.write(
  JSON.stringify({
    xyaf_fraction_sha256: sha(xyafFraction),
    xyaf_fraction_byte26: xyafFraction[26],
    figure_fraction_code: figureFractionCode,
    xycf_sha256: sha(xycf),
    xyfs_sha256: sha(fs),
    xyaf_sha256: sha(xyaf),
    xycf_len: xycf.length,
    xyfs_len: fs.length,
    xyaf_len: xyaf.length,
  }) + "\n",
);
