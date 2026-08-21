import koffi from "koffi";

import {
  ABI_VERSION,
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
