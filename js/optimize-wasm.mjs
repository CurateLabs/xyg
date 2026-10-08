// Build-only pinned Binaryen pass. The browser artifact has no optimizer dependency.
import { execFileSync } from "node:child_process";
import { mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");
export function optimizeWasm(input) {
  // Consume the already-read source bytes, so packaging cannot validate one
  // version and optimize a concurrently replaced file.
  const directory = mkdtempSync(join(tmpdir(), "xyg-wasm-opt-"));
  try {
    const source = join(directory, "source.wasm");
    const output = join(directory, "optimized.wasm");
    writeFileSync(source, input);
    execFileSync(process.execPath, [join(root, "node_modules", "binaryen", "bin", "wasm-opt"),
      source, "-O3", "--all-features", "-o", output], {stdio: "pipe", maxBuffer: 1024 * 1024});
    return readFileSync(output);
  } finally { rmSync(directory, { recursive: true, force: true }); }
}
