import {
  graphProjectionCreate,
  graphProjectionDestroy,
  temporalColumnCreate,
  temporalColumnDestroy,
  temporalGraphCancel,
  temporalGraphCreate,
  temporalGraphDestroy,
  temporalGraphFrame,
  temporalGraphRequiredBudget,
  temporalGraphSetFocus,
  temporalGraphSetPinned,
  temporalGraphSetSelection,
  temporalGraphSnapshot,
} from "./abi.js";

function createPlane(plane, name) {
  if (plane == null) return 0n;
  if (typeof plane !== "object" || plane.values == null || plane.validity == null) {
    throw new TypeError(`${name} requires values and validity TypedArrays`);
  }
  return temporalColumnCreate({
    values: plane.values,
    validity: plane.validity,
    timezone: plane.timezone ?? "UTC",
  });
}

/** Rust-owned temporal filtering over canonical graph UUID identity. */
export class TemporalGraph {
  #handle = null;

  constructor({
    nodeIds,
    edgeIds,
    sourceIds,
    targetIds,
    nodeValidFrom = null,
    nodeValidTo = null,
    nodeEventAt = null,
    edgeValidFrom = null,
    edgeValidTo = null,
    edgeEventAt = null,
    directed = true,
  }) {
    const projection = graphProjectionCreate({
      nodeIds, edgeIds, sourceIds, targetIds, directed,
    });
    const columns = [];
    try {
      for (const [name, plane] of [
        ["nodeValidFrom", nodeValidFrom],
        ["nodeValidTo", nodeValidTo],
        ["nodeEventAt", nodeEventAt],
        ["edgeValidFrom", edgeValidFrom],
        ["edgeValidTo", edgeValidTo],
        ["edgeEventAt", edgeEventAt],
      ]) columns.push(createPlane(plane, name));
      this.#handle = temporalGraphCreate({
        projectionHandle: projection,
        nodeValidFrom: columns[0],
        nodeValidTo: columns[1],
        nodeEventAt: columns[2],
        edgeValidFrom: columns[3],
        edgeValidTo: columns[4],
        edgeEventAt: columns[5],
      });
    } finally {
      for (const column of columns) if (column !== 0n) temporalColumnDestroy(column);
      graphProjectionDestroy(projection);
    }
  }

  #openHandle() {
    if (this.#handle == null) throw new Error("TemporalGraph is closed");
    return this.#handle;
  }

  get requiredBudget() {
    return temporalGraphRequiredBudget(this.#openHandle());
  }

  setSelection({ nodes = new Uint8Array(), edges = new Uint8Array() } = {}) {
    temporalGraphSetSelection(this.#openHandle(), { nodes, edges });
    return this;
  }

  setFocus(focus = null) {
    temporalGraphSetFocus(this.#openHandle(), focus);
    return this;
  }

  setPinned(nodes = new Uint8Array()) {
    temporalGraphSetPinned(this.#openHandle(), nodes);
    return this;
  }

  frame({ revision, cursor, range, budget = null }) {
    return temporalGraphFrame(this.#openHandle(), { revision, cursor, range, budget });
  }

  snapshot() {
    return temporalGraphSnapshot(this.#openHandle());
  }

  cancel() {
    temporalGraphCancel(this.#openHandle());
  }

  close() {
    const handle = this.#handle;
    this.#handle = null;
    if (handle != null) temporalGraphDestroy(handle);
  }
}
