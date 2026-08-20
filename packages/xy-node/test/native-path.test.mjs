import assert from "node:assert/strict";
import test from "node:test";

import {
  ABI_VERSION,
  NATIVE_LIBRARY_NAMES,
  assertAbiVersion,
  candidateNativeLibraries,
  nativeLibraryFileName,
} from "../src/native-path.js";

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

test("lookup uses packaged and cargo paths, not system directories", () => {
  const packageDir = "/repo/packages/xy-node";
  const cwd = "/tmp/project";
  const candidates = candidateNativeLibraries({
    platform: "linux",
    env: { XYG_NATIVE_LIB: "/explicit/libxyg_core.so" },
    packageDir,
    cwd,
  });
  assert.equal(candidates[0], "/explicit/libxyg_core.so");
  const relative = candidateNativeLibraries({
    platform: "linux",
    env: { XYG_NATIVE_LIB: "rel/libxyg_core.so" },
    packageDir,
    cwd,
  });
  assert.equal(relative[0], "/tmp/project/rel/libxyg_core.so");
  assert.ok(candidates.some((c) => c.endsWith("/packages/xy-node/_native_lib/libxyg_core.so")));
  assert.ok(candidates.some((c) => c.endsWith("/target/release/libxyg_core.so")));
  assert.ok(candidates.some((c) => c.endsWith("/target/debug/libxyg_core.so")));
  for (const candidate of candidates) {
    assert.equal(candidate.includes("/usr/lib"), false);
    assert.equal(candidate.includes("/usr/local"), false);
  }

  const darwin = candidateNativeLibraries({
    platform: "darwin",
    env: {},
    packageDir,
    cwd,
  });
  assert.ok(darwin.every((c) => c.endsWith("libxyg_core.dylib")));
  const win = candidateNativeLibraries({
    platform: "win32",
    env: {},
    packageDir,
    cwd,
  });
  assert.ok(win.every((c) => c.endsWith("xyg_core.dll")));
});

test("ABI mismatch fails before other symbols are usable", () => {
  assert.equal(ABI_VERSION, 67);
  assert.doesNotThrow(() => assertAbiVersion(62, 62));
  assert.throws(
    () => assertAbiVersion(59, 60),
    /ABI mismatch: wrapper expects 60, library reports 59/,
  );
});
