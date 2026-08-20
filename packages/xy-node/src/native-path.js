import fs from "node:fs";
import { createRequire } from "node:module";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { ABI_VERSION } from "./_abi_generated.js";

export { ABI_VERSION };

/** Platform filenames for the one shipped cdylib. */
export const NATIVE_LIBRARY_NAMES = Object.freeze([
  "libxyg_core.so",
  "libxyg_core.dylib",
  "xyg_core.dll",
]);

/**
 * Exact optional platform packages (#52). Keys are
 * `${process.platform}-${process.arch}`.
 */
export const PLATFORM_PACKAGES = Object.freeze({
  "darwin-arm64": "@curatelabs/xyg-node-darwin-arm64",
  "darwin-x64": "@curatelabs/xyg-node-darwin-x64",
  "linux-x64": "@curatelabs/xyg-node-linux-x64",
  "linux-arm64": "@curatelabs/xyg-node-linux-arm64",
  "win32-x64": "@curatelabs/xyg-node-win32-x64",
});

const DEFAULT_REQUIRE = createRequire(
  path.join(path.dirname(fileURLToPath(import.meta.url)), "..", "package.json"),
);

export function nativeLibraryFileName(platform = process.platform) {
  if (platform === "win32") {
    return "xyg_core.dll";
  }
  if (platform === "darwin") {
    return "libxyg_core.dylib";
  }
  return "libxyg_core.so";
}

export function platformPackageId(
  platform = process.platform,
  arch = process.arch,
) {
  return `${platform}-${arch}`;
}

/**
 * Windows arm64 and any other non-matrix platform fail before any filesystem
 * search (#52 BDD: unsupported Windows arm64 is explicit).
 */
export function assertSupportedPlatform(
  platform = process.platform,
  arch = process.arch,
) {
  const id = platformPackageId(platform, arch);
  if (platform === "win32" && arch === "arm64") {
    throw new Error(
      [
        "XYG Node does not support Windows arm64.",
        "Install on win32-x64, or use the Python/browser hosts on this machine.",
        "Supported Node native packages: darwin-arm64, darwin-x64, linux-x64, linux-arm64, win32-x64.",
        "Remediation: run GraphForge/XYG Node on a supported architecture, or set XYG_NATIVE_LIB only on a supported platform during development.",
      ].join(" "),
    );
  }
  if (!Object.hasOwn(PLATFORM_PACKAGES, id)) {
    throw new Error(
      [
        `XYG Node has no exact-platform package for ${id}.`,
        "Supported: darwin-arm64, darwin-x64, linux-x64, linux-arm64, win32-x64.",
        "Windows arm64 is intentionally unsupported.",
        "Remediation: use a supported OS/arch or the Python/browser hosts.",
      ].join(" "),
    );
  }
  return id;
}

export function resolvePlatformPackageName(
  platform = process.platform,
  arch = process.arch,
) {
  const id = assertSupportedPlatform(platform, arch);
  return PLATFORM_PACKAGES[id];
}

/**
 * Resolve the native library from the matching optional platform package.
 * Uses `require.resolve(<pkg>/package.json)` so ESM platform packages work from
 * the sync CJS require bridge. Returns null when the package is not installed or
 * its binary is absent (source checkouts). Does not search system paths.
 */
export function tryResolvePlatformPackageLibrary({
  platform = process.platform,
  arch = process.arch,
  requireFn = DEFAULT_REQUIRE,
} = {}) {
  const packageName = resolvePlatformPackageName(platform, arch);
  let packageJsonPath;
  try {
    packageJsonPath = requireFn.resolve(`${packageName}/package.json`);
  } catch (err) {
    if (
      err &&
      (err.code === "MODULE_NOT_FOUND" || err.code === "ERR_MODULE_NOT_FOUND")
    ) {
      return null;
    }
    throw err;
  }
  const candidate = path.join(
    path.dirname(packageJsonPath),
    nativeLibraryFileName(platform),
  );
  if (fs.existsSync(candidate)) {
    return candidate;
  }
  return null;
}

/**
 * Packaged and development lookup only. Never searches system library paths.
 *
 * Order: exact optional platform package, `XYG_NATIVE_LIB`, package
 * `_native_lib/`, repo `target/{release,debug}/`, cwd `target/{release,debug}/`.
 */
export function candidateNativeLibraries({
  platform = process.platform,
  arch = process.arch,
  env = process.env,
  packageDir,
  cwd = process.cwd(),
  requireFn = DEFAULT_REQUIRE,
} = {}) {
  assertSupportedPlatform(platform, arch);
  if (!packageDir) {
    throw new TypeError("candidateNativeLibraries requires packageDir");
  }
  const name = nativeLibraryFileName(platform);
  const repoRoot = path.resolve(packageDir, "..", "..");
  const candidates = [];
  const fromPlatform = tryResolvePlatformPackageLibrary({
    platform,
    arch,
    requireFn,
  });
  if (fromPlatform) {
    candidates.push(fromPlatform);
  }
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
  const platform = opts?.platform ?? process.platform;
  const arch = opts?.arch ?? process.arch;
  assertSupportedPlatform(platform, arch);
  const packageName = resolvePlatformPackageName(platform, arch);
  const candidates = candidateNativeLibraries(opts);
  for (const candidate of candidates) {
    if (candidate && fs.existsSync(candidate)) {
      return candidate;
    }
  }
  throw new Error(
    [
      "Unable to find XYG native library (libxyg_core).",
      `Expected optional dependency ${packageName} with its bundled library,`,
      "or set XYG_NATIVE_LIB / run `cargo build --release` from the repository root.",
      "Lookup never searches system library directories or falls back to Python.",
      `Searched: ${candidates.join(", ") || "(none)"}`,
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
