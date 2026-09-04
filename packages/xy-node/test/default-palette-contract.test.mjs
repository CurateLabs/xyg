import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

import {
  DEFAULT_MARK_COLOR,
  DEFAULT_PALETTE,
  DEFAULT_PALETTE_CONTRACT,
  defaultPaletteContract,
  figure,
} from "../src/index.js";

const fixture = JSON.parse(await readFile(
  new URL("../../../tests/fixtures/default_palette_contract.json", import.meta.url),
  "utf8",
));

test("Node consumes the exact Rust-owned default palette contract", () => {
  assert.equal(DEFAULT_PALETTE_CONTRACT.version, fixture.version);
  assert.deepEqual(DEFAULT_PALETTE, fixture.colors);
  assert.deepEqual(
    Array.from(DEFAULT_PALETTE_CONTRACT.rgba),
    fixture.rgba8.flat(),
  );
  assert.equal(DEFAULT_MARK_COLOR, fixture.default_mark_color);
  assert.deepEqual(defaultPaletteContract().colors, fixture.colors);
});

test("Node omitted mark color resolves to the Rust-owned first row", () => {
  const chart = figure().line([0, 1], [1, 2]);
  chart.traces[0].id = 0;
  chart.traces[0].style = { opacity: 0.9 };
  const { spec } = chart.buildPayload();
  assert.equal(spec.traces[0].style.color, fixture.default_mark_color);
});
