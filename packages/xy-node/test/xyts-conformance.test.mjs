import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";

import { sceneRasterCommands, sceneSvg } from "../src/index.js";

const fixture = JSON.parse(fs.readFileSync(
  new URL("../../../tests/fixtures/xyts_cross_host.json", import.meta.url), "utf8",
));

test("native Node consumes exact Rust-generated XYTS Scene v11 output", () => {
  assert.equal(fixture.authority, "crates/xyg-wasm/src/compile.rs");
  assert.equal(fixture.scene_version, 11);
  assert.equal(fixture.painter_version, 8);
  for (const value of fixture.successful) {
    const scene = Uint8Array.from(Buffer.from(value.scene_hex, "hex"));
    const view = new DataView(scene.buffer, scene.byteOffset, scene.byteLength);
    assert.equal(Buffer.from(scene.subarray(0, 4)).toString(), "XYGS", value.name);
    assert.equal(view.getUint32(4, true), fixture.scene_version, value.name);
    assert.equal(Number(view.getBigUint64(16, true)), value.records, value.name);
    assert.equal(Number(view.getBigUint64(24, true)), value.styles, value.name);
    assert.match(sceneSvg(scene), /^<svg xmlns=/, value.name);
    assert.ok(sceneRasterCommands(scene).length > 16, value.name);
  }
});

test("native Node retains arbitrary u64 data identity from the Rust fixture", () => {
  const value = fixture.successful.find((entry) => entry.name === "all_marks_reversed_domain");
  const scene = Uint8Array.from(Buffer.from(value.scene_hex, "hex"));
  const view = new DataView(scene.buffer, scene.byteOffset, scene.byteLength);
  const records = 160 + value.styles * 16;
  assert.equal(view.getBigUint64(records + 8, true), 0x5859010000000000n);
  assert.equal(scene[records + 3], 0x80, "literal prefix-like identity must remain data");
  assert.equal(view.getFloat64(records + 48, true), 8);
  assert.equal(view.getBigUint64(records + 2 * 56 + 8, true), 0x8000000000000001n);
  assert.equal(view.getBigUint64(records + 5 * 56 + 8, true), 0x8000000000000002n);
});
