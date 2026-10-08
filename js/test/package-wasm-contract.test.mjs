// Build gate negative controls; isolated outputs must remain unchanged on rejection.
import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { copyFileSync, mkdirSync, mkdtempSync, readFileSync, rmSync, symlinkSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import test from "node:test";
import binaryen from "binaryen";

const root = join(dirname(fileURLToPath(import.meta.url)), "../..");
const manifest = JSON.parse(readFileSync(join(root, "spec/wasm/abi.json"), "utf8"));
for (const [name, abi, scene, start, diagnostic] of [
  ["wrong ABI", manifest.abi_version - 1, manifest.scene_version, false, "version differs for xyg_wasm_abi_version"],
  ["wrong Scene", manifest.abi_version, manifest.scene_version - 1, false, "version differs for xyg_wasm_scene_version"],
  ["start function", manifest.abi_version, manifest.scene_version, true, "must not contain a start function"],
]) test(`packaging rejects ${name} before publication`, () => {
  const directory = mkdtempSync(join(tmpdir(), "xyg-package-contract-"));
  try {
    mkdirSync(join(directory, "js"));
    mkdirSync(join(directory, "spec/wasm"), { recursive: true });
    for (const script of ["package-wasm.mjs", "optimize-wasm.mjs"]) copyFileSync(join(root, "js", script), join(directory, "js", script));
    copyFileSync(join(root, "spec/wasm/abi.json"), join(directory, "spec/wasm/abi.json"));
    symlinkSync(join(root, "node_modules"), join(directory, "node_modules"), "dir");
    const outputs = ["packages/xy-client/dist/xyg-wasm.wasm", "python/xyg/static/xyg-wasm.wasm",
      "packages/xy-client/dist/xyg-wasm-inline.js", "python/xyg/static/xyg-wasm-inline.js"];
    for (const output of outputs) {
      mkdirSync(dirname(join(directory, output)), { recursive: true });
      writeFileSync(join(directory, output), "previous valid artifact");
    }
    const functions = manifest.exports.map(item => {
      const value = item.name === "xyg_wasm_abi_version" ? abi : item.name === "xyg_wasm_scene_version" ? scene : 0;
      return `(func (export "${item.name}") ${item.params.map(() => "(param i32)").join(" ")} (result i32) (i32.const ${value}))`;
    }).join("\n");
    const module = binaryen.parseText(`(module (memory (export "memory") 1) ${functions}
      ${start ? "(func $start (loop $forever (br $forever))) (start $start)" : ""})`);
    try { writeFileSync(join(directory, "input.wasm"), module.emitBinary()); } finally { module.dispose(); }
    assert.throws(() => execFileSync(process.execPath, [join(directory, "js/package-wasm.mjs"), join(directory, "input.wasm")],
      { timeout: 10_000, stdio: "pipe" }), error => {
      assert.equal(error.signal, null, "gate must reject instead of hanging");
      assert.ok(error.stderr.toString().includes(diagnostic), error.stderr.toString());
      return true;
    });
    for (const output of outputs) assert.equal(readFileSync(join(directory, output), "utf8"), "previous valid artifact");
  } finally { rmSync(directory, { recursive: true, force: true }); }
});
