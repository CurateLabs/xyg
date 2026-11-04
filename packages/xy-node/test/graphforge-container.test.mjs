// Pure wire codec regressions: this file runs without koffi or a native core.
import assert from "node:assert/strict";
import test from "node:test";
import { decodeContainer, encodeContainer, DTYPE } from "../src/graphforge-container.js";

const MAGIC = "XYGI";
const numeric = [
  ["u32", Uint32Array, [0, 1, 0x12345678, 0xffffffff]],
  ["u64", BigUint64Array, [0n, 1n, 9007199254740993n, 0xffffffffffffffffn]],
  ["i64", BigInt64Array, [0n, -1n, -(2n ** 63n), 2n ** 63n - 1n]],
  ["f64", Float64Array, [0, -0, -1.25, Number.MIN_VALUE, Number.MAX_VALUE]],
];
const cases = [
  ["Uint8Array", bytes => Uint8Array.from(bytes)],
  ["ArrayBuffer", bytes => Uint8Array.from(bytes).buffer],
  ["unaligned Uint8Array", bytes => {
    const backing = new Uint8Array(bytes.length + 19).fill(0xa5);
    backing.set(bytes, 3);
    return backing.subarray(3, 3 + bytes.length);
  }],
  ["unaligned DataView", bytes => {
    const backing = new Uint8Array(bytes.length + 19).fill(0xa5);
    backing.set(bytes, 3);
    return new DataView(backing.buffer, 3, bytes.length);
  }],
  ["pooled Buffer", bytes => {
    const backing = Buffer.allocUnsafe(bytes.length + 16).fill(0xa5);
    backing.set(bytes, 8);
    const input = backing.subarray(8, 8 + bytes.length);
    assert.ok(input.buffer.byteLength > input.byteLength);
    return input;
  }],
  ["odd backing Buffer", bytes => {
    const backing = Buffer.alloc(bytes.length + 1, 0xa5);
    backing.set(bytes);
    return backing.subarray(0, bytes.length);
  }],
  ["aligned sentinel Buffer", bytes => {
    const backing = Buffer.alloc(bytes.length + 16, 0xa5);
    backing.set(bytes, 8);
    return backing.subarray(8, 8 + bytes.length);
  }],
  ["unaligned sentinel Buffer", bytes => {
    const backing = Buffer.alloc(bytes.length + 19, 0xa5);
    backing.set(bytes, 3);
    return backing.subarray(3, 3 + bytes.length);
  }],
];
const asBytes = input => input instanceof ArrayBuffer
  ? new Uint8Array(input) : new Uint8Array(input.buffer, input.byteOffset, input.byteLength);

for (const [label, wrap] of cases) {
  test(`${label}: exact numeric spans, BigInts, zero index, empty sections and detached results`, () => {
    for (const [dtype, Array_, values] of numeric) {
      for (const expected of [values, []]) {
        const encoded = encodeContainer(MAGIC, [{ name: "values", dtype: DTYPE[dtype], values: expected }]);
        const input = wrap(encoded);
        const source = asBytes(input);
        assert.deepEqual([...source], [...encoded]);
        const sections = decodeContainer(input, MAGIC);
        assert.deepEqual([...sections.keys()], ["values#0"]);
        const section = sections.get("values#0");
        assert.equal(section.index, 0);
        assert.equal(section.dtype, DTYPE[dtype]);
        assert.equal(section.count, expected.length);
        assert.ok(section.value instanceof Array_);
        assert.equal(section.value.length, expected.length, "no prefix/suffix values");
        assert.equal(section.value.byteLength, expected.length * Array_.BYTES_PER_ELEMENT);
        assert.deepEqual([...section.value], expected);
        const before = Uint8Array.from(source);
        if (expected.length) section.value[0] = dtype === "u64" || dtype === "i64" ? 77n : 77;
        assert.deepEqual(source, before, "decoded writes must not change input");
        const again = decodeContainer(input, MAGIC).get("values#0").value;
        source.fill(0);
        assert.deepEqual([...again], expected, "input writes must not change decoded values");
      }
    }
  });

  test(`${label}: text offsets decode ASCII, UTF-8 and empty lists within the payload`, () => {
    const texts = [["", "alpha", "omega"], ["é", "🙂", "", "雪"], []];
    const encoded = encodeContainer(MAGIC, texts.map((values, index) => ({ name: "labels", index, dtype: DTYPE.texts, values })));
    const input = wrap(encoded);
    const sections = decodeContainer(input, MAGIC);
    assert.equal(sections.size, texts.length);
    texts.forEach((expected, index) => {
      const section = sections.get(`labels#${index}`);
      assert.equal(section.count, expected.length);
      assert.deepEqual(section.value, expected);
    });
    asBytes(input).fill(0);
    texts.forEach((expected, index) => assert.deepEqual(sections.get(`labels#${index}`).value, expected));
  });

  test(`${label}: generic f64 framing preserves nonfinite values for downstream policy`, () => {
    // Finiteness is the consuming Rust operation's policy, not container framing.
    const values = [NaN, Infinity, -Infinity];
    const input = wrap(encodeContainer(MAGIC, [{ name: "values", dtype: DTYPE.f64, values }]));
    assert.deepEqual([...decodeContainer(input, MAGIC).get("values#0").value], values);
  });
}

test("Buffer and Uint8Array reject the same malformed section bytes", () => {
  const numericBytes = () => encodeContainer(MAGIC, [{ name: "values", dtype: DTYPE.u64, values: [7n, 9n, 1n] }]);
  const textBytes = () => encodeContainer(MAGIC, [{ name: "labels", dtype: DTYPE.texts, values: ["abc", "de"] }]);
  const malformed = [
    ["version", numericBytes, view => view.setUint32(4, 2, true), /version/],
    ["total length", numericBytes, view => view.setBigUint64(16, 1n, true), /header/],
    ["name range", numericBytes, view => view.setUint32(32, 999, true), /name range/],
    ["unknown dtype", numericBytes, view => view.setUint32(40, 99, true), /section size/],
    ["count mismatch", numericBytes, view => view.setBigUint64(56, 4n, true), /section size/],
    ["unaligned offset", numericBytes, view => view.setBigUint64(48, 81n, true), /section range/],
    ["outside payload", numericBytes, view => view.setBigUint64(64, 1024n, true), /section range/],
    ["short text offsets", textBytes, view => view.setBigUint64(64, 8n, true), /texts/],
    ["decreasing text offsets", textBytes, view => view.setBigUint64(Number(view.getBigUint64(48, true)) + 16, 2n, true), /text offsets/],
    ["out of range text offsets", textBytes, view => view.setBigUint64(Number(view.getBigUint64(48, true)) + 8, 99n, true), /text offsets/],
  ];
  for (const [label, create, corrupt, reason] of malformed) {
    const bytes = create();
    corrupt(new DataView(bytes.buffer));
    for (const [wrapper, wrap] of cases) {
      assert.throws(() => decodeContainer(wrap(bytes), MAGIC), error => error instanceof RangeError && reason.test(error.message), `${label}: ${wrapper}`);
    }
  }
  const duplicate = encodeContainer(MAGIC, [0, 0].map(index => ({ name: "values", index, dtype: DTYPE.u32, values: [1] })));
  for (const [, wrap] of cases) assert.throws(() => decodeContainer(wrap(duplicate), MAGIC), /duplicate section/);
});
