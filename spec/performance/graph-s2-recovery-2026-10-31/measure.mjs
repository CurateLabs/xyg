// Measure the exact release output with the shipped optimizer and Node gzip6.
import { readFileSync, writeFileSync, mkdirSync } from "node:fs";
import { gzipSync } from "node:zlib";
import { createHash } from "node:crypto";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import { optimizeWasm } from "../../../js/optimize-wasm.mjs";
const root = fileURLToPath(new URL("../../../", import.meta.url));
const output = process.argv[2] ?? join(root, "target/task-tmp/s2-recovery");
mkdirSync(output, { recursive: true });
const source = readFileSync(join(root, "target/wasm32-unknown-unknown/release/xyg_wasm.wasm"));
const bytes = optimizeWasm(source);
const gzip = gzipSync(bytes);
const sha = b => createHash("sha256").update(b).digest("hex");
const result = {
  node: process.version,
  sourceBytes: source.length, sourceSha256: sha(source), optimizedBytes: bytes.length,
  gzip6Bytes: gzip.length, optimizedSha256: sha(bytes), gzip6Sha256: sha(gzip),
  rawGate: 1511 * 1024, gzip6Gate: 625 * 1024,
  rawHeadroom: 1511 * 1024 - bytes.length, gzip6Headroom: 625 * 1024 - gzip.length,
};
writeFileSync(join(output, "optimized.wasm"), bytes);
writeFileSync(join(output, "artifact.json"), JSON.stringify(result, null, 2) + "\n");
console.log(JSON.stringify(result, null, 2));
