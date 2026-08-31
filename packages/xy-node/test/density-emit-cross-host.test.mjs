import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";

import { PROTOCOL_VERSION, abiVersion, figure } from "../src/index.js";

const fixture = JSON.parse(
  fs.readFileSync(new URL("../../../tests/fixtures/density_emit_cross_host.json", import.meta.url), "utf8"),
);

function buildCase(name) {
  const fig = figure({ width: 240, height: 160 });
  if (name === "scatter_density_colormap") {
    fig.scatter([0, 1, 2], [0, 1, 0.5], { forceDensity: true, colormap: "plasma" });
    fig.traces[0].id = 21;
    fig.traces[0].color_ch = { ...fig.traces[0].color_ch, colormap: "magma" };
  } else if (name === "scatter_density_dropped_channels") {
    fig.scatter([0, 1, 2], [0, 1, 0.5], { forceDensity: true, size: [1, 2, 3] });
    fig.traces[0].id = 22;
  } else {
    throw new Error(`unknown case ${name}`);
  }
  return fig.buildPayload();
}

test("density emit cross-host fixture contract", () => {
  assert.equal(fixture.schema, "xyg.density-emit-cross-host/v1");
  assert.equal(fixture.protocol, PROTOCOL_VERSION);
  assert.equal(Number(fixture.abi_version), abiVersion());
  assert.equal(fixture.cases.length, 2);
});

for (const entry of fixture.cases) {
  test(`Node density wire metadata matches fixture for ${entry.name}`, () => {
    const { spec } = buildCase(entry.name);
    const trace = spec.traces[0];
    const density = trace.density ?? {};
    assert.equal(trace.id, entry.trace_id);
    assert.equal(trace.tier, entry.tier);
    assert.equal(density.colormap, entry.density_colormap);
    assert.deepEqual(density.dropped_channels ?? [], entry.density_dropped_channels);
    assert.equal(Boolean(density.channels_dropped), entry.density_channels_dropped);
  });
}
