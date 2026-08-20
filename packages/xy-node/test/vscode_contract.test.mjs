import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

const vscodePath = path.join(
  path.dirname(fileURLToPath(import.meta.url)),
  "..",
  "src",
  "vscode.js",
);

test("vscode.js points webviews at the host-neutral paint client", () => {
  const src = fs.readFileSync(vscodePath, "utf8");
  assert.equal(
    src.includes("python/xyg/static"),
    false,
    "VS Code webviews must not be documented as loading python/xyg/static",
  );
  assert.ok(src.includes("@curatelabs/xyg"), "webview contract must name @curatelabs/xyg");
  assert.ok(src.includes("toHtml"), "extension host should re-export toHtml");
});
