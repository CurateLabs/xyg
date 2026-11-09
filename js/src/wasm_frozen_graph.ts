// Shared Worker byte staging only; Rust owns XYFX validation, export and recovery.
import { readXygWasmError, XYG_WASM_STATUS, type XygWasmExports } from './wasm_abi_generated';
export function executeFrozenGraph(
  exports: XygWasmExports, handle: number, command: unknown, budget: number,
): {status: number; detail?: string; response?: ArrayBuffer} {
  if (!(command instanceof ArrayBuffer) || command.byteLength < 32 || command.byteLength > budget) {
    return {status: XYG_WASM_STATUS.INVALID_ARGUMENT, detail: 'frozen graph command is malformed'};
  }
  let status = exports.xyg_wasm_arena_resize(handle, command.byteLength);
  if (status !== XYG_WASM_STATUS.OK) return {status, detail: readXygWasmError(exports, handle)};
  const ptr = exports.xyg_wasm_arena_ptr(handle) >>> 0;
  if (!ptr || ptr + command.byteLength > exports.memory.buffer.byteLength) throw new Error('invalid frozen graph staging range');
  new Uint8Array(exports.memory.buffer, ptr, command.byteLength).set(new Uint8Array(command));
  status = exports.xyg_wasm_frozen_graph_execute(handle, 0, command.byteLength);
  if (status !== XYG_WASM_STATUS.OK) {
    const detail = readXygWasmError(exports, handle); exports.xyg_wasm_arena_resize(handle, 0);
    return {status, detail};
  }
  const outputPtr = exports.xyg_wasm_output_ptr(handle) >>> 0;
  const length = exports.xyg_wasm_output_len(handle) >>> 0;
  if (length && (!outputPtr || length < 64 || length > budget || outputPtr + length > exports.memory.buffer.byteLength)) throw new Error('invalid frozen graph output range');
  const response = length ? new Uint8Array(exports.memory.buffer, outputPtr, length).slice().buffer : new ArrayBuffer(0);
  exports.xyg_wasm_arena_resize(handle, 0);
  return {status, response};
}
