// Read the exact compiler output; use the unchanged shipped optimizer and gzip6.
import { readFileSync, writeFileSync, mkdirSync } from "node:fs";
import { gzipSync } from "node:zlib";
import { createHash } from "node:crypto";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import { optimizeWasm } from "../../../js/optimize-wasm.mjs";
const root = fileURLToPath(new URL("../../../", import.meta.url));
const output = process.argv[2] ?? "/tmp/xyg-s1-size-reproduction";
mkdirSync(output, { recursive: true });
const source = readFileSync(join(root, "target/wasm32-unknown-unknown/release/xyg_wasm.wasm"));
const bytes = optimizeWasm(source);
const gzip = gzipSync(bytes);
const sha = b => createHash("sha256").update(b).digest("hex");
const result = {
  sourceBytes: source.length, sourceSha256: sha(source), optimizedBytes: bytes.length,
  gzip6Bytes: gzip.length, optimizedSha256: sha(bytes), gzip6Sha256: sha(gzip),
  rawGate: 1543168, gzip6Gate: 638976,
  rawHeadroom: 1543168 - bytes.length, gzip6Headroom: 638976 - gzip.length,
};
writeFileSync(join(output, "optimized.wasm"), bytes);
writeFileSync(join(output, "size.json"), JSON.stringify(result, null, 2) + "\n");
console.log(JSON.stringify(result, null, 2));
