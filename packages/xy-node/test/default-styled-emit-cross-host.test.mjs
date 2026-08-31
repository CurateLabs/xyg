import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";

import { DEFAULT_PALETTE, PROTOCOL_VERSION, abiVersion, figure } from "../src/index.js";

const fixture = JSON.parse(
  fs.readFileSync(
    new URL("../../../tests/fixtures/default_styled_emit_cross_host.json", import.meta.url),
    "utf8",
  ),
);

function buildCase(name) {
  const entry = fixture.cases.find((c) => c.name === name);
  if (entry == null) throw new Error(`unknown case ${name}`);
  const fig = figure({ width: 240, height: 160 });
  fig.line([0, 1], [0, 1]);
  fig.traces[0].id = entry.trace_id;
  fig.traces[0].style = { opacity: 0.9 };
  return fig.buildPayload();
}

test("default-styled emit cross-host fixture contract", () => {
  assert.equal(fixture.schema, "xyg.default-styled-emit-cross-host/v1");
  assert.equal(fixture.protocol, PROTOCOL_VERSION);
  assert.equal(Number(fixture.abi_version), abiVersion());
  assert.equal(fixture.cases.length, 1);
});

for (const entry of fixture.cases) {
  test(`Node default-styled emit matches fixture for ${entry.name}`, () => {
    const { spec } = buildCase(entry.name);
    const trace = spec.traces[0];
    assert.equal(trace.id, entry.trace_id);
    assert.equal(trace.kind, entry.kind);
    assert.deepEqual(trace.style, entry.style);
    assert.equal(DEFAULT_PALETTE[trace.id % DEFAULT_PALETTE.length], entry.palette_color);
  });
}
