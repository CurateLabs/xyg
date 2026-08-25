#!/usr/bin/env node
// Copy a separately compiled raw xyg-wasm artifact into the browser package.
// Keeping this separate from js/build.mjs lets native/Python builds remain
// independent of the direct-browser target while CI verifies both paths.
import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const root = join(here, "..");
const source = process.argv[2]
  ?? join(root, "target", "wasm32-unknown-unknown", "release", "xyg_wasm.wasm");
const output = join(root, "packages", "xy-client", "dist", "xyg-wasm.wasm");
const inlineOutput = join(root, "packages", "xy-client", "dist", "xyg-wasm-inline.js");
const pythonInlineOutput = join(root, "python", "xyg", "static", "xyg-wasm-inline.js");
const manifest = JSON.parse(readFileSync(join(root, "spec", "wasm", "abi.json"), "utf8"));
const bytes = readFileSync(source);

function readU32(state) {
  let value = 0;
  let shift = 0;
  while (true) {
    if (state.offset >= state.bytes.length || shift > 28) {
      throw new Error("invalid unsigned LEB128 in xyg-wasm artifact");
    }
    const byte = state.bytes[state.offset++];
    value |= (byte & 0x7f) << shift;
    if ((byte & 0x80) === 0) return value >>> 0;
    shift += 7;
  }
}

function readName(state) {
  const length = readU32(state);
  const end = state.offset + length;
  if (end > state.bytes.length) throw new Error("truncated name in xyg-wasm artifact");
  const value = new TextDecoder().decode(state.bytes.subarray(state.offset, end));
  state.offset = end;
  return value;
}

function readVector(state, readItem) {
  return Array.from({ length: readU32(state) }, () => readItem(state));
}

function rawSignatures(input) {
  const state = { bytes: new Uint8Array(input), offset: 8 };
  const types = [];
  const functions = [];
  const exports = new Map();
  while (state.offset < state.bytes.length) {
    const id = state.bytes[state.offset++];
    const size = readU32(state);
    const end = state.offset + size;
    if (end > state.bytes.length) throw new Error("truncated section in xyg-wasm artifact");
    if (id === 1) {
      types.push(...readVector(state, (cursor) => {
        if (cursor.bytes[cursor.offset++] !== 0x60) {
          throw new Error("unsupported function type in xyg-wasm artifact");
        }
        return {
          params: readVector(cursor, (item) => item.bytes[item.offset++]),
          results: readVector(cursor, (item) => item.bytes[item.offset++]),
        };
      }));
    } else if (id === 3) {
      functions.push(...readVector(state, readU32));
    } else if (id === 7) {
      for (const item of readVector(state, (cursor) => ({
        name: readName(cursor),
        kind: cursor.bytes[cursor.offset++],
        index: readU32(cursor),
      }))) {
        exports.set(item.name, item);
      }
    }
    state.offset = end;
  }
  return { types, functions, exports };
}

function wasmType(rustType) {
  if (["i32", "u32", "usize"].includes(rustType)) return 0x7f;
  throw new Error(`unsupported Rust ABI type in manifest: ${rustType}`);
}

const module = await WebAssembly.compile(bytes);
const imports = WebAssembly.Module.imports(module);
if (imports.length) {
  throw new Error(`xyg-wasm must not request ambient imports: ${JSON.stringify(imports)}`);
}
const actual = new Set(WebAssembly.Module.exports(module).map((item) => item.name));
const raw = rawSignatures(bytes);
for (const item of manifest.exports) {
  if (!actual.has(item.name)) throw new Error(`xyg-wasm missing manifest export ${item.name}`);
  const entry = raw.exports.get(item.name);
  if (!entry || entry.kind !== 0) {
    throw new Error(`xyg-wasm manifest export ${item.name} is not a function`);
  }
  const signature = raw.types[raw.functions[entry.index]];
  const expected = {
    params: item.params.map(wasmType),
    results: [wasmType(item.result)],
  };
  if (!signature
      || signature.params.join(",") !== expected.params.join(",")
      || signature.results.join(",") !== expected.results.join(",")) {
    throw new Error(`xyg-wasm artifact signature differs for ${item.name}`);
  }
}
if (!actual.has("memory")) throw new Error("xyg-wasm missing exported linear memory");
mkdirSync(dirname(output), { recursive: true });
// Publish the exact bytes compiled and signature-checked above; rereading the
// source path here would create a validate-then-copy race.
writeFileSync(output, bytes);
// Classic standalone exports cannot fetch a sibling file from file: URLs or
// start a module Worker. Emit one deterministic, CSP-safe script payload that
// a future Blob Worker may import with `importScripts`-free classic code.
const base64 = bytes.toString("base64");
const digest = (await import("node:crypto")).createHash("sha256").update(bytes).digest("hex");
const classicWorker = readFileSync(join(root, "packages", "xy-client", "dist", "wasm-inline-worker.js"), "utf8");
if (/\b(?:fetch\s*\(|importScripts\s*\(|import\.meta|type:\s*["']module)/.test(classicWorker)) {
  throw new Error("inline classic worker must not use fetch, module URLs, or importScripts");
}
const inline = `/* generated by js/package-wasm.mjs; do not edit */\n` +
  `globalThis.__xygInlineWasm={sha256:${JSON.stringify(digest)},base64:${JSON.stringify(base64)},` +
  `classicWorkerSource:${JSON.stringify(classicWorker)}};\n`;
writeFileSync(inlineOutput, inline);
writeFileSync(pythonInlineOutput, inline);
console.log(`packaged raw xyg-wasm artifact at ${output}`);
console.log(`packaged deterministic inline WASM artifact at ${inlineOutput}`);
