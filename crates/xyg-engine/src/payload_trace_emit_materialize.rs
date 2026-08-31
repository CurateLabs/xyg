//! Trace payload entry materialize (ABI 321).

use crate::kernels::{self, normalize_f32_into};
use crate::lod_plan::{
    payload_bar_compact_admit, payload_errorbar_role_keys, payload_m4_indices,
    payload_visible_indices, PayloadIndexSel,
};
use crate::payload_channel_materialize::{payload_channel_materialize, PayloadChannelMaterializeOut};
use crate::payload_column_gather_materialize::{
    payload_column_gather_materialize, PayloadColumnMaterializeIn, PayloadColumnMaterializeOut,
};
use crate::payload_emit::{
    payload_bar_hist_emit_plan, payload_base_entry_plan, payload_channel_ship_plan,
    payload_column_ship_plan, payload_heatmap_emit_plan, payload_mesh_emit_plan,
    payload_nonxy_emit_plan, payload_ribbon_emit_plan, payload_scatter_emit_plan,
    payload_segments_emit_gather, payload_segments_emit_plan, payload_transition_entry_attach,
    PayloadChannelShipEntry, PayloadColumnShipEntry, PAYLOAD_BAR_HIST_KIND_BAR_COMPACT,
    PAYLOAD_BAR_ORIENTATION_HORIZONTAL, PAYLOAD_BAR_ORIENTATION_VERTICAL,
    PAYLOAD_CHAN_KEY_COLOR, PAYLOAD_CHAN_KEY_SIZE, PAYLOAD_CHAN_SHIP_COLOR,
    PAYLOAD_CHAN_SHIP_COLOR_SIZE, PAYLOAD_CHAN_SHIP_STYLE, PAYLOAD_CHAN_SLOT_COLOR,
    PAYLOAD_CHAN_SLOT_COLOR2, PAYLOAD_CHAN_SLOT_STROKE, PAYLOAD_CHAN_WIRE_ROLE_COLOR,
    PAYLOAD_CHAN_WIRE_ROLE_SIZE, PAYLOAD_CHAN_WIRE_ROLE_STYLE, PAYLOAD_COL_KEY_POS,
    PAYLOAD_COL_KEY_VALUE0, PAYLOAD_COL_KEY_VALUE1, PAYLOAD_COL_SCALE_X, PAYLOAD_COL_SCALE_Y,
    PAYLOAD_COL_SHIP_F64, PAYLOAD_COL_SHIP_OFFSET, PAYLOAD_COL_SHIP_VALUES,
    PAYLOAD_GATHER_M4, PAYLOAD_GATHER_RECT_FINITE, PAYLOAD_GATHER_SEGMENTS,
    PAYLOAD_GATHER_VALID_INDICES, PAYLOAD_GATHER_VISIBLE_SEL, PAYLOAD_HEATMAP_PATH_GRID,
    PAYLOAD_HEATMAP_PATH_RGBA, PAYLOAD_NONXY_KIND_HEXBIN, PAYLOAD_NONXY_KIND_RECT,
    PAYLOAD_SEGMENTS_TIER_DECIMATED, PAYLOAD_SHIP_CHANNELS_ALWAYS, PAYLOAD_SHIP_CHANNELS_IF_COLOR,
    PAYLOAD_TRACE_SLOT_BASE, PAYLOAD_TRACE_SLOT_X, PAYLOAD_TRACE_SLOT_X0, PAYLOAD_TRACE_SLOT_X1,
    PAYLOAD_TRACE_SLOT_Y, PAYLOAD_TRACE_SLOT_Y0, PAYLOAD_TRACE_SLOT_Y1, PAYLOAD_COLUMN_SHIP_MAX,
    PAYLOAD_CHANNEL_SHIP_MAX,
};

pub const PAYLOAD_TRACE_EMIT_MAX_BYTES: usize = 1 << 28;
pub const PAYLOAD_TRACE_EMIT_MAX_GEOM: usize = 8;
pub const PAYLOAD_TRACE_EMIT_MAX_CHANNELS: usize = 5;
pub const PAYLOAD_TRACE_EMIT_PATH_ENTRY: i32 = 0;
pub const PAYLOAD_TRACE_EMIT_PATH_DENSITY: i32 = 1;
pub const PAYLOAD_TRACE_EMIT_PATH_RECT_FALLBACK: i32 = 2;
pub const PAYLOAD_TRACE_EMIT_PATH_HEATMAP_RGBA: i32 = 3;
pub const PAYLOAD_TRACE_EMIT_PATH_HEATMAP_GRID: i32 = 4;
pub const PAYLOAD_TRACE_COL_X: usize = 0;
pub const PAYLOAD_TRACE_COL_Y: usize = 1;
pub const PAYLOAD_TRACE_COL_X0: usize = 2;
pub const PAYLOAD_TRACE_COL_X1: usize = 3;
pub const PAYLOAD_TRACE_COL_Y0: usize = 4;
pub const PAYLOAD_TRACE_COL_Y1: usize = 5;
pub const PAYLOAD_TRACE_COL_BASE: usize = 6;

const TRACE_SLOTS: [usize; 7] = [
    PAYLOAD_TRACE_SLOT_X as usize,
    PAYLOAD_TRACE_SLOT_Y as usize,
    PAYLOAD_TRACE_SLOT_X0 as usize,
    PAYLOAD_TRACE_SLOT_X1 as usize,
    PAYLOAD_TRACE_SLOT_Y0 as usize,
    PAYLOAD_TRACE_SLOT_Y1 as usize,
    PAYLOAD_TRACE_SLOT_BASE as usize,
];

#[derive(Clone, Debug, Default)]
pub struct PayloadTraceColumnIn<'a> {
    pub present: i32,
    pub values: &'a [f64],
    pub col_min: f64,
    pub col_max: f64,
    pub null_count: u64,
    pub sticky_offset: f64,
    pub kind: Option<&'a str>,
}

#[derive(Clone, Debug, Default)]
pub struct PayloadTraceChannelIn<'a> {
    pub present: i32,
    pub mode: i32,
    pub n_categories: usize,
    pub domain_lo: f64,
    pub domain_hi: f64,
    pub values_f64: &'a [f64],
    pub values_u8: &'a [u8],
    pub style_dtype_u8: i32,
    pub null_count: u64,
}

#[derive(Clone, Debug)]
pub struct PayloadTraceEmitMaterializeIn<'a> {
    pub kind: &'a str,
    pub n_points: u64,
    pub segment_count: u64,
    pub polar: i32,
    pub force_density: i32,
    pub per_item: i32,
    pub x_axis_type: i32,
    pub y_axis_type: i32,
    pub x_axis_scale: &'a str,
    pub y_axis_scale: &'a str,
    pub xr0: f64,
    pub xr1: f64,
    pub px_width: u32,
    pub style_color_is_none: i32,
    pub has_trace_animation: i32,
    pub has_transition_keys: i32,
    pub has_tooltip_rows: i32,
    pub n_tooltip_rows: usize,
    pub orientation: &'a str,
    pub has_color2_ch: i32,
    pub has_color_ch: i32,
    pub has_stroke_ch: i32,
    pub has_style_channels: i32,
    pub color_ch: PayloadTraceChannelIn<'a>,
    pub stroke_ch: PayloadTraceChannelIn<'a>,
    pub color2_ch: PayloadTraceChannelIn<'a>,
    pub size_ch: PayloadTraceChannelIn<'a>,
    pub style_channels: PayloadTraceChannelIn<'a>,
    pub transition_keys_lo: Option<&'a [u32]>,
    pub transition_keys_hi: Option<&'a [u32]>,
    pub columns: [PayloadTraceColumnIn<'a>; 7],
    pub bin_x: Option<&'a [f64]>,
    pub bin_x0: f64,
    pub bin_x1: f64,
    pub heatmap_rows: u32,
    pub heatmap_cols: u32,
    pub has_rgba_grid: i32,
    pub borrow_heatmaps: i32,
    pub style_colormap_is_none: i32,
    pub grid_values: Option<&'a [f64]>,
    pub grid_domain_lo: f64,
    pub grid_domain_hi: f64,
    pub max_rows: usize,
}

#[derive(Clone, Debug)]
pub struct PayloadTraceGeomOut {
    pub registry_key: i32,
    pub nested: i32,
    pub column: PayloadColumnMaterializeOut,
}

#[derive(Clone, Debug)]
pub struct PayloadTraceChannelWireOut {
    pub registry_key: i32,
    pub wire: PayloadChannelMaterializeOut,
}

#[derive(Clone, Debug, Default)]
pub struct PayloadTraceBarOut {
    pub orientation: i32,
    pub value_axis: i32,
    pub width: f64,
    pub has_value0_const: i32,
    pub value0_const: f64,
}

#[derive(Clone, Debug)]
pub struct PayloadTraceHeatmapOut {
    pub grid_buf: PayloadColumnMaterializeOut,
}

#[derive(Clone, Debug, Default)]
pub struct PayloadTraceEmitMaterialized {
    pub emit_path: i32,
    pub tier: i32,
    pub n_marks: u64,
    pub decimation_px: u32,
    pub apply_palette_default: i32,
    pub attach_animation: i32,
    pub attach_transition: i32,
    pub attach_tooltip: i32,
    pub filter_tooltip_by_sel: i32,
    pub tooltip_length_ok: i32,
    pub clear_shipped_sel: i32,
    pub set_shipped_sel: i32,
    pub drill_mode_false: i32,
    pub attempt_role_keys: i32,
    pub animation_fallback: i32,
    pub geometry: Vec<PayloadTraceGeomOut>,
    pub channels: Vec<PayloadTraceChannelWireOut>,
    pub transition_lo: Vec<u8>,
    pub transition_hi: Vec<u8>,
    pub bar: Option<PayloadTraceBarOut>,
    pub heatmap: Option<PayloadTraceHeatmapOut>,
    pub heatmap_attach_color: i32,
    pub heatmap_attach_encoding: i32,
    pub heatmap_borrow_canonical: i32,
}

fn col_values<'a>(cols: &'a [PayloadTraceColumnIn<'a>], idx: usize) -> Option<&'a [f64]> {
    (cols[idx].present != 0).then_some(cols[idx].values)
}

fn apply_sel(values: &[f64], sel: Option<&[u32]>) -> Result<Vec<f64>, i32> {
    match sel {
        None => Ok(values.to_vec()),
        Some(sel) if sel.is_empty() => Ok(Vec::new()),
        Some(sel) => sel
            .iter()
            .map(|&i| values.get(i as usize).copied().ok_or(-1))
            .collect(),
    }
}

fn combine_sel(outer: Option<&[u32]>, inner: &[u32]) -> Vec<u32> {
    match outer {
        None => inner.to_vec(),
        Some(o) => inner.iter().map(|&j| o[j as usize]).collect(),
    }
}

fn min_max(values: &[f64]) -> (f64, f64) {
    let mut lo = f64::INFINITY;
    let mut hi = f64::NEG_INFINITY;
    for &v in values {
        if v.is_finite() {
            lo = lo.min(v);
            hi = hi.max(v);
        }
    }
    if lo.is_finite() { (lo, hi) } else { (0.0, 0.0) }
}

fn finite_indices(candidates: &[&[f64]], len: usize) -> Result<Option<Vec<u32>>, i32> {
    if candidates.is_empty() {
        return Ok(None);
    }
    let mut out = vec![0u32; len];
    let count = kernels::valid_row_indices_f64(candidates, 0, &mut out).ok_or(-1)?;
    if count == len { Ok(None) } else { out.truncate(count); Ok(Some(out)) }
}

fn rect_finite_sel(cols: &[PayloadTraceColumnIn<'_>], len: usize, color: &PayloadTraceChannelIn<'_>) -> Result<Option<Vec<u32>>, i32> {
    let mut cands = Vec::new();
    for idx in [PAYLOAD_TRACE_COL_X0, PAYLOAD_TRACE_COL_X1, PAYLOAD_TRACE_COL_Y0, PAYLOAD_TRACE_COL_Y1] {
        if cols[idx].null_count > 0 {
            cands.push(cols[idx].values);
        }
    }
    if color.present != 0 && color.mode == 1 {
        cands.push(color.values_f64);
    }
    finite_indices(&cands, len)
}

fn column_plan(kind: &str, x_type: i32, y_type: i32, orient: i32) -> Result<(i32, i32, Vec<PayloadColumnShipEntry>), i32> {
    let mut gather = 0;
    let mut gather_color = 0;
    let mut n = 0usize;
    let mut xs = 0;
    let mut ys = 0;
    let mut cols = [PayloadColumnShipEntry { registry_key: 0, trace_slot: 0, ship_method: 0, ship_scale: 0, gather: 0 }; PAYLOAD_COLUMN_SHIP_MAX];
    if payload_column_ship_plan(kind, x_type, y_type, orient, &mut gather, &mut gather_color, &mut n, &mut xs, &mut ys, &mut cols) == 0 {
        return Err(-1);
    }
    Ok((gather, gather_color, cols[..n].to_vec()))
}

fn gather_arrays(plan: &[PayloadColumnShipEntry], cols: &[PayloadTraceColumnIn<'_>], sel: Option<&[u32]>) -> Result<Vec<Vec<f64>>, i32> {
    let mut max_key = 0usize;
    for e in plan { max_key = max_key.max(e.registry_key as usize); }
    let mut out = vec![Vec::new(); max_key + 1];
    for e in plan {
        let slot = TRACE_SLOTS.iter().position(|&s| s == e.trace_slot as usize).unwrap_or(e.trace_slot as usize);
        out[e.registry_key as usize] = apply_sel(cols[slot].values, sel)?;
    }
    Ok(out)
}

fn materialize_columns(plan: &[PayloadColumnShipEntry], cols: &[PayloadTraceColumnIn<'_>], arrays: &[Vec<f64>], x_scale: &str, y_scale: &str) -> Result<Vec<PayloadColumnMaterializeOut>, i32> {
    let mut inputs = Vec::with_capacity(plan.len());
    for e in plan {
        let slot = TRACE_SLOTS.iter().position(|&s| s == e.trace_slot as usize).unwrap_or(e.trace_slot as usize);
        let col = &cols[slot];
        let values = &arrays[e.registry_key as usize];
        let (lo, hi, sticky, kind) = if e.ship_method == PAYLOAD_COL_SHIP_OFFSET {
            (col.col_min, col.col_max, col.sticky_offset, col.kind)
        } else if e.ship_method == PAYLOAD_COL_SHIP_VALUES {
            let mm = min_max(values); (mm.0, mm.1, 0.0, col.kind)
        } else {
            (0.0, 0.0, 0.0, col.kind)
        };
        inputs.push(PayloadColumnMaterializeIn {
            ship_method: e.ship_method,
            ship_scale: e.ship_scale,
            values,
            col_min: lo,
            col_max: hi,
            kind,
            sticky_offset: sticky,
            axis_scale: if e.ship_scale == PAYLOAD_COL_SCALE_Y { y_scale } else { x_scale },
        });
    }
    payload_column_gather_materialize(None, &inputs)
}

fn materialize_channel(role: i32, ch: &PayloadTraceChannelIn<'_>, sel: Option<&[u32]>) -> Result<PayloadChannelMaterializeOut, i32> {
    payload_channel_materialize(role, ch.mode, ch.n_categories, ch.style_dtype_u8, 0, ch.domain_lo, ch.domain_hi, 0, sel, ch.values_f64, ch.values_u8)
}

fn materialize_channels(plan: &[PayloadChannelShipEntry], inp: &PayloadTraceEmitMaterializeIn<'_>, sel: Option<&[u32]>) -> Result<Vec<PayloadTraceChannelWireOut>, i32> {
    let mut out = Vec::new();
    for e in plan {
        match e.ship_method {
            PAYLOAD_CHAN_SHIP_COLOR_SIZE => {
                out.push(PayloadTraceChannelWireOut { registry_key: PAYLOAD_CHAN_KEY_COLOR, wire: materialize_channel(PAYLOAD_CHAN_WIRE_ROLE_COLOR, &inp.color_ch, sel)? });
                out.push(PayloadTraceChannelWireOut { registry_key: PAYLOAD_CHAN_KEY_SIZE, wire: materialize_channel(PAYLOAD_CHAN_WIRE_ROLE_SIZE, &inp.size_ch, sel)? });
            }
            PAYLOAD_CHAN_SHIP_COLOR => {
                let ch = match e.trace_slot { PAYLOAD_CHAN_SLOT_COLOR => &inp.color_ch, PAYLOAD_CHAN_SLOT_COLOR2 => &inp.color2_ch, PAYLOAD_CHAN_SLOT_STROKE => &inp.stroke_ch, _ => return Err(-1) };
                out.push(PayloadTraceChannelWireOut { registry_key: e.registry_key, wire: materialize_channel(PAYLOAD_CHAN_WIRE_ROLE_COLOR, ch, sel)? });
            }
            PAYLOAD_CHAN_SHIP_STYLE => out.push(PayloadTraceChannelWireOut { registry_key: e.registry_key, wire: materialize_channel(PAYLOAD_CHAN_WIRE_ROLE_STYLE, &inp.style_channels, sel)? }),
            _ => return Err(-1),
        }
    }
    Ok(out)
}

fn attach_transition(out: &mut PayloadTraceEmitMaterialized, inp: &PayloadTraceEmitMaterializeIn<'_>, sel: Option<&[u32]>, tier_direct: i32, n_marks: usize, key_lo: Option<&[u32]>, key_hi: Option<&[u32]>) -> Result<(), i32> {
    let mut aa = 0; let mut ak = 0; let mut fk = 0; let mut sk = 0; let mut af = 0; let mut at = 0; let mut ft = 0; let mut tok = 1;
    if payload_transition_entry_attach(inp.has_trace_animation, out.attach_animation, i32::from(key_lo.is_some() || inp.has_transition_keys != 0), i32::from(key_lo.is_some()), i32::from(sel.is_some()), tier_direct, n_marks, inp.transition_keys_lo.map(|k| k.len()).unwrap_or(0), key_lo.map(|k| k.len()).unwrap_or(0), sel.map(|s| s.len()).unwrap_or(0), inp.max_rows, inp.has_tooltip_rows, inp.n_tooltip_rows, inp.n_points as usize, &mut aa, &mut ak, &mut fk, &mut sk, &mut af, &mut at, &mut ft, &mut tok) == 0 { return Err(-1); }
    out.attach_animation = out.attach_animation.max(aa);
    out.attach_transition = i32::from(ak != 0);
    out.attach_tooltip = at; out.filter_tooltip_by_sel = ft; out.tooltip_length_ok = tok; out.animation_fallback = af;
    if sk == 0 { return Ok(()); }
    let lo_src = key_lo.or(inp.transition_keys_lo).ok_or(-1)?;
    let hi_src = key_hi.or(inp.transition_keys_hi).ok_or(-1)?;
    let (lo, hi) = if fk != 0 { (sel.ok_or(-1)?.iter().map(|&i| lo_src[i as usize]).collect::<Vec<_>>(), sel.ok_or(-1)?.iter().map(|&i| hi_src[i as usize]).collect()) } else { (lo_src.to_vec(), hi_src.to_vec()) };
    out.transition_lo = lo.iter().flat_map(|v| v.to_le_bytes()).collect();
    out.transition_hi = hi.iter().flat_map(|v| v.to_le_bytes()).collect();
    Ok(())
}

fn emit_kind(kind: &str) -> &str {
    match kind {
        "histogram" | "box" | "violin" => "rect",
        "bar" | "column" => "bar_compact",
        "error_band" => "area",
        "errorbar" | "stem" | "box_median" | "box_whisker" | "contour" => "segments",
        other => other,
    }
}

pub fn payload_trace_emit_materialize(inp: &PayloadTraceEmitMaterializeIn<'_>) -> Result<PayloadTraceEmitMaterialized, i32> {
    let mut out = PayloadTraceEmitMaterialized { emit_path: PAYLOAD_TRACE_EMIT_PATH_ENTRY, tooltip_length_ok: 1, ..Default::default() };
    let x_log = inp.x_axis_scale == "log";
    let y_log = inp.y_axis_scale == "log";
    let kind = emit_kind(inp.kind);

    if inp.kind == "scatter" {
        let mut ed = 0; let mut cs = 0; let mut df = 0; let mut ss = 0; let mut td = 0; let mut nm = 0usize; let mut ap = 0; let mut aa = 0; let mut xs = 0; let mut ys = 0; let mut cslo = 0; let mut its = 0; let mut atr = 0; let mut att = 0; let mut fts = 0; let mut tok = 1;
        if payload_scatter_emit_plan(inp.n_points, inp.polar, inp.force_density, 0, inp.per_item, inp.n_points as usize, inp.has_trace_animation, inp.x_axis_type, inp.y_axis_type, inp.has_transition_keys, inp.has_tooltip_rows, inp.n_tooltip_rows, &mut ed, &mut cs, &mut df, &mut ss, &mut td, &mut nm, &mut ap, &mut aa, &mut xs, &mut ys, &mut cslo, &mut its, &mut atr, &mut att, &mut fts, &mut tok) == 0 { return Err(-1); }
        if ed != 0 { out.emit_path = PAYLOAD_TRACE_EMIT_PATH_DENSITY; out.clear_shipped_sel = cs; out.drill_mode_false = df; out.attach_transition = atr; return Ok(out); }
        out.set_shipped_sel = ss; out.n_marks = nm as u64; out.attach_animation = aa; out.attach_tooltip = att; out.filter_tooltip_by_sel = fts; out.tooltip_length_ok = tok;
    }

    if inp.kind == "heatmap" {
        let rows = inp.heatmap_rows as usize; let cols_n = inp.heatmap_cols as usize;
        let mut path = 0; let mut td = 0; let mut nm = 0usize; let mut ac = 0; let mut bc = 0; let mut ae = 0; let mut uc = 0;
        if payload_heatmap_emit_plan(inp.has_rgba_grid, rows, cols_n, inp.style_colormap_is_none, inp.borrow_heatmaps, &mut path, &mut td, &mut nm, &mut ac, &mut bc, &mut ae, &mut uc) == 0 { return Err(-1); }
        out.n_marks = nm as u64;
        if path == PAYLOAD_HEATMAP_PATH_RGBA { out.emit_path = PAYLOAD_TRACE_EMIT_PATH_HEATMAP_RGBA; return Ok(out); }
        out.emit_path = PAYLOAD_TRACE_EMIT_PATH_HEATMAP_GRID; out.heatmap_attach_color = ac; out.heatmap_attach_encoding = ae; out.heatmap_borrow_canonical = bc;
        if bc == 0 {
            let grid = inp.grid_values.ok_or(-1)?;
            let mut enc = vec![0f32; grid.len()];
            normalize_f32_into(grid, inp.grid_domain_lo, inp.grid_domain_hi, f32::NAN, &mut enc);
            out.heatmap = Some(PayloadTraceHeatmapOut { grid_buf: PayloadColumnMaterializeOut { dtype_code: 0, offset: 0.0, scale: 1.0, has_kind: 0, len: enc.len() as u32, bytes: enc.iter().flat_map(|v| v.to_le_bytes()).collect() } });
        }
        let _ = uc; return Ok(out);
    }

    if kind == "bar_compact" {
        let x0 = col_values(&inp.columns, PAYLOAD_TRACE_COL_X0).ok_or(-1)?;
        let x1 = col_values(&inp.columns, PAYLOAD_TRACE_COL_X1).ok_or(-1)?;
        let y0 = col_values(&inp.columns, PAYLOAD_TRACE_COL_Y0).ok_or(-1)?;
        let y1 = col_values(&inp.columns, PAYLOAD_TRACE_COL_Y1).ok_or(-1)?;
        let x = col_values(&inp.columns, PAYLOAD_TRACE_COL_X).ok_or(-1)?;
        let y = col_values(&inp.columns, PAYLOAD_TRACE_COL_Y).ok_or(-1)?;
        let orient = if inp.orientation == "horizontal" { PAYLOAD_BAR_ORIENTATION_HORIZONTAL } else { PAYLOAD_BAR_ORIENTATION_VERTICAL };
        let (widths, pos, v0, v1) = if orient == PAYLOAD_BAR_ORIENTATION_VERTICAL {
            (x1.iter().zip(x0).map(|(a,b)| a-b).collect::<Vec<_>>(), x.to_vec(), y0.to_vec(), y.to_vec())
        } else {
            (y1.iter().zip(y0).map(|(a,b)| a-b).collect(), y0.iter().zip(y1).map(|(a,b)| (a+b)/2.0).collect(), x0.to_vec(), x1.to_vec())
        };
        let mut width = 0.0; let mut v0c = 0.0; let mut hv0 = 0; let mut compact = 0;
        if payload_bar_compact_admit(&widths, &v0, &mut width, &mut v0c, &mut hv0, &mut compact) == 0 { return Err(-1); }
        if compact == 0 { out.emit_path = PAYLOAD_TRACE_EMIT_PATH_RECT_FALLBACK; return Ok(out); }
        let finite = rect_finite_sel(&inp.columns, x0.len(), &inp.color_ch)?;
        let pos = apply_sel(&pos, finite.as_deref())?; let v0 = apply_sel(&v0, finite.as_deref())?; let v1 = apply_sel(&v1, finite.as_deref())?;
        let mut eb = 0; let mut td = 0; let mut nm = 0usize; let mut ap = 0; let mut xs = 0; let mut ys = 0; let mut ps = 0; let mut vs = 0; let mut va = 0; let mut cslot = 0; let mut ist = 0; let mut atr = 0;
        if payload_bar_hist_emit_plan(PAYLOAD_BAR_HIST_KIND_BAR_COMPACT, 1, pos.len(), inp.style_color_is_none, inp.x_axis_type, inp.y_axis_type, orient, &mut eb, &mut td, &mut nm, &mut ap, &mut xs, &mut ys, &mut ps, &mut vs, &mut va, &mut cslot, &mut ist, &mut atr) == 0 { return Err(-1); }
        out.n_marks = nm as u64; out.apply_palette_default = ap; out.attach_transition = atr;
        let (_, _, plan) = column_plan("bar_compact", inp.x_axis_type, inp.y_axis_type, orient)?;
        let mut arrays = vec![Vec::new(); PAYLOAD_COL_KEY_VALUE1 as usize + 1];
        arrays[PAYLOAD_COL_KEY_POS as usize] = pos; arrays[PAYLOAD_COL_KEY_VALUE0 as usize] = v0; arrays[PAYLOAD_COL_KEY_VALUE1 as usize] = v1;
        let plan_f: Vec<_> = plan.iter().filter(|c| hv0 == 0 || c.registry_key != PAYLOAD_COL_KEY_VALUE0).copied().collect();
        let mats = materialize_columns(&plan_f, &inp.columns, &arrays, inp.x_axis_scale, inp.y_axis_scale)?;
        out.bar = Some(PayloadTraceBarOut { orientation: orient, value_axis: va, width, has_value0_const: hv0, value0_const: v0c });
        for (e, c) in plan_f.iter().zip(mats.iter()) { out.geometry.push(PayloadTraceGeomOut { registry_key: e.registry_key, nested: 1, column: c.clone() }); }
        let mut nc = 0usize; let mut cp = [PayloadChannelShipEntry { registry_key: 0, trace_slot: 0, ship_method: 0 }; PAYLOAD_CHANNEL_SHIP_MAX];
        if payload_channel_ship_plan(cslot, ist, 0, inp.has_color_ch, inp.has_stroke_ch, inp.has_style_channels, &mut nc, &mut cp) == 0 { return Err(-1); }
        out.channels = materialize_channels(&cp[..nc], inp, finite.as_deref())?;
        attach_transition(&mut out, inp, finite.as_deref(), 1, nm, None, None)?;
        return Ok(out);
    }

    let orient = if inp.orientation == "horizontal" { PAYLOAD_BAR_ORIENTATION_HORIZONTAL } else { PAYLOAD_BAR_ORIENTATION_VERTICAL };
    let (gather, gather_color, plan) = column_plan(kind, inp.x_axis_type, inp.y_axis_type, orient)?;
    let mut sel: Option<Vec<u32>> = None; let mut ch_sel: Option<Vec<u32>> = None; let mut dec = false; let mut role_lo: Option<Vec<u32>> = None; let mut role_hi: Option<Vec<u32>> = None; let mut attempt_role = 0;

    if gather == PAYLOAD_GATHER_M4 {
        let x = col_values(&inp.columns, PAYLOAD_TRACE_COL_X).ok_or(-1)?; let y = col_values(&inp.columns, PAYLOAD_TRACE_COL_Y).ok_or(-1)?; let base = col_values(&inp.columns, PAYLOAD_TRACE_COL_BASE);
        let (tier, idx) = payload_m4_indices(inp.n_points, inp.polar != 0, x, y, inp.xr0, inp.xr1, inp.px_width as usize, inp.bin_x, inp.bin_x0, inp.bin_x1).ok_or(-1)?;
        dec = tier != 0; if dec { sel = Some(if idx.is_empty() { Vec::new() } else { idx }); }
        let xg = apply_sel(x, sel.as_deref())?; let yg = apply_sel(y, sel.as_deref())?; let bg = base.map(|b| apply_sel(b, sel.as_deref())).transpose()?;
        if let PayloadIndexSel::Indices(v) = payload_visible_indices(&xg, &yg, x_log, y_log, bg.as_deref(), dec, inp.columns[PAYLOAD_TRACE_COL_X].null_count > 0, inp.columns[PAYLOAD_TRACE_COL_Y].null_count > 0, base.is_some(), inp.columns[PAYLOAD_TRACE_COL_BASE].null_count > 0).ok_or(-1)? {
            sel = Some(if let Some(ref s) = sel { combine_sel(Some(s), &v) } else { v });
        }
        out.decimation_px = inp.px_width;
    } else if gather == PAYLOAD_GATHER_VISIBLE_SEL {
        let x = col_values(&inp.columns, PAYLOAD_TRACE_COL_X).ok_or(-1)?; let y = col_values(&inp.columns, PAYLOAD_TRACE_COL_Y).ok_or(-1)?;
        if let PayloadIndexSel::Indices(v) = payload_visible_indices(x, y, x_log, y_log, None, false, inp.columns[PAYLOAD_TRACE_COL_X].null_count > 0, inp.columns[PAYLOAD_TRACE_COL_Y].null_count > 0, false, false).ok_or(-1)? { sel = Some(v); }
        if inp.kind == "scatter" { out.set_shipped_sel = 1; ch_sel = sel.clone(); }
    } else if gather == PAYLOAD_GATHER_SEGMENTS {
        let x0 = col_values(&inp.columns, PAYLOAD_TRACE_COL_X0).ok_or(-1)?; let n = x0.len();
        let mut tier = 0; let mut roles = 0; let mut keep = 1; let mut idx = vec![0u32; n]; let mut src = vec![0u32; n]; let mut rl = vec![0u32; n];
        let n_out = payload_segments_emit_gather(inp.kind, n, inp.segment_count as usize, f64::from(inp.px_width), &mut tier, &mut roles, &mut keep, &mut idx, &mut src, &mut rl).ok_or(-1)?;
        if keep == 0 { idx.truncate(n_out); sel = Some(idx); dec = tier == PAYLOAD_SEGMENTS_TIER_DECIMATED; }
        if roles != 0 {
            src.truncate(n_out); rl.truncate(n_out);
            if let Some(ref s) = sel { let mut ns = Vec::with_capacity(s.len()); let mut nr = Vec::with_capacity(s.len()); for &i in s { ns.push(src[i as usize]); nr.push(rl[i as usize]); } src = ns; rl = nr; }
            ch_sel = sel.clone();
            if inp.kind == "errorbar" && inp.has_transition_keys != 0 { attempt_role = 1; }
        }
        let _x0g = apply_sel(x0, sel.as_deref())?;
        let _x1g = apply_sel(col_values(&inp.columns, PAYLOAD_TRACE_COL_X1).ok_or(-1)?, sel.as_deref())?;
        let _y0g = apply_sel(col_values(&inp.columns, PAYLOAD_TRACE_COL_Y0).ok_or(-1)?, sel.as_deref())?;
        let _y1g = apply_sel(col_values(&inp.columns, PAYLOAD_TRACE_COL_Y1).ok_or(-1)?, sel.as_deref())?;
        if let Some(f) = rect_finite_sel(&inp.columns, x0.len(), &inp.color_ch)? {
            sel = Some(if let Some(ref s) = sel { combine_sel(Some(s), &f) } else { f }); ch_sel = sel.clone();
        }
        if attempt_role != 0 && !dec {
            let lo = inp.transition_keys_lo.ok_or(-1)?; let hi = inp.transition_keys_hi.ok_or(-1)?;
            let mut ol = vec![0u32; src.len()]; let mut oh = vec![0u32; src.len()];
            if payload_errorbar_role_keys(lo, hi, &src, &rl, &mut ol, &mut oh).is_some() { role_lo = Some(ol); role_hi = Some(oh); } else { attempt_role = 0; }
        }
    } else if gather == PAYLOAD_GATHER_RECT_FINITE {
        let x0 = col_values(&inp.columns, PAYLOAD_TRACE_COL_X0).ok_or(-1)?;
        sel = rect_finite_sel(&inp.columns, x0.len(), &inp.color_ch)?; ch_sel = sel.clone();
    } else if gather == PAYLOAD_GATHER_VALID_INDICES {
        let cands: Vec<&[f64]> = plan.iter().map(|e| { let slot = TRACE_SLOTS.iter().position(|&s| s == e.trace_slot as usize).unwrap_or(e.trace_slot as usize); inp.columns[slot].values }).collect();
        let mut cand_cols = Vec::new(); for (i, e) in plan.iter().enumerate() { if inp.columns[TRACE_SLOTS.iter().position(|&s| s == e.trace_slot as usize).unwrap_or(e.trace_slot as usize)].null_count > 0 { cand_cols.push(cands[i]); } }
        if gather_color != 0 && inp.color_ch.present != 0 && inp.color_ch.mode == 1 { cand_cols.push(inp.color_ch.values_f64); }
        sel = finite_indices(&cand_cols, cands[0].len())?; ch_sel = sel.clone();
    }

    let arrays = gather_arrays(&plan, &inp.columns, sel.as_deref())?;
    let mats = materialize_columns(&plan, &inp.columns, &arrays, inp.x_axis_scale, inp.y_axis_scale)?;
    for (e, c) in plan.iter().zip(mats.iter()) { out.geometry.push(PayloadTraceGeomOut { registry_key: e.registry_key, nested: 0, column: c.clone() }); }
    out.n_marks = mats.first().map(|c| c.len as u64).unwrap_or(0); out.tier = i32::from(dec); if dec { out.decimation_px = inp.px_width; }

    let mut ap = 0; let mut aa = 0; let mut cslot = PAYLOAD_SHIP_CHANNELS_IF_COLOR; let mut ist = 1; let mut atr = 0;
    match kind {
        "line" | "area" => { let mut nm = out.n_marks as usize; payload_base_entry_plan(inp.has_trace_animation, nm, inp.style_color_is_none, inp.x_axis_type, inp.y_axis_type, &mut aa, &mut nm, &mut ap, &mut 0, &mut 0); out.n_marks = nm as u64; out.attach_animation = aa; atr = i32::from(inp.has_transition_keys != 0); }
        "scatter" => { ap = 0; cslot = PAYLOAD_SHIP_CHANNELS_ALWAYS; }
        "hexbin" => { let mut td = 0; let mut nm = out.n_marks as usize; payload_nonxy_emit_plan(PAYLOAD_NONXY_KIND_HEXBIN, nm, inp.style_color_is_none, inp.x_axis_type, inp.y_axis_type, &mut td, &mut nm, &mut ap, &mut 0, &mut 0, &mut cslot, &mut ist, &mut atr); out.n_marks = nm as u64; }
        "rect" => { let mut td = 0; let mut nm = out.n_marks as usize; payload_nonxy_emit_plan(PAYLOAD_NONXY_KIND_RECT, nm, inp.style_color_is_none, inp.x_axis_type, inp.y_axis_type, &mut td, &mut nm, &mut ap, &mut 0, &mut 0, &mut cslot, &mut ist, &mut atr); out.n_marks = nm as u64; }
        "segments" => { let mut nm = out.n_marks as usize; payload_segments_emit_plan(inp.kind, nm, inp.style_color_is_none, inp.x_axis_type, inp.y_axis_type, inp.has_transition_keys, &mut nm, &mut ap, &mut 0, &mut 0, &mut cslot, &mut ist, &mut atr, &mut 0, &mut attempt_role); out.n_marks = nm as u64; out.attempt_role_keys = attempt_role; }
        "ribbon" => { let mut nm = out.n_marks as usize; payload_ribbon_emit_plan(nm, inp.style_color_is_none, inp.x_axis_type, inp.y_axis_type, 0, inp.has_color2_ch, &mut 0, &mut nm, &mut ap, &mut 0, &mut 0, &mut cslot, &mut ist, &mut atr, &mut 0, &mut 0); out.n_marks = nm as u64; }
        "triangle_mesh" => { let mut nm = out.n_marks as usize; payload_mesh_emit_plan(nm, inp.style_color_is_none, inp.x_axis_type, inp.y_axis_type, 0, 0, 0, &mut 0, &mut nm, &mut ap, &mut 0, &mut 0, &mut cslot, &mut ist, &mut atr, &mut 0, &mut 0); out.n_marks = nm as u64; }
        _ => {}
    }
    out.apply_palette_default = ap; out.attach_transition = atr.max(out.attach_transition);
    let mut nc = 0usize; let mut cp = [PayloadChannelShipEntry { registry_key: 0, trace_slot: 0, ship_method: 0 }; PAYLOAD_CHANNEL_SHIP_MAX];
    if payload_channel_ship_plan(cslot, ist, inp.has_color2_ch, inp.has_color_ch, inp.has_stroke_ch, inp.has_style_channels, &mut nc, &mut cp) == 0 { return Err(-1); }
    out.channels = materialize_channels(&cp[..nc], inp, ch_sel.as_deref())?;
    let n_marks_final = out.n_marks as usize;
    attach_transition(&mut out, inp, ch_sel.as_deref(), i32::from(!dec), n_marks_final, role_lo.as_deref(), role_hi.as_deref())?;
    Ok(out)
}
