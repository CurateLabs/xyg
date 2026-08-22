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
pub const NO_COMPOUND: u64 = u64::MAX;

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
        let p = usize::try_from(parents[i]).ok().filter(|&p| p < n)?;
        if p == i {
            return None;
        }
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
}
