/**
 * Named-section container codec shared by the `XYGQ` GraphForge composition
 * request and the `XYGF` composition document
 * (spec/design/graphforge-compositions.md §5). Pure framing: sections are
 * read and written by name and dtype only; their meaning is Rust's. The
 * browser twin is `js/src/49_wasm_graphforge.ts`; both decode the same bytes.
 */

export const CONTAINER_VERSION = 1;
export const REQUEST_MAGIC = "XYGQ";
export const DOCUMENT_MAGIC = "XYGF";
const HEADER_BYTES = 32;
const ENTRY_BYTES = 40;
const MAX_ENTRIES = 8192;

export const DTYPE = Object.freeze({
  u8: 1, u32: 2, u64: 3, i64: 4, f64: 5, bytes: 6, uuid: 7, utf8: 8, texts: 9,
});
const WIDTH = { 1: 1, 2: 4, 3: 8, 4: 8, 5: 8, 6: 1, 7: 16, 8: 1 };
const NAME = /^[a-z0-9._]{1,64}$/;

const align8 = (n) => (n + 7) & ~7;

function asBytes(value, label) {
  if (value instanceof Uint8Array) return value;
  if (value instanceof ArrayBuffer) return new Uint8Array(value);
  if (ArrayBuffer.isView(value)) return new Uint8Array(value.buffer, value.byteOffset, value.byteLength);
  throw new TypeError(`${label} must be bytes (Uint8Array, Buffer, or ArrayBuffer)`);
}

/**
 * Encode sections `[{name, index, dtype, values}]` into one container.
 * `values`: typed array / array for numeric dtypes, bytes for `bytes`,
 * string for `utf8`, string[] for `texts`, 16-byte-per-item bytes for `uuid`.
 */
export function encodeContainer(magic, sections) {
  if (sections.length > MAX_ENTRIES) throw new RangeError("too many container sections");
  const encoder = new TextEncoder();
  const prepared = sections.map(({ name, index = 0, dtype, values }) => {
    if (!NAME.test(name)) throw new TypeError(`invalid section name ${JSON.stringify(name)}`);
    if (!Number.isInteger(index) || index < 0 || index > 0xffffffff) throw new RangeError("section index must be u32");
    let payload;
    let count;
    switch (dtype) {
      case DTYPE.u8: payload = Uint8Array.from(values); count = payload.length; break;
      case DTYPE.u32: { const a = Uint32Array.from(values); payload = new Uint8Array(a.buffer); count = a.length; break; }
      case DTYPE.u64: { const a = BigUint64Array.from(values, BigInt); payload = new Uint8Array(a.buffer); count = a.length; break; }
      case DTYPE.i64: { const a = BigInt64Array.from(values, BigInt); payload = new Uint8Array(a.buffer); count = a.length; break; }
      case DTYPE.f64: { const a = Float64Array.from(values); payload = new Uint8Array(a.buffer); count = a.length; break; }
      case DTYPE.bytes: payload = asBytes(values, name); count = payload.length; break;
      case DTYPE.uuid: {
        payload = asBytes(values, name);
        if (payload.length % 16) throw new RangeError(`${name} must hold 16-byte UUIDs`);
        count = payload.length / 16;
        break;
      }
      case DTYPE.utf8: payload = encoder.encode(String(values)); count = payload.length; break;
      case DTYPE.texts: {
        const parts = [...values].map((v) => encoder.encode(String(v)));
        const offsets = new BigUint64Array(parts.length + 1);
        let at = 0;
        parts.forEach((p, i) => { at += p.length; offsets[i + 1] = BigInt(at); });
        payload = new Uint8Array(offsets.byteLength + at);
        payload.set(new Uint8Array(offsets.buffer), 0);
        let cursor = offsets.byteLength;
        for (const p of parts) { payload.set(p, cursor); cursor += p.length; }
        count = parts.length;
        break;
      }
      default: throw new TypeError(`unknown dtype ${dtype}`);
    }
    return { name: encoder.encode(name), index, dtype, count, payload };
  });
  const names = prepared.reduce((n, s) => n + s.name.length, 0);
  const namesStart = HEADER_BYTES + prepared.length * ENTRY_BYTES;
  let cursor = align8(namesStart + names);
  const offsets = prepared.map((s) => { const at = cursor; cursor = align8(cursor + s.payload.length); return at; });
  const out = new Uint8Array(cursor);
  const view = new DataView(out.buffer);
  out.set(encoder.encode(magic), 0);
  view.setUint32(4, CONTAINER_VERSION, true);
  view.setUint32(8, prepared.length, true);
  view.setUint32(12, names, true);
  view.setBigUint64(16, BigInt(cursor), true);
  let nameAt = 0;
  prepared.forEach((s, i) => {
    const at = HEADER_BYTES + i * ENTRY_BYTES;
    view.setUint32(at, nameAt, true);
    view.setUint32(at + 4, s.name.length, true);
    view.setUint32(at + 8, s.dtype, true);
    view.setUint32(at + 12, s.index, true);
    view.setBigUint64(at + 16, BigInt(offsets[i]), true);
    view.setBigUint64(at + 24, BigInt(s.count), true);
    view.setBigUint64(at + 32, BigInt(s.payload.length), true);
    out.set(s.name, namesStart + nameAt);
    nameAt += s.name.length;
    out.set(s.payload, offsets[i]);
  });
  return out;
}

/**
 * Decode a container into `Map<"name#index", {name, index, dtype, count,
 * value}>`. Numeric sections become typed arrays (copied, so they are
 * aligned and detached from the source), `utf8` a string, `texts` a string[],
 * `uuid`/`bytes` a Uint8Array.
 */
export function decodeContainer(input, magic) {
  const bytes = asBytes(input, "container");
  const view = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
  const fail = (reason) => { throw new RangeError(`malformed ${magic} container: ${reason}`); };
  if (bytes.length < HEADER_BYTES || new TextDecoder().decode(bytes.subarray(0, 4)) !== magic) fail("magic");
  if (view.getUint32(4, true) !== CONTAINER_VERSION) fail("version");
  const count = view.getUint32(8, true);
  const names = view.getUint32(12, true);
  if (count > MAX_ENTRIES || view.getBigUint64(16, true) !== BigInt(bytes.length)) fail("header");
  const namesStart = HEADER_BYTES + count * ENTRY_BYTES;
  const payloadStart = align8(namesStart + names);
  if (payloadStart > bytes.length) fail("names");
  const decoder = new TextDecoder("utf-8", { fatal: true });
  const sections = new Map();
  for (let i = 0; i < count; i += 1) {
    const at = HEADER_BYTES + i * ENTRY_BYTES;
    const nameOffset = view.getUint32(at, true);
    const nameLength = view.getUint32(at + 4, true);
    if (nameOffset + nameLength > names) fail("name range");
    const name = decoder.decode(bytes.subarray(namesStart + nameOffset, namesStart + nameOffset + nameLength));
    if (!NAME.test(name)) fail("name");
    const dtype = view.getUint32(at + 8, true);
    const index = view.getUint32(at + 12, true);
    const offset = Number(view.getBigUint64(at + 16, true));
    const n = Number(view.getBigUint64(at + 24, true));
    const length = Number(view.getBigUint64(at + 32, true));
    if (offset % 8 || offset < payloadStart || offset + length > bytes.length) fail("section range");
    const payload = bytes.subarray(offset, offset + length);
    let value;
    const copy = () => payload.slice().buffer;
    if (dtype === DTYPE.texts) {
      const head = (n + 1) * 8;
      if (length < head) fail("texts");
      const offs = new BigUint64Array(payload.slice(0, head).buffer);
      const text = payload.subarray(head);
      value = [];
      for (let k = 0; k < n; k += 1) {
        const start = Number(offs[k]);
        const end = Number(offs[k + 1]);
        if (end < start || end > text.length) fail("text offsets");
        value.push(decoder.decode(text.subarray(start, end)));
      }
    } else {
      const width = WIDTH[dtype];
      if (width == null || n * width !== length) fail("section size");
      switch (dtype) {
        case DTYPE.u8: value = payload.slice(); break;
        case DTYPE.u32: value = new Uint32Array(copy()); break;
        case DTYPE.u64: value = new BigUint64Array(copy()); break;
        case DTYPE.i64: value = new BigInt64Array(copy()); break;
        case DTYPE.f64: value = new Float64Array(copy()); break;
        case DTYPE.utf8: value = decoder.decode(payload); break;
        default: value = payload.slice(); break;
      }
    }
    const key = `${name}#${index}`;
    if (sections.has(key)) fail("duplicate section");
    sections.set(key, { name, index, dtype, count: n, value });
  }
  return sections;
}
