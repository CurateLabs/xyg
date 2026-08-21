import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

import {
  ABI_VERSION,
  NATIVE_LIBRARY_NAMES,
  PLATFORM_PACKAGES,
  assertAbiVersion,
  assertSupportedPlatform,
  candidateNativeLibraries,
  nativeLibraryFileName,
  resolvePlatformPackageName,
  tryResolvePlatformPackageLibrary,
} from "../src/native-path.js";

const facadePackageJson = JSON.parse(
  fs.readFileSync(
    path.join(path.dirname(fileURLToPath(import.meta.url)), "..", "package.json"),
    "utf8",
  ),
);

function missingRequire() {
  const fn = () => {
    throw Object.assign(new Error("not installed"), { code: "MODULE_NOT_FOUND" });
  };
  fn.resolve = () => {
    throw Object.assign(new Error("not installed"), { code: "MODULE_NOT_FOUND" });
  };
  return fn;
}

test("candidate names cover Linux, macOS, and Windows", () => {
  assert.deepEqual(NATIVE_LIBRARY_NAMES, [
    "libxyg_core.so",
    "libxyg_core.dylib",
    "xyg_core.dll",
  ]);
  assert.equal(nativeLibraryFileName("linux"), "libxyg_core.so");
  assert.equal(nativeLibraryFileName("darwin"), "libxyg_core.dylib");
  assert.equal(nativeLibraryFileName("win32"), "xyg_core.dll");
});

test("optionalDependencies list every exact-platform package", () => {
  const optional = facadePackageJson.optionalDependencies ?? {};
  assert.deepEqual(
    Object.keys(optional).sort(),
    Object.values(PLATFORM_PACKAGES).sort(),
  );
  for (const [id, name] of Object.entries(PLATFORM_PACKAGES)) {
    assert.equal(optional[name], `file:../xyg-node-${id}`);
  }
});

test("facade selects only the matching platform package name", () => {
  assert.equal(
    resolvePlatformPackageName("darwin", "arm64"),
    "@curatelabs/xyg-node-darwin-arm64",
  );
  assert.equal(
    resolvePlatformPackageName("linux", "x64"),
    "@curatelabs/xyg-node-linux-x64",
  );
  assert.equal(
    resolvePlatformPackageName("win32", "x64"),
    "@curatelabs/xyg-node-win32-x64",
  );
});

test("Windows arm64 is an explicit unsupported-platform error", () => {
  assert.throws(
    () => assertSupportedPlatform("win32", "arm64"),
    /does not support Windows arm64/,
  );
  assert.throws(
    () =>
      candidateNativeLibraries({
        platform: "win32",
        arch: "arm64",
        env: {},
        packageDir: "/repo/packages/xy-node",
        cwd: "/tmp/project",
      }),
    /does not support Windows arm64/,
  );
});

test("unknown platform/arch fails before filesystem search", () => {
  assert.throws(
    () => assertSupportedPlatform("sunos", "x64"),
    /no exact-platform package for sunos-x64/,
  );
});

test("lookup prefers exact platform package, then packaged and cargo paths", () => {
  const packageDir = "/repo/packages/xy-node";
  const cwd = "/tmp/project";
  const stagedDir = "/tmp/staged-platform";
  const staged = path.join(stagedDir, "libxyg_core.so");
  const requireFn = {
    resolve(spec) {
      assert.equal(spec, "@curatelabs/xyg-node-linux-x64/package.json");
      return path.join(stagedDir, "package.json");
    },
  };
  const exists = fs.existsSync;
  fs.existsSync = (p) => p === staged || exists.call(fs, p);
  try {
    const candidates = candidateNativeLibraries({
      platform: "linux",
      arch: "x64",
      env: { XYG_NATIVE_LIB: "/explicit/libxyg_core.so" },
      packageDir,
      cwd,
      requireFn,
    });
    assert.equal(candidates[0], staged);
    assert.equal(candidates[1], "/explicit/libxyg_core.so");
    assert.ok(
      candidates.some((c) =>
        c.endsWith("/packages/xy-node/_native_lib/libxyg_core.so"),
      ),
    );
    assert.ok(candidates.some((c) => c.endsWith("/target/release/libxyg_core.so")));
    assert.ok(candidates.some((c) => c.endsWith("/target/debug/libxyg_core.so")));
    for (const candidate of candidates) {
      assert.equal(candidate.includes("/usr/lib"), false);
      assert.equal(candidate.includes("/usr/local"), false);
    }
  } finally {
    fs.existsSync = exists;
  }

  const relative = candidateNativeLibraries({
    platform: "linux",
    arch: "x64",
    env: { XYG_NATIVE_LIB: "rel/libxyg_core.so" },
    packageDir,
    cwd,
    requireFn: missingRequire(),
  });
  assert.equal(relative[0], "/tmp/project/rel/libxyg_core.so");

  const darwin = candidateNativeLibraries({
    platform: "darwin",
    arch: "arm64",
    env: {},
    packageDir,
    cwd,
    requireFn: missingRequire(),
  });
  assert.ok(darwin.every((c) => c.endsWith("libxyg_core.dylib")));
  const win = candidateNativeLibraries({
    platform: "win32",
    arch: "x64",
    env: {},
    packageDir,
    cwd,
    requireFn: missingRequire(),
  });
  assert.ok(win.every((c) => c.endsWith("xyg_core.dll")));
});

test("tryResolvePlatformPackageLibrary ignores missing optional packages", () => {
  const missing = tryResolvePlatformPackageLibrary({
    platform: "linux",
    arch: "x64",
    requireFn: missingRequire(),
  });
  assert.equal(missing, null);
});

test("tryResolvePlatformPackageLibrary returns staged binary path", () => {
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), "xyg-node-platform-"));
  const libPath = path.join(tmp, "libxyg_core.so");
  fs.writeFileSync(libPath, "");
  fs.writeFileSync(path.join(tmp, "package.json"), "{}");
  try {
    const resolved = tryResolvePlatformPackageLibrary({
      platform: "linux",
      arch: "x64",
      requireFn: {
        resolve(spec) {
          assert.equal(spec, "@curatelabs/xyg-node-linux-x64/package.json");
          return path.join(tmp, "package.json");
        },
      },
    });
    assert.equal(resolved, libPath);
  } finally {
    fs.rmSync(tmp, { recursive: true, force: true });
  }
});

test("ABI mismatch fails before other symbols are usable", () => {
  assert.equal(ABI_VERSION, 79);
  assert.doesNotThrow(() => assertAbiVersion(62, 62));
  assert.throws(
    () => assertAbiVersion(59, 60),
    /ABI mismatch: wrapper expects 60, library reports 59/,
  );
});
