/**
 * Non-throwing entry point for hosts that must degrade gracefully when the
 * native core is unavailable (e.g. a VS Code extension activating on an
 * unsupported platform).
 *
 * ```js
 * const loaded = await loadXygNode();
 * if (!loaded.ok) showError(loaded.code, loaded.message);   // stable code
 * else loaded.xyg.composeGraphForge(...);
 * ```
 *
 * `code` is one of `NATIVE_ERROR_CODES` (`XYG_NATIVE_UNSUPPORTED_PLATFORM`,
 * `XYG_NATIVE_LIBRARY_MISSING`, `XYG_NATIVE_LIBRARY_PATH_INVALID`,
 * `XYG_NATIVE_LOAD_FAILED`, `XYG_NATIVE_ABI_MISMATCH`). This module imports
 * no native code itself.
 */
import { NATIVE_ERROR_CODES, XygNativeError } from "./native-path.js";

export { NATIVE_ERROR_CODES, XygNativeError };

export async function loadXygNode() {
  try {
    const xyg = await import("./index.js");
    return { ok: true, xyg, abiVersion: xyg.abiVersion() };
  } catch (error) {
    const known = Object.values(NATIVE_ERROR_CODES).includes(error?.code);
    return {
      ok: false,
      code: known ? error.code : NATIVE_ERROR_CODES.LOAD_FAILED,
      message: String(error?.message ?? error),
      ...(error?.platform != null ? { platform: error.platform, arch: error.arch } : {}),
      ...(error?.expected != null ? { expected: error.expected, actual: error.actual } : {}),
    };
  }
}
