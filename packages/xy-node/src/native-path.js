import fs from "node:fs";
import path from "node:path";

/** Lockstep with `crates/xyg-core/src/lib.rs` and `python/xy/_native.py`. */
export const ABI_VERSION = 58;

/** Platform filenames for the one shipped cdylib. */
export const NATIVE_LIBRARY_NAMES = Object.freeze([
  "libxyg_core.so",
  "libxyg_core.dylib",
  "xyg_core.dll",
]);

export function nativeLibraryFileName(platform = process.platform) {
  if (platform === "win32") {
    return "xyg_core.dll";
  }
  if (platform === "darwin") {
    return "libxyg_core.dylib";
  }
  return "libxyg_core.so";
}

/**
 * Packaged and development lookup only. Never searches system library paths.
 *
 * Order: `XYG_NATIVE_LIB`, package `_native_lib/`, repo `target/{release,debug}/`,
 * cwd `target/{release,debug}/`.
 */
export function candidateNativeLibraries({
  platform = process.platform,
  env = process.env,
  packageDir,
  cwd = process.cwd(),
} = {}) {
  if (!packageDir) {
    throw new TypeError("candidateNativeLibraries requires packageDir");
  }
  const name = nativeLibraryFileName(platform);
  const repoRoot = path.resolve(packageDir, "..", "..");
  const candidates = [];
  if (env.XYG_NATIVE_LIB) {
    candidates.push(path.resolve(cwd, env.XYG_NATIVE_LIB));
  }
  candidates.push(path.resolve(packageDir, "_native_lib", name));
  candidates.push(path.resolve(repoRoot, "target", "release", name));
  candidates.push(path.resolve(repoRoot, "target", "debug", name));
  candidates.push(path.resolve(cwd, "target", "release", name));
  candidates.push(path.resolve(cwd, "target", "debug", name));
  return candidates;
}

export function resolveNativeLibrary(opts) {
  const candidates = candidateNativeLibraries(opts);
  for (const candidate of candidates) {
    if (candidate && fs.existsSync(candidate)) {
      return candidate;
    }
  }
  throw new Error(
    [
      "Unable to find XYG native library (libxyg_core).",
      "Set XYG_NATIVE_LIB to the platform library or run `cargo build --release` from the repository root.",
      `Searched: ${candidates.join(", ")}`,
    ].join(" "),
  );
}

export function assertAbiVersion(got, expected = ABI_VERSION) {
  if (got !== expected) {
    throw new Error(
      `XYG native ABI mismatch: wrapper expects ${expected}, library reports ${got}. Rebuild with \`cargo build --release\` or reinstall so the native library matches the host bindings.`,
    );
  }
}
