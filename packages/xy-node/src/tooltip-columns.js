/**
 * Typed wire encoding for semantic hover rows (graph-mark.md §2, "Tooltip
 * columns"); Python `xyg._tooltip_columns` is the same encoding byte for byte.
 *
 * Hosts keep `trace.tooltip_rows` as row objects. On the wire each key becomes
 * one typed column: `uuid` (16 bytes; a column holding any UUID uses this
 * kind, and its other strings are dictionary text stored in the slot's first
 * four bytes), `f64` (8 little-endian bytes in a u8 column, since packed blobs
 * are only 4-byte aligned), `bool` (1 byte), or `text` (u32 index). All text
 * shares one dictionary per entry. An optional u8 presence plane records absent
 * (0), null (1), value (2), or dictionary text in a uuid column (3), and is
 * omitted when every row has a value. Non-finite numbers ship as null, as JSON
 * would. Rows whose keys do not follow one shared order, or whose values are
 * not one scalar kind per key, keep the JSON `tooltip_rows` form.
 */

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/;
const nibble = (code) => (code <= 57 ? code - 48 : code - 87);
const ABSENT = 0;
const NULL = 1;
const VALUE = 2;
const TEXT = 3;

function kindOf(value) {
  if (value === null) return "null";
  if (typeof value === "boolean") return "bool";
  if (typeof value === "number") return "f64";
  if (typeof value === "string") return "text";
  return null;
}

/**
 * Ship `rows` as typed columns through the payload writer `pw`; `rows` are
 * read, never kept or mutated.
 * @returns {object|null} the `tooltip_columns` entry, or null to keep JSON rows
 */
export function encodeTooltipRows(rows, pw) {
  const n = rows.length;
  if (n === 0) return null;
  const keys = [];
  const position = new Map();
  for (const row of rows) {
    if (row === null || typeof row !== "object" || Array.isArray(row)) return null;
    let last = -1;
    // for...in walks own keys in Object.keys order without allocating an array.
    for (const key in row) {
      if (!Object.prototype.hasOwnProperty.call(row, key) || row[key] === undefined) continue; // JSON drops it: absent
      let at = position.get(key);
      if (at === undefined) {
        at = keys.length;
        position.set(key, at);
        keys.push(key);
      }
      if (at <= last) return null; // rows disagree on key order
      last = at;
    }
  }
  const kinds = [];
  for (const key of keys) {
    let kind = "null";
    let anyUuid = false;
    for (const row of rows) {
      const value = row[key];
      if (value === undefined) continue;
      const k = kindOf(value);
      if (k === null) return null;
      if (k === "null") continue;
      if (kind !== "null" && kind !== k) return null;
      kind = k;
      if (k === "text" && !anyUuid && UUID.test(value)) anyUuid = true;
    }
    kinds.push(kind === "null" ? "bool" : anyUuid ? "uuid" : kind);
  }

  const data = [];
  const present = [];
  const dictionary = [];
  const lookup = new Map();
  const intern = (text) => {
    let index = lookup.get(text);
    if (index === undefined) {
      index = dictionary.length;
      lookup.set(text, index);
      dictionary.push(text);
    }
    return index;
  };
  keys.forEach((key, c) => {
    const kind = kinds[c];
    const presence = new Uint8Array(n).fill(VALUE);
    let plane = null;
    let view = null;
    let indices = null;
    if (kind === "uuid") {
      plane = new Uint8Array(n * 16);
      view = new DataView(plane.buffer);
    } else if (kind === "f64") {
      plane = new Uint8Array(n * 8);
      view = new DataView(plane.buffer);
    } else if (kind === "bool") plane = new Uint8Array(n);
    else indices = new Uint32Array(n);
    for (let i = 0; i < n; i += 1) {
      const value = rows[i][key];
      if (value === undefined) {
        presence[i] = ABSENT;
      } else if (value === null || (kind === "f64" && !Number.isFinite(value))) {
        presence[i] = NULL;
      } else if (kind === "uuid") {
        if (UUID.test(value)) {
          for (let b = 0, p = 0; b < 16; b += 1, p += 2) {
            if (value.charCodeAt(p) === 45) p += 1;
            plane[i * 16 + b] = (nibble(value.charCodeAt(p)) << 4) | nibble(value.charCodeAt(p + 1));
          }
        } else {
          presence[i] = TEXT;
          view.setUint32(i * 16, intern(value), true);
        }
      } else if (kind === "f64") {
        view.setFloat64(i * 8, value, true);
      } else if (kind === "bool") {
        plane[i] = value ? 1 : 0;
      } else {
        indices[i] = intern(value);
      }
    }
    present.push(presence.every((v) => v === VALUE) ? null : pw.shipU8(presence));
    data.push(kind === "text" ? pw.shipU32(indices) : pw.shipU8(plane));
  });
  return { n, keys, kinds, data, present, dict: dictionary };
}

function columnBytes(columns, payload, index) {
  const meta = columns[index];
  const width = meta.dtype === "u8" ? 1 : meta.dtype === "f64" ? 8 : 4;
  const source = Number.isInteger(meta.buf) ? payload[meta.buf] : payload;
  const bytes = source instanceof Uint8Array
    ? source
    : ArrayBuffer.isView(source)
      ? new Uint8Array(source.buffer, source.byteOffset, source.byteLength)
      : new Uint8Array(source);
  return bytes.subarray(Number(meta.byte_offset), Number(meta.byte_offset) + Number(meta.len) * width);
}

const HEX = Array.from({ length: 256 }, (_, i) => i.toString(16).padStart(2, "0"));

/** An own field even for keys like `__proto__` (plain assignment would set the prototype). */
function setField(row, key, value) {
  Object.defineProperty(row, key, { value, enumerable: true, writable: true, configurable: true });
}

/**
 * The rows a payload trace entry carries, from either wire form. `payload` is
 * the packed blob or the split buffer list `buildPayload` returned.
 * @returns {object[]|null}
 */
export function decodeTooltipRows(spec, payload, entry) {
  if (entry.tooltip_rows != null) return entry.tooltip_rows;
  const cols = entry.tooltip_columns;
  if (cols == null) return null;
  const rows = Array.from({ length: cols.n }, () => ({}));
  cols.keys.forEach((key, c) => {
    const kind = cols.kinds[c];
    const raw = columnBytes(spec.columns, payload, cols.data[c]);
    const flags = cols.present[c] == null ? null : columnBytes(spec.columns, payload, cols.present[c]);
    const view = new DataView(raw.buffer, raw.byteOffset, raw.byteLength);
    for (let i = 0; i < cols.n; i += 1) {
      const state = flags == null ? VALUE : flags[i];
      if (state === ABSENT) continue;
      if (state === NULL) {
        setField(rows[i], key, null);
      } else if (state === TEXT) {
        setField(rows[i], key, cols.dict[view.getUint32(i * 16, true)]);
      } else if (kind === "uuid") {
        let h = "";
        for (let b = 0; b < 16; b += 1) h += HEX[raw[i * 16 + b]];
        setField(rows[i], key, `${h.slice(0, 8)}-${h.slice(8, 12)}-${h.slice(12, 16)}-${h.slice(16, 20)}-${h.slice(20)}`);
      } else if (kind === "f64") {
        setField(rows[i], key, view.getFloat64(i * 8, true));
      } else if (kind === "bool") {
        setField(rows[i], key, raw[i] !== 0);
      } else {
        setField(rows[i], key, cols.dict[view.getUint32(i * 4, true)]);
      }
    }
  });
  return rows;
}
