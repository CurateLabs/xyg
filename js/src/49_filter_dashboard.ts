/** Ordinary linked charts (§34). DOM input and binary framing only: the Rust
 * session owns predicates, tiers, exact counts, canonical membership and paint. */
import type { ChartView } from "./50_chartview";

type Binding = {
  view: ChartView;
  id: bigint;
  sourceId: bigint;
  epoch: bigint;
  dimension: string;
  axis?: "x" | "y";
  cuts: number[];
  step: number;
  grid: {
    x: string;
    y: string;
    width: number;
    height: number;
    xRange: [number, number];
    yRange: [number, number];
    colors?: number[];
  };
};
/** Attach existing public composed ChartViews to one explicit canonical source.
 * Existing range brush gestures and focused-canvas keys share these methods.
 * B starts a range; Home/End choose an endpoint; arrows edit; Enter commits;
 * Escape restores the saved Rust predicate; Delete clears all brush clauses.
 * @experimental Bounded ordinary linked density; full #112 qualification remains open. */
export async function attachFilterDashboard(session: any, bindings: Binding[]) {
  if (
    !bindings.length ||
    bindings.some(
      (b) =>
        b.sourceId !== session.sourceId ||
        b.epoch !== session.epoch ||
        b.view._filterDashboard ||
        b.view._borrowedSurface ||
        b.view._polarGeometry() ||
        b.view.spec.graph_host ||
        b.view.spec.geo_host ||
        b.dimension !== (b.axis === "y" ? b.grid.y : b.grid.x) ||
        b.view.gpuTraces.length !== 1 ||
        b.view.gpuTraces[0].trace.kind !== "scatter" ||
        (b.view.gpuTraces[0].trace.x_axis ?? "x") !== "x" ||
        (b.view.gpuTraces[0].trace.y_axis ?? "y") !== "y" ||
        b.view._axisMode("x") !== 0 ||
        b.view._axisMode("y") !== 0 ||
        (b.view.gpuTraces[0].trace.color?.mode &&
          b.view.gpuTraces[0].trace.color.mode !== "constant") ||
        !Number.isFinite(b.step) ||
        b.step <= 0,
    )
  )
    throw new TypeError(
      "explicit compatible source, ordinary scatter views and positive keyboard steps are required",
    );
  if (
    new Set(bindings.map((b) => b.id)).size !== bindings.length ||
    new Set(bindings.map((b) => b.view)).size !== bindings.length
  )
    throw new TypeError("linked view identities must be unique");
  const grids = bindings.map((b) => ({ id: b.id, ...b.grid }));
  let chain = Promise.resolve(),
    generation = 0,
    closed = false,
    editing: { binding: Binding; bounds: number[]; endpoint: number } | null =
      null;
  let pointer: Binding | null = null,
    transaction = false,
    invalid = false;
  let ranges = new Map<bigint, number[]>(),
    savedRanges: Map<bigint, number[]> | null = null;
  const listeners: { view: ChartView; handler: EventListener }[] = [];
  const announce = (text: string, pending = false) => {
    for (const b of bindings) {
      b.view.canvas.setAttribute("aria-busy", String(pending));
      b.view.a11yLive.textContent = text;
    }
  };
  const active = async (b: Binding) =>
    (session.activateDensity ?? session.configureDensity).call(session,
      { id: b.id, dimension: b.dimension, cuts: b.cuts },
      grids,
    );
  const cancelEdit = async () => {
    if (transaction) {
      await session.cancelEdit();
      transaction = false;
      ranges = savedRanges;
      savedRanges = null;
    }
  };
  const beginEdit = async (b: Binding) => {
    await cancelEdit();
    await session.beginEdit();
    transaction = true;
    savedRanges = new Map(ranges);
    await active(b);
  };
  const commitEdit = async () => {
    if (transaction) {
      await session.commitEdit();
      transaction = false;
      savedRanges = null;
    }
  };
  const editRange = async (b: Binding, bounds: number[], paint = false) => {
    const reply = await (paint && typeof session.rangePaint === "function"
      ? session.rangePaint(bounds[0], bounds[1], { exact: true })
      : session.range(bounds[0], bounds[1], { exact: true }));
    ranges.set(b.id, bounds);
    return reply;
  };
  const apply = (reply: any, token: number) => {
    if (closed || token !== generation) return false;
    if (
      reply.sourceId !== session.sourceId ||
      reply.epoch !== session.epoch ||
      reply.sourceRevision !== session.sourceRevision ||
      reply.density.length !== bindings.length
    )
      throw new Error("stale or incompatible density packet");
    const replacements: { view: ChartView; old: any; next: any }[] = [];
    try {
      for (const b of bindings) {
        const view = b.view,
          plane = reply.density.find((p: any) => p.id === b.id);
        if (!plane || view._destroyed || view._glLost)
          throw new Error("linked surface is unavailable");
        const old = view.gpuTraces[0],
          columns = view.spec.columns;
        const bytes = new Uint8Array(
          plane.grid.byteLength + plane.rgba.byteLength,
        );
        bytes.set(
          new Uint8Array(
            plane.grid.buffer,
            plane.grid.byteOffset,
            plane.grid.byteLength,
          ),
        );
        bytes.set(plane.rgba, plane.grid.byteLength);
        const trace = {
          ...old.trace,
          tier: "density",
          n_points: Number(reply.sourceRows),
          n_marks: plane.grid.length,
          visible: Number(reply.sourceRows),
          density: {
            w: plane.width,
            h: plane.height,
            max: plane.maximum,
            enc: "f32",
            buf: 0,
            rgba: 1,
            colormap: old.trace.density?.colormap,
            x_range: plane.xRange,
            y_range: plane.yRange,
            filter: "nearest",
            coverage: "resolved",
          },
        };
        let next: any;
        try {
          view.spec.columns = [
            { dtype: "f32", len: plane.grid.length, byte_offset: 0 },
            {
              dtype: "u8",
              len: plane.rgba.length,
              byte_offset: plane.grid.byteLength,
            },
          ];
          next = view._buildTrace(bytes, trace);
        } finally {
          view.spec.columns = columns;
        }
        replacements.push({ view, old, next });
        if (view.gl.getError() !== view.gl.NO_ERROR)
          throw new Error("linked density upload failed");
        next.filterCounts = {
          total: plane.totals,
          selected: plane.selected,
          sourceId: reply.sourceId,
          epoch: reply.epoch,
          sourceRevision: reply.sourceRevision,
          revision: reply.revision,
          hash: reply.filterHash,
        };
      }
      // No async boundary: all five complete textures exist before publication.
      if (closed || token !== generation)
        throw new Error("superseded density publication");
      for (const { view, next } of replacements) {
        view.gpuTraces[0] = next;
        view._reapplyLegendVisibility();
        view._pickDirty = true;
        view._updatePickable();
      }
      for (const { view, old } of replacements)
        view._destroyTraceResources(old, new Set());
      for (const b of bindings) {
        const view = b.view,
          bounds = ranges.get(b.id);
        if (bounds) {
          const lo = Math.min(...bounds),
            hi = Math.max(...bounds),
            isY = b.axis === "y";
          view._boxSelection = {
            mode: isY ? "y" : "x",
            x0: isY ? view.view.x0 : lo,
            x1: isY ? view.view.x1 : hi,
            y0: isY ? lo : view.view.y0,
            y1: isY ? hi : view.view.y1,
          };
          view._stateSelection = { range: { ...view._boxSelection } };
          view._renderBoxSelection();
        } else {
          view._clearBoxOverlay();
          view._stateSelection = null;
        }
        view.canvas.style.visibility = "";
        view.draw();
        view._dispatchChartEvent("filter", { reply });
      }
    } catch (error) {
      for (const { view, next } of replacements)
        if (view.gpuTraces[0] !== next)
          view._destroyTraceResources(next, new Set());
      throw error;
    }
    controller.latest = reply;
    controller.error = null;
    for (const b of bindings) {
      if (!b.view._badges) b.view._buildReductionBadges(b.view.root);
      else b.view._refreshReductionBadges();
    }
    announce(
      `${reply.selectedCount} canonical rows selected across ${reply.affectedCount} views. Filter complete.`,
    );
    return true;
  };
  const enqueue = (work: () => Promise<any>, paint = true) => {
    const token = ++generation;
    announce("Filter pending.", true);
    const task = chain.then(async () => {
      if (closed || invalid)
        throw new Error(
          "filter dashboard source is unavailable; bind a new canonical session",
        );
      const result = await work();
      if (!paint) return null;
      const reply = result?.density?.length
        ? result : await session.paint({ exact: true });
      apply(reply, token);
      return reply;
    });
    chain = task.then(
      () => {},
      (error) => {
        if (token === generation) {
          controller.error = error;
          announce(`Filter failed: ${error.message}`);
          for (const b of bindings)
            b.view._dispatchChartEvent("filter_error", { error });
        }
      },
    );
    return task;
  };
  const controller: any = {
    latest: null,
    error: null,
    instructions: (view: ChartView) =>
      ` Range filter for ${bindings.find((b) => b.view === view).dimension}. Press B to create a range; Home or End chooses an endpoint; arrows adjust it; Enter commits; Escape cancels; Delete clears filters.`,
    badgeItems: () => {
      if (invalid) return ["Filter source unavailable"];
      const r = controller.latest;
      if (!r) return [];
      const work =
        r.tier === 3n
          ? "indexed"
          : r.fallback & 1n
            ? "exact boundary scan"
            : "exact rebuild";
      return [
        `${r.selectedCount} of ${r.sourceRows} canonical rows selected · ${work}`,
      ];
    },
    dragMode: (view: ChartView) =>
      bindings.find((b) => b.view === view).axis === "y"
        ? "select-y"
        : "select-x",
    ready: () => chain,
    refresh: () => enqueue(async () => {}),
    range: (id: bigint, lo: number, hi: number) =>
      enqueue(async () => {
        const b = bindings.find((b) => b.id === id);
        if (!b) throw new TypeError("unknown linked view");
        await commitEdit();
        await active(b);
        return editRange(b, [lo, hi], true);
      }),
    clear: () => {
      editing = null;
      pointer = null;
      return enqueue(async () => {
        await cancelEdit();
        editing = null;
        pointer = null;
        await session.clear();
        ranges.clear();
      });
    },
    append: (columns: any) =>
      enqueue(async () => {
        await session.append(columns);
      }),
    baseFilter: (ranges: any[], mask?: Uint8Array) =>
      enqueue(async () => {
        await session.baseFilter(ranges, mask);
      }),
    evict: () =>
      enqueue(async () => {
        await session.evict();
      }),
    beginPointer: (view: ChartView) => {
      const b = bindings.find((b) => b.view === view);
      pointer = b;
      editing = null;
      void enqueue(async () => {
        await beginEdit(b);
      }, false);
    },
    movePointer: (view: ChartView, d0: number[], d1: number[]) => {
      const b = pointer;
      if (!b || b.view !== view) return;
      const i = b.axis === "y" ? 1 : 0;
      void enqueue(async () => {
        return editRange(b, [d0[i], d1[i]], true);
      });
    },
    cancelPointer: () => {
      if (!pointer) return;
      pointer = null;
      void enqueue(async () => {
        await cancelEdit();
      });
    },
    pointer: (view: ChartView, d0: number[], d1: number[]) => {
      const b = bindings.find((b) => b.view === view),
        i = b.axis === "y" ? 1 : 0,
        wasPointer = pointer === b;
      pointer = null;
      void enqueue(async () => {
        if (!wasPointer) await beginEdit(b);
        await editRange(b, [d0[i], d1[i]]);
        await commitEdit();
      });
    },
    rejectTool: (mode: string) => {
      const error = new Error(
        `Selection tool ${mode} is unavailable in this range-filter binding.`,
      );
      controller.error = error;
      announce(error.message);
      for (const b of bindings)
        b.view._dispatchChartEvent("filter_error", { error });
    },
    rejectExternal: (type: string) => {
      const error = new Error(
        `External ${type} is unavailable while the canonical filter session owns selection. Use the filter protocol.`,
      );
      controller.error = error;
      announce(error.message);
      for (const b of bindings)
        b.view._dispatchChartEvent("filter_error", { error });
    },
    invalidateSource: () => {
      invalid = true;
      generation++;
      for (const b of bindings) {
        b.view.canvas.style.visibility = "hidden";
        b.view._refreshReductionBadges();
      }
      announce(
        "Canonical source changed outside the filter session. Bind a new canonical session.",
      );
    },
    key: (view: ChartView, e: KeyboardEvent) => {
      const b = bindings.find((b) => b.view === view);
      if (pointer && !["Delete", "Backspace", "Escape"].includes(e.key))
        return false;
      if (
        ![
          "b",
          "B",
          "Home",
          "End",
          "ArrowLeft",
          "ArrowRight",
          "ArrowUp",
          "ArrowDown",
          "Enter",
          "Escape",
          "Delete",
          "Backspace",
        ].includes(e.key)
      )
        return false;
      if (
        editing &&
        editing.binding.view !== view &&
        e.key !== "Delete" &&
        e.key !== "Backspace"
      )
        return false;
      if (
        e.key !== "b" &&
        e.key !== "B" &&
        e.key !== "Delete" &&
        e.key !== "Backspace" &&
        !editing
      )
        return false;
      e.preventDefault();
      e.stopPropagation();
      if (e.key === "Delete" || e.key === "Backspace") {
        void controller.clear();
        return true;
      }
      if (e.key === "b" || e.key === "B") {
        if (editing) return true;
        const range = b.axis === "y" ? b.grid.yRange : b.grid.xRange;
        editing = {
          binding: b,
          bounds: [Math.min(...range), Math.max(...range)],
          endpoint: 0,
        };
        const bounds = [...editing.bounds];
        void enqueue(async () => {
          await beginEdit(b);
          return editRange(b, bounds, true);
        });
      } else if (e.key === "Escape") {
        editing = null;
        void enqueue(async () => {
          await cancelEdit();
        });
      } else if (e.key === "Enter") {
        editing = null;
        void enqueue(async () => {
          await commitEdit();
        });
      } else if (e.key === "Home" || e.key === "End") {
        editing.endpoint = e.key === "Home" ? 0 : 1;
        announce(
          `Editing ${editing.endpoint === 0 ? "lower" : "upper"} range endpoint.`,
        );
      } else {
        editing.bounds[editing.endpoint] += ["ArrowRight", "ArrowUp"].includes(
          e.key,
        )
          ? editing.binding.step
          : -editing.binding.step;
        const bounds = [...editing.bounds];
        void enqueue(async () => {
          return editRange(b, bounds, true);
        });
      }
      return true;
    },
    destroy: () => {
      if (closed) return;
      closed = true;
      generation++;
      for (const { view, handler } of listeners) view._unlisten(handler);
      for (const b of bindings) {
        delete b.view._filterDashboard;
        b.view._initA11y();
        b.view._syncModebarSelect?.();
        b.view.canvas.removeAttribute("aria-keyshortcuts");
        b.view.canvas.setAttribute("aria-busy", "false");
      }
    },
  };
  try {
    await active(bindings[0]);
    for (const b of bindings) {
      b.view._wasmDensity?.destroy?.();
      b.view._wasmDensity = null;
      b.view._filterDashboard = controller;
      b.view._initA11y();
      b.view._setDragMode(b.axis === "y" ? "select-y" : "select-x");
      b.view.canvas.setAttribute(
        "aria-keyshortcuts",
        "B Home End ArrowLeft ArrowRight Enter Escape Delete",
      );
      const lost = () => {
        b.view.canvas.style.visibility = "hidden";
        generation++;
        announce("Filter surface rebuilding.", true);
      };
      const restored = () => {
        void controller.refresh();
      };
      for (const [event, handler] of [
        ["xy:context_lost", lost],
        ["xy:context_restored", restored],
      ] as const) {
        b.view._listen(b.view.root, event, handler);
        listeners.push({ view: b.view, handler });
      }
    }
    await controller.refresh();
    return controller;
  } catch (error) {
    controller.destroy();
    throw error;
  }
}
