//! Public static-export support predicate (M2 #271).
//!
//! Hosts pack authored `XYEF` v1 facts (viewport flags, key lists, axis
//! codes, annotation field names, and per-trace column observations). ABI 152
//! owns `XYEP` v1 layout, kind/step/annotation code tables, and flag
//! derivation so Python and Node cannot drift on the public-export envelope.
//! Rust then owns the allowlists, check order, and stable
//! `XYG_SCENE_UNSUPPORTED_*` wording over that envelope. An empty reason
//! means the public Scene route applies; hosts then compile through the
//! existing Scene consumers and may still report compiler or viewport
//! diagnostics. ABI 171 admits scatter `stroke_width` without `stroke` as
//! match-fill (mark color at the authored width). ABI 173 admits heatmap
//! `corner_radius` on the public Scene (cartesian rounded Rects / polar wedges).
//! ABI 174 admits violin/box `corner_radius` on that same Rect tessellation.
//! ABI 175 admits violin/box `fill_opacity` / `stroke_opacity` on that public
//! Scene (XYMS already composites those channels). ABI 176 admits
//! bar/column/histogram `fill_opacity` / `stroke_opacity` the same way.
//! ABI 177 admits heatmap `fill_opacity` on that public Scene (XYMS fill alpha).
//! ABI 193 admits heatmap/hexbin `stroke` / `stroke_width` / `stroke_opacity` on
//! that public Scene (XYMS stroke alpha). Polar painted Image blit tessellates
//! when stroke is visible and then uses the 10k tessellation cell ceiling.
//! ABI 191 admits constant multi-character scatter `marker_glyph` via XYMG v2.
//! ABI 192 admits polar painted heatmap as one inverse-raster Image blit
//! (`FLAG_POLAR` allowlists polar axis keys; painted polar heatmaps use the
//! `MAX_SCENE_IMAGE_PIXELS` cell cap). Constant-style polar lattices still
//! tessellate to PolyFill wedges under the 10k public cell ceiling.
//! ABI 178 admits scatter `fill_opacity` / `stroke_opacity` the same way.
//! ABI 179 admits hexbin `fill_opacity` on that public Scene (XYMS fill alpha).
//! ABI 180 admits triangle_mesh `fill_opacity` / constant stroke paint the same way.
//! ABI 182 admits triangle_mesh `joined_fill` as one identity PolyFill ring
//! from the Rust boundary walk (disconnected meshes keep per-face triangles;
//! `role` other than `triangle-mesh` stays fail-closed).
//! ABI 183 admits constant ribbon `color2_ch` as XYGR mark-space `dir=right`
//! (hosts omit `FLAG_COLOR2` / `OBS_GRADIENT` on that path). ABI 190 intern
//! per-item two-ended paint from packed XYHP kind 5. Polar ribbon, and `role` other than `ribbon` stay fail-closed.
//! ABI 184 admits cartesian unwrapped text `dx`/`dy`/`anchor` as XYAW `wrap=0`.
//! ABI 185 admits labelled cartesian marker `dx`/`dy`/`anchor` as XYAW `wrap=0`.
//! ABI 186 admits cartesian colormap hexbin as a 1×N XYHP plane interned onto
//! HexCell PolyFills. Polar hexbin, custom reducers, and per-item RGBA stay
//! fail-closed.
//! ABI 187 admits cartesian unwrapped text `rotation` as XYAW `wrap=0` (XYAW v2 / XYLB v6).
//! ABI 188 admits labelled cartesian marker `rotation` as XYAW `wrap=0` (nums[8]).
//! ABI 189 owns heatmap/hexbin cell-fill tessellation eligibility from packed
//! XYTA. ABI 190 intern cartesian per-item two-ended ribbon `color2_ch` from
//! packed XYHP kind 5 (hosts omit `FLAG_COLOR2` / `OBS_GRADIENT` on that path).
//! Polar ribbon, custom `role`, and explicit `FLAG_COLOR2` stay fail-closed.
//! Rotation, html, `class_name`, and polar stay fail-closed.
//! Rust owns the public PolyFill group budget, including
//! companion traces that share the browser painter's 1,024-group ceiling.

use crate::scene::{SceneError, MAX_SCENE_IMAGE_PIXELS};

const XYEP_MAGIC: &[u8; 4] = b"XYEP";
const XYEP_VERSION: u32 = 1;
const XYEP_HEADER_BYTES: usize = 36;
const XYEP_AXIS_BYTES: usize = 8;
const XYEP_ANNOTATION_BYTES: usize = 4;
const XYEP_TRACE_BYTES: usize = 72;
const XYEF_MAGIC: &[u8; 4] = b"XYEF";
const XYEF_VERSION: u32 = 1;
const XYEF_HEADER_BYTES: usize = 36;
const XYEF_AXIS_BYTES: usize = 8;
const XYEF_ANNOTATION_BYTES: usize = 8;
const XYEF_TRACE_PREFIX_BYTES: usize = 80;
const MAX_XYEP_KEYS: usize = 256;
const MAX_XYEP_KEY_BYTES: usize = 256;
const MAX_XYEP_TRACES: usize = 4_096;
const MAX_XYEP_ANNOTATIONS: usize = 128;
const MAX_XYEP_AXES: usize = 16;
const MAX_PUBLIC_TRIANGLE_MESHES: usize = 1_024;
const MAX_PUBLIC_HEATMAP_CELLS: usize = 10_000;
const MAX_PUBLIC_POINTS: usize = 10_000;
const MAX_PUBLIC_STEP_POINTS: usize = 10_001;

const FLAG_FLUID_WIDTH: u32 = 1 << 0;
const FLAG_FLUID_HEIGHT: u32 = 1 << 1;
const FLAG_CHROME_STYLES: u32 = 1 << 2;
const FLAG_TITLE_OPTIONS: u32 = 1 << 3;
const FLAG_POLAR: u32 = 1 << 4;

const ANN_WRAP: u8 = 1 << 0;
const ANN_DX: u8 = 1 << 1;
const ANN_DY: u8 = 1 << 2;
const ANN_ANCHOR: u8 = 1 << 3;
const ANN_NOT_OBJECT: u8 = 1 << 4;

const TRACE_HAS_X: u32 = 1 << 0;
const TRACE_HAS_Y: u32 = 1 << 1;
const TRACE_XY_LEN_EQUAL: u32 = 1 << 2;
#[allow(dead_code)]
const TRACE_X_FINITE: u32 = 1 << 3;
#[allow(dead_code)]
const TRACE_Y_FINITE: u32 = 1 << 4;
const TRACE_ENDPOINTS_PRESENT: u32 = 1 << 5;
const TRACE_ENDPOINTS_LEN_EQUAL: u32 = 1 << 6;
const TRACE_MESH_PRESENT: u32 = 1 << 7;
const TRACE_MESH_LEN_EQUAL: u32 = 1 << 8;
const TRACE_MESH_FINITE: u32 = 1 << 9;
const TRACE_JOINED_FILL: u32 = 1 << 10;
const TRACE_HEATMAP_COLORMAP: u32 = 1 << 11;
const TRACE_HEATMAP_SHAPE_OK: u32 = 1 << 12;
const TRACE_HEATMAP_EXTENT_OK: u32 = 1 << 13;
const TRACE_HEATMAP_FINITE: u32 = 1 << 14;
const TRACE_HEX_XY_OK: u32 = 1 << 15;
const TRACE_HEX_FINITE: u32 = 1 << 16;
const TRACE_STROKE_WIDTH_ONLY: u32 = 1 << 17;
const TRACE_COMPANION_XY_MATCH: u32 = 1 << 18;
const TRACE_COMPANION_AXES_MATCH: u32 = 1 << 19;
const TRACE_BOX_OUTLIER_FINITE: u32 = 1 << 20;
const TRACE_SYMBOL_NON_STRING: u32 = 1 << 21;
const TRACE_DENSITY_BLIT: u32 = 1 << 22;

const OBS_HAS_X: u32 = 1 << 0;
const OBS_HAS_Y: u32 = 1 << 1;
const OBS_X_FINITE: u32 = 1 << 2;
const OBS_Y_FINITE: u32 = 1 << 3;
const OBS_HAS_X0: u32 = 1 << 4;
const OBS_HAS_Y0: u32 = 1 << 5;
const OBS_HAS_X1: u32 = 1 << 6;
const OBS_HAS_Y1: u32 = 1 << 7;
const OBS_X0_FINITE: u32 = 1 << 8;
const OBS_Y0_FINITE: u32 = 1 << 9;
const OBS_X1_FINITE: u32 = 1 << 10;
const OBS_Y1_FINITE: u32 = 1 << 11;
const OBS_JOINED_FILL: u32 = 1 << 12;
const OBS_HEATMAP_TRUECOLOR: u32 = 1 << 13;
const OBS_HEATMAP_RGBA_GRID: u32 = 1 << 16;
const OBS_HEATMAP_SHAPE_OK: u32 = 1 << 17;
const OBS_HEATMAP_EXTENT_OK: u32 = 1 << 18;
const OBS_HEATMAP_FINITE: u32 = 1 << 19;
const OBS_STROKE_WIDTH_ONLY: u32 = 1 << 20;
const OBS_COMPANION_XY_MATCH: u32 = 1 << 21;
const OBS_COMPANION_AXES_MATCH: u32 = 1 << 22;
const OBS_SYMBOL_NON_STRING: u32 = 1 << 23;
const OBS_DENSITY_BLIT: u32 = 1 << 24;

/// Why an XYEF packing request was rejected. Discriminants are the C-ABI
/// error codes (returned negated by `xyg_scene_pack_public_export`).
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ExportPackError {
    Length = 1,
    Version = 2,
    Limit = 3,
    #[allow(dead_code)]
    Output = 4,
    #[allow(dead_code)]
    Shape = 5,
    Payload = 6,
}

const KIND_SCATTER: u8 = 0;
const KIND_LINE: u8 = 1;
const KIND_BAR: u8 = 2;
const KIND_COLUMN: u8 = 3;
const KIND_HISTOGRAM: u8 = 4;
const KIND_VIOLIN: u8 = 5;
const KIND_BOX: u8 = 6;
const KIND_BOX_WHISKER: u8 = 7;
const KIND_BOX_MEDIAN: u8 = 8;
const KIND_SEGMENTS: u8 = 9;
const KIND_ERRORBAR: u8 = 10;
const KIND_STEM: u8 = 11;
const KIND_AREA: u8 = 12;
const KIND_ERROR_BAND: u8 = 13;
const KIND_RIBBON: u8 = 14;
const KIND_TRIANGLE_MESH: u8 = 15;
const KIND_HEXBIN: u8 = 16;
const KIND_HEATMAP: u8 = 17;
const KIND_CONTOUR: u8 = 18;

const PUBLIC_FIGURE_STYLE_KEYS: &[&str] = &["background", "--chart-bg"];
const PUBLIC_LEGEND_KEYS: &[&str] = &["loc", "title", "highlight", "toggle"];
const PUBLIC_COLORBAR_KEYS: &[&str] = &["domain", "stops", "ticks", "minor_ticks", "title"];
const PUBLIC_AXIS_KEYS: &[&str] = &[
    "type",
    "constant",
    "nonpositive",
    "domain",
    "label",
    "side",
    "tick_sides",
    "tick_label_sides",
    "tick_values",
    "tick_labels",
    "minor_tick_values",
    "style",
    "minor_style",
    "format",
];
const POLAR_AXIS_KEYS: &[&str] = &[
    "theta_unit",
    "theta_zero",
    "theta_direction",
    "sector",
    "grid_shape",
    "categories",
    "hole",
    "r_origin",
];
const POLAR_SCENE_KINDS: &[&str] = &[
    "line", "scatter", "area", "bar", "column", "errorbar", "heatmap", "contour",
];
const PUBLIC_SYMBOLS: &[&str] = &[
    "circle",
    "square",
    "diamond",
    "triangle",
    "cross",
    "hexagon",
    "pentagon",
    "star",
    "triangle_down",
    "triangle_left",
    "triangle_right",
    "x",
    "point",
    "pixel",
    "thin_diamond",
    "plus_line",
    "x_line",
    "horizontal_line",
    "vertical_line",
];
const HEXBIN_REDUCES: &[&str] = &["count", "mean", "sum"];

struct Cursor<'a> {
    bytes: &'a [u8],
    offset: usize,
}

impl<'a> Cursor<'a> {
    fn new(bytes: &'a [u8]) -> Self {
        Self { bytes, offset: 0 }
    }

    fn remaining(&self) -> usize {
        self.bytes.len().saturating_sub(self.offset)
    }

    fn u8(&mut self) -> Result<u8, SceneError> {
        let value = *self.bytes.get(self.offset).ok_or(SceneError::Length)?;
        self.offset += 1;
        Ok(value)
    }

    fn u16(&mut self) -> Result<u16, SceneError> {
        let raw = self
            .bytes
            .get(self.offset..self.offset + 2)
            .ok_or(SceneError::Length)?;
        self.offset += 2;
        Ok(u16::from_le_bytes(
            raw.try_into().map_err(|_| SceneError::Length)?,
        ))
    }

    fn u32(&mut self) -> Result<u32, SceneError> {
        let raw = self
            .bytes
            .get(self.offset..self.offset + 4)
            .ok_or(SceneError::Length)?;
        self.offset += 4;
        Ok(u32::from_le_bytes(
            raw.try_into().map_err(|_| SceneError::Length)?,
        ))
    }

    fn f64(&mut self) -> Result<f64, SceneError> {
        let raw = self
            .bytes
            .get(self.offset..self.offset + 8)
            .ok_or(SceneError::Length)?;
        self.offset += 8;
        Ok(f64::from_le_bytes(
            raw.try_into().map_err(|_| SceneError::Length)?,
        ))
    }

    fn bytes(&mut self, count: usize) -> Result<&'a [u8], SceneError> {
        let end = self.offset.checked_add(count).ok_or(SceneError::Limit)?;
        let slice = self.bytes.get(self.offset..end).ok_or(SceneError::Length)?;
        self.offset = end;
        Ok(slice)
    }

    fn key(&mut self) -> Result<&'a str, SceneError> {
        let len = self.u16()? as usize;
        if len > MAX_XYEP_KEY_BYTES {
            return Err(SceneError::Limit);
        }
        let raw = self.bytes(len)?;
        std::str::from_utf8(raw).map_err(|_| SceneError::Length)
    }

    fn keys(&mut self, count: u32) -> Result<Vec<&'a str>, SceneError> {
        if count as usize > MAX_XYEP_KEYS {
            return Err(SceneError::Limit);
        }
        let mut keys = Vec::with_capacity(count as usize);
        for _ in 0..count {
            keys.push(self.key()?);
        }
        Ok(keys)
    }
}

fn kind_public(kind: u8) -> bool {
    kind <= KIND_CONTOUR
}

fn kind_extent_geometry(kind: u8) -> bool {
    matches!(kind, KIND_HEATMAP | KIND_CONTOUR)
}

fn kind_literal_geometry(kind: u8) -> bool {
    kind_public(kind) && kind != KIND_SCATTER && !kind_extent_geometry(kind)
}

fn kind_segment(kind: u8) -> bool {
    matches!(
        kind,
        KIND_SEGMENTS
            | KIND_ERRORBAR
            | KIND_STEM
            | KIND_BOX_WHISKER
            | KIND_BOX_MEDIAN
            | KIND_CONTOUR
    )
}

fn kind_band(kind: u8) -> bool {
    matches!(kind, KIND_AREA | KIND_ERROR_BAND)
}

fn annotation_fields(kind: u8) -> Option<&'static [&'static str]> {
    Some(match kind {
        1 => &[
            "kind",
            "x",
            "y",
            "text",
            "dx",
            "dy",
            "anchor",
            "wrap",
            "rotation",
            "style",
            "class_name",
        ],
        2 => &["kind", "axis", "value", "text", "style", "class_name"],
        3 => &[
            "kind",
            "axis",
            "start",
            "end",
            "text",
            "style",
            "class_name",
        ],
        4 => &[
            "kind",
            "x",
            "y",
            "text",
            "dx",
            "dy",
            "anchor",
            "size",
            "symbol",
            "rotation",
            "style",
            "class_name",
        ],
        5 => &[
            "kind",
            "x0",
            "y0",
            "x1",
            "y1",
            "text",
            "style",
            "class_name",
        ],
        6 => &[
            "kind",
            "x",
            "y",
            "text",
            "dx",
            "dy",
            "anchor",
            "wrap",
            "style",
            "class_name",
        ],
        _ => return None,
    })
}

fn public_style_keys(kind: u8) -> &'static [&'static str] {
    match kind {
        KIND_SCATTER => &[
            "color",
            "opacity",
            "symbol",
            "size",
            "role",
            "stroke",
            "stroke_width",
            "marker_path",
            "marker_glyph",
            "fill_opacity",
            "stroke_opacity",
        ],
        KIND_LINE => &[
            "color", "opacity", "width", "step", "dash", "linecap", "curve",
        ],
        KIND_BAR | KIND_COLUMN => &[
            "color",
            "opacity",
            "role",
            "orientation",
            "fill",
            "stroke",
            "stroke_width",
            "corner_radius",
            "wedge_gap",
            "fill_opacity",
            "stroke_opacity",
        ],
        KIND_HISTOGRAM => &[
            "color",
            "opacity",
            "role",
            "cumulative",
            "density",
            "fill",
            "stroke",
            "stroke_width",
            "corner_radius",
            "fill_opacity",
            "stroke_opacity",
        ],
        KIND_VIOLIN => &[
            "color",
            "opacity",
            "role",
            "fill",
            "stroke",
            "stroke_width",
            "corner_radius",
            "fill_opacity",
            "stroke_opacity",
        ],
        KIND_BOX => &[
            "color",
            "opacity",
            "role",
            "stroke",
            "stroke_width",
            "box_orientation",
            "corner_radius",
            "fill_opacity",
            "stroke_opacity",
        ],
        KIND_BOX_WHISKER | KIND_BOX_MEDIAN | KIND_SEGMENTS | KIND_ERRORBAR | KIND_STEM
        | KIND_CONTOUR => &["color", "opacity", "width", "role", "dash", "linecap"],
        KIND_AREA => &[
            "color",
            "opacity",
            "line_color",
            "line_width",
            "line_opacity",
            "stroke_perimeter",
            "fill",
            "fill_opacity",
            "stroke_opacity",
            "dash",
            "linecap",
            "curve",
            "step",
            "role",
        ],
        KIND_ERROR_BAND => &[
            "color",
            "opacity",
            "line_width",
            "line_opacity",
            "role",
            "fill",
            "fill_opacity",
            "stroke_opacity",
            "curve",
            "step",
        ],
        KIND_RIBBON => &[
            "opacity",
            "role",
            "stroke",
            "stroke_width",
            "fill_opacity",
            "stroke_opacity",
        ],
        KIND_TRIANGLE_MESH => &[
            "opacity",
            "role",
            "color",
            "fill_opacity",
            "stroke",
            "stroke_width",
            "stroke_opacity",
            "joined_fill",
        ],
        KIND_HEXBIN => &[
            "color",
            "opacity",
            "hex_dx",
            "hex_dy",
            "role",
            "reduce",
            "fill_opacity",
            "stroke",
            "stroke_width",
            "stroke_opacity",
        ],
        KIND_HEATMAP => &[
            "color",
            "opacity",
            "role",
            "domain",
            "x_range",
            "y_range",
            "colormap",
            "truecolor",
            "corner_radius",
            "fill_opacity",
            "stroke",
            "stroke_width",
            "stroke_opacity",
        ],
        _ => &[],
    }
}

fn accepted_segment_role(kind: u8, role: &str) -> bool {
    match kind {
        KIND_SEGMENTS => role == "segments",
        KIND_ERRORBAR => role == "y-errorbar" || role == "x-errorbar",
        KIND_CONTOUR => role == "contour",
        KIND_STEM => role == "stem",
        KIND_BOX_WHISKER => role == "box-whisker",
        KIND_BOX_MEDIAN => role == "box-median",
        _ => false,
    }
}

fn extra_key(keys: &[&str], allowed: &[&str]) -> bool {
    keys.iter().any(|key| !allowed.contains(key))
}

fn put_key(buf: &mut Vec<u8>, key: &str) -> Result<(), ExportPackError> {
    let bytes = key.as_bytes();
    if bytes.len() > MAX_XYEP_KEY_BYTES {
        return Err(ExportPackError::Limit);
    }
    buf.extend_from_slice(&(bytes.len() as u16).to_le_bytes());
    buf.extend_from_slice(bytes);
    Ok(())
}

fn put_keys(buf: &mut Vec<u8>, keys: &[&str]) -> Result<(), ExportPackError> {
    if keys.len() > MAX_XYEP_KEYS {
        return Err(ExportPackError::Limit);
    }
    for key in keys {
        put_key(buf, key)?;
    }
    Ok(())
}

fn take_utf8<'a>(cursor: &mut Cursor<'a>, len: usize) -> Result<&'a str, ExportPackError> {
    if len > MAX_XYEP_KEY_BYTES {
        return Err(ExportPackError::Limit);
    }
    let raw = cursor.bytes(len).map_err(|_| ExportPackError::Length)?;
    std::str::from_utf8(raw).map_err(|_| ExportPackError::Payload)
}

fn export_kind_code(name: &str) -> u8 {
    match name {
        "scatter" => KIND_SCATTER,
        "line" => KIND_LINE,
        "bar" => KIND_BAR,
        "column" => KIND_COLUMN,
        "histogram" => KIND_HISTOGRAM,
        "violin" => KIND_VIOLIN,
        "box" => KIND_BOX,
        "box_whisker" => KIND_BOX_WHISKER,
        "box_median" => KIND_BOX_MEDIAN,
        "segments" => KIND_SEGMENTS,
        "errorbar" => KIND_ERRORBAR,
        "stem" => KIND_STEM,
        "area" => KIND_AREA,
        "error_band" => KIND_ERROR_BAND,
        "ribbon" => KIND_RIBBON,
        "triangle_mesh" => KIND_TRIANGLE_MESH,
        "hexbin" => KIND_HEXBIN,
        "heatmap" => KIND_HEATMAP,
        "contour" => KIND_CONTOUR,
        _ => 255,
    }
}

fn export_step_code(name: &str) -> u8 {
    match name {
        "pre" => 1,
        "mid" => 2,
        "post" => 3,
        _ => 0,
    }
}

fn export_annotation_kind(name: &str) -> u8 {
    match name {
        "text" => 1,
        "rule" => 2,
        "band" => 3,
        "marker" => 4,
        "arrow" => 5,
        "callout" => 6,
        _ => 0,
    }
}

fn annotation_flags(not_object: bool, fields: &[&str]) -> u8 {
    let mut flags = 0u8;
    if not_object {
        flags |= ANN_NOT_OBJECT;
    }
    if fields.iter().any(|key| *key == "wrap") {
        flags |= ANN_WRAP;
    }
    if fields.iter().any(|key| *key == "dx") {
        flags |= ANN_DX;
    }
    if fields.iter().any(|key| *key == "dy") {
        flags |= ANN_DY;
    }
    if fields.iter().any(|key| *key == "anchor") {
        flags |= ANN_ANCHOR;
    }
    flags
}

fn derive_trace_flags(
    obs: u32,
    n_x: u32,
    n_y: u32,
    n_x0: u32,
    n_y0: u32,
    n_x1: u32,
    n_y1: u32,
) -> u32 {
    let mut flags = 0u32;
    let has_x = obs & OBS_HAS_X != 0;
    let has_y = obs & OBS_HAS_Y != 0;
    let has_x0 = obs & OBS_HAS_X0 != 0;
    let has_y0 = obs & OBS_HAS_Y0 != 0;
    let has_x1 = obs & OBS_HAS_X1 != 0;
    let has_y1 = obs & OBS_HAS_Y1 != 0;
    let x_finite = obs & OBS_X_FINITE != 0;
    let y_finite = obs & OBS_Y_FINITE != 0;
    let x0_finite = obs & OBS_X0_FINITE != 0;
    let y0_finite = obs & OBS_Y0_FINITE != 0;
    let x1_finite = obs & OBS_X1_FINITE != 0;
    let y1_finite = obs & OBS_Y1_FINITE != 0;
    if has_x {
        flags |= TRACE_HAS_X;
    }
    if has_y {
        flags |= TRACE_HAS_Y;
    }
    if has_x && has_y && n_x == n_y {
        flags |= TRACE_XY_LEN_EQUAL | TRACE_HEX_XY_OK;
    }
    if x_finite {
        flags |= TRACE_X_FINITE;
    }
    if y_finite {
        flags |= TRACE_Y_FINITE;
    }
    if x_finite && y_finite {
        flags |= TRACE_HEX_FINITE | TRACE_BOX_OUTLIER_FINITE;
    }
    if has_x0 && has_y0 && has_x1 && has_y1 {
        flags |= TRACE_ENDPOINTS_PRESENT;
        if n_x0 == n_y0 && n_x0 == n_x1 && n_x0 == n_y1 {
            flags |= TRACE_ENDPOINTS_LEN_EQUAL;
        }
    }
    if has_x && has_y && has_x0 && has_y0 && has_x1 && has_y1 {
        flags |= TRACE_MESH_PRESENT;
        if n_x == n_y && n_x == n_x0 && n_x == n_y0 && n_x == n_x1 && n_x == n_y1 {
            flags |= TRACE_MESH_LEN_EQUAL;
        }
        if x_finite && y_finite && x0_finite && y0_finite && x1_finite && y1_finite {
            flags |= TRACE_MESH_FINITE;
        }
    }
    if obs & OBS_JOINED_FILL != 0 {
        flags |= TRACE_JOINED_FILL;
    }
    if obs & OBS_HEATMAP_TRUECOLOR != 0 && obs & OBS_HEATMAP_RGBA_GRID == 0 {
        flags |= TRACE_HEATMAP_COLORMAP;
    }
    if obs & OBS_HEATMAP_SHAPE_OK != 0 {
        flags |= TRACE_HEATMAP_SHAPE_OK;
    }
    if obs & OBS_HEATMAP_EXTENT_OK != 0 {
        flags |= TRACE_HEATMAP_EXTENT_OK;
    }
    if obs & OBS_HEATMAP_FINITE != 0 {
        flags |= TRACE_HEATMAP_FINITE;
    }
    if obs & OBS_STROKE_WIDTH_ONLY != 0 {
        flags |= TRACE_STROKE_WIDTH_ONLY;
    }
    if obs & OBS_COMPANION_XY_MATCH != 0 {
        flags |= TRACE_COMPANION_XY_MATCH;
    }
    if obs & OBS_COMPANION_AXES_MATCH != 0 {
        flags |= TRACE_COMPANION_AXES_MATCH;
    }
    if obs & OBS_SYMBOL_NON_STRING != 0 {
        flags |= TRACE_SYMBOL_NON_STRING;
    }
    if obs & OBS_DENSITY_BLIT != 0 {
        flags |= TRACE_DENSITY_BLIT;
    }
    flags
}

/// Pack authored XYEF v1 facts into the public-export `XYEP` v1 envelope.
///
/// Hosts pass viewport flags, key lists, axis codes, annotation field names,
/// and per-trace column observations. Rust owns kind/step/annotation codes,
/// flag derivation, and XYEP record layout.
pub fn pack_public_export(bytes: &[u8]) -> Result<Vec<u8>, ExportPackError> {
    if bytes.len() < XYEF_HEADER_BYTES || bytes.get(..4) != Some(&XYEF_MAGIC[..]) {
        return Err(ExportPackError::Length);
    }
    let mut cursor = Cursor::new(bytes);
    let _magic = cursor.bytes(4).map_err(|_| ExportPackError::Length)?;
    let version = cursor.u32().map_err(|_| ExportPackError::Length)?;
    if version != XYEF_VERSION {
        return Err(ExportPackError::Version);
    }
    let flags = cursor.u32().map_err(|_| ExportPackError::Length)?;
    let n_style_keys = cursor.u32().map_err(|_| ExportPackError::Length)?;
    let n_legend_keys = cursor.u32().map_err(|_| ExportPackError::Length)?;
    let n_colorbar_keys = cursor.u32().map_err(|_| ExportPackError::Length)?;
    let n_axes = cursor.u32().map_err(|_| ExportPackError::Length)?;
    let n_annotations = cursor.u32().map_err(|_| ExportPackError::Length)?;
    let n_traces = cursor.u32().map_err(|_| ExportPackError::Length)?;
    if n_axes as usize > MAX_XYEP_AXES
        || n_annotations as usize > MAX_XYEP_ANNOTATIONS
        || n_traces as usize > MAX_XYEP_TRACES
    {
        return Err(ExportPackError::Limit);
    }

    let style_keys = cursor
        .keys(n_style_keys)
        .map_err(|_| ExportPackError::Length)?;
    let legend_keys = cursor
        .keys(n_legend_keys)
        .map_err(|_| ExportPackError::Length)?;
    let colorbar_keys = cursor
        .keys(n_colorbar_keys)
        .map_err(|_| ExportPackError::Length)?;

    let mut out = Vec::from(*XYEP_MAGIC);
    out.extend_from_slice(&XYEP_VERSION.to_le_bytes());
    out.extend_from_slice(&flags.to_le_bytes());
    out.extend_from_slice(&n_style_keys.to_le_bytes());
    out.extend_from_slice(&n_legend_keys.to_le_bytes());
    out.extend_from_slice(&n_colorbar_keys.to_le_bytes());
    out.extend_from_slice(&n_axes.to_le_bytes());
    out.extend_from_slice(&n_annotations.to_le_bytes());
    out.extend_from_slice(&n_traces.to_le_bytes());
    put_keys(&mut out, &style_keys)?;
    put_keys(&mut out, &legend_keys)?;
    put_keys(&mut out, &colorbar_keys)?;

    for _ in 0..n_axes {
        if cursor.remaining() < XYEF_AXIS_BYTES {
            return Err(ExportPackError::Length);
        }
        let axis = cursor
            .bytes(XYEF_AXIS_BYTES)
            .map_err(|_| ExportPackError::Length)?;
        out.extend_from_slice(axis);
        let n_keys =
            u16::from_le_bytes(axis[6..8].try_into().map_err(|_| ExportPackError::Length)?) as u32;
        let keys = cursor.keys(n_keys).map_err(|_| ExportPackError::Length)?;
        put_keys(&mut out, &keys)?;
    }

    for _ in 0..n_annotations {
        if cursor.remaining() < XYEF_ANNOTATION_BYTES {
            return Err(ExportPackError::Length);
        }
        let not_object = cursor.u8().map_err(|_| ExportPackError::Length)? != 0;
        let _reserved0 = cursor.u8().map_err(|_| ExportPackError::Length)?;
        let _reserved1 = cursor.u8().map_err(|_| ExportPackError::Length)?;
        let _reserved2 = cursor.u8().map_err(|_| ExportPackError::Length)?;
        let kind_len = cursor.u16().map_err(|_| ExportPackError::Length)? as usize;
        let n_fields = cursor.u16().map_err(|_| ExportPackError::Length)? as u32;
        let kind_name = take_utf8(&mut cursor, kind_len)?;
        let fields = cursor.keys(n_fields).map_err(|_| ExportPackError::Length)?;
        let kind = if not_object {
            0
        } else {
            export_annotation_kind(kind_name)
        };
        let flags_ann = annotation_flags(not_object, &fields);
        out.push(kind);
        out.push(flags_ann);
        out.extend_from_slice(&(fields.len() as u16).to_le_bytes());
        put_keys(&mut out, &fields)?;
    }

    for _ in 0..n_traces {
        if cursor.remaining() < XYEF_TRACE_PREFIX_BYTES {
            return Err(ExportPackError::Length);
        }
        let obs = cursor.u32().map_err(|_| ExportPackError::Length)?;
        let n_x = cursor.u32().map_err(|_| ExportPackError::Length)?;
        let n_y = cursor.u32().map_err(|_| ExportPackError::Length)?;
        let n_x0 = cursor.u32().map_err(|_| ExportPackError::Length)?;
        let n_y0 = cursor.u32().map_err(|_| ExportPackError::Length)?;
        let n_x1 = cursor.u32().map_err(|_| ExportPackError::Length)?;
        let n_y1 = cursor.u32().map_err(|_| ExportPackError::Length)?;
        let heatmap_rows = cursor.u32().map_err(|_| ExportPackError::Length)?;
        let heatmap_cols = cursor.u32().map_err(|_| ExportPackError::Length)?;
        let heatmap_values = cursor.u32().map_err(|_| ExportPackError::Length)?;
        let n_style = cursor.u16().map_err(|_| ExportPackError::Length)? as u32;
        let kind_len = cursor.u16().map_err(|_| ExportPackError::Length)? as usize;
        let step_len = cursor.u16().map_err(|_| ExportPackError::Length)? as usize;
        let role_len = cursor.u16().map_err(|_| ExportPackError::Length)? as usize;
        let symbol_len = cursor.u16().map_err(|_| ExportPackError::Length)? as usize;
        let reduce_len = cursor.u16().map_err(|_| ExportPackError::Length)? as usize;
        let prev_len = cursor.u16().map_err(|_| ExportPackError::Length)? as usize;
        let prev2_len = cursor.u16().map_err(|_| ExportPackError::Length)? as usize;
        let prev3_len = cursor.u16().map_err(|_| ExportPackError::Length)? as usize;
        let _reserved = cursor.u16().map_err(|_| ExportPackError::Length)?;
        let _pad = cursor.u32().map_err(|_| ExportPackError::Length)?;
        let hex_dx = cursor.f64().map_err(|_| ExportPackError::Length)?;
        let hex_dy = cursor.f64().map_err(|_| ExportPackError::Length)?;
        let kind_name = take_utf8(&mut cursor, kind_len)?;
        let step_name = take_utf8(&mut cursor, step_len)?;
        let role = take_utf8(&mut cursor, role_len)?;
        let symbol = take_utf8(&mut cursor, symbol_len)?;
        let reduce = take_utf8(&mut cursor, reduce_len)?;
        let prev_name = take_utf8(&mut cursor, prev_len)?;
        let prev2_name = take_utf8(&mut cursor, prev2_len)?;
        let prev3_name = take_utf8(&mut cursor, prev3_len)?;
        let style_keys = cursor.keys(n_style).map_err(|_| ExportPackError::Length)?;
        let flags_tr = derive_trace_flags(obs, n_x, n_y, n_x0, n_y0, n_x1, n_y1);
        let prev_kind = if prev_name.is_empty() {
            255
        } else {
            export_kind_code(prev_name)
        };
        let prev2_kind = if prev2_name.is_empty() {
            255
        } else {
            export_kind_code(prev2_name)
        };
        let prev3_kind = if prev3_name.is_empty() {
            255
        } else {
            export_kind_code(prev3_name)
        };
        out.push(export_kind_code(kind_name));
        out.push(export_step_code(step_name));
        out.push(prev_kind);
        out.push(prev2_kind);
        out.push(prev3_kind);
        out.push(0);
        out.extend_from_slice(&0u16.to_le_bytes());
        out.extend_from_slice(&flags_tr.to_le_bytes());
        out.extend_from_slice(&n_x.to_le_bytes());
        out.extend_from_slice(&n_y.to_le_bytes());
        out.extend_from_slice(&n_x0.to_le_bytes());
        out.extend_from_slice(&n_y0.to_le_bytes());
        out.extend_from_slice(&n_x1.to_le_bytes());
        out.extend_from_slice(&n_y1.to_le_bytes());
        out.extend_from_slice(&heatmap_rows.to_le_bytes());
        out.extend_from_slice(&heatmap_cols.to_le_bytes());
        out.extend_from_slice(&heatmap_values.to_le_bytes());
        out.extend_from_slice(&(style_keys.len() as u16).to_le_bytes());
        out.extend_from_slice(&(role.len() as u16).to_le_bytes());
        out.extend_from_slice(&(symbol.len() as u16).to_le_bytes());
        out.extend_from_slice(&(reduce.len() as u16).to_le_bytes());
        out.extend_from_slice(&hex_dx.to_le_bytes());
        out.extend_from_slice(&hex_dy.to_le_bytes());
        out.extend_from_slice(role.as_bytes());
        out.extend_from_slice(symbol.as_bytes());
        out.extend_from_slice(reduce.as_bytes());
        put_keys(&mut out, &style_keys)?;
    }
    if cursor.remaining() != 0 {
        return Err(ExportPackError::Length);
    }
    Ok(out)
}

/// Return Rust's stable public-export diagnostic, or an empty slice when the
/// bounded Scene route applies. Malformed envelopes fail closed.
pub fn scene_public_export_reason(bytes: &[u8]) -> Result<&'static str, SceneError> {
    if bytes.len() < XYEP_HEADER_BYTES || &bytes[..4] != XYEP_MAGIC {
        return Err(SceneError::Length);
    }
    let mut cursor = Cursor::new(bytes);
    let _magic = cursor.bytes(4)?;
    let version = cursor.u32()?;
    if version != XYEP_VERSION {
        return Err(SceneError::Version);
    }
    let flags = cursor.u32()?;
    let n_style_keys = cursor.u32()?;
    let n_legend_keys = cursor.u32()?;
    let n_colorbar_keys = cursor.u32()?;
    let n_axes = cursor.u32()?;
    let n_annotations = cursor.u32()?;
    let n_traces = cursor.u32()?;
    if n_axes as usize > MAX_XYEP_AXES
        || n_annotations as usize > MAX_XYEP_ANNOTATIONS
        || n_traces as usize > MAX_XYEP_TRACES
    {
        return Err(SceneError::Limit);
    }

    let style_keys = cursor.keys(n_style_keys)?;
    let legend_keys = cursor.keys(n_legend_keys)?;
    let colorbar_keys = cursor.keys(n_colorbar_keys)?;

    struct AxisRec<'a> {
        axis_id: u8,
        resolved_kind: u8,
        authored_type: u8,
        domain_present: bool,
        side: u8,
        keys: Vec<&'a str>,
    }
    let mut axes = Vec::with_capacity(n_axes as usize);
    for _ in 0..n_axes {
        if cursor.remaining() < XYEP_AXIS_BYTES {
            return Err(SceneError::Length);
        }
        axes.push(AxisRec {
            axis_id: cursor.u8()?,
            resolved_kind: cursor.u8()?,
            authored_type: cursor.u8()?,
            domain_present: cursor.u8()? != 0,
            side: cursor.u8()?,
            keys: {
                let _reserved = cursor.u8()?;
                let count = cursor.u16()? as u32;
                cursor.keys(count)?
            },
        });
    }

    struct AnnRec<'a> {
        kind: u8,
        flags: u8,
        fields: Vec<&'a str>,
    }
    let mut annotations = Vec::with_capacity(n_annotations as usize);
    for _ in 0..n_annotations {
        if cursor.remaining() < XYEP_ANNOTATION_BYTES {
            return Err(SceneError::Length);
        }
        let kind = cursor.u8()?;
        let flags = cursor.u8()?;
        let n_fields = cursor.u16()? as u32;
        annotations.push(AnnRec {
            kind,
            flags,
            fields: cursor.keys(n_fields)?,
        });
    }

    struct TraceRec<'a> {
        kind: u8,
        step: u8,
        prev_kind: u8,
        prev2_kind: u8,
        prev3_kind: u8,
        flags: u32,
        n_x: u32,
        n_x0: u32,
        heatmap_rows: u32,
        heatmap_cols: u32,
        heatmap_values: u32,
        role: &'a str,
        symbol: &'a str,
        reduce: &'a str,
        hex_dx: f64,
        hex_dy: f64,
        style_keys: Vec<&'a str>,
    }
    let mut traces = Vec::with_capacity(n_traces as usize);
    for _ in 0..n_traces {
        if cursor.remaining() < XYEP_TRACE_BYTES {
            return Err(SceneError::Length);
        }
        let kind = cursor.u8()?;
        let step = cursor.u8()?;
        let prev_kind = cursor.u8()?;
        let prev2_kind = cursor.u8()?;
        let prev3_kind = cursor.u8()?;
        let _pad = cursor.u8()?;
        let _reserved = cursor.u16()?;
        let flags = cursor.u32()?;
        let n_x = cursor.u32()?;
        let _n_y = cursor.u32()?;
        let n_x0 = cursor.u32()?;
        let _n_y0 = cursor.u32()?;
        let _n_x1 = cursor.u32()?;
        let _n_y1 = cursor.u32()?;
        let heatmap_rows = cursor.u32()?;
        let heatmap_cols = cursor.u32()?;
        let heatmap_values = cursor.u32()?;
        let n_style_keys = cursor.u16()? as u32;
        let role_len = cursor.u16()? as usize;
        let symbol_len = cursor.u16()? as usize;
        let reduce_len = cursor.u16()? as usize;
        let hex_dx = cursor.f64()?;
        let hex_dy = cursor.f64()?;
        if role_len > MAX_XYEP_KEY_BYTES
            || symbol_len > MAX_XYEP_KEY_BYTES
            || reduce_len > MAX_XYEP_KEY_BYTES
        {
            return Err(SceneError::Limit);
        }
        let role = std::str::from_utf8(cursor.bytes(role_len)?).map_err(|_| SceneError::Length)?;
        let symbol =
            std::str::from_utf8(cursor.bytes(symbol_len)?).map_err(|_| SceneError::Length)?;
        let reduce =
            std::str::from_utf8(cursor.bytes(reduce_len)?).map_err(|_| SceneError::Length)?;
        traces.push(TraceRec {
            kind,
            step,
            prev_kind,
            prev2_kind,
            prev3_kind,
            flags,
            n_x,
            n_x0,
            heatmap_rows,
            heatmap_cols,
            heatmap_values,
            role,
            symbol,
            reduce,
            hex_dx,
            hex_dy,
            style_keys: cursor.keys(n_style_keys)?,
        });
    }
    if cursor.remaining() != 0 {
        return Err(SceneError::Length);
    }

    if flags & (FLAG_FLUID_WIDTH | FLAG_FLUID_HEIGHT) != 0 {
        return Ok("XYG_SCENE_UNSUPPORTED_FLUID_VIEWPORT");
    }
    if extra_key(&style_keys, PUBLIC_FIGURE_STYLE_KEYS) || flags & FLAG_CHROME_STYLES != 0 {
        return Ok("XYG_SCENE_UNSUPPORTED_PUBLIC_STYLE");
    }
    if flags & FLAG_TITLE_OPTIONS != 0 {
        return Ok("XYG_SCENE_UNSUPPORTED_PUBLIC_TEXT");
    }
    for annotation in &annotations {
        let allowed = annotation_fields(annotation.kind);
        if annotation.flags & ANN_NOT_OBJECT != 0
            || allowed.is_none()
            || extra_key(&annotation.fields, allowed.unwrap())
        {
            return Ok("XYG_SCENE_UNSUPPORTED_PUBLIC_ANNOTATION");
        }
    }
    // ABI 184 admits cartesian unwrapped text dx/dy/anchor as XYAW wrap=0.
    // ABI 185 admits labelled cartesian marker dx/dy/anchor the same way
    // (keep the marker mark row; skip AttachedRow). Unlabelled marker layout
    // flags are unused. ABI 187 admits cartesian unwrapped text rotation the
    // same XYAW wrap=0 path. ABI 188 admits labelled cartesian marker rotation
    // the same way (XYAW nums[8]). html, class_name, and polar stay fail-closed.
    if extra_key(&legend_keys, PUBLIC_LEGEND_KEYS) {
        return Ok("XYG_SCENE_UNSUPPORTED_PUBLIC_LEGEND");
    }
    for axis in &axes {
        if axis.resolved_kind != 0 || !matches!(axis.authored_type, 0 | 1 | 2 | 3) {
            return Ok("XYG_SCENE_UNSUPPORTED_PUBLIC_AXIS");
        }
        let axis_allowed: Vec<&str> = if flags & FLAG_POLAR != 0 {
            PUBLIC_AXIS_KEYS
                .iter()
                .chain(POLAR_AXIS_KEYS.iter())
                .copied()
                .collect()
        } else {
            PUBLIC_AXIS_KEYS.to_vec()
        };
        if extra_key(&axis.keys, axis_allowed.as_slice()) {
            return Ok("XYG_SCENE_UNSUPPORTED_PUBLIC_AXIS");
        }
    }
    if extra_key(&colorbar_keys, PUBLIC_COLORBAR_KEYS) {
        return Ok("XYG_SCENE_UNSUPPORTED_PUBLIC_COLORBAR");
    }
    // Literal geometry is anchored to the primary Cartesian x/y viewport.
    // Missing x or y is the same as an empty options dict: no domain.
    // Heatmap/contour lattices carry their own cell extent, so they autorange
    // like scatter and do not require an authored axis domain.
    let needs_authored_domain = traces.iter().any(|trace| kind_literal_geometry(trace.kind));
    let needs_primary_axes =
        needs_authored_domain || traces.iter().any(|trace| kind_extent_geometry(trace.kind));
    if needs_primary_axes {
        for wanted in [0u8, 1u8] {
            let Some(axis) = axes.iter().find(|axis| axis.axis_id == wanted) else {
                return Ok("XYG_SCENE_UNSUPPORTED_PUBLIC_AXIS");
            };
            let default_side = if wanted == 0 { 1 } else { 2 };
            if axis.side != 0 && axis.side != default_side {
                return Ok("XYG_SCENE_UNSUPPORTED_PUBLIC_AXIS");
            }
            if needs_authored_domain && !axis.domain_present {
                return Ok("XYG_SCENE_UNSUPPORTED_PUBLIC_AXIS");
            }
        }
    }

    let mut public_triangle_mesh_count = 0usize;
    for trace in &traces {
        let point_limit = if trace.kind == KIND_LINE && matches!(trace.step, 1 | 2 | 3) {
            MAX_PUBLIC_STEP_POINTS
        } else {
            MAX_PUBLIC_POINTS
        };
        if trace.flags & TRACE_HAS_X != 0
            && trace.n_x as usize > point_limit
            && (trace.kind != KIND_SCATTER || trace.flags & TRACE_DENSITY_BLIT == 0)
        {
            return Ok("XYG_SCENE_UNSUPPORTED_PUBLIC_LOD");
        }
        if kind_band(trace.kind) && (trace.flags & TRACE_HAS_X == 0 || trace.n_x < 2) {
            return Ok("XYG_SCENE_UNSUPPORTED_PUBLIC_BAND");
        }
        if !kind_public(trace.kind) {
            return Ok("XYG_SCENE_UNSUPPORTED_PUBLIC_MARK");
        }
        if kind_segment(trace.kind) {
            if trace.flags & TRACE_ENDPOINTS_PRESENT == 0 {
                return Ok("XYG_SCENE_UNSUPPORTED_PUBLIC_SEGMENTS");
            }
            if trace.flags & TRACE_ENDPOINTS_LEN_EQUAL == 0
                || trace.n_x0 as usize > MAX_PUBLIC_POINTS
            {
                return Ok("XYG_SCENE_UNSUPPORTED_PUBLIC_SEGMENTS");
            }
            if !accepted_segment_role(trace.kind, trace.role) {
                return Ok("XYG_SCENE_UNSUPPORTED_PUBLIC_STYLE");
            }
        }
        if matches!(trace.kind, KIND_VIOLIN | KIND_BOX) {
            if trace.flags & TRACE_ENDPOINTS_PRESENT == 0 {
                return Ok("XYG_SCENE_UNSUPPORTED_PUBLIC_MARK");
            }
            if trace.flags & TRACE_ENDPOINTS_LEN_EQUAL == 0
                || trace.n_x0 as usize > MAX_PUBLIC_POINTS
            {
                return Ok("XYG_SCENE_UNSUPPORTED_PUBLIC_LOD");
            }
            let expected = if trace.kind == KIND_VIOLIN {
                "violin"
            } else {
                "box"
            };
            if trace.role != expected {
                return Ok("XYG_SCENE_UNSUPPORTED_PUBLIC_STYLE");
            }
        }
        if trace.kind == KIND_RIBBON && trace.role != "ribbon" {
            return Ok("XYG_SCENE_UNSUPPORTED_PUBLIC_STYLE");
        }
        if trace.kind == KIND_TRIANGLE_MESH {
            if trace.flags & TRACE_MESH_PRESENT == 0 {
                return Ok("XYG_SCENE_UNSUPPORTED_PUBLIC_TRIANGLE_MESH");
            }
            public_triangle_mesh_count = public_triangle_mesh_count
                .checked_add(trace.n_x as usize)
                .ok_or(SceneError::Limit)?;
            if trace.flags & TRACE_MESH_LEN_EQUAL == 0
                || public_triangle_mesh_count > MAX_PUBLIC_TRIANGLE_MESHES
                || trace.flags & TRACE_MESH_FINITE == 0
            {
                return Ok("XYG_SCENE_UNSUPPORTED_PUBLIC_TRIANGLE_MESH");
            }
            if trace.role != "triangle-mesh" {
                return Ok("XYG_SCENE_UNSUPPORTED_PUBLIC_STYLE");
            }
        }
        if trace.kind == KIND_HEXBIN {
            if trace.flags & TRACE_HEX_XY_OK == 0 {
                return Ok("XYG_SCENE_UNSUPPORTED_PUBLIC_MARK");
            }
            public_triangle_mesh_count = public_triangle_mesh_count
                .checked_add(trace.n_x as usize)
                .ok_or(SceneError::Limit)?;
            if trace.n_x as usize > MAX_PUBLIC_TRIANGLE_MESHES
                || public_triangle_mesh_count > MAX_PUBLIC_TRIANGLE_MESHES
                || trace.flags & TRACE_HEX_FINITE == 0
            {
                return Ok("XYG_SCENE_UNSUPPORTED_PUBLIC_LOD");
            }
            let pitch_ok = trace.hex_dx.is_finite()
                && trace.hex_dy.is_finite()
                && trace.hex_dx > 0.0
                && trace.hex_dy > 0.0;
            if trace.role != "hexbin" || !HEXBIN_REDUCES.contains(&trace.reduce) || !pitch_ok {
                return Ok("XYG_SCENE_UNSUPPORTED_PUBLIC_STYLE");
            }
        }
        if trace.kind == KIND_HEATMAP {
            if trace.flags & TRACE_HEATMAP_COLORMAP != 0 {
                return Ok("XYG_SCENE_UNSUPPORTED_PUBLIC_STYLE");
            }
            if trace.flags & TRACE_HEATMAP_SHAPE_OK == 0
                || trace.flags & TRACE_HEATMAP_EXTENT_OK == 0
            {
                return Ok("XYG_SCENE_UNSUPPORTED_PUBLIC_MARK");
            }
            let cells = (trace.heatmap_rows as usize)
                .checked_mul(trace.heatmap_cols as usize)
                .ok_or(SceneError::Limit)?;
            let polar_painted = flags & FLAG_POLAR != 0
                && (trace.style_keys.contains(&"colormap")
                    || trace.style_keys.contains(&"truecolor"));
            let polar_painted_stroke = polar_painted
                && trace.style_keys.contains(&"stroke")
                && trace.style_keys.contains(&"stroke_width");
            let cell_cap = if polar_painted && !polar_painted_stroke {
                MAX_SCENE_IMAGE_PIXELS
            } else {
                MAX_PUBLIC_HEATMAP_CELLS
            };
            if cells > cell_cap
                || trace.heatmap_values as usize != cells
                || trace.flags & TRACE_HEATMAP_FINITE == 0
            {
                return Ok("XYG_SCENE_UNSUPPORTED_PUBLIC_LOD");
            }
            if trace.role != "heatmap" {
                return Ok("XYG_SCENE_UNSUPPORTED_PUBLIC_STYLE");
            }
        }
        if trace.kind == KIND_SCATTER && !trace.role.is_empty() {
            if trace.flags & TRACE_HAS_X == 0
                || trace.flags & TRACE_HAS_Y == 0
                || trace.flags & TRACE_XY_LEN_EQUAL == 0
            {
                return Ok("XYG_SCENE_UNSUPPORTED_PUBLIC_STYLE");
            }
            if trace.role == "stem-marker" {
                if trace.prev_kind != KIND_STEM || trace.flags & TRACE_COMPANION_XY_MATCH == 0 {
                    return Ok("XYG_SCENE_UNSUPPORTED_PUBLIC_STYLE");
                }
            } else if trace.role == "box-outlier" {
                if trace.prev3_kind != KIND_BOX_WHISKER
                    || trace.prev2_kind != KIND_BOX
                    || trace.prev_kind != KIND_BOX_MEDIAN
                    || trace.n_x as usize > MAX_PUBLIC_POINTS
                    || trace.flags & TRACE_BOX_OUTLIER_FINITE == 0
                    || trace.flags & TRACE_COMPANION_AXES_MATCH == 0
                {
                    return Ok("XYG_SCENE_UNSUPPORTED_PUBLIC_STYLE");
                }
            } else {
                return Ok("XYG_SCENE_UNSUPPORTED_PUBLIC_STYLE");
            }
        }
        if trace.kind == KIND_SCATTER
            && (trace.flags & TRACE_SYMBOL_NON_STRING != 0
                || !PUBLIC_SYMBOLS.contains(&if trace.symbol.is_empty() {
                    "circle"
                } else {
                    trace.symbol
                }))
        {
            return Ok("XYG_SCENE_UNSUPPORTED_PUBLIC_SYMBOL");
        }
        if extra_key(&trace.style_keys, public_style_keys(trace.kind)) {
            return Ok("XYG_SCENE_UNSUPPORTED_PUBLIC_STYLE");
        }
    }
    if public_triangle_mesh_count > 0 {
        let extra_groups = traces
            .iter()
            .filter(|trace| trace.kind != KIND_TRIANGLE_MESH && trace.kind != KIND_HEXBIN)
            .count();
        if public_triangle_mesh_count
            .checked_add(extra_groups)
            .ok_or(SceneError::Limit)?
            > MAX_PUBLIC_TRIANGLE_MESHES
        {
            return Ok("XYG_SCENE_UNSUPPORTED_PUBLIC_TRIANGLE_MESH");
        }
    }
    Ok("")
}

const XYFS_MAGIC: &[u8; 4] = b"XYFS";
const XYFS_VERSION: u32 = 1;
const XYFS_VERSION_TRACES: u32 = 2;
const XYFS_HEADER_BYTES: usize = 16;
const XYFS_V2_HEADER_BYTES: usize = 20;
const XYFS_AXIS_BYTES: usize = 8;
const XYFS_TRACE_BYTES: usize = 8;
const MAX_XYFS_KIND_BYTES: usize = 32;

const OBS_POLAR: u32 = 1 << 0;
const OBS_CUSTOM_FONT: u32 = 1 << 1;
const OBS_BROWSER_CSS: u32 = 1 << 2;
const OBS_GRADIENT: u32 = 1 << 3;
const OBS_COLORBAR: u32 = 1 << 4;
const OBS_EXTRA_LEGEND: u32 = 1 << 5;
const OBS_LABELED_ANNOTATION: u32 = 1 << 7;
const OBS_MASK: u32 = (1 << 9) - 1;

const FIGURE_AXIS_SET_REASON: &str =
    "Scene v12 figure compilation currently supports exactly x/y axes";
const FIGURE_AXIS_KEYS_REASON: &str =
    "Scene v12 does not yet encode tick formatting, collision policy, or advanced axis layout";
const FIGURE_TRACE_AXIS_REASON: &str = "Scene v12 currently supports only the primary x/y axes";
const FIGURE_HIDDEN_REASON: &str = "Scene v12 does not yet encode hidden or per-item styled marks";
const FIGURE_DENSITY_REASON: &str = "Scene v12 does not yet encode density-tier scatter";
const FIGURE_DASHED_REASON: &str = "Scene v12 does not yet encode authored markers";
const FIGURE_JOINED_FILL_REASON: &str = "Scene v12 does not yet encode joined triangle-mesh fills";
const FIGURE_HEX_REDUCE_REASON: &str = "Scene v12 does not yet encode custom hexbin reducers";
const FIGURE_HEATMAP_REASON: &str = "Scene v12 does not yet encode heatmap colormap";

const XYFS_TRACE_UNSUPPORTED_KIND: u16 = 1 << 0;
const XYFS_TRACE_NON_PRIMARY_AXIS: u16 = 1 << 1;
const XYFS_TRACE_HIDDEN_OR_PER_ITEM: u16 = 1 << 2;
const XYFS_TRACE_DENSITY: u16 = 1 << 3;
const XYFS_TRACE_DASHED_MARKERS: u16 = 1 << 4;
const XYFS_TRACE_RECT_GRADIENT: u16 = 1 << 5;
const XYFS_TRACE_CORNER_RADIUS: u16 = 1 << 6;
const XYFS_TRACE_WEDGE_GAP: u16 = 1 << 7;
const XYFS_TRACE_JOINED_FILL: u16 = 1 << 8;
const XYFS_TRACE_CUSTOM_HEX_REDUCE: u16 = 1 << 9;
const XYFS_TRACE_HEATMAP_COLORMAP: u16 = 1 << 10;
const XYFS_TRACE_NON_CSS_FILL: u16 = 1 << 11;
const XYFS_TRACE_FLAG_MASK: u16 = (1 << 12) - 1;

/// Return Rust's figure-compile support diagnostic for a packed `XYFS`
/// envelope. Hosts pack literal observations, axis ids/keys, and (v2)
/// per-trace allowlist flags; Rust maps those onto the Scene feature mask,
/// enforces the primary x/y axis set, the Scene axis-key allowlist, and the
/// figure-compile trace allowlist. v1 envelopes remain accepted as
/// observation-plus-axis-only probes.
pub fn scene_figure_support_reason(bytes: &[u8]) -> Result<String, SceneError> {
    scene_figure_support_reason_with_attach(bytes, &[])
}

/// ABI 189: same XYFS probe, relaxing per-item / heatmap-colormap fail-closed
/// bits when packed XYTA tessellates those traces onto cell fills.
pub fn scene_figure_support_reason_with_attach(
    bytes: &[u8],
    xyta: &[u8],
) -> Result<String, SceneError> {
    use crate::scene::{
        scene_support_reason, SCENE_FEATURE_BROWSER_CSS, SCENE_FEATURE_COLORBAR,
        SCENE_FEATURE_CUSTOM_FONT, SCENE_FEATURE_EXTRA_LEGEND, SCENE_FEATURE_GRADIENT,
        SCENE_FEATURE_LABELED_ANNOTATION, SCENE_FEATURE_POLAR, SCENE_SUPPORT_REQUEST_VERSION,
    };

    if bytes.len() < XYFS_HEADER_BYTES || &bytes[..4] != XYFS_MAGIC {
        return Err(SceneError::Length);
    }
    let mut cursor = Cursor::new(bytes);
    let _magic = cursor.bytes(4)?;
    let version = cursor.u32()?;
    if version != XYFS_VERSION && version != XYFS_VERSION_TRACES {
        return Err(SceneError::Version);
    }
    let flags = cursor.u32()?;
    if flags & !OBS_MASK != 0 {
        return Err(SceneError::Version);
    }
    let n_axes = cursor.u32()?;
    let n_traces = if version == XYFS_VERSION_TRACES {
        if bytes.len() < XYFS_V2_HEADER_BYTES {
            return Err(SceneError::Length);
        }
        cursor.u32()?
    } else {
        0
    };
    if n_axes as usize > MAX_XYEP_AXES || n_traces as usize > MAX_XYEP_TRACES {
        return Err(SceneError::Limit);
    }

    let mut features = 0u64;
    if flags & OBS_CUSTOM_FONT != 0 {
        features |= SCENE_FEATURE_CUSTOM_FONT;
    }
    if flags & OBS_BROWSER_CSS != 0 {
        features |= SCENE_FEATURE_BROWSER_CSS;
    }
    if flags & OBS_GRADIENT != 0 {
        features |= SCENE_FEATURE_GRADIENT;
    }
    if flags & OBS_COLORBAR != 0 {
        features |= SCENE_FEATURE_COLORBAR;
    }
    if flags & OBS_EXTRA_LEGEND != 0 {
        features |= SCENE_FEATURE_EXTRA_LEGEND;
    }
    if flags & OBS_LABELED_ANNOTATION != 0 {
        features |= SCENE_FEATURE_LABELED_ANNOTATION;
    }

    let mut has_x = false;
    let mut has_y = false;
    let mut axis_keys: Vec<Vec<&str>> = Vec::new();
    for _ in 0..n_axes {
        if cursor.remaining() < XYFS_AXIS_BYTES {
            return Err(SceneError::Length);
        }
        let axis_id = cursor.u8()?;
        let _pad0 = cursor.u8()?;
        let _pad1 = cursor.u8()?;
        let _pad2 = cursor.u8()?;
        let n_keys = cursor.u32()?;
        match axis_id {
            0 => has_x = true,
            1 => has_y = true,
            _ => {
                return Ok(FIGURE_AXIS_SET_REASON.to_string());
            }
        }
        axis_keys.push(cursor.keys(n_keys)?);
    }
    if n_axes != 2 || !has_x || !has_y {
        return Ok(FIGURE_AXIS_SET_REASON.to_string());
    }

    let mut traces = Vec::with_capacity(n_traces as usize);
    for _ in 0..n_traces {
        if cursor.remaining() < XYFS_TRACE_BYTES {
            return Err(SceneError::Length);
        }
        let trace_flags = cursor.u16()?;
        if trace_flags & !XYFS_TRACE_FLAG_MASK != 0 {
            return Err(SceneError::Version);
        }
        let kind_len = cursor.u8()? as usize;
        let pad = cursor.u8()?;
        let reserved = cursor.u32()?;
        if pad != 0 || reserved != 0 || kind_len > MAX_XYFS_KIND_BYTES {
            return Err(SceneError::Length);
        }
        let kind_bytes = cursor.bytes(kind_len)?;
        if kind_bytes.contains(&0) {
            return Err(SceneError::Length);
        }
        let kind = std::str::from_utf8(kind_bytes)
            .map_err(|_| SceneError::Length)?
            .to_string();
        traces.push((trace_flags, kind));
    }
    if cursor.remaining() != 0 {
        return Err(SceneError::Length);
    }

    if flags & OBS_POLAR != 0 {
        let unsupported: Vec<&str> = traces
            .iter()
            .map(|(_, kind)| {
                if kind.is_empty() {
                    "mark"
                } else {
                    kind.as_str()
                }
            })
            .filter(|kind| !POLAR_SCENE_KINDS.contains(kind))
            .collect();
        if !unsupported.is_empty() {
            features |= SCENE_FEATURE_POLAR;
        }
    }
    let feature_reason = scene_support_reason(SCENE_SUPPORT_REQUEST_VERSION, features)?;
    if !feature_reason.is_empty() {
        return Ok(feature_reason.to_string());
    }

    let axis_allowed: Vec<&str> = if flags & OBS_POLAR != 0 {
        PUBLIC_AXIS_KEYS
            .iter()
            .chain(POLAR_AXIS_KEYS.iter())
            .copied()
            .collect()
    } else {
        PUBLIC_AXIS_KEYS.to_vec()
    };
    for keys in &axis_keys {
        if extra_key(keys.as_slice(), axis_allowed.as_slice()) {
            return Ok(FIGURE_AXIS_KEYS_REASON.to_string());
        }
    }

    if let Some((_, kind)) = traces
        .iter()
        .find(|(flags, _)| flags & XYFS_TRACE_UNSUPPORTED_KIND != 0)
    {
        let kind = if kind.is_empty() {
            "mark"
        } else {
            kind.as_str()
        };
        return Ok(format!(
            "Scene v12 figure compilation does not yet support {kind}"
        ));
    }
    let tessellation = crate::scene_trace_attach::xyta_cell_fill_tessellation(xyta).ok();
    for (index, (trace_flags, kind)) in traces.iter().enumerate() {
        let kind = if kind.is_empty() {
            "mark"
        } else {
            kind.as_str()
        };
        let tess = tessellation
            .as_ref()
            .and_then(|all| all.get(index).copied())
            .unwrap_or(crate::scene_trace_attach::CellFillTessellation::None);
        let hexbin_cells =
            kind == "hexbin" && tess != crate::scene_trace_attach::CellFillTessellation::None;
        let heatmap_cells =
            kind == "heatmap" && tess != crate::scene_trace_attach::CellFillTessellation::None;
        let ribbon_ends =
            kind == "ribbon" && tess == crate::scene_trace_attach::CellFillTessellation::Ribbon;
        if trace_flags & XYFS_TRACE_NON_PRIMARY_AXIS != 0 {
            return Ok(FIGURE_TRACE_AXIS_REASON.to_string());
        }
        if trace_flags & XYFS_TRACE_HIDDEN_OR_PER_ITEM != 0 && !hexbin_cells && !ribbon_ends {
            return Ok(FIGURE_HIDDEN_REASON.to_string());
        }
        if trace_flags & XYFS_TRACE_DENSITY != 0 {
            return Ok(FIGURE_DENSITY_REASON.to_string());
        }
        if trace_flags & XYFS_TRACE_DASHED_MARKERS != 0 {
            return Ok(FIGURE_DASHED_REASON.to_string());
        }
        if trace_flags & XYFS_TRACE_RECT_GRADIENT != 0 {
            return Ok(format!(
                "Scene v12 does not yet encode {kind} gradient fills"
            ));
        }
        if trace_flags & XYFS_TRACE_CORNER_RADIUS != 0 {
            return Ok(format!(
                "Scene v12 does not yet encode {kind} corner_radius"
            ));
        }
        if trace_flags & XYFS_TRACE_WEDGE_GAP != 0 {
            return Ok(format!("Scene v12 does not yet encode {kind} wedge_gap"));
        }
        if trace_flags & XYFS_TRACE_JOINED_FILL != 0 {
            return Ok(FIGURE_JOINED_FILL_REASON.to_string());
        }
        if trace_flags & XYFS_TRACE_CUSTOM_HEX_REDUCE != 0 {
            return Ok(FIGURE_HEX_REDUCE_REASON.to_string());
        }
        if trace_flags & XYFS_TRACE_HEATMAP_COLORMAP != 0 && !heatmap_cells {
            return Ok(FIGURE_HEATMAP_REASON.to_string());
        }
        if trace_flags & XYFS_TRACE_NON_CSS_FILL != 0 {
            return Ok(format!(
                "Scene v12 does not yet encode {kind} non-CSS fills"
            ));
        }
    }
    Ok(String::new())
}

#[cfg(test)]
mod tests {
    use super::*;

    fn put_keys(buf: &mut Vec<u8>, keys: &[&str]) {
        for key in keys {
            let bytes = key.as_bytes();
            buf.extend_from_slice(&(bytes.len() as u16).to_le_bytes());
            buf.extend_from_slice(bytes);
        }
    }

    fn header(
        flags: u32,
        n_style: u32,
        n_legend: u32,
        n_colorbar: u32,
        n_axes: u32,
        n_ann: u32,
        n_traces: u32,
    ) -> Vec<u8> {
        let mut buf = Vec::from(*XYEP_MAGIC);
        buf.extend_from_slice(&XYEP_VERSION.to_le_bytes());
        buf.extend_from_slice(&flags.to_le_bytes());
        buf.extend_from_slice(&n_style.to_le_bytes());
        buf.extend_from_slice(&n_legend.to_le_bytes());
        buf.extend_from_slice(&n_colorbar.to_le_bytes());
        buf.extend_from_slice(&n_axes.to_le_bytes());
        buf.extend_from_slice(&n_ann.to_le_bytes());
        buf.extend_from_slice(&n_traces.to_le_bytes());
        buf
    }

    fn empty_figure() -> Vec<u8> {
        header(0, 0, 0, 0, 0, 0, 0)
    }

    #[test]
    fn heatmap_and_contour_autorange_without_authored_axis_domain() {
        fn put_axis(buf: &mut Vec<u8>, axis_id: u8, domain_present: bool) {
            buf.extend_from_slice(&[axis_id, 0, 0, u8::from(domain_present), 0, 0, 0, 0]);
        }
        fn put_heatmap(buf: &mut Vec<u8>) {
            let role = b"heatmap";
            buf.push(KIND_HEATMAP);
            buf.extend_from_slice(&[0, 255, 255, 255, 0, 0, 0]);
            let flags = TRACE_HEATMAP_SHAPE_OK | TRACE_HEATMAP_EXTENT_OK | TRACE_HEATMAP_FINITE;
            buf.extend_from_slice(&flags.to_le_bytes());
            buf.extend_from_slice(&[0u8; 24]);
            buf.extend_from_slice(&2u32.to_le_bytes());
            buf.extend_from_slice(&2u32.to_le_bytes());
            buf.extend_from_slice(&4u32.to_le_bytes());
            buf.extend_from_slice(&0u16.to_le_bytes());
            buf.extend_from_slice(&(role.len() as u16).to_le_bytes());
            buf.extend_from_slice(&0u16.to_le_bytes());
            buf.extend_from_slice(&0u16.to_le_bytes());
            buf.extend_from_slice(&f64::NAN.to_le_bytes());
            buf.extend_from_slice(&f64::NAN.to_le_bytes());
            buf.extend_from_slice(role);
        }
        let mut ok = header(0, 0, 0, 0, 2, 0, 1);
        put_axis(&mut ok, 0, false);
        put_axis(&mut ok, 1, false);
        put_heatmap(&mut ok);
        assert_eq!(scene_public_export_reason(&ok), Ok(""));

        let mut line = header(0, 0, 0, 0, 2, 0, 1);
        put_axis(&mut line, 0, false);
        put_axis(&mut line, 1, false);
        line.push(KIND_LINE);
        line.extend_from_slice(&[0, 255, 255, 255, 0, 0, 0]);
        line.extend_from_slice(&0u32.to_le_bytes());
        line.extend_from_slice(&[0u8; 36]);
        line.extend_from_slice(&0u16.to_le_bytes());
        line.extend_from_slice(&0u16.to_le_bytes());
        line.extend_from_slice(&0u16.to_le_bytes());
        line.extend_from_slice(&0u16.to_le_bytes());
        line.extend_from_slice(&f64::NAN.to_le_bytes());
        line.extend_from_slice(&f64::NAN.to_le_bytes());
        assert_eq!(
            scene_public_export_reason(&line),
            Ok("XYG_SCENE_UNSUPPORTED_PUBLIC_AXIS")
        );
    }

    #[test]
    fn fluid_viewport_is_ordered_first() {
        let bytes = header(FLAG_FLUID_WIDTH, 0, 0, 0, 0, 0, 0);
        assert_eq!(
            scene_public_export_reason(&bytes),
            Ok("XYG_SCENE_UNSUPPORTED_FLUID_VIEWPORT")
        );
    }

    #[test]
    fn figure_style_allowlist_is_rust_owned() {
        let mut bytes = header(0, 1, 0, 0, 0, 0, 0);
        put_keys(&mut bytes, &["font-family"]);
        assert_eq!(
            scene_public_export_reason(&bytes),
            Ok("XYG_SCENE_UNSUPPORTED_PUBLIC_STYLE")
        );
        let mut ok = header(0, 1, 0, 0, 0, 0, 0);
        put_keys(&mut ok, &["background"]);
        assert_eq!(scene_public_export_reason(&ok), Ok(""));
    }

    #[test]
    fn rejects_unknown_version_and_trailing_bytes() {
        let mut bad = empty_figure();
        bad[4] = 2;
        assert_eq!(scene_public_export_reason(&bad), Err(SceneError::Version));
        let mut extra = empty_figure();
        extra.push(0);
        assert_eq!(scene_public_export_reason(&extra), Err(SceneError::Length));
    }

    fn put_xyfs_axes(buf: &mut Vec<u8>, axes: &[(u8, &[&str])]) {
        for (axis_id, keys) in axes {
            buf.push(*axis_id);
            buf.extend_from_slice(&[0, 0, 0]);
            buf.extend_from_slice(&(keys.len() as u32).to_le_bytes());
            put_keys(buf, keys);
        }
    }

    fn xyfs(flags: u32, axes: &[(u8, &[&str])]) -> Vec<u8> {
        let mut buf = Vec::from(*XYFS_MAGIC);
        buf.extend_from_slice(&XYFS_VERSION.to_le_bytes());
        buf.extend_from_slice(&flags.to_le_bytes());
        buf.extend_from_slice(&(axes.len() as u32).to_le_bytes());
        put_xyfs_axes(&mut buf, axes);
        buf
    }

    fn xyfs_v2(flags: u32, axes: &[(u8, &[&str])], traces: &[(u16, &str)]) -> Vec<u8> {
        let mut buf = Vec::from(*XYFS_MAGIC);
        buf.extend_from_slice(&XYFS_VERSION_TRACES.to_le_bytes());
        buf.extend_from_slice(&flags.to_le_bytes());
        buf.extend_from_slice(&(axes.len() as u32).to_le_bytes());
        buf.extend_from_slice(&(traces.len() as u32).to_le_bytes());
        put_xyfs_axes(&mut buf, axes);
        for (trace_flags, kind) in traces {
            buf.extend_from_slice(&trace_flags.to_le_bytes());
            buf.push(kind.len() as u8);
            buf.push(0);
            buf.extend_from_slice(&0u32.to_le_bytes());
            buf.extend_from_slice(kind.as_bytes());
        }
        buf
    }

    const PRIMARY_XY: [(u8, &'static [&'static str]); 2] =
        [(0, &["label", "side"]), (1, &["label", "side"])];

    #[test]
    fn figure_support_accepts_primary_xy_with_allowlisted_keys() {
        assert_eq!(
            scene_figure_support_reason(&xyfs(0, &PRIMARY_XY)),
            Ok(String::new())
        );
        assert_eq!(
            scene_figure_support_reason(&xyfs_v2(0, &PRIMARY_XY, &[(0, "scatter")])),
            Ok(String::new())
        );
    }

    #[test]
    fn figure_support_maps_polar_before_axis_keys() {
        assert_eq!(
            scene_figure_support_reason(&xyfs_v2(
                OBS_POLAR,
                &PRIMARY_XY,
                &[(XYFS_TRACE_UNSUPPORTED_KIND, "stem")]
            )),
            Ok(
                "XYG_SCENE_UNSUPPORTED_POLAR: Scene v26 supports polar line, scatter, area, bar, column, errorbar, heatmap, and contour only"
                    .to_string()
            )
        );
    }

    #[test]
    fn figure_support_accepts_polar_bar_heatmap_and_contour() {
        assert_eq!(
            scene_figure_support_reason(&xyfs_v2(OBS_POLAR, &PRIMARY_XY, &[(0, "bar")])),
            Ok(String::new())
        );
        assert_eq!(
            scene_figure_support_reason(&xyfs_v2(OBS_POLAR, &PRIMARY_XY, &[(0, "column")])),
            Ok(String::new())
        );
        assert_eq!(
            scene_figure_support_reason(&xyfs_v2(OBS_POLAR, &PRIMARY_XY, &[(0, "errorbar")])),
            Ok(String::new())
        );
        assert_eq!(
            scene_figure_support_reason(&xyfs_v2(OBS_POLAR, &PRIMARY_XY, &[(0, "heatmap")])),
            Ok(String::new())
        );
        assert_eq!(
            scene_figure_support_reason(&xyfs_v2(OBS_POLAR, &PRIMARY_XY, &[(0, "contour")])),
            Ok(String::new())
        );
    }

    #[test]
    fn figure_support_accepts_polar_scatter_and_polar_axis_keys() {
        assert_eq!(
            scene_figure_support_reason(&xyfs_v2(
                OBS_POLAR,
                &[
                    (0, &["label", "theta_unit", "theta_zero"]),
                    (1, &["label", "hole", "r_origin"]),
                ],
                &[(0, "scatter")]
            )),
            Ok(String::new())
        );
        assert_eq!(
            scene_figure_support_reason(&xyfs(OBS_POLAR, &[(0, &["collision"]), (1, &["label"])])),
            Ok(FIGURE_AXIS_KEYS_REASON.to_string())
        );
    }

    #[test]
    fn figure_support_rejects_unknown_axis_keys_and_non_primary_ids() {
        assert_eq!(
            scene_figure_support_reason(&xyfs(0, &[(0, &["collision"]), (1, &["label"])])),
            Ok(FIGURE_AXIS_KEYS_REASON.to_string())
        );
        assert_eq!(
            scene_figure_support_reason(&xyfs(0, &[(0, &["label"])])),
            Ok(FIGURE_AXIS_SET_REASON.to_string())
        );
        assert_eq!(
            scene_figure_support_reason(&xyfs(0, &[(0, &["label"]), (2, &["label"])])),
            Ok(FIGURE_AXIS_SET_REASON.to_string())
        );
    }

    #[test]
    fn figure_support_rejects_unknown_version_and_observation_bits() {
        let mut bad = xyfs(0, &[(0, &[]), (1, &[])]);
        bad[4] = 3;
        assert_eq!(scene_figure_support_reason(&bad), Err(SceneError::Version));
        assert_eq!(
            scene_figure_support_reason(&xyfs(1 << 20, &[(0, &[]), (1, &[])])),
            Err(SceneError::Version)
        );
    }

    #[test]
    fn figure_support_rejects_unsupported_kind_before_density() {
        assert_eq!(
            scene_figure_support_reason(&xyfs_v2(
                0,
                &PRIMARY_XY,
                &[(XYFS_TRACE_UNSUPPORTED_KIND, "text")]
            )),
            Ok("Scene v12 figure compilation does not yet support text".to_string())
        );
        assert_eq!(
            scene_figure_support_reason(&xyfs_v2(
                0,
                &PRIMARY_XY,
                &[(XYFS_TRACE_UNSUPPORTED_KIND | XYFS_TRACE_DENSITY, "text")]
            )),
            Ok("Scene v12 figure compilation does not yet support text".to_string())
        );
    }

    #[test]
    fn figure_support_rejects_density_hidden_and_corner_radius() {
        assert_eq!(
            scene_figure_support_reason(&xyfs_v2(
                0,
                &PRIMARY_XY,
                &[(XYFS_TRACE_DENSITY, "scatter")]
            )),
            Ok(FIGURE_DENSITY_REASON.to_string())
        );
        assert_eq!(
            scene_figure_support_reason(&xyfs_v2(
                0,
                &PRIMARY_XY,
                &[(XYFS_TRACE_HIDDEN_OR_PER_ITEM, "scatter")]
            )),
            Ok(FIGURE_HIDDEN_REASON.to_string())
        );
        assert_eq!(
            scene_figure_support_reason(&xyfs_v2(
                0,
                &PRIMARY_XY,
                &[(XYFS_TRACE_CORNER_RADIUS, "rect")]
            )),
            Ok("Scene v12 does not yet encode rect corner_radius".to_string())
        );
    }

    #[test]
    fn figure_support_rejects_extra_axis_before_trace_flags() {
        assert_eq!(
            scene_figure_support_reason(&xyfs_v2(
                0,
                &[(0, &["label"]), (1, &["label"]), (2, &["label"])],
                &[(XYFS_TRACE_DENSITY, "scatter")]
            )),
            Ok(FIGURE_AXIS_SET_REASON.to_string())
        );
    }

    fn xyta_one(flags: u32, rows: i32, cols: i32, grid: &[f64], cmap: &[u8]) -> Vec<u8> {
        use crate::scene_trace_attach::{
            XYTA_HEADER_BYTES, XYTA_MAGIC, XYTA_PREFIX_BYTES, XYTA_VERSION,
        };
        let mut attach = vec![0u8; XYTA_HEADER_BYTES];
        attach[..4].copy_from_slice(XYTA_MAGIC);
        attach[4..8].copy_from_slice(&XYTA_VERSION.to_le_bytes());
        attach[8..12].copy_from_slice(&1u32.to_le_bytes());
        let mut prefix = vec![0u8; XYTA_PREFIX_BYTES];
        prefix[..4].copy_from_slice(&flags.to_le_bytes());
        prefix[8..12].copy_from_slice(&rows.to_le_bytes());
        prefix[12..16].copy_from_slice(&cols.to_le_bytes());
        prefix[16..20].copy_from_slice(&(grid.len() as u32).to_le_bytes());
        prefix[48..50].copy_from_slice(&(cmap.len() as u16).to_le_bytes());
        attach.extend_from_slice(&prefix);
        for value in grid {
            attach.extend_from_slice(&value.to_le_bytes());
        }
        attach.extend_from_slice(cmap);
        attach
    }

    #[test]
    fn figure_support_relaxes_hexbin_and_heatmap_from_packed_xyta() {
        use crate::scene_trace_attach::{
            FLAG_HAS_GRID, FLAG_HAS_NAMED_CMAP, FLAG_HEATMAP, FLAG_SHAPE, FLAG_TRUECOLOR,
        };
        let named = FLAG_HEATMAP | FLAG_SHAPE | FLAG_HAS_GRID | FLAG_HAS_NAMED_CMAP;
        let hexbin_xyta = xyta_one(named, 1, 2, &[0.0, 1.0], b"viridis");
        let heatmap_xyta = xyta_one(named, 2, 2, &[0.0, 1.0, 2.0, 3.0], b"viridis");
        let truecolor_xyta = xyta_one(FLAG_HEATMAP | FLAG_TRUECOLOR | FLAG_SHAPE, 2, 2, &[], b"");
        assert_eq!(
            scene_figure_support_reason_with_attach(
                &xyfs_v2(0, &PRIMARY_XY, &[(XYFS_TRACE_HIDDEN_OR_PER_ITEM, "hexbin")]),
                &hexbin_xyta,
            ),
            Ok(String::new())
        );
        assert_eq!(
            scene_figure_support_reason_with_attach(
                &xyfs_v2(0, &PRIMARY_XY, &[(XYFS_TRACE_HIDDEN_OR_PER_ITEM, "hexbin")]),
                &[],
            ),
            Ok(FIGURE_HIDDEN_REASON.to_string())
        );
        assert_eq!(
            scene_figure_support_reason_with_attach(
                &xyfs_v2(
                    0,
                    &PRIMARY_XY,
                    &[(XYFS_TRACE_HIDDEN_OR_PER_ITEM, "scatter")]
                ),
                &hexbin_xyta,
            ),
            Ok(FIGURE_HIDDEN_REASON.to_string())
        );
        assert_eq!(
            scene_figure_support_reason_with_attach(
                &xyfs_v2(0, &PRIMARY_XY, &[(XYFS_TRACE_HEATMAP_COLORMAP, "heatmap")]),
                &heatmap_xyta,
            ),
            Ok(String::new())
        );
        assert_eq!(
            scene_figure_support_reason_with_attach(
                &xyfs_v2(0, &PRIMARY_XY, &[(XYFS_TRACE_HEATMAP_COLORMAP, "heatmap")]),
                &truecolor_xyta,
            ),
            Ok(FIGURE_HEATMAP_REASON.to_string())
        );
        assert_eq!(
            scene_figure_support_reason_with_attach(
                &xyfs_v2(0, &PRIMARY_XY, &[(XYFS_TRACE_HIDDEN_OR_PER_ITEM, "hexbin")]),
                b"XXXX",
            ),
            Ok(FIGURE_HIDDEN_REASON.to_string())
        );
    }

    fn xyef_header(
        flags: u32,
        n_style: u32,
        n_legend: u32,
        n_colorbar: u32,
        n_axes: u32,
        n_ann: u32,
        n_traces: u32,
    ) -> Vec<u8> {
        let mut buf = Vec::from(*XYEF_MAGIC);
        buf.extend_from_slice(&XYEF_VERSION.to_le_bytes());
        buf.extend_from_slice(&flags.to_le_bytes());
        buf.extend_from_slice(&n_style.to_le_bytes());
        buf.extend_from_slice(&n_legend.to_le_bytes());
        buf.extend_from_slice(&n_colorbar.to_le_bytes());
        buf.extend_from_slice(&n_axes.to_le_bytes());
        buf.extend_from_slice(&n_ann.to_le_bytes());
        buf.extend_from_slice(&n_traces.to_le_bytes());
        buf
    }

    fn xyef_axis(axis_id: u8, domain_present: bool) -> [u8; 8] {
        [axis_id, 0, 0, u8::from(domain_present), 0, 0, 0, 0]
    }

    fn xyef_trace(
        kind: &str,
        obs: u32,
        n_x: u32,
        heatmap_rows: u32,
        heatmap_cols: u32,
        heatmap_values: u32,
        role: &str,
    ) -> Vec<u8> {
        let kind_b = kind.as_bytes();
        let role_b = role.as_bytes();
        let mut prefix = [0u8; XYEF_TRACE_PREFIX_BYTES];
        prefix[0..4].copy_from_slice(&obs.to_le_bytes());
        prefix[4..8].copy_from_slice(&n_x.to_le_bytes());
        prefix[8..12].copy_from_slice(&n_x.to_le_bytes());
        prefix[12..16].copy_from_slice(&n_x.to_le_bytes());
        prefix[16..20].copy_from_slice(&n_x.to_le_bytes());
        prefix[20..24].copy_from_slice(&n_x.to_le_bytes());
        prefix[24..28].copy_from_slice(&n_x.to_le_bytes());
        prefix[28..32].copy_from_slice(&heatmap_rows.to_le_bytes());
        prefix[32..36].copy_from_slice(&heatmap_cols.to_le_bytes());
        prefix[36..40].copy_from_slice(&heatmap_values.to_le_bytes());
        prefix[42..44].copy_from_slice(&(kind_b.len() as u16).to_le_bytes());
        prefix[46..48].copy_from_slice(&(role_b.len() as u16).to_le_bytes());
        prefix[64..72].copy_from_slice(&f64::NAN.to_le_bytes());
        prefix[72..80].copy_from_slice(&f64::NAN.to_le_bytes());
        let mut out = prefix.to_vec();
        out.extend_from_slice(kind_b);
        out.extend_from_slice(role_b);
        out
    }

    #[test]
    fn pack_public_export_empty_figure_is_supported() {
        let facts = xyef_header(0, 0, 0, 0, 0, 0, 0);
        let envelope = pack_public_export(&facts).unwrap();
        assert_eq!(&envelope[..4], b"XYEP");
        assert_eq!(scene_public_export_reason(&envelope), Ok(""));
    }

    #[test]
    fn pack_public_export_maps_kind_and_rejects_line_without_domain() {
        let mut facts = xyef_header(0, 0, 0, 0, 2, 0, 1);
        facts.extend_from_slice(&xyef_axis(0, false));
        facts.extend_from_slice(&xyef_axis(1, false));
        facts.extend_from_slice(&xyef_trace(
            "line",
            OBS_HAS_X | OBS_HAS_Y | OBS_X_FINITE | OBS_Y_FINITE,
            2,
            0,
            0,
            0,
            "",
        ));
        let envelope = pack_public_export(&facts).unwrap();
        assert_eq!(envelope[XYEP_HEADER_BYTES + 16], KIND_LINE);
        assert_eq!(
            scene_public_export_reason(&envelope),
            Ok("XYG_SCENE_UNSUPPORTED_PUBLIC_AXIS")
        );
    }

    #[test]
    fn pack_public_export_heatmap_autorange_without_authored_domain() {
        let mut facts = xyef_header(0, 0, 0, 0, 2, 0, 1);
        facts.extend_from_slice(&xyef_axis(0, false));
        facts.extend_from_slice(&xyef_axis(1, false));
        facts.extend_from_slice(&xyef_trace(
            "heatmap",
            OBS_HEATMAP_SHAPE_OK | OBS_HEATMAP_EXTENT_OK | OBS_HEATMAP_FINITE,
            0,
            2,
            2,
            4,
            "heatmap",
        ));
        let envelope = pack_public_export(&facts).unwrap();
        assert_eq!(envelope[XYEP_HEADER_BYTES + 16], KIND_HEATMAP);
        assert_eq!(scene_public_export_reason(&envelope), Ok(""));
    }

    #[test]
    fn pack_public_export_annotation_wrap_from_field_keys() {
        let mut facts = xyef_header(0, 0, 0, 0, 0, 1, 0);
        facts.extend_from_slice(&[0u8, 0, 0, 0]);
        facts.extend_from_slice(&(4u16).to_le_bytes());
        facts.extend_from_slice(&(2u16).to_le_bytes());
        facts.extend_from_slice(b"text");
        put_keys(&mut facts, &["kind", "wrap"]);
        let envelope = pack_public_export(&facts).unwrap();
        let ann = XYEP_HEADER_BYTES;
        assert_eq!(envelope[ann], 1);
        assert_eq!(envelope[ann + 1] & ANN_WRAP, ANN_WRAP);
        assert_eq!(envelope[ann + 1] & ANN_NOT_OBJECT, 0);
    }

    #[test]
    fn pack_public_export_truecolor_heatmap_sets_colormap_flag() {
        let mut facts = xyef_header(0, 0, 0, 0, 2, 0, 1);
        facts.extend_from_slice(&xyef_axis(0, true));
        facts.extend_from_slice(&xyef_axis(1, true));
        facts.extend_from_slice(&xyef_trace(
            "heatmap",
            OBS_HEATMAP_TRUECOLOR
                | OBS_HEATMAP_SHAPE_OK
                | OBS_HEATMAP_EXTENT_OK
                | OBS_HEATMAP_FINITE,
            0,
            2,
            2,
            4,
            "heatmap",
        ));
        let envelope = pack_public_export(&facts).unwrap();
        let flags = u32::from_le_bytes(
            envelope[XYEP_HEADER_BYTES + 16 + 8..XYEP_HEADER_BYTES + 16 + 12]
                .try_into()
                .unwrap(),
        );
        assert_eq!(flags & TRACE_HEATMAP_COLORMAP, TRACE_HEATMAP_COLORMAP);
    }

    #[test]
    fn public_export_triangle_mesh_counts_companion_traces_toward_group_budget() {
        let mesh_obs = OBS_HAS_X
            | OBS_HAS_Y
            | OBS_X_FINITE
            | OBS_Y_FINITE
            | OBS_HAS_X0
            | OBS_HAS_Y0
            | OBS_HAS_X1
            | OBS_HAS_Y1
            | OBS_X0_FINITE
            | OBS_Y0_FINITE
            | OBS_X1_FINITE
            | OBS_Y1_FINITE;
        let scatter_obs = OBS_HAS_X | OBS_HAS_Y | OBS_X_FINITE | OBS_Y_FINITE;
        let mut boundary = xyef_header(0, 0, 0, 0, 2, 0, 1);
        boundary.extend_from_slice(&xyef_axis(0, true));
        boundary.extend_from_slice(&xyef_axis(1, true));
        boundary.extend_from_slice(&xyef_trace(
            "triangle_mesh",
            mesh_obs,
            1024,
            0,
            0,
            0,
            "triangle-mesh",
        ));
        let envelope = pack_public_export(&boundary).unwrap();
        assert_eq!(scene_public_export_reason(&envelope), Ok(""));

        let mut mixed = xyef_header(0, 0, 0, 0, 2, 0, 2);
        mixed.extend_from_slice(&xyef_axis(0, true));
        mixed.extend_from_slice(&xyef_axis(1, true));
        mixed.extend_from_slice(&xyef_trace(
            "triangle_mesh",
            mesh_obs,
            1024,
            0,
            0,
            0,
            "triangle-mesh",
        ));
        mixed.extend_from_slice(&xyef_trace("scatter", scatter_obs, 1, 0, 0, 0, ""));
        let mixed_envelope = pack_public_export(&mixed).unwrap();
        assert_eq!(
            scene_public_export_reason(&mixed_envelope),
            Ok("XYG_SCENE_UNSUPPORTED_PUBLIC_TRIANGLE_MESH")
        );
    }
}
