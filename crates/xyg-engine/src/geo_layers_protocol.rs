//! Bounded XYLK/XYLM v1 transport for the shared geographic catalog (#49).
//! Byte framing is host-neutral; all defaults and presentation policy remain Rust-owned.
use crate::geo::{GeoCrs, GeoError, column_from_descriptor_bytes};
use crate::geo_interaction::{
    GeoFeatureKey, GeoInteractionEvent, GeoInteractionResult, GeoInteractionState, GeoPickIndex,
    GeoSelectionMode,
};
use crate::geo_layers::*;
use crate::geo_viewport::GeoViewport;
use crate::scene::LegendLocation;

pub const HEADER_BYTES: usize = 128;
pub const LAYER_BYTES: usize = 384;
pub const PATCH_BYTES: usize = 48;
pub const LABEL_BYTES: usize = 48;
pub const OUTPUT_HEADER_BYTES: usize = 128;
pub const OUTPUT_LAYER_BYTES: usize = 128;
pub const MAX_PROTOCOL_BYTES: usize = 384 * 1024 * 1024;
fn invalid() -> GeoError {
    GeoError::InvalidArgument
}
fn add(a: usize, b: usize) -> Result<usize, GeoError> {
    a.checked_add(b).ok_or(GeoError::ResourceLimit)
}
fn mul(a: usize, b: usize) -> Result<usize, GeoError> {
    a.checked_mul(b).ok_or(GeoError::ResourceLimit)
}
fn u32_at(b: &[u8], at: usize) -> u32 {
    u32::from_le_bytes(b[at..at + 4].try_into().unwrap())
}
fn u64_at(b: &[u8], at: usize) -> u64 {
    u64::from_le_bytes(b[at..at + 8].try_into().unwrap())
}
fn f64_at(b: &[u8], at: usize) -> f64 {
    f64::from_le_bytes(b[at..at + 8].try_into().unwrap())
}
fn count(b: &[u8], at: usize) -> Result<usize, GeoError> {
    usize::try_from(u64_at(b, at)).map_err(|_| GeoError::ResourceLimit)
}
fn zero(b: &[u8]) -> Result<(), GeoError> {
    if b.iter().any(|&v| v != 0) {
        Err(invalid())
    } else {
        Ok(())
    }
}
fn finite(b: &[u8], at: usize) -> Result<f64, GeoError> {
    let v = f64_at(b, at);
    if v.is_finite() {
        Ok(v)
    } else {
        Err(GeoError::NonFiniteCoordinate)
    }
}
fn text(b: &[u8]) -> Result<&str, GeoError> {
    std::str::from_utf8(b).map_err(|_| invalid())
}
fn take<'a>(b: &'a [u8], cursor: &mut usize, len: usize) -> Result<&'a [u8], GeoError> {
    let end = add(*cursor, len)?;
    let padded = add(end, 7)? & !7;
    let plane = b.get(*cursor..end).ok_or_else(invalid)?;
    zero(b.get(end..padded).ok_or_else(invalid)?)?;
    *cursor = padded;
    Ok(plane)
}
fn descriptor_frame(b: &[u8]) -> Result<(usize, usize), GeoError> {
    if b.len() < 64 || &b[..4] != b"XYGD" || u32_at(b, 4) != 1 || u32_at(b, 16) > 1 {
        return Err(invalid());
    }
    if b.len() > 256 * 1024 * 1024 {
        return Err(GeoError::ResourceLimit);
    }
    zero(&b[20..24])?;
    let n = count(b, 24)?;
    let vertices = count(b, 32)?;
    let mut cursor = 64;
    take(b, &mut cursor, mul(vertices, 16)?)?;
    take(b, &mut cursor, n)?;
    take(
        b,
        &mut cursor,
        if u32_at(b, 16) == 1 { mul(n, 8)? } else { 0 },
    )?;
    for at in [40, 48, 56] {
        take(b, &mut cursor, mul(count(b, at)?, 4)?)?;
    }
    if cursor != b.len() {
        return Err(invalid());
    }
    Ok((n, vertices))
}
fn kind(n: u32) -> Result<GeoLayerKind, GeoError> {
    match n {
        1 => Ok(GeoLayerKind::Points),
        2 => Ok(GeoLayerKind::Bubbles),
        3 => Ok(GeoLayerKind::Routes),
        4 => Ok(GeoLayerKind::Arcs),
        5 => Ok(GeoLayerKind::Polygons),
        6 => Ok(GeoLayerKind::Choropleth),
        7 => Ok(GeoLayerKind::Density),
        _ => Err(invalid()),
    }
}
fn location(n: u32) -> Result<LegendLocation, GeoError> {
    match n {
        0 => Ok(LegendLocation::UpperRight),
        1 => Ok(LegendLocation::UpperLeft),
        2 => Ok(LegendLocation::LowerLeft),
        3 => Ok(LegendLocation::LowerRight),
        4 => Ok(LegendLocation::CenterRight),
        5 => Ok(LegendLocation::CenterLeft),
        6 => Ok(LegendLocation::UpperCenter),
        7 => Ok(LegendLocation::LowerCenter),
        8 => Ok(LegendLocation::Center),
        _ => Err(invalid()),
    }
}
fn patch(b: &[u8]) -> Result<GeoStylePatch, GeoError> {
    let mask = u32_at(b, 0);
    if mask & !63 != 0 {
        return Err(invalid());
    }
    zero(&b[40..48])?;
    let symbol = u32_at(b, 4);
    if symbol > 255 {
        return Err(invalid());
    }
    for (bit, range) in [
        (32, 4..8),
        (1, 8..12),
        (2, 12..16),
        (4, 16..24),
        (8, 24..32),
        (16, 32..40),
    ] {
        if mask & bit == 0 {
            zero(&b[range])?;
        }
    }
    let width = finite(b, 16)?;
    let diameter = finite(b, 24)?;
    let opacity = finite(b, 32)?;
    Ok(GeoStylePatch {
        fill: (mask & 1 != 0).then(|| b[8..12].try_into().unwrap()),
        stroke: (mask & 2 != 0).then(|| b[12..16].try_into().unwrap()),
        stroke_width: (mask & 4 != 0).then_some(width),
        diameter: (mask & 8 != 0).then_some(diameter),
        opacity: (mask & 16 != 0).then_some(opacity),
        symbol: (mask & 32 != 0).then_some(symbol as u8),
    })
}
fn apply(p: GeoStylePatch, s: &mut GeoStyle) {
    if let Some(v) = p.fill {
        s.fill = v
    }
    if let Some(v) = p.stroke {
        s.stroke = v
    }
    if let Some(v) = p.stroke_width {
        s.stroke_width = v
    }
    if let Some(v) = p.diameter {
        s.diameter = v
    }
    if let Some(v) = p.opacity {
        s.opacity = v
    }
    if let Some(v) = p.symbol {
        s.symbol = v
    }
}
struct Frame<'a> {
    header: &'a [u8],
    descriptor: &'a [u8],
    patches: &'a [u8],
    values: &'a [u8],
    stops: &'a [u8],
    state: &'a [u8],
    labels: &'a [u8],
    legend: &'a [u8],
    label_text: &'a [u8],
}
struct Options<'a> {
    patches: Vec<GeoStylePatch>,
    values: Vec<f64>,
    stops: Vec<[u8; 3]>,
    labels: Vec<GeoLabel<'a>>,
}

fn event(b: &[u8]) -> Result<GeoInteractionEvent, GeoError> {
    let op = u32_at(b, 0);
    let mode = match u32_at(b, 4) {
        0 => GeoSelectionMode::Replace,
        1 => GeoSelectionMode::Add,
        2 => GeoSelectionMode::Toggle,
        _ => return Err(invalid()),
    };
    zero(&b[12..16])?;
    for at in [32, 40, 48, 56] {
        finite(b, at)?;
    }
    if op != 5 {
        zero(&b[8..12])?;
    }
    if ![2, 3, 7].contains(&op) {
        zero(&b[4..8])?;
    }
    if ![6, 7].contains(&op) {
        zero(&b[16..32])?;
    }
    if ![1, 2, 3].contains(&op) {
        zero(&b[32..64])?;
    }
    if op == 1 || op == 2 {
        zero(&b[48..64])?;
    }
    let key = GeoFeatureKey {
        layer_id: u64_at(b, 16),
        feature_id: u64_at(b, 24),
    };
    Ok(match op {
        1 => GeoInteractionEvent::Hover {
            x: f64_at(b, 32),
            y: f64_at(b, 40),
        },
        2 => GeoInteractionEvent::SelectAt {
            x: f64_at(b, 32),
            y: f64_at(b, 40),
            mode,
        },
        3 => GeoInteractionEvent::Brush {
            bounds: [f64_at(b, 32), f64_at(b, 40), f64_at(b, 48), f64_at(b, 56)],
            mode,
        },
        4 => GeoInteractionEvent::Clear,
        5 => GeoInteractionEvent::FocusStep {
            delta: i32::from_le_bytes(b[8..12].try_into().unwrap()),
        },
        6 => GeoInteractionEvent::FocusFeature { key },
        7 => GeoInteractionEvent::SelectFeature { key, mode },
        _ => return Err(invalid()),
    })
}

/// Parse the complete framing and its conservative peak before allocating source/option planes.
pub fn execute(bytes: &[u8], budget: usize) -> Result<Vec<u8>, GeoError> {
    execute_with_compiler(bytes, budget, &mut compile)
}

/// One framing/options policy serves ordinary catalogs and geographic tile
/// composition. The callback returns the same ordinary compiled catalog.
/// A normalization retry drops its previous compiled result before calling it.
#[inline(never)]
pub(crate) fn execute_with_compiler(
    bytes: &[u8],
    budget: usize,
    compiler: &mut dyn FnMut(&GeoCatalog<'_>) -> Result<GeoCompiled, GeoError>,
) -> Result<Vec<u8>, GeoError> {
    if budget > MAX_PROTOCOL_BYTES || bytes.len() > budget || budget < 65536 {
        return Err(GeoError::ResourceLimit);
    }
    if bytes.len() < HEADER_BYTES || &bytes[..4] != b"XYLK" || u32_at(bytes, 4) != 1 {
        return Err(invalid());
    }
    let layers = u32_at(bytes, 8) as usize;
    let flags = u32_at(bytes, 12);
    if layers > MAX_GEO_LAYERS {
        return Err(GeoError::ResourceLimit);
    }
    if flags & !3 != 0 || u32_at(bytes, 20) > 1 {
        return Err(invalid());
    }
    zero(&bytes[96..128])?;
    let viewport = GeoViewport::new(
        GeoCrs::from_u32(u32_at(bytes, 16)).ok_or(GeoError::UnsupportedCrs)?,
        finite(bytes, 24)?,
        finite(bytes, 32)?,
        finite(bytes, 40)?,
        finite(bytes, 48)?,
        finite(bytes, 56)?,
        finite(bytes, 64)?,
        finite(bytes, 72)?,
        u32_at(bytes, 20) == 1,
    )?;
    let legend_location = location(u32_at(bytes, 80))?;
    let title_len = u32_at(bytes, 84) as usize;
    let legend_font = finite(bytes, 88)?;
    if flags & 1 == 0 {
        zero(&bytes[80..96])?
    }
    if title_len > 8192 {
        return Err(GeoError::ResourceLimit);
    }
    let mut cursor = HEADER_BYTES;
    let title = text(take(bytes, &mut cursor, title_len)?)?;
    let interaction_event = if flags & 2 != 0 {
        Some(event(take(bytes, &mut cursor, 64)?)?)
    } else {
        None
    };
    let reserve = add(mul(bytes.len(), 3)?, 32768)?;
    let compiler_budget = budget.checked_sub(reserve).ok_or(GeoError::ResourceLimit)?
        / if interaction_event.is_some() { 4 } else { 2 };
    let mut base = 32768usize;
    let mut working = 0usize;
    let mut frames = Vec::with_capacity(layers);
    for _ in 0..layers {
        let h = take(bytes, &mut cursor, LAYER_BYTES)?;
        let k = kind(u32_at(h, 8))?;
        let f = u32_at(h, 12);
        if f & !255 != 0 {
            return Err(invalid());
        }
        zero(&h[260..264])?;
        zero(&h[328..384])?;
        patch(&h[16..64])?;
        for (i, bit) in [32, 64, 128].into_iter().enumerate() {
            let p = &h[64 + i * 48..112 + i * 48];
            patch(p)?;
            if f & bit == 0 {
                zero(p)?
            }
        }
        for at in [208, 216, 224, 232, 240] {
            finite(h, at)?;
        }
        for (bit, range) in [(1, 208..224), (2, 224..240), (4, 240..252), (8, 252..260)] {
            if f & bit == 0 {
                zero(&h[range])?
            }
        }
        let lens = [
            count(h, 264)?,
            count(h, 272)?,
            count(h, 280)?,
            count(h, 288)?,
            count(h, 296)?,
            count(h, 304)?,
            count(h, 312)?,
            count(h, 320)?,
        ];
        if lens[0] < 64 || lens[3] > 256 || lens[5] > 128 || lens[6] > 8192 || lens[7] > 8192 {
            return Err(if lens[0] < 64 {
                invalid()
            } else {
                GeoError::ResourceLimit
            });
        }
        if f & 16 == 0 && lens[6] != 0 {
            return Err(invalid());
        }
        let descriptor = take(bytes, &mut cursor, lens[0])?;
        let patches = take(bytes, &mut cursor, mul(lens[1], 48)?)?;
        let values = take(bytes, &mut cursor, mul(lens[2], 8)?)?;
        let stops = take(bytes, &mut cursor, mul(lens[3], 3)?)?;
        let state = take(bytes, &mut cursor, lens[4])?;
        let labels = take(bytes, &mut cursor, mul(lens[5], 48)?)?;
        let legend = take(bytes, &mut cursor, lens[6])?;
        let label_text = take(bytes, &mut cursor, lens[7])?;
        let (n, vertices) = descriptor_frame(descriptor)?;
        for len in [lens[1], lens[2], lens[4]] {
            if len != 0 && len != n {
                return Err(invalid());
            }
        }
        for p in patches.chunks_exact(48) {
            patch(p)?;
        }
        if state.iter().any(|v| v & !15 != 0) {
            return Err(invalid());
        }
        text(legend)?;
        text(label_text)?;
        for label in labels.chunks_exact(48) {
            if u32_at(label, 0) as usize >= n || u32_at(label, 4) > 2 {
                return Err(invalid());
            }
            for at in [8, 16, 24] {
                finite(label, at)?;
            }
            zero(&label[36..40])?;
            let start = u32_at(label, 40) as usize;
            let end = add(start, u32_at(label, 44) as usize)?;
            text(label_text.get(start..end).ok_or_else(invalid)?)?;
        }
        base = add(base, mul(n, 64)?)?;
        base = add(base, mul(add(lens[6], lens[7])?, 4)?)?;
        let scratch = match k {
            GeoLayerKind::Polygons | GeoLayerKind::Choropleth => {
                add(mul(vertices, 4096)?, 65536 * 128)?
            }
            GeoLayerKind::Arcs => {
                let steps = if f & 4 != 0 {
                    u32_at(h, 248)
                } else {
                    crate::geom::BEZIER_STEPS as u32
                };
                if steps > MAX_GEO_ARC_STEPS {
                    return Err(GeoError::ResourceLimit);
                }
                mul(mul(vertices, steps as usize + 1)?, 256)?
            }
            _ => mul(vertices, 256)?,
        };
        working = working.max(scratch);
        if k == GeoLayerKind::Density {
            let (cols, rows) = if f & 8 != 0 {
                (u32_at(h, 252), u32_at(h, 256))
            } else {
                (512, 384)
            };
            let cells = mul(cols as usize, rows as usize)?;
            if cells == 0
                || cols > 4096
                || rows > 4096
                || cells > crate::scene::MAX_SCENE_IMAGE_PIXELS
            {
                return Err(GeoError::ResourceLimit);
            }
            base = add(base, add(mul(cells, 128)?, mul(vertices, 64)?)?)?;
        }
        frames.push(Frame {
            header: h,
            descriptor,
            patches,
            values,
            stops,
            state,
            labels,
            legend,
            label_text,
        });
    }
    if cursor != bytes.len() {
        return Err(invalid());
    }
    if add(base, working)? > compiler_budget {
        return Err(GeoError::ResourceLimit);
    }
    let mut sources = Vec::with_capacity(layers);
    let mut options = Vec::with_capacity(layers);
    for frame in &frames {
        sources.push(column_from_descriptor_bytes(
            frame.descriptor,
            compiler_budget,
        )?);
        let patches = frame
            .patches
            .chunks_exact(48)
            .map(patch)
            .collect::<Result<Vec<_>, _>>()?;
        let values = frame.values.chunks_exact(8).map(|v| f64_at(v, 0)).collect();
        let stops = frame
            .stops
            .chunks_exact(3)
            .map(|v| v.try_into().unwrap())
            .collect();
        let mut labels = Vec::with_capacity(frame.labels.len() / 48);
        for l in frame.labels.chunks_exact(48) {
            let start = u32_at(l, 40) as usize;
            let end = start + u32_at(l, 44) as usize;
            labels.push(GeoLabel {
                feature_index: u32_at(l, 0),
                anchor: u32_at(l, 4) as u8,
                font_size: f64_at(l, 8),
                coordinate: [f64_at(l, 16), f64_at(l, 24)],
                rgba: l[32..36].try_into().unwrap(),
                text: text(&frame.label_text[start..end])?,
            });
        }
        options.push(Options {
            patches,
            values,
            stops,
            labels,
        });
    }
    let mut inputs = Vec::with_capacity(layers);
    for (i, frame) in frames.iter().enumerate() {
        let h = frame.header;
        let f = u32_at(h, 12);
        let opt = &options[i];
        let mut input = GeoLayer::new(u64_at(h, 0), kind(u32_at(h, 8))?, &sources[i]);
        apply(patch(&h[16..64])?, &mut input.style);
        if f & 32 != 0 {
            input.state_styles.selected = patch(&h[64..112])?
        }
        if f & 64 != 0 {
            input.state_styles.hovered = patch(&h[112..160])?
        }
        if f & 128 != 0 {
            input.state_styles.focused = patch(&h[160..208])?
        }
        input.feature_styles = &opt.patches;
        input.values = &opt.values;
        input.color_stops = &opt.stops;
        input.state_flags = frame.state;
        input.labels = &opt.labels;
        input.legend_label = if f & 16 != 0 {
            Some(text(frame.legend)?)
        } else {
            None
        };
        if f & 1 != 0 {
            input.value_domain = Some([f64_at(h, 208), f64_at(h, 216)])
        }
        if f & 2 != 0 {
            input.bubble_diameters = [f64_at(h, 224), f64_at(h, 232)]
        }
        if f & 4 != 0 {
            input.arc = GeoArcOptions {
                bend: f64_at(h, 240),
                steps: u32_at(h, 248),
            }
        }
        if f & 8 != 0 {
            input.density = GeoDensityOptions {
                columns: u32_at(h, 252),
                rows: u32_at(h, 256),
            }
        }
        inputs.push(input);
    }
    let legend = if flags & 1 != 0 {
        Some(GeoLegend {
            title,
            location: legend_location,
            font_size: legend_font,
        })
    } else {
        None
    };
    let baseline = compiler(&GeoCatalog {
        viewport,
        layers: &inputs,
        legend,
        budget: compiler_budget,
    })?;
    let interaction = if let Some(event) = interaction_event {
        let index = GeoPickIndex::new(&baseline, compiler_budget)?;
        Some(index.apply(&index.initial_state(), event)?)
    } else {
        Some(GeoInteractionResult {
            state: GeoInteractionState::from_compiled(&baseline)?,
            hits: Vec::new(),
        })
    };
    let normalized = interaction.as_ref().is_some_and(|i| {
        i.state
            .layer_flags
            .iter()
            .zip(&baseline.layers)
            .any(|(flags, layer)| flags != &layer.state_flags)
    });
    let result = if normalized {
        let i = interaction.as_ref().unwrap();
        drop(baseline);
        for (layer, flags) in inputs.iter_mut().zip(&i.state.layer_flags) {
            layer.state_flags = flags;
        }
        compiler(&GeoCatalog {
            viewport,
            layers: &inputs,
            legend,
            budget: compiler_budget,
        })?
    } else {
        baseline
    };
    encode(
        result,
        interaction,
        budget
            .checked_sub(reserve)
            .and_then(|n| {
                n.checked_sub(if interaction_event.is_some() {
                    compiler_budget
                } else {
                    0
                })
            })
            .ok_or(GeoError::ResourceLimit)?,
    )
}
fn append<T: Copy, const N: usize>(out: &mut Vec<u8>, values: &[T], f: fn(T) -> [u8; N]) {
    for &v in values {
        out.extend_from_slice(&f(v))
    }
    while out.len() % 8 != 0 {
        out.push(0)
    }
}
/// Allocation-free encoded-size admission shared with immutable tile receipts.
pub(crate) fn encoded_size(
    result: &GeoCompiled,
    interaction: Option<&GeoInteractionResult>,
) -> Result<usize, GeoError> {
    let mut length = add(128, add(result.scene.len(), 7)? & !7)?;
    length = add(length, add(mul(result.style_owners.len(), 4)?, 7)? & !7)?;
    for l in &result.layers {
        length = add(length, 128)?;
        for (count, size) in [
            (l.feature_ids.len(), 8),
            (l.validity.len(), 1),
            (l.state_flags.len(), 1),
            (l.visible_feature_indices.len(), 4),
        ] {
            length = add(length, add(mul(count, size)?, 7)? & !7)?
        }
        if let Some(d) = &l.density {
            for p in [&d.counts, &d.offsets, &d.feature_indices] {
                length = add(length, add(mul(p.len(), 4)?, 7)? & !7)?
            }
        }
    }
    if let Some(i) = interaction {
        for hit in &i.hits {
            length = add(
                length,
                add(24, add(mul(hit.feature_indices.len(), 4)?, 7)? & !7)?,
            )?;
        }
    }
    Ok(length)
}

fn encode(
    result: GeoCompiled,
    mut interaction: Option<GeoInteractionResult>,
    budget: usize,
) -> Result<Vec<u8>, GeoError> {
    // Input state has already been rebuilt into result metadata/Scene. Release
    // normalization clones before admitting the encoded output allocation.
    if let Some(i) = &mut interaction {
        i.state.layer_flags = Vec::new();
    }
    let length = encoded_size(&result, interaction.as_ref())?;
    if mul(length, 2)? > budget {
        return Err(GeoError::ResourceLimit);
    }
    let mut out = Vec::with_capacity(length);
    out.resize(128, 0);
    out[..4].copy_from_slice(b"XYLM");
    out[4..8].copy_from_slice(&1u32.to_le_bytes());
    let c = result.camera;
    out[8..12].copy_from_slice(&(c.crs as u32).to_le_bytes());
    out[12..16].copy_from_slice(&u32::from(c.world_wrap).to_le_bytes());
    for (i, v) in [
        c.center_x_bits,
        c.center_y_bits,
        c.zoom_bits,
        c.width_bits,
        c.height_bits,
        c.bearing_deg_bits,
        c.pitch_deg_bits,
    ]
    .into_iter()
    .enumerate()
    {
        out[16 + i * 8..24 + i * 8].copy_from_slice(&v.to_le_bytes());
    }
    for (at, n) in [
        (72, result.scene.len()),
        (80, result.layers.len()),
        (88, result.style_owners.len()),
    ] {
        out[at..at + 8].copy_from_slice(&(n as u64).to_le_bytes());
    }
    if let Some(i) = &interaction {
        if let Some(k) = i.state.focus {
            out[96..100].copy_from_slice(&1u32.to_le_bytes());
            out[104..112].copy_from_slice(&k.layer_id.to_le_bytes());
            out[112..120].copy_from_slice(&k.feature_id.to_le_bytes());
        }
        out[120..128].copy_from_slice(&(i.hits.len() as u64).to_le_bytes());
    }
    append(&mut out, &result.scene, u8::to_le_bytes);
    for owner in result.style_owners {
        out.extend_from_slice(&owner.unwrap_or(u32::MAX).to_le_bytes())
    }
    while out.len() % 8 != 0 {
        out.push(0)
    }
    for l in result.layers {
        let mut h = [0u8; 128];
        h[..8].copy_from_slice(&l.layer_id.to_le_bytes());
        h[8..12].copy_from_slice(&(l.kind as u32).to_le_bytes());
        let flags = u32::from(l.visible_bounds.is_some()) | (u32::from(l.density.is_some()) * 2);
        h[12..16].copy_from_slice(&flags.to_le_bytes());
        h[16..24].copy_from_slice(&l.source_digest);
        h[24..32].copy_from_slice(&(l.feature_ids.len() as u64).to_le_bytes());
        h[32..40].copy_from_slice(&(l.visible_feature_indices.len() as u64).to_le_bytes());
        h[64..68].copy_from_slice(&l.dropped_channels.to_le_bytes());
        if let Some(bounds) = l.visible_bounds {
            for (i, v) in bounds.into_iter().enumerate() {
                h[72 + i * 8..80 + i * 8].copy_from_slice(&v.to_le_bytes())
            }
        }
        if let Some(d) = &l.density {
            h[40..44].copy_from_slice(&d.columns.to_le_bytes());
            h[44..48].copy_from_slice(&d.rows.to_le_bytes());
            h[48..56].copy_from_slice(&(d.counts.len() as u64).to_le_bytes());
            h[56..64].copy_from_slice(&(d.feature_indices.len() as u64).to_le_bytes());
        }
        out.extend_from_slice(&h);
        append(&mut out, &l.feature_ids, u64::to_le_bytes);
        append(&mut out, &l.validity, u8::to_le_bytes);
        append(&mut out, &l.state_flags, u8::to_le_bytes);
        append(&mut out, &l.visible_feature_indices, u32::to_le_bytes);
        if let Some(d) = l.density {
            append(&mut out, &d.counts, u32::to_le_bytes);
            append(&mut out, &d.offsets, u32::to_le_bytes);
            append(&mut out, &d.feature_indices, u32::to_le_bytes);
        }
    }
    if let Some(i) = interaction {
        for hit in i.hits {
            out.extend_from_slice(&hit.key.layer_id.to_le_bytes());
            out.extend_from_slice(&hit.key.feature_id.to_le_bytes());
            out.extend_from_slice(&(hit.feature_indices.len() as u64).to_le_bytes());
            append(&mut out, &hit.feature_indices, u32::to_le_bytes);
        }
    }
    debug_assert_eq!(out.len(), length);
    Ok(out)
}

#[cfg(test)]
mod tests {
    use super::*;
    fn request() -> Vec<u8> {
        let mut d = vec![0u8; 96];
        d[..4].copy_from_slice(b"XYGD");
        for (at, n) in [(4, 1u32), (8, 1), (12, 4326), (16, 1)] {
            d[at..at + 4].copy_from_slice(&n.to_le_bytes());
        }
        for at in [24, 32] {
            d[at..at + 8].copy_from_slice(&1u64.to_le_bytes());
        }
        d[80] = 1;
        d[88..96].copy_from_slice(&u64::MAX.to_le_bytes());
        let mut r = vec![0u8; 128 + 384];
        r[..4].copy_from_slice(b"XYLK");
        for (at, n) in [(4, 1u32), (8, 1), (16, 4326)] {
            r[at..at + 4].copy_from_slice(&n.to_le_bytes());
        }
        for (at, n) in [(48, 800f64), (56, 600f64)] {
            r[at..at + 8].copy_from_slice(&n.to_le_bytes());
        }
        r[128..136].copy_from_slice(&u64::MAX.to_le_bytes());
        r[136..140].copy_from_slice(&1u32.to_le_bytes());
        r[392..400].copy_from_slice(&(d.len() as u64).to_le_bytes());
        r.extend_from_slice(&d);
        r
    }
    fn event_request(op: u32) -> Vec<u8> {
        let mut r = request();
        r[12..16].copy_from_slice(&2u32.to_le_bytes());
        let mut e = [0u8; 64];
        e[..4].copy_from_slice(&op.to_le_bytes());
        if op == 1 || op == 2 {
            e[32..40].copy_from_slice(&400f64.to_le_bytes());
            e[40..48].copy_from_slice(&300f64.to_le_bytes());
        }
        if op == 6 || op == 7 {
            e[16..24].copy_from_slice(&u64::MAX.to_le_bytes());
            e[24..32].copy_from_slice(&u64::MAX.to_le_bytes());
        }
        r.splice(128..128, e);
        r
    }
    #[test]
    fn events_lower_full_u64_hits_and_focus() {
        for op in [1, 2, 6, 7] {
            let out = execute(&event_request(op), 64 << 20).unwrap();
            assert_eq!(u64_at(&out, 120), 1);
            let at = out.len() - 32;
            assert_eq!(u64_at(&out, at), u64::MAX);
            assert_eq!(u64_at(&out, at + 8), u64::MAX);
            assert_eq!(u64_at(&out, at + 16), 1);
            assert_eq!(u32_at(&out, at + 24), 0);
            if op == 6 {
                assert_eq!(u32_at(&out, 96), 1);
                assert_eq!(u64_at(&out, 104), u64::MAX);
                assert_eq!(u64_at(&out, 112), u64::MAX);
            }
        }
    }
    #[test]
    fn compile_only_focus_normalization_rebuilds_consistent_scene() {
        let mut r = request();
        let at = 128;
        r[at + 296..at + 304].copy_from_slice(&1u64.to_le_bytes());
        r.extend_from_slice(&[8, 0, 0, 0, 0, 0, 0, 0]);
        let out = execute(&r, 64 << 20).unwrap();
        assert_eq!(u32_at(&out, 96), 1);
        assert_eq!(u64_at(&out, 104), u64::MAX);
        assert_eq!(u64_at(&out, 112), u64::MAX);
        assert_eq!(u64_at(&out, 120), 0);
    }
    #[test]
    fn malformed_event_is_atomic() {
        let mut r = event_request(6);
        r[128 + 32] = 1;
        assert_eq!(execute(&r, 64 << 20), Err(GeoError::InvalidArgument));
        let mut r = event_request(2);
        r[132..136].copy_from_slice(&3u32.to_le_bytes());
        assert_eq!(execute(&r, 64 << 20), Err(GeoError::InvalidArgument));
        let mut r = event_request(6);
        r[144..152].copy_from_slice(&5u64.to_le_bytes());
        assert_eq!(execute(&r, 64 << 20), Err(GeoError::InvalidArgument));
    }
    #[test]
    fn full_u64_scene_and_metadata() {
        let r = request();
        let out = execute(&r, 64 << 20).unwrap();
        assert_eq!(&out[..4], b"XYLM");
        assert_eq!(u64_at(&out, 80), 1);
        let scene = u64_at(&out, 72) as usize;
        assert_eq!(&out[128..132], b"XYGS");
        let owners = u64_at(&out, 88) as usize;
        let at = 128 + ((scene + 7) & !7) + ((owners * 4 + 7) & !7);
        assert_eq!(u64_at(&out, at), u64::MAX);
        assert_eq!(u64_at(&out, at + 128), u64::MAX);
        assert_eq!(out[at + 136], 1);
        assert_eq!(u64_at(&out, at + 32), 1);
    }
    #[test]
    fn framing_is_fail_closed() {
        let r = request();
        for at in [96, 128 + 328, 128 + 16 + 40, 512 + 20, 512 + 81] {
            let mut bad = r.clone();
            bad[at] = 1;
            assert_eq!(execute(&bad, 64 << 20), Err(GeoError::InvalidArgument));
        }
        let mut trailing = r.clone();
        trailing.push(0);
        assert_eq!(execute(&trailing, 64 << 20), Err(GeoError::InvalidArgument));
        let mut huge = r.clone();
        huge[392..400].copy_from_slice(&u64::MAX.to_le_bytes());
        assert_eq!(execute(&huge, 64 << 20), Err(GeoError::ResourceLimit));
    }
    #[test]
    fn presence_masks_and_peak_are_bounded() {
        let r = request();
        let mut bad = r.clone();
        bad[144..148].copy_from_slice(&64u32.to_le_bytes());
        assert_eq!(execute(&bad, 64 << 20), Err(GeoError::InvalidArgument));
        let mut bad = r.clone();
        bad[152] = 255;
        assert_eq!(execute(&bad, 64 << 20), Err(GeoError::InvalidArgument));
        assert_eq!(execute(&r, 65536), Err(GeoError::ResourceLimit));
        let mut bad = r;
        bad[8..12].copy_from_slice(&65u32.to_le_bytes());
        assert_eq!(execute(&bad, 64 << 20), Err(GeoError::ResourceLimit));
    }
}
