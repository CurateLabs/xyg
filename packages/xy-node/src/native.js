import koffi from "koffi";

import {
  ABI_VERSION,
  _configureGeneratedAbiTraceFromEnv,
  bindAbiVersion,
  bindGeneratedAbi,
} from "./_abi_generated.js";

import {
  NATIVE_ERROR_CODES,
  XygNativeError,
  assertAbiVersion,
  resolveNativeLibrary,
} from "./native-path.js";

export * from "./_abi_generated.js";
export { nativeLibraryFileName, NATIVE_LIBRARY_NAMES, NATIVE_ERROR_CODES, XygNativeError } from "./native-path.js";

export function resolvePackageNativeLibrary() {
  return resolveNativeLibrary();
}

const libraryPath = resolvePackageNativeLibrary();
let lib;
try {
  lib = koffi.load(libraryPath);
} catch (cause) {
  throw new XygNativeError(
    NATIVE_ERROR_CODES.LOAD_FAILED,
    `XYG native library could not be loaded from ${libraryPath}: ${cause?.message ?? cause}. Reinstall the exact-platform package or rebuild the development library.`,
    { cause, libraryPath },
  );
}

export const nativeLibraryPath = libraryPath;

// Bind and check ABI_VERSION before any other symbol so a mismatched
// libxyg_core cannot be half-bound (xyg-naming.md §3).
const xygAbiVersion = bindAbiVersion(lib);
assertAbiVersion(xygAbiVersion(), ABI_VERSION);
export const xyAbiVersion = xygAbiVersion;

try {
  bindGeneratedAbi(lib);
} catch (cause) {
  // The version matched but a declared symbol is absent or mistyped: the
  // library is not the build these bindings were generated for.
  throw new XygNativeError(
    NATIVE_ERROR_CODES.ABI_MISMATCH,
    `XYG native library ${libraryPath} reports ABI ${ABI_VERSION} but lacks a declared symbol: ${cause?.message ?? cause}. Rebuild or reinstall so library and bindings come from one release.`,
    { cause, libraryPath, expected: ABI_VERSION, actual: ABI_VERSION },
  );
}
_configureGeneratedAbiTraceFromEnv();

export function pointer(view, cType) {
  if (view == null) {
    return null;
  }
  if (!ArrayBuffer.isView(view)) {
    throw new TypeError("native pointer arguments must be TypedArrays or DataViews");
  }
  if (view.byteLength === 0) {
    return null;
  }
  const buffer = Buffer.from(view.buffer, view.byteOffset, view.byteLength);
  return koffi.as(buffer, cType);
}

const PolarAbiInput = koffi.struct("XygPolarAbiInput", {
  data: "const uint8_t *",
  len: "size_t",
});

export function polarAbiInputPointer(polar) {
  if (polar == null || polar.length === 0) {
    return { ptr: 0, keep: null };
  }
  const data = Buffer.from(polar.buffer, polar.byteOffset, polar.byteLength);
  const encoded = Buffer.alloc(koffi.sizeof(PolarAbiInput));
  koffi.encode(encoded, PolarAbiInput, {
    data: koffi.as(data, "const uint8_t *"),
    len: BigInt(polar.length),
  });
  return { ptr: koffi.as(encoded, "const uint8_t *"), keep: [encoded, data] };
}
