// Exact production build + unchanged shipping optimizer. This does NOT publish
// or qualify the package: package-wasm.mjs must independently pass its guards.
import fs from "node:fs";
import path from "node:path";
import { createHash } from "node:crypto";
import { gzipSync } from "node:zlib";
import { optimizeWasm } from "../../../js/optimize-wasm.mjs";
const receipt = path.dirname(new URL(import.meta.url).pathname);
const root = process.cwd();
const rawPath = path.join(root, "target/wasm32-unknown-unknown/release/xyg_wasm.wasm");
const prefix = process.argv[2] ?? "production";
const raw = fs.readFileSync(rawPath);
const candidate = optimizeWasm(raw);
const gzip = gzipSync(candidate, { level: 6 });
const sha = (b) => createHash("sha256").update(b).digest("hex");
const metadata = { provenance: "production release target, unchanged shipping optimizer; rejected candidate, not a packaged asset set", rawInput: { path: rawPath, bytes: raw.length, sha256: sha(raw) }, optimized: { bytes: candidate.length, sha256: sha(candidate) }, gzip6: { bytes: gzip.length, sha256: sha(gzip) }, budget: { raw: 1838 * 1024, gzip6: 751 * 1024 }, passed: candidate.length <= 1838 * 1024 && gzip.length <= 751 * 1024 };
fs.writeFileSync(path.join(receipt, `${prefix}-candidate.wasm.gz`), gzip, { flag: "wx" });
fs.writeFileSync(path.join(receipt, `${prefix}-sizes.json`), JSON.stringify(metadata, null, 2) + "\n", { flag: "wx" });
// Stage these same rejected bytes only for the unmodified functional probes.
// No package manifest or inline bundle is invented, and the package gate stays red.
for (const dir of ["packages/xy-client/dist", "python/xyg/static"]) fs.writeFileSync(path.join(root, dir, "xyg-wasm.wasm"), candidate);
console.log(JSON.stringify(metadata, null, 2));
