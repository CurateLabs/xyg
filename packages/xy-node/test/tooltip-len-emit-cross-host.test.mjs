import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";

import { PROTOCOL_VERSION, abiVersion, figure } from "../src/index.js";

const fixture = JSON.parse(
  fs.readFileSync(
    new URL("../../../tests/fixtures/tooltip_len_emit_cross_host.json", import.meta.url),
    "utf8",
  ),
);

function buildCase(name) {
  const entry = fixture.cases.find((c) => c.name === name);
  if (entry == null) throw new Error(`unknown case ${name}`);
  const fig = figure({ width: 240, height: 160 });
  if (name === "scatter_tooltip_ok") {
    fig.scatter([1, 2, 3], [1, 2, 3]);
    fig.traces[0].tooltip_rows = [{ rank: 1 }, { rank: 2 }, { rank: 3 }];
    fig.traces[0].id = entry.trace_id;
  } else if (name === "segments_tooltip_ok") {
    fig.segments([0, 1], [0, 1], [1, 2], [1, 2]);
    fig.traces[0].tooltip_rows = [{ id: "a" }, { id: "b" }];
    fig.traces[0].id = entry.trace_id;
  } else if (name === "ribbon_tooltip_ok") {
    fig.ribbon([0, 1], [1, 2], [0, 1], [1, 2], [0.5, 1.5], [1.5, 2.5]);
    fig.traces[0].tooltip_rows = [{ id: "a" }, { id: "b" }];
    fig.traces[0].id = entry.trace_id;
  } else if (name === "scatter_tooltip_mismatch") {
    fig.scatter([0, 1], [0, 1]);
    fig.traces[0].tooltip_rows = [{ id: "a" }];
    fig.traces[0].id = entry.trace_id;
  } else if (name === "segments_tooltip_mismatch") {
    fig.segments([0, 1], [0, 1], [1, 2], [1, 2]);
    fig.traces[0].tooltip_rows = [{ id: "a" }];
    fig.traces[0].id = entry.trace_id;
  } else if (name === "ribbon_tooltip_mismatch") {
    fig.ribbon([0], [1], [0], [1], [0], [1]);
    fig.traces[0].tooltip_rows = [{ id: "a" }, { id: "b" }];
    fig.traces[0].id = entry.trace_id;
  } else {
    throw new Error(`unknown case ${name}`);
  }
  return { fig, entry };
}

test("tooltip-len emit cross-host fixture contract", () => {
  assert.equal(fixture.schema, "xyg.tooltip-len-emit-cross-host/v1");
  assert.equal(fixture.protocol, PROTOCOL_VERSION);
  assert.equal(Number(fixture.abi_version), abiVersion());
  assert.equal(fixture.cases.length, 6);
});

for (const entry of fixture.cases) {
  test(`Node tooltip-len emit matches fixture for ${entry.name}`, () => {
    const { fig } = buildCase(entry.name);
    if (entry.expect_error) {
      assert.throws(
        () => fig.buildPayload(),
        (err) => String(err?.message ?? err).includes(entry.error_match),
      );
      return;
    }
    const { spec } = fig.buildPayload();
    const trace = spec.traces[0];
    assert.equal(trace.id, entry.trace_id);
    assert.equal(trace.kind, entry.kind);
    assert.equal(trace.n_points, entry.n_points);
    assert.deepEqual(trace.tooltip_rows, entry.tooltip_rows);
  });
}
