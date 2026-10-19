// Deterministic generation and early, actionable failure of the WASM packager (#1005, §33).
import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { copyFileSync, existsSync, mkdirSync, mkdtempSync, readFileSync, rmSync, symlinkSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import test from "node:test";
import binaryen from "binaryen";

const root = join(dirname(fileURLToPath(import.meta.url)), "../..");
const manifest = JSON.parse(readFileSync(join(root, "spec/wasm/abi.json"), "utf8"));

function workspace() {
  const directory = mkdtempSync(join(tmpdir(), "xyg-package-manifest-"));
  mkdirSync(join(directory, "js"));
  mkdirSync(join(directory, "spec/wasm"), { recursive: true });
  for (const script of ["package-wasm.mjs", "optimize-wasm.mjs"]) copyFileSync(join(root, "js", script), join(directory, "js", script));
  copyFileSync(join(root, "spec/wasm/abi.json"), join(directory, "spec/wasm/abi.json"));
  symlinkSync(join(root, "node_modules"), join(directory, "node_modules"), "dir");
  return directory;
}

function validModule(directory) {
  const functions = manifest.exports.map(item => {
    const value = item.name === "xyg_wasm_abi_version" ? manifest.abi_version
      : item.name === "xyg_wasm_scene_version" ? manifest.scene_version : 0;
    return `(func (export "${item.name}") ${item.params.map(kind => `(param ${["u64", "i64"].includes(kind) ? "i64" : "i32"})`).join(" ")} (result i32) (i32.const ${value}))`;
  }).join("\n");
  const module = binaryen.parseText(`(module (memory (export "memory") 1) ${functions})`);
  try { writeFileSync(join(directory, "input.wasm"), module.emitBinary()); } finally { module.dispose(); }
  return join(directory, "input.wasm");
}

const run = (directory, input) => execFileSync(process.execPath,
  [join(directory, "js/package-wasm.mjs"), input], { timeout: 30_000, stdio: "pipe" });

test("packaging is deterministic and emits matching version/hash manifests", () => {
  const directory = workspace();
  try {
    mkdirSync(join(directory, "packages/xy-client/dist"), { recursive: true });
    writeFileSync(join(directory, "packages/xy-client/dist/wasm-inline-worker.js"), "(()=>{})();");
    const input = validModule(directory);
    const outputs = ["packages/xy-client/dist", "python/xyg/static"].flatMap(dir =>
      ["xyg-wasm.wasm", "xyg-wasm-inline.js", "xyg-wasm.manifest.json"].map(name => `${dir}/${name}`));
    run(directory, input);
    const first = outputs.map(output => readFileSync(join(directory, output)));
    run(directory, input);
    assert.deepEqual(outputs.map(output => readFileSync(join(directory, output))), first);
    const meta = JSON.parse(readFileSync(join(directory, "packages/xy-client/dist/xyg-wasm.manifest.json"), "utf8"));
    assert.equal(meta.abi_version, manifest.abi_version);
    assert.equal(meta.scene_version, manifest.scene_version);
    assert.equal(meta.painter_version, manifest.painter_version);
    assert.equal(meta.bytes, readFileSync(join(directory, "packages/xy-client/dist/xyg-wasm.wasm")).length);
    assert.deepEqual(readFileSync(join(directory, "packages/xy-client/dist/xyg-wasm.manifest.json")),
      readFileSync(join(directory, "python/xyg/static/xyg-wasm.manifest.json")));
  } finally { rmSync(directory, { recursive: true, force: true }); }
});

test("withheld producer inputs fail early naming the producer command", () => {
  const directory = workspace();
  try {
    assert.throws(() => run(directory, join(directory, "missing.wasm")), error => {
      const text = error.stderr.toString();
      assert.match(text, /raw wasm32 module is missing/);
      assert.match(text, /cargo build -p xyg-wasm --release --target wasm32-unknown-unknown/);
      return true;
    });
    assert.throws(() => run(directory, validModule(directory)), error => {
      const text = error.stderr.toString();
      assert.match(text, /classic inline worker is missing/);
      assert.match(text, /node js\/build\.mjs/);
      return true;
    });
    assert.equal(existsSync(join(directory, "packages/xy-client/dist/xyg-wasm.wasm")), false,
      "a failed packaging run must not leave a half-published asset set");
  } finally { rmSync(directory, { recursive: true, force: true }); }
});
