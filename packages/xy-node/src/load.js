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
 * `code` is one of `LOAD_ERROR_CODES`: the native codes
 * (`XYG_NATIVE_UNSUPPORTED_PLATFORM`, `XYG_NATIVE_LIBRARY_MISSING`,
 * `XYG_NATIVE_LIBRARY_PATH_INVALID`, `XYG_NATIVE_LOAD_FAILED`,
 * `XYG_NATIVE_ABI_MISMATCH`), `XYG_NODE_DEPENDENCY_MISSING` when a
 * JavaScript dependency such as `koffi` is not installed, or
 * `XYG_NODE_IMPORT_FAILED` for any other failure importing the package.
 * Messages carry no paths or loader text. This module imports no native code
 * itself.
 */
import { NATIVE_ERROR_CODES, XygNativeError } from "./native-path.js";

export { NATIVE_ERROR_CODES, XygNativeError };

export const LOAD_ERROR_CODES = Object.freeze({
  ...NATIVE_ERROR_CODES,
  DEPENDENCY_MISSING: "XYG_NODE_DEPENDENCY_MISSING",
  IMPORT_FAILED: "XYG_NODE_IMPORT_FAILED",
});

export async function loadXygNode({ importer = () => import("./index.js") } = {}) {
  try {
    const xyg = await importer();
    return { ok: true, xyg, abiVersion: xyg.abiVersion() };
  } catch (error) {
    if (error instanceof XygNativeError || Object.values(NATIVE_ERROR_CODES).includes(error?.code)) {
      return {
        ok: false,
        code: error.code,
        message: String(error.message),
        ...(error.platform != null ? { platform: error.platform, arch: error.arch } : {}),
        ...(error.expected !== undefined ? { expected: error.expected, actual: error.actual } : {}),
      };
    }
    // A packaging problem, not a native one: Node's own messages name
    // filesystem paths, so they are summarized rather than forwarded.
    const missing = error?.code === "ERR_MODULE_NOT_FOUND" || error?.code === "MODULE_NOT_FOUND";
    return {
      ok: false,
      code: missing ? LOAD_ERROR_CODES.DEPENDENCY_MISSING : LOAD_ERROR_CODES.IMPORT_FAILED,
      message: missing
        ? "A JavaScript dependency of @curatelabs/xyg-node (such as koffi) is not installed. Reinstall the package with its dependencies."
        : "@curatelabs/xyg-node could not be imported. Reinstall the package.",
    };
  }
}
