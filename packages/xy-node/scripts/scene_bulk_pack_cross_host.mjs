import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import { sceneChromePack, sceneFigureSupportMaterialize } from "../src/sceneBulkNative.js";
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
  hasCustomFont: support.has_custom_font,
  hasBrowserCss: support.has_browser_css,
  hasExtraLegends: support.has_extra_legends,
  annotations: support.annotations,
  axes: support.axes,
  traces: support.traces,
});

process.stdout.write(
  JSON.stringify({
    xycf_sha256: sha(xycf),
    xyfs_sha256: sha(fs),
    xycf_len: xycf.length,
    xyfs_len: fs.length,
  }) + "\n",
);
