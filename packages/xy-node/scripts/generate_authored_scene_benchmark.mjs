#!/usr/bin/env node
/** Generate Node's independently-authored #116 four-tier Scene artifacts.
 *
 * This intentionally uses only the public Node Figure surface.  CI compares
 * these files byte-for-byte with Python's matching public Figure artifacts;
 * neither host is allowed to consume the other host's Scene as its input.
 */
import crypto from "node:crypto";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { Figure } from "../src/index.js";

const counts = [100, 10_000, 100_000, 1_000_000];
const here = path.dirname(fileURLToPath(import.meta.url));
const fixture = JSON.parse(fs.readFileSync(path.join(here, "../../../tests/fixtures/authored_scene_v20.json"), "utf8"));
const outputIndex = process.argv.indexOf("--output-dir");
if (outputIndex < 0 || !process.argv[outputIndex + 1]) throw new Error("--output-dir is required");
const outputDir = path.resolve(process.argv[outputIndex + 1]);
fs.mkdirSync(outputDir, { recursive: true });

function authoredScene(count) {
  const authoring = fixture.authoring;
  const x = Float64Array.from({ length: count }, (_, index) => index / (count - 1));
  const y = Float64Array.from({ length: count }, (_, index) => ((index * 37) % 997) / 498 - 1);
  const figure = new Figure({
    width: authoring.viewport[0], height: authoring.viewport[1], title: authoring.title,
    legend: authoring.legend,
    annotations: [
      { kind: "callout", ...authoring.callout },
      { kind: "callout", ...authoring.wrapped_callout },
    ],
  });
  figure.style = authoring.style;
  figure.setAxis("x", authoring.axes.x); figure.setAxis("y", authoring.axes.y);
  figure.colorbarOptions = authoring.colorbar;
  // Match Python's explicit ``density=False``: the evidence exercises the
  // supported direct Scene transport at every tier, not Node's interactive
  // density heuristic.
  // Node's public Figure keeps paint options under ``style``.  Preserve the
  // fixture's declarative values explicitly rather than relying on Node's
  // matching defaults: Python's public authoring makes the diamond literal.
  figure.scatter(x, y, {
    id: authoring.scatter.id,
    name: authoring.scatter.name,
    style: {
      color: authoring.scatter.color,
      size: authoring.scatter.size,
      opacity: authoring.scatter.opacity,
      symbol: authoring.scatter.symbol,
    },
    force_direct: true,
  });
  return figure.toScene();
}

const measurements = counts.map((count) => {
  const scene = authoredScene(count);
  const file = `authored-scene-${count}.bin`;
  fs.writeFileSync(path.join(outputDir, file), scene);
  return { count, file, sceneBytes: scene.byteLength, sceneSha256: crypto.createHash("sha256").update(scene).digest("hex") };
});
const report = { schema: "xyg-authored-scene-workload-v1", measurements };
fs.writeFileSync(path.join(outputDir, "authored-scene-manifest.json"), `${JSON.stringify(report, null, 2)}\n`);
console.log(JSON.stringify(report));
