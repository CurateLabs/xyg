import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

/** @type {const} */
export const packageName = "@curatelabs/xyg-node-darwin-arm64";
/** @type {const} */
export const platform = "darwin";
/** @type {const} */
export const arch = "arm64";
/** @type {const} */
export const libraryFileName = "libxyg_core.dylib";

const packageDir = path.dirname(fileURLToPath(import.meta.url));

/**
 * Absolute path to the bundled cdylib for this exact platform package.
 * Release packaging places `libxyg_core.dylib` next to this module.
 */
export function resolveNativeLibrary() {
  const candidate = path.join(packageDir, libraryFileName);
  if (!fs.existsSync(candidate)) {
    throw new Error(
      [
        `${packageName} is installed but ${libraryFileName} is missing.`,
        "Rebuild the release platform package or set XYG_NATIVE_LIB for a source checkout.",
        `Expected: ${candidate}`,
      ].join(" "),
    );
  }
  return candidate;
}
