#!/usr/bin/env node
// Copy a separately compiled raw xyg-wasm artifact into the browser package.
// Keeping this separate from js/build.mjs lets native/Python builds remain
// independent of the direct-browser target while CI verifies both paths.
import { copyFileSync, mkdirSync, readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const root = join(here, "..");
const source = process.argv[2]
  ?? join(root, "target", "wasm32-unknown-unknown", "release", "xyg_wasm.wasm");
const output = join(root, "packages", "xy-client", "dist", "xyg-wasm.wasm");
const manifest = JSON.parse(readFileSync(join(root, "spec", "wasm", "abi.json"), "utf8"));
const bytes = readFileSync(source);
const module = await WebAssembly.compile(bytes);
const imports = WebAssembly.Module.imports(module);
if (imports.length) {
  throw new Error(`xyg-wasm must not request ambient imports: ${JSON.stringify(imports)}`);
}
const actual = new Set(WebAssembly.Module.exports(module).map((item) => item.name));
for (const item of manifest.exports) {
  if (!actual.has(item.name)) throw new Error(`xyg-wasm missing manifest export ${item.name}`);
}
if (!actual.has("memory")) throw new Error("xyg-wasm missing exported linear memory");
mkdirSync(dirname(output), { recursive: true });
copyFileSync(source, output);
console.log(`packaged raw xyg-wasm artifact at ${output}`);
