import assert from "node:assert/strict";
import test from "node:test";

import { payloadChannelWireEncode } from "../src/encode.js";

test("payloadChannelWireEncode continuous f32 and quantized u8", () => {
  assert.deepEqual(
    payloadChannelWireEncode({ role: "color", mode: "continuous" }),
    {
      bufKind: "f32",
      transform: "normalize",
      markDtypeU8: false,
      shipPalette: false,
      setN: false,
    },
  );
  assert.deepEqual(
    payloadChannelWireEncode({
      role: "size",
      mode: "continuous",
      quantizeContinuous: true,
    }),
    {
      bufKind: "u8",
      transform: "quantize_u8",
      markDtypeU8: true,
      shipPalette: false,
      setN: false,
    },
  );
});

test("payloadChannelWireEncode categorical u8 vs f32 threshold", () => {
  assert.deepEqual(
    payloadChannelWireEncode({
      role: "color",
      mode: "categorical",
      nCategories: 256,
    }),
    {
      bufKind: "u8",
      transform: "raw",
      markDtypeU8: true,
      shipPalette: true,
      setN: false,
    },
  );
  assert.equal(
    payloadChannelWireEncode({
      role: "color",
      mode: "categorical",
      nCategories: 257,
    }).bufKind,
    "f32",
  );
});

test("payloadChannelWireEncode direct rgba and style routing", () => {
  assert.deepEqual(
    payloadChannelWireEncode({ role: "color", mode: "direct_rgba" }),
    {
      bufKind: "u8",
      transform: "rgba_pack",
      markDtypeU8: false,
      shipPalette: false,
      setN: true,
    },
  );
  assert.deepEqual(
    payloadChannelWireEncode({
      role: "style",
      mode: "direct",
      styleDtypeU8: true,
    }),
    {
      bufKind: "u8",
      transform: "raw",
      markDtypeU8: false,
      shipPalette: false,
      setN: true,
    },
  );
});

test("payloadChannelWireEncode rejects invalid role/mode pairs", () => {
  assert.throws(
    () => payloadChannelWireEncode({ role: "size", mode: "categorical" }),
    /invalid payload-channel-wire-encode arguments/,
  );
});
