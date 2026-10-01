// Python ↔ Node GraphForge parity (xyg#37): every case in
// tests/fixtures/graphforge/cross_host.json (written by the Python host,
// scripts/gen_graphforge_cross_host.py) must frame the same `XYGQ` request and
// compose the same `XYGF` document bytes here. Node ↔ WASM equivalence is
// graphforge-wasm-parity.test.mjs, so all three hosts agree byte for byte.
import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import fs from "node:fs";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

import { composeGraphForgeRequest, encodeGraphForgeRequest } from "../src/graphforge.js";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../../..");
const RESULTS = path.join(ROOT, "tests/fixtures/graphforge/results");
const DERIVED = path.join(ROOT, "tests/fixtures/graphforge/derived");
const MANIFEST = JSON.parse(fs.readFileSync(path.join(RESULTS, "manifest.json"), "utf8"));
const FIXTURE = JSON.parse(fs.readFileSync(path.join(ROOT, "tests/fixtures/graphforge/cross_host.json"), "utf8"));
const arrow = (name) => fs.readFileSync(path.join(RESULTS, `${name}.arrow`));
const sha256 = (bytes) => createHash("sha256").update(bytes).digest("hex");

function request(c) {
  const base = c.base
    ? { tables: [arrow(MANIFEST.bases[c.base].nodes), arrow(MANIFEST.bases[c.base].edges)], generation: MANIFEST.bases[c.base].generation }
    : undefined;
  const layers = c.layers.map((layer) => ({
    result: arrow(layer.result),
    intent: layer.intent,
    ...(layer.generation ? { generation: MANIFEST.bases[layer.generation].generation } : {}),
    ...(layer.result_id != null ? { resultId: layer.result_id } : {}),
    ...(layer.missing != null ? { missing: layer.missing } : {}),
    ...(layer.extra != null ? { extra: layer.extra } : {}),
    ...(layer.rows != null ? { rows: layer.rows } : {}),
    ...(layer.coordinates ? { coordinates: fs.readFileSync(path.join(DERIVED, `${layer.coordinates}.arrow`)) } : {}),
  }));
  return encodeGraphForgeRequest({ base, layers, select: c.select ?? null, render: c.render ?? null });
}

test("Node frames and composes the Python-pinned GraphForge bytes for every case", () => {
  assert.equal(FIXTURE.schema, "xyg.graphforge-cross-host/v1");
  assert.ok(FIXTURE.cases.length >= 99);
  for (const c of FIXTURE.cases) {
    const req = request(c);
    assert.equal(sha256(req), c.request_sha256, `${c.name}: request bytes differ from Python`);
    assert.equal(sha256(composeGraphForgeRequest(req)), c.document_sha256, `${c.name}: document bytes differ from Python`);
  }
});
