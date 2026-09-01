/**
 * Cross-host LOD parity probe: lodPlan, drillDecision, encodeF32Values.
 */
import { readFileSync } from "node:fs";
import { createHash } from "node:crypto";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

import { drillDecision, encodeF32Values, lodPlan } from "../src/encode.js";

const ROOT = join(dirname(fileURLToPath(import.meta.url)), "..", "..", "..");
const FIXTURE = join(ROOT, "tests", "fixtures", "lod_cross_host.json");

function shaF32(values) {
  const bytes = new Float32Array(values).buffer;
  return createHash("sha256").update(Buffer.from(bytes)).digest("hex");
}

function runCase(spec) {
  if (spec.kind === "lod_plan") {
    const plan = lodPlan(spec.visible, spec.budget, {
      inDrill: spec.in_drill,
      exitFactor: spec.exit_factor,
      pxW: spec.width,
      pxH: spec.height,
      targetPerCell: spec.target_per_cell,
    });
    return {
      name: spec.name,
      exact: plan.exact,
      mode: plan.mode,
      grid_w: plan.gridW,
      grid_h: plan.gridH,
    };
  }
  if (spec.kind === "drill_decision") {
    const decision = drillDecision(spec.visible, spec.budget, {
      inDrill: spec.in_drill,
      exitFactor: spec.exit_factor,
    });
    return {
      name: spec.name,
      exact: decision.exact,
    };
  }
  const column = encodeF32Values(spec.values, spec.offset, spec.lo, spec.hi, {
    kind: spec.kind,
  });
  const meta = { ...column.meta };
  return {
    name: spec.name,
    meta,
    values_sha256: shaF32(column.values),
    length: column.length,
  };
}

const fixture = JSON.parse(readFileSync(FIXTURE, "utf8"));
const cases = fixture.cases.map(runCase);
process.stdout.write(`${JSON.stringify({ cases })}\n`);
