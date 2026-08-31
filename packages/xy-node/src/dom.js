/** Stable browser DOM slot names for CSS/Tailwind hooks (Python `dom.py`). */

export const CHART_DOM_SLOTS = new Set([
  "root",
  "title",
  "chrome",
  "canvas",
  "annotation_layer",
  "labels",
  "legend",
  "legend_title",
  "legend_item",
  "legend_swatch",
  "legend_label",
  "colorbar",
  "colorbar_bar",
  "colorbar_extension",
  "colorbar_line",
  "colorbar_tick",
  "colorbar_minor_tick",
  "colorbar_title",
  "tooltip",
  "tooltip_title",
  "tooltip_row",
  "tooltip_label",
  "tooltip_value",
  "modebar",
  "modebar_drag_handle",
  "modebar_control_group",
  "modebar_separator",
  "modebar_button",
  "modebar_icon",
  "modebar_zoom_value",
  "modebar_indicator",
  "modebar_selection_icon",
  "modebar_menu",
  "modebar_menu_separator",
  "modebar_menu_icon",
  "modebar_menu_label",
  "modebar_history_controls",
  "selection",
  "crosshair_x",
  "crosshair_y",
  "badge",
  "badge_item",
  "axis_band",
  "axis_line",
  "tick_mark",
  "tick_label",
  "axis_title",
  "annotation_label",
]);

/** Reject unknown DOM slots before they reach the standalone/widget spec. */
export function validateDomSlots(mapping, label) {
  if (mapping == null || typeof mapping !== "object" || Array.isArray(mapping)) {
    return;
  }
  const unknown = Object.keys(mapping)
    .filter((slot) => !CHART_DOM_SLOTS.has(slot))
    .sort();
  if (unknown.length > 0) {
    const slots = [...CHART_DOM_SLOTS].join(", ");
    throw new RangeError(
      `${label} has unknown slot(s) ${JSON.stringify(unknown)}; expected one of: ${slots}`,
    );
  }
}
