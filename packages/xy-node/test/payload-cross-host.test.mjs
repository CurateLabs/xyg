import assert from "node:assert/strict";
import crypto from "node:crypto";
import fs from "node:fs";
import test from "node:test";

import { PROTOCOL_VERSION, abiVersion, figure } from "../src/index.js";

const fixture = JSON.parse(
  fs.readFileSync(new URL("../../../tests/fixtures/payload_cross_host.json", import.meta.url), "utf8"),
);

function sha256(buf) {
  return crypto.createHash("sha256").update(Buffer.from(buf)).digest("hex");
}

function buildCase(name) {
  const fig = figure({ width: 240, height: 160 });
  if (name === "scatter_direct") {
    fig.scatter([0, 1, 2], [0, 1, 0.5]);
    fig.traces[0].id = 7;
  } else if (name === "line_transition_keys") {
    fig.line([0, 1, 2], [0, 1, 0.5]);
    fig.traces[0].id = 8;
    fig.traces[0].transition_keys = [
      [1, 2],
      [3, 4],
      [5, 6],
    ];
  } else if (name === "histogram_fixed_bins") {
    fig.histogram([0, 1, 1, 2, 3], { bins: 3, range: [0, 3] });
    fig.traces[0].id = 10;
  } else if (name === "segments_pass_through") {
    fig.segments([0, 1], [0, 1], [1, 2], [1, 0]);
    fig.traces[0].id = 12;
  } else {
    throw new Error(`unknown case ${name}`);
  }
  return fig.buildPayload();
}

test("payload cross-host fixture contract", () => {
  assert.equal(fixture.schema, "xyg.payload-cross-host/v1");
  assert.equal(fixture.protocol, PROTOCOL_VERSION);
  assert.equal(Number(fixture.abi_version), abiVersion());
  assert.equal(fixture.cases.length, 4);
});

for (const entry of fixture.cases) {
  test(`Node payload blob matches Python fixture for ${entry.name}`, () => {
    const { spec, buffers } = buildCase(entry.name);
    const trace = spec.traces[0];
    assert.equal(trace.id, entry.trace_id);
    assert.equal(trace.kind, entry.kind);
    assert.equal(buffers.length, entry.payload_blob_len);
    assert.equal(sha256(buffers), entry.payload_blob_sha256);
    assert.equal(Buffer.from(buffers).toString("hex"), entry.payload_blob_hex);
    if (entry.trace_keys != null) {
      assert.deepEqual(trace.keys, entry.trace_keys);
      const lo = spec.columns[trace.keys.lo];
      const hi = spec.columns[trace.keys.hi];
      assert.equal(
        Buffer.from(buffers).subarray(lo.byte_offset, lo.byte_offset + lo.len * 4).toString("hex"),
        entry.keys_lo_hex,
      );
      assert.equal(
        Buffer.from(buffers).subarray(hi.byte_offset, hi.byte_offset + hi.len * 4).toString("hex"),
        entry.keys_hi_hex,
      );
    }
  });
}
