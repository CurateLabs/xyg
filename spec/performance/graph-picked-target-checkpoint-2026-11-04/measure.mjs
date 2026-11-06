// Re-measure the exact compiled input with the unchanged production optimizer.
// This does not publish assets or bypass the package gate.
import { createHash } from "node:crypto";
import { existsSync, readFileSync, writeFileSync } from "node:fs";
import { gzipSync } from "node:zlib";
import { optimizeWasm } from "../../../js/optimize-wasm.mjs";
const receipt = new URL("./", import.meta.url);
const hash = bytes => createHash("sha256").update(bytes).digest("hex");
const raw = readFileSync("target/wasm32-unknown-unknown/release/xyg_wasm.wasm");
const native = readFileSync("target/release/libxyg_core.so");
const optimized = optimizeWasm(raw);
const zipped = gzipSync(optimized, { level: 6 });
const rawLimit = 1878 * 1024, gzipLimit = 765 * 1024;
const result = {
  node: process.version,
  rawCompiledWasm: { bytes: raw.length, sha256: hash(raw) },
  native: { bytes: native.length, sha256: hash(native) },
  optimized: { bytes: optimized.length, sha256: hash(optimized), limit: rawLimit, overage: optimized.length - rawLimit },
  gzip6: { bytes: zipped.length, sha256: hash(zipped), limit: gzipLimit, overage: zipped.length - gzipLimit },
  packaged: ["packages/xy-client/dist/xyg-wasm.wasm", "python/xyg/static/xyg-wasm.wasm"].map(path => ({ path, exists: existsSync(path) })),
  note: "Separate same-input invocation of js/optimize-wasm.mjs after normal production package gate; no shipping qualification.",
};
writeFileSync(new URL("rejected-module.wasm.gz", receipt), zipped, { flag: "wx" });
writeFileSync(new URL("artifacts.json", receipt), JSON.stringify(result, null, 2) + "\n", { flag: "wx" });
console.log(JSON.stringify(result, null, 2));
