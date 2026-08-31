import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";

import { PROTOCOL_VERSION, SCATTER_DENSITY_THRESHOLD, abiVersion, figure } from "../src/index.js";

const fixture = JSON.parse(
  fs.readFileSync(new URL("../../../tests/fixtures/force_emit_cross_host.json", import.meta.url), "utf8"),
);

function fill(n, fn) {
  const out = new Float64Array(n);
  for (let i = 0; i < n; i += 1) out[i] = fn(i);
  return out;
}

function buildCase(name) {
  const entry = fixture.cases.find((c) => c.name === name);
  if (entry == null) throw new Error(`unknown case ${name}`);
  const n = entry.n_points;
  const x = fill(n, (i) => i / n);
  const y = fill(n, (i) => ((i * 3) % n) / n);
  const fig = figure({ width: 240, height: 160 });
  fig.scatter(x, y, entry.node_opts ?? {});
  fig.traces[0].id = entry.trace_id;
  return fig.buildPayload();
}

test("force emit cross-host fixture contract", () => {
  assert.equal(fixture.schema, "xyg.force-emit-cross-host/v1");
  assert.equal(fixture.protocol, PROTOCOL_VERSION);
  assert.equal(Number(fixture.abi_version), abiVersion());
  assert.equal(fixture.scatter_density_threshold, SCATTER_DENSITY_THRESHOLD);
  assert.equal(fixture.cases.length, 2);
});

for (const entry of fixture.cases) {
  test(`Node force emit tier matches fixture for ${entry.name}`, () => {
    const { spec } = buildCase(entry.name);
    const trace = spec.traces[0];
    assert.equal(trace.id, entry.trace_id);
    assert.equal(trace.n_points, entry.n_points);
    assert.equal(trace.tier, entry.tier);
    assert.equal(trace.n_marks, entry.n_marks);
  });
}
