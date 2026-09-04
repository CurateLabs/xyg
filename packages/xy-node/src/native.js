import koffi from "koffi";

import {
  ABI_VERSION,
  _configureGeneratedAbiTraceFromEnv,
  bindAbiVersion,
  bindGeneratedAbi,
} from "./_abi_generated.js";

import {
  assertAbiVersion,
  resolveNativeLibrary,
} from "./native-path.js";

export * from "./_abi_generated.js";
export { nativeLibraryFileName, NATIVE_LIBRARY_NAMES } from "./native-path.js";

export function resolvePackageNativeLibrary() {
  return resolveNativeLibrary();
}

const libraryPath = resolvePackageNativeLibrary();
const lib = koffi.load(libraryPath);

export const nativeLibraryPath = libraryPath;

// Bind and check ABI_VERSION before any other symbol so a mismatched
// libxyg_core cannot be half-bound (xyg-naming.md §3).
const xygAbiVersion = bindAbiVersion(lib);
assertAbiVersion(xygAbiVersion(), ABI_VERSION);
export const xyAbiVersion = xygAbiVersion;

bindGeneratedAbi(lib);
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
