// Shared test-only actual C/WASM replay calls. No wire validation bypass.
import assert from "node:assert/strict";
import * as native from "../src/native.js";
import { decodeContainer } from "../src/graphforge-container.js";
export const ptr = (bytes) => native.pointer(bytes, "uint8_t *");
export function equalBytes(actual, expected, label) {
  const left = Buffer.from(actual);
  const right = Buffer.from(expected);
  let differences = "";
  if (!left.equals(right)) {
    const a = decodeContainer(actual, "XYGR");
    const b = decodeContainer(expected, "XYGR");
    const json = (v) => JSON.stringify(v, (_, x) => typeof x === "bigint" ? `${x}n` : x);
    differences = [...new Set([...a.keys(), ...b.keys()])]
      .filter((key) => json(a.get(key)?.value) !== json(b.get(key)?.value))
      .map((key) => `${key}: WASM=${json(a.get(key)?.value)} native=${json(b.get(key)?.value)}`).join("; ");
  }
  assert.equal(Buffer.compare(left, right), 0, `${label}${differences ? `: ${differences}` : ""}`);
}

export function nativeCall(fn, handle, bytes, capacity) {
  const output = new Uint8Array(capacity).fill(0xa5);
  const length = new BigUint64Array(1);
  const status = fn(handle, ptr(bytes), BigInt(bytes.length), ptr(output), BigInt(capacity), native.pointer(length, "size_t *"));
  return { status, length: Number(length[0]), output };
}

export function nativeComplete(fn, handle, bytes) {
  const zero = nativeCall(fn, handle, bytes, 0);
  assert.equal(zero.status, -5, "zero capacity applies once and reports required bytes");
  assert.ok(zero.length > 0);
  const short = nativeCall(fn, handle, bytes, zero.length - 1);
  assert.equal(short.status, -5);
  assert.equal(short.length, zero.length);
  assert.ok(short.output.every((v) => v === 0xa5), "short output is untouched");
  const exact = nativeCall(fn, handle, bytes, zero.length);
  assert.equal(exact.status, 0);
  assert.equal(exact.length, zero.length);
  assert.deepEqual(nativeCall(fn, handle, bytes, zero.length).output, exact.output, "serialized retry is byte-identical");
  return exact.output;
}

export function wasmCall(x, handle, name, bytes) {
  assert.equal(x.xyg_wasm_arena_resize(handle, bytes.length), 0);
  new Uint8Array(x.memory.buffer, x.xyg_wasm_arena_ptr(handle) >>> 0, bytes.length).set(bytes);
  const status = x[name](handle, 0, bytes.length);
  const output = new Uint8Array(x.memory.buffer, x.xyg_wasm_output_ptr(handle) >>> 0, x.xyg_wasm_output_len(handle) >>> 0).slice();
  return { status, output };
}

