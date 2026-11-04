// Snapshot actual production output. A failed producer remains explicitly failed;
// independently reusing the identical pinned optimizer only retains its bytes.
import { readFileSync, writeFileSync, existsSync } from "node:fs";
import { createHash } from "node:crypto";
import { gzipSync } from "node:zlib";
import { execFileSync } from "node:child_process";
import { optimizeWasm } from "../../../js/optimize-wasm.mjs";
const receipt = new URL("./", import.meta.url), passed = process.argv[2] === "passed";
if (!passed && process.argv[2] !== "failed") throw new Error("declare actual package result passed|failed");
const sha = bytes => createHash("sha256").update(bytes).digest("hex");
const rawPath = "target/wasm32-unknown-unknown/release/xyg_wasm.wasm", raw = readFileSync(rawPath);
const module = passed ? readFileSync("packages/xy-client/dist/xyg-wasm.wasm") : optimizeWasm(raw), packed = gzipSync(module, { level: 6 });
const files = execFileSync("git", ["ls-files", "-z"]).toString().split("\0").filter(p => p && (p.startsWith("crates/") || p.startsWith("js/src/") || p.startsWith(".cargo/") || p.startsWith("spec/wasm/") || ["Cargo.toml", "Cargo.lock", "rust-toolchain.toml", "js/build.mjs", "js/package-wasm.mjs", "js/optimize-wasm.mjs", "js/tsconfig.json", "package.json", "package-lock.json"].includes(p)));
const inputs = Object.fromEntries(files.sort().map(p => [p, sha(readFileSync(p))]));
const artifacts = {};
for (const p of [rawPath, "target/release/libxyg_core.so", ...(passed ? ["packages/xy-client/dist", "python/xyg/static"].flatMap(dir => ["index.js", "standalone.js", "wasm-worker.js", "xyg-wasm.wasm", "xyg-wasm-inline.js", "xyg-wasm.manifest.json"].map(name => `${dir}/${name}`)).concat(["packages/xy-client/dist/wasm-inline-worker.js"]) : [])]) {
  const data = readFileSync(p); artifacts[p] = { bytes: data.length, sha256: sha(data) };
}
const limits = { raw: 1878 * 1024, gzip6: 765 * 1024 }, fits = module.length <= limits.raw && packed.length <= limits.gzip6;
if (passed !== fits) throw new Error("declared package result disagrees with unchanged hard gates");
const metadata = { packagePassed: passed, sourceBase: execFileSync("git", ["rev-parse", "HEAD"]).toString().trim(), sourceSha256: sha(Buffer.from(JSON.stringify(inputs))), sourceInputs: inputs, artifacts,
  optimized: { bytes: module.length, gzip6: packed.length, sha256: sha(module), gzip6Sha256: sha(packed), limits, headroom: { raw: limits.raw-module.length, gzip6: limits.gzip6-packed.length } },
  provenance: passed ? "Fresh actual native/WASM release compilation and normal shipping packager" : "Failed normal shipping producer; identical pinned optimizer rerun only to preserve unpublished failed output; no dependent qualification", versions: { native: 399, wasm: 35, scene: 34, painter: 17 } };
for (const [name, data] of [["artifacts.json", JSON.stringify(metadata, null, 2)+"\n"], [passed ? "shipping-module.wasm.gz" : "failed-production-module.wasm.gz", packed]]) {
  const path = new URL(name, receipt); if (existsSync(path)) throw new Error(`refusing to overwrite ${name}`); writeFileSync(path, data, { flag: "wx" });
}
console.log(JSON.stringify({ packagePassed: passed, optimized: metadata.optimized }, null, 2));
