//! Rust-owned graph label acceptance, visual-state precedence, and compound bounds (#34).

pub const STATE_NORMAL: u8 = 0;
pub const STATE_AGGREGATE: u8 = 1;
pub const STATE_PINNED: u8 = 2;
pub const STATE_NEIGHBOR: u8 = 3;
pub const STATE_HOVERED: u8 = 4;
pub const STATE_SELECTED: u8 = 5;
pub const STATE_FILTERED: u8 = 6;
pub const STATE_DISABLED: u8 = 7;
pub const FLAG_HOVERED: u32 = 1 << 0;
pub const FLAG_SELECTED: u32 = 1 << 1;
pub const FLAG_NEIGHBOR: u32 = 1 << 2;
pub const FLAG_FILTERED: u32 = 1 << 3;
pub const FLAG_PINNED: u32 = 1 << 4;
pub const FLAG_AGGREGATE: u32 = 1 << 5;
pub const FLAG_DISABLED: u32 = 1 << 6;
pub const KNOWN_STATE_FLAGS: u32 = (1 << 7) - 1;
pub const NO_COMPOUND: u64 = u64::MAX;
pub const RESOLVED_STYLE_VERSION: u32 = 1;
pub const MAX_SEMANTIC_CODE: u8 = 7;
pub const THEME_LIGHT: u8 = 0;
pub const THEME_DARK: u8 = 1;

/// Complete painter-facing graph style. Hosts may customize the semantic input
/// mapping, but never reinterpret these resolved values.
#[derive(Clone, Copy, Debug, PartialEq)]
pub struct ResolvedGraphStyle {
    pub fill: [u8; 4],
    pub stroke: [u8; 4],
    pub halo: [u8; 4],
    pub size: f32,
    pub width: f32,
    pub opacity: f32,
    pub shape: u8,
    pub dash: u8,
    pub arrow: u8,
    pub state: u8,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct GraphLegendEntry {
    pub field: u8,
    pub value: u8,
    pub color: [u8; 4],
    pub shape: u8,
}

// Color-blind-safe, light/dark-background-tested semantic colors. Code zero is
// deliberately neutral; unknown codes fail closed rather than being modulo-mapped.
const LIGHT_PALETTE: [[u8; 4]; 8] = [
    [75, 85, 99, 255],
    [0, 90, 156, 255],
    [156, 74, 0, 255],
    [0, 107, 79, 255],
    [122, 62, 107, 255],
    [0, 109, 131, 255],
    [155, 44, 0, 255],
    [112, 92, 0, 255],
];
const DARK_PALETTE: [[u8; 4]; 8] = [
    [170, 178, 191, 255],
    [86, 180, 233, 255],
    [230, 159, 0, 255],
    [0, 184, 135, 255],
    [204, 121, 167, 255],
    [125, 211, 252, 255],
    [240, 120, 69, 255],
    [240, 228, 66, 255],
];

fn palette(theme: u8) -> Option<&'static [[u8; 4]; 8]> {
    match theme {
        THEME_LIGHT => Some(&LIGHT_PALETTE),
        THEME_DARK => Some(&DARK_PALETTE),
        _ => None,
    }
}

fn metric_domain(metric: &[f64]) -> (f64, f64) {
    let mut lo = f64::INFINITY;
    let mut hi = f64::NEG_INFINITY;
    for value in metric.iter().copied().filter(|v| v.is_finite()) {
        lo = lo.min(value);
        hi = hi.max(value);
    }
    if !lo.is_finite() {
        (0.0, 0.0)
    } else {
        (lo, hi)
    }
}

fn metric_unit(value: f64, domain: (f64, f64)) -> f32 {
    if !value.is_finite() || domain.0 == domain.1 {
        0.5
    } else {
        // Scaling first avoids `hi - lo == inf` for opposite-sign finite
        // extrema while retaining a finite, monotonic unit coordinate.
        let scale = domain.0.abs().max(domain.1.abs()).max(value.abs());
        let unit =
            ((value / scale) - (domain.0 / scale)) / ((domain.1 / scale) - (domain.0 / scale));
        if unit.is_finite() {
            unit.clamp(0.0, 1.0) as f32
        } else {
            0.5
        }
    }
}

/// Resolve canonical GraphForge class/epistemic/status/metric fields to paint.
/// Input vocabularies are closed (0..=7), outputs are all-or-nothing, and the
/// same routine serves nodes and edges (`edge=true`).
pub fn resolve_semantic_styles(
    classes: &[u8],
    epistemic: &[u8],
    statuses: &[u8],
    metric: &[f64],
    flags: &[u32],
    edge: bool,
    theme: u8,
    out: &mut [ResolvedGraphStyle],
) -> Option<(f64, f64)> {
    let n = classes.len();
    if [
        epistemic.len(),
        statuses.len(),
        metric.len(),
        flags.len(),
        out.len(),
    ]
    .iter()
    .any(|&len| len != n)
        || classes
            .iter()
            .chain(epistemic)
            .chain(statuses)
            .any(|&v| v > MAX_SEMANTIC_CODE)
        || flags.iter().any(|&value| value & !KNOWN_STATE_FLAGS != 0)
    {
        return None;
    }
    let colors = palette(theme)?;
    let domain = metric_domain(metric);
    let mut resolved = Vec::with_capacity(n);
    for i in 0..n {
        let state = resolve_visual_state(flags[i]);
        let unit = metric_unit(metric[i], domain);
        let mut fill = colors[classes[i] as usize];
        let mut stroke = colors[statuses[i] as usize];
        let halo = colors[epistemic[i] as usize];
        // Active semantic paint is opaque so its measured non-text contrast is
        // preserved after composition. Filtered/disabled are intentional
        // inactive-state exemptions below.
        let mut opacity = 1.0;
        let mut width = if edge {
            0.75 + 3.25 * unit
        } else {
            1.0 + 1.5 * unit
        };
        if state == STATE_SELECTED {
            stroke = if theme == THEME_LIGHT {
                [0, 0, 0, 255]
            } else {
                [255, 255, 255, 255]
            };
            width += 2.5;
        }
        if state == STATE_HOVERED {
            width += 1.25;
        }
        if state == STATE_NEIGHBOR {
            width += 0.5;
        }
        if state == STATE_PINNED {
            width += 1.75;
        }
        if state == STATE_AGGREGATE {
            width += 0.75;
        }
        if state == STATE_FILTERED {
            opacity = 0.08;
        }
        if state == STATE_DISABLED {
            opacity = 0.28;
            fill = colors[0];
        }
        resolved.push(ResolvedGraphStyle {
            fill,
            stroke,
            halo,
            size: if edge { 0.0 } else { 7.0 + 13.0 * unit },
            width,
            opacity,
            shape: if edge {
                0
            } else if state == STATE_AGGREGATE {
                5
            } else {
                classes[i] % 6
            },
            dash: if edge {
                if state == STATE_PINNED {
                    3
                } else if state == STATE_AGGREGATE {
                    2
                } else {
                    epistemic[i] % 4
                }
            } else {
                0
            },
            arrow: u8::from(edge && statuses[i] != 0),
            state,
        });
    }
    out.copy_from_slice(&resolved);
    Some(domain)
}

/// Deterministic, de-duplicated legend descriptors ordered field then code.
pub fn semantic_legend(
    classes: &[u8],
    epistemic: &[u8],
    statuses: &[u8],
    theme: u8,
) -> Option<Vec<GraphLegendEntry>> {
    if classes
        .iter()
        .chain(epistemic)
        .chain(statuses)
        .any(|&v| v > MAX_SEMANTIC_CODE)
    {
        return None;
    }
    let colors = palette(theme)?;
    let mut entries = Vec::new();
    for (field, values) in [(0, classes), (1, epistemic), (2, statuses)] {
        let mut seen = [false; 8];
        for &value in values {
            seen[value as usize] = true;
        }
        for (value, present) in seen.into_iter().enumerate() {
            if present {
                entries.push(GraphLegendEntry {
                    field,
                    value: value as u8,
                    color: colors[value],
                    shape: if field == 0 { value as u8 % 6 } else { 0 },
                });
            }
        }
    }
    Some(entries)
}

#[must_use]
pub fn resolve_visual_state(flags: u32) -> u8 {
    if flags & FLAG_DISABLED != 0 {
        STATE_DISABLED
    } else if flags & FLAG_FILTERED != 0 {
        STATE_FILTERED
    } else if flags & FLAG_SELECTED != 0 {
        STATE_SELECTED
    } else if flags & FLAG_HOVERED != 0 {
        STATE_HOVERED
    } else if flags & FLAG_NEIGHBOR != 0 {
        STATE_NEIGHBOR
    } else if flags & FLAG_PINNED != 0 {
        STATE_PINNED
    } else if flags & FLAG_AGGREGATE != 0 {
        STATE_AGGREGATE
    } else {
        STATE_NORMAL
    }
}

pub fn resolve_visual_states(flags: &[u32], out: &mut [u8]) -> Option<()> {
    if flags.len() != out.len() {
        return None;
    }
    for (flag, state) in flags.iter().zip(out.iter_mut()) {
        *state = resolve_visual_state(*flag);
    }
    Some(())
}

pub fn label_accept(priorities: &[f64], budget: u64, floor: f64, out: &mut [u8]) -> Option<u64> {
    if priorities.len() != out.len() {
        return None;
    }
    out.fill(0);
    let mut ranked: Vec<(usize, f64)> = priorities
        .iter()
        .copied()
        .enumerate()
        .filter(|(_, p)| p.is_finite() && (!floor.is_finite() || *p >= floor))
        .collect();
    ranked.sort_by(|a, b| b.1.total_cmp(&a.1).then_with(|| a.0.cmp(&b.0)));
    let take = usize::try_from(budget)
        .unwrap_or(usize::MAX)
        .min(ranked.len());
    for &(index, _) in ranked.iter().take(take) {
        out[index] = 1;
    }
    Some(take as u64)
}

#[allow(clippy::too_many_arguments)]
pub fn compound_bounds(
    x: &[f64],
    y: &[f64],
    parents: &[u64],
    validity: &[u8],
    parent_of: &mut [u64],
    is_compound: &mut [u8],
    xmin: &mut [f64],
    xmax: &mut [f64],
    ymin: &mut [f64],
    ymax: &mut [f64],
) -> Option<()> {
    let n = x.len();
    if [
        y.len(),
        parents.len(),
        validity.len(),
        parent_of.len(),
        is_compound.len(),
        xmin.len(),
        xmax.len(),
        ymin.len(),
        ymax.len(),
    ]
    .iter()
    .any(|&len| len != n)
    {
        return None;
    }
    // Validate the complete parent graph before writing any membership/bounds.
    // A compound cycle has no meaningful root and must fail atomically.
    let mut direct_parent = vec![None; n];
    for i in 0..n {
        if validity[i] == 0 {
            continue;
        }
        let parent = usize::try_from(parents[i]).ok().filter(|&p| p < n)?;
        if parent == i {
            return None;
        }
        direct_parent[i] = Some(parent);
    }
    let mut color = vec![0u8; n];
    for start in 0..n {
        let mut node = start;
        let mut path = Vec::new();
        let mut reached_root = false;
        while color[node] == 0 {
            color[node] = 1;
            path.push(node);
            let Some(parent) = direct_parent[node] else {
                reached_root = true;
                break;
            };
            node = parent;
        }
        if !reached_root && color[node] == 1 && path.contains(&node) {
            return None;
        }
        for visited in path {
            color[visited] = 2;
        }
    }
    parent_of.fill(NO_COMPOUND);
    is_compound.fill(0);
    xmin.fill(f64::NAN);
    xmax.fill(f64::NAN);
    ymin.fill(f64::NAN);
    ymax.fill(f64::NAN);
    let mut expand = |p: usize, px: f64, py: f64| {
        if !px.is_finite() || !py.is_finite() {
            return;
        }
        if xmin[p].is_nan() {
            xmin[p] = px;
            xmax[p] = px;
            ymin[p] = py;
            ymax[p] = py;
        } else {
            xmin[p] = xmin[p].min(px);
            xmax[p] = xmax[p].max(px);
            ymin[p] = ymin[p].min(py);
            ymax[p] = ymax[p].max(py);
        }
    };
    for i in 0..n {
        if validity[i] == 0 {
            continue;
        }
        let p = direct_parent[i]?;
        parent_of[i] = parents[i];
        is_compound[p] = 1;
        expand(p, x[i], y[i]);
    }
    for i in 0..n {
        if is_compound[i] != 0 {
            expand(i, x[i], y[i]);
        }
    }
    Some(())
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn precedence_is_stable() {
        assert_eq!(
            resolve_visual_state(FLAG_SELECTED | FLAG_DISABLED),
            STATE_DISABLED
        );
        assert_eq!(
            resolve_visual_state(FLAG_SELECTED | FLAG_HOVERED),
            STATE_SELECTED
        );
    }
    #[test]
    fn labels_are_deterministic() {
        let mut out = [0; 5];
        assert_eq!(
            label_accept(&[1., 5., 5., 3., f64::NAN], 2, f64::NAN, &mut out),
            Some(2)
        );
        assert_eq!(out, [0, 1, 1, 0, 0]);
    }
    #[test]
    fn compounds_include_parent_and_children() {
        let mut po = [0; 4];
        let mut ic = [0; 4];
        let mut xmin = [0.; 4];
        let mut xmax = [0.; 4];
        let mut ymin = [0.; 4];
        let mut ymax = [0.; 4];
        compound_bounds(
            &[0., -1., 2., 9.],
            &[0., 1., 3., 9.],
            &[0, 0, 0, 0],
            &[0, 1, 1, 0],
            &mut po,
            &mut ic,
            &mut xmin,
            &mut xmax,
            &mut ymin,
            &mut ymax,
        )
        .unwrap();
        assert_eq!(po, [NO_COMPOUND, 0, 0, NO_COMPOUND]);
        assert_eq!((xmin[0], xmax[0], ymin[0], ymax[0]), (-1., 2., 0., 3.));
    }
    #[test]
    fn compound_cycles_fail_before_writing_outputs() {
        let mut po = [11; 3];
        let mut ic = [12; 3];
        let mut xmin = [13.; 3];
        let mut xmax = [14.; 3];
        let mut ymin = [15.; 3];
        let mut ymax = [16.; 3];
        assert_eq!(
            compound_bounds(
                &[0.; 3],
                &[0.; 3],
                &[1, 2, 0],
                &[1; 3],
                &mut po,
                &mut ic,
                &mut xmin,
                &mut xmax,
                &mut ymin,
                &mut ymax
            ),
            None
        );
        assert_eq!(po, [11; 3]);
        assert_eq!(ic, [12; 3]);
        assert_eq!(xmin, [13.; 3]);
        assert_eq!(ymax, [16.; 3]);
    }

    #[test]
    fn semantic_style_golden_and_state_precedence_are_stable() {
        let mut out = [ResolvedGraphStyle {
            fill: [0; 4],
            stroke: [0; 4],
            halo: [0; 4],
            size: 0.0,
            width: 0.0,
            opacity: 0.0,
            shape: 0,
            dash: 0,
            arrow: 0,
            state: 0,
        }; 3];
        let domain = resolve_semantic_styles(
            &[1, 2, 3],
            &[2, 3, 4],
            &[1, 2, 3],
            &[10.0, 20.0, 30.0],
            &[0, FLAG_HOVERED | FLAG_SELECTED, FLAG_DISABLED],
            false,
            THEME_LIGHT,
            &mut out,
        )
        .unwrap();
        assert_eq!(domain, (10.0, 30.0));
        assert_eq!(out[0].fill, [0, 90, 156, 255]);
        assert_eq!((out[0].size, out[0].shape), (7.0, 1));
        assert_eq!(
            (out[1].state, out[1].stroke),
            (STATE_SELECTED, [0, 0, 0, 255])
        );
        assert_eq!((out[2].state, out[2].opacity), (STATE_DISABLED, 0.28));
    }

    #[test]
    fn edge_style_and_legend_are_deterministic() {
        let mut out = [ResolvedGraphStyle {
            fill: [0; 4],
            stroke: [0; 4],
            halo: [0; 4],
            size: 0.0,
            width: 0.0,
            opacity: 0.0,
            shape: 0,
            dash: 0,
            arrow: 0,
            state: 0,
        }; 2];
        resolve_semantic_styles(
            &[2, 2],
            &[3, 1],
            &[0, 4],
            &[f64::NAN, 8.0],
            &[0, 0],
            true,
            THEME_LIGHT,
            &mut out,
        )
        .unwrap();
        assert_eq!(out[0].size, 0.0);
        assert_eq!((out[0].dash, out[0].arrow), (3, 0));
        assert_eq!((out[1].dash, out[1].arrow), (1, 1));
        let legend = semantic_legend(&[2, 1, 2], &[3, 3, 1], &[4, 0, 4], THEME_LIGHT).unwrap();
        assert_eq!(
            legend
                .iter()
                .map(|e| (e.field, e.value))
                .collect::<Vec<_>>(),
            vec![(0, 1), (0, 2), (1, 1), (1, 3), (2, 0), (2, 4)]
        );
    }

    #[test]
    fn semantic_resolution_is_atomic_and_bounded() {
        let sentinel = ResolvedGraphStyle {
            fill: [9; 4],
            stroke: [9; 4],
            halo: [9; 4],
            size: 9.0,
            width: 9.0,
            opacity: 9.0,
            shape: 9,
            dash: 9,
            arrow: 9,
            state: 9,
        };
        let mut out = [sentinel];
        assert_eq!(
            resolve_semantic_styles(&[8], &[0], &[0], &[0.0], &[0], false, THEME_LIGHT, &mut out),
            None
        );
        assert_eq!(out, [sentinel]);
    }

    fn luminance(color: [u8; 4]) -> f64 {
        let linear = |byte: u8| {
            let c = f64::from(byte) / 255.0;
            if c <= 0.04045 {
                c / 12.92
            } else {
                ((c + 0.055) / 1.055).powf(2.4)
            }
        };
        0.2126 * linear(color[0]) + 0.7152 * linear(color[1]) + 0.0722 * linear(color[2])
    }

    fn contrast(a: [u8; 4], b: [u8; 4]) -> f64 {
        let (lo, hi) = {
            let x = luminance(a);
            let y = luminance(b);
            (x.min(y), x.max(y))
        };
        (hi + 0.05) / (lo + 0.05)
    }

    fn composite(color: [u8; 4], opacity: f32, background: [u8; 4]) -> [u8; 4] {
        let alpha = (f32::from(color[3]) / 255.0) * opacity;
        let channel = |index| {
            ((f32::from(color[index]) * alpha) + (f32::from(background[index]) * (1.0 - alpha)))
                .round() as u8
        };
        [channel(0), channel(1), channel(2), 255]
    }

    fn blank_style() -> ResolvedGraphStyle {
        ResolvedGraphStyle {
            fill: [0; 4],
            stroke: [0; 4],
            halo: [0; 4],
            size: 0.0,
            width: 0.0,
            opacity: 0.0,
            shape: 0,
            dash: 0,
            arrow: 0,
            state: 0,
        }
    }

    #[test]
    fn actual_active_styles_meet_non_text_contrast_in_both_themes() {
        let active = [
            0,
            FLAG_AGGREGATE,
            FLAG_PINNED,
            FLAG_NEIGHBOR,
            FLAG_HOVERED,
            FLAG_SELECTED,
        ];
        for (theme, background) in [
            (THEME_LIGHT, [255, 255, 255, 255]),
            (THEME_DARK, [17, 24, 39, 255]),
        ] {
            for edge in [false, true] {
                for code in 0..=MAX_SEMANTIC_CODE {
                    for flags in active {
                        let mut out = [blank_style()];
                        resolve_semantic_styles(
                            &[code],
                            &[code],
                            &[code],
                            &[1.0],
                            &[flags],
                            edge,
                            theme,
                            &mut out,
                        )
                        .unwrap();
                        for color in [out[0].fill, out[0].stroke, out[0].halo] {
                            let painted = composite(color, out[0].opacity, background);
                            assert!(contrast(painted, background) >= 3.0, "theme={theme} edge={edge} code={code} flags={flags} color={color:?}");
                        }
                    }
                }
            }
        }
    }

    #[test]
    fn inactive_states_are_explicit_contrast_exemptions() {
        for (flag, expected) in [(FLAG_FILTERED, 0.08), (FLAG_DISABLED, 0.28)] {
            let mut out = [blank_style()];
            resolve_semantic_styles(
                &[1],
                &[1],
                &[1],
                &[1.0],
                &[flag],
                false,
                THEME_LIGHT,
                &mut out,
            )
            .unwrap();
            assert_eq!(out[0].opacity, expected);
        }
    }

    #[test]
    fn every_winning_active_state_changes_node_and_edge_paint() {
        for edge in [false, true] {
            let mut styles = Vec::new();
            for flag in [
                0,
                FLAG_AGGREGATE,
                FLAG_PINNED,
                FLAG_NEIGHBOR,
                FLAG_HOVERED,
                FLAG_SELECTED,
            ] {
                let mut out = [blank_style()];
                resolve_semantic_styles(
                    &[1],
                    &[1],
                    &[1],
                    &[1.0],
                    &[flag],
                    edge,
                    THEME_LIGHT,
                    &mut out,
                )
                .unwrap();
                styles.push(out[0]);
            }
            for i in 0..styles.len() {
                for j in i + 1..styles.len() {
                    assert_ne!(styles[i], styles[j], "edge={edge} states {i}/{j}");
                }
            }
        }
    }

    #[test]
    fn unknown_interaction_bits_fail_atomically() {
        let sentinel = ResolvedGraphStyle {
            state: 99,
            ..blank_style()
        };
        let mut out = [sentinel];
        assert_eq!(
            resolve_semantic_styles(
                &[1],
                &[1],
                &[1],
                &[1.0],
                &[1 << 7],
                false,
                THEME_LIGHT,
                &mut out
            ),
            None
        );
        assert_eq!(out, [sentinel]);
    }

    #[test]
    fn extreme_finite_metric_domain_emits_only_finite_paint() {
        let blank = ResolvedGraphStyle {
            fill: [0; 4],
            stroke: [0; 4],
            halo: [0; 4],
            size: 0.0,
            width: 0.0,
            opacity: 0.0,
            shape: 0,
            dash: 0,
            arrow: 0,
            state: 0,
        };
        let mut out = [blank; 3];
        resolve_semantic_styles(
            &[1; 3],
            &[1; 3],
            &[1; 3],
            &[-f64::MAX, 0.0, f64::MAX],
            &[0; 3],
            false,
            THEME_DARK,
            &mut out,
        )
        .unwrap();
        assert!(out.iter().all(|style| style.size.is_finite()
            && style.width.is_finite()
            && style.opacity.is_finite()));
        assert_eq!(
            out.iter().map(|style| style.size).collect::<Vec<_>>(),
            vec![7.0, 13.5, 20.0]
        );
    }
}
