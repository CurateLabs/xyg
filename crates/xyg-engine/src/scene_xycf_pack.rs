//! Figure chrome XYCF v1 facts packing (M2 Push 3A, ABI 319).
//!
//! Hosts marshal title/labels, tick arrays, XYCH, legend/colorbar literals,
//! and collision extras. Rust owns the XYCF v1 header and concat order.

pub const SCENE_XYCF_PACK_MAX: usize = 1 << 20;

const XYCF_MAGIC: &[u8; 4] = b"XYCF";
const XYCF_VERSION: u32 = 1;
pub const XYCF_HEADER_BYTES: usize = 288;

/// Host-marshaled XYCF header scalars plus sidecar lengths.
#[derive(Clone, Copy, Debug)]
pub struct XycfPackHeader {
    pub flags: u32,
    pub collision_header: u32,
    pub width: f64,
    pub height: f64,
    pub margin_left: f64,
    pub margin_right: f64,
    pub margin_top: f64,
    pub margin_bottom: f64,
    pub pad_left: f64,
    pub pad_right: f64,
    pub pad_top: f64,
    pub pad_bottom: f64,
    pub x_scale_kind: u32,
    pub y_scale_kind: u32,
    pub x_lo: f64,
    pub x_hi: f64,
    pub x_constant: f64,
    pub y_lo: f64,
    pub y_hi: f64,
    pub y_constant: f64,
    pub x_nonpositive_mask: u8,
    pub y_nonpositive_mask: u8,
    pub tick_kinds: u16,
    pub title_len: u32,
    pub x_label_len: u32,
    pub y_label_len: u32,
    pub x_format_len: u32,
    pub y_format_len: u32,
    pub x_major_len: u32,
    pub x_minor_len: u32,
    pub y_major_len: u32,
    pub y_minor_len: u32,
    pub x_label_count: u32,
    pub y_label_count: u32,
    pub chrome_len: u32,
    pub legend_loc_len: u32,
    pub legend_title_len: u32,
    pub legend_ncols: u32,
    pub legend_font_size: f64,
    pub legend_title_font_size: f64,
    pub legend_flags: u32,
    pub legend_count: u32,
    pub legend_text_rgba: [u8; 4],
    pub legend_frame_rgba: [u8; 4],
    pub colorbar_obs: u32,
    pub colorbar_stop_count: u32,
    pub colorbar_tick_count: u32,
    pub colorbar_title_len: u32,
    pub colorbar_lo: f64,
    pub colorbar_hi: f64,
    pub colorbar_text_rgba: [u8; 4],
}

/// Variable-length XYCF sidecars in concat order.
#[derive(Clone, Copy, Debug)]
pub struct XycfPackSidecars<'a> {
    pub title: &'a [u8],
    pub x_label: &'a [u8],
    pub y_label: &'a [u8],
    pub x_format: &'a [u8],
    pub y_format: &'a [u8],
    pub x_major: &'a [f64],
    pub x_minor: &'a [f64],
    pub y_major: &'a [f64],
    pub y_minor: &'a [f64],
    pub x_labels_blob: &'a [u8],
    pub y_labels_blob: &'a [u8],
    pub chrome: &'a [u8],
    pub legend_loc: &'a [u8],
    pub legend_title: &'a [u8],
    pub legend_meta: &'a [u8],
    pub legend_lens: &'a [u32],
    pub legend_blob: &'a [u8],
    pub colorbar_stops_blob: &'a [u8],
    pub colorbar_ticks: &'a [f64],
    pub colorbar_title: &'a [u8],
    pub collision_extra: &'a [u8],
}

fn write_header_full(out: &mut [u8], header: &XycfPackHeader) -> Result<(), i32> {
    if out.len() < XYCF_HEADER_BYTES {
        return Err(-1);
    }
    out[..4].copy_from_slice(XYCF_MAGIC);
    out[4..8].copy_from_slice(&XYCF_VERSION.to_le_bytes());
    out[8..12].copy_from_slice(&header.flags.to_le_bytes());
    out[12..16].copy_from_slice(&header.collision_header.to_le_bytes());
    let scalars = [
        header.width,
        header.height,
        header.margin_left,
        header.margin_right,
        header.margin_top,
        header.margin_bottom,
        header.pad_left,
        header.pad_right,
        header.pad_top,
        header.pad_bottom,
    ];
    for (i, value) in scalars.iter().enumerate() {
        let at = 16 + i * 8;
        out[at..at + 8].copy_from_slice(&value.to_le_bytes());
    }
    out[96..100].copy_from_slice(&header.x_scale_kind.to_le_bytes());
    out[100..104].copy_from_slice(&header.y_scale_kind.to_le_bytes());
    let axis = [
        header.x_lo,
        header.x_hi,
        header.x_constant,
        header.y_lo,
        header.y_hi,
        header.y_constant,
    ];
    for (i, value) in axis.iter().enumerate() {
        let at = 104 + i * 8;
        out[at..at + 8].copy_from_slice(&value.to_le_bytes());
    }
    out[152] = header.x_nonpositive_mask;
    out[153] = header.y_nonpositive_mask;
    out[154..156].copy_from_slice(&header.tick_kinds.to_le_bytes());
    let counts = [
        header.title_len,
        header.x_label_len,
        header.y_label_len,
        header.x_format_len,
        header.y_format_len,
        header.x_major_len,
        header.x_minor_len,
        header.y_major_len,
        header.y_minor_len,
        header.x_label_count,
        header.y_label_count,
        header.chrome_len,
        header.legend_loc_len,
        header.legend_title_len,
        header.legend_ncols,
    ];
    for (i, value) in counts.iter().enumerate() {
        let at = 156 + i * 4;
        out[at..at + 4].copy_from_slice(&value.to_le_bytes());
    }
    out[216..224].copy_from_slice(&header.legend_font_size.to_le_bytes());
    out[224..232].copy_from_slice(&header.legend_title_font_size.to_le_bytes());
    out[232..236].copy_from_slice(&header.legend_flags.to_le_bytes());
    out[236..240].copy_from_slice(&header.legend_count.to_le_bytes());
    out[240..244].copy_from_slice(&header.legend_text_rgba);
    out[244..248].copy_from_slice(&header.legend_frame_rgba);
    out[248..252].copy_from_slice(&header.colorbar_obs.to_le_bytes());
    out[252..256].copy_from_slice(&header.colorbar_stop_count.to_le_bytes());
    out[256..260].copy_from_slice(&header.colorbar_tick_count.to_le_bytes());
    out[260..264].copy_from_slice(&header.colorbar_title_len.to_le_bytes());
    out[264..272].copy_from_slice(&header.colorbar_lo.to_le_bytes());
    out[272..280].copy_from_slice(&header.colorbar_hi.to_le_bytes());
    out[280..284].copy_from_slice(&header.colorbar_text_rgba);
    out[284..288].copy_from_slice(&0u32.to_le_bytes());
    Ok(())
}

fn check_len(actual: usize, expected: usize) -> Result<(), i32> {
    if actual != expected {
        return Err(-1);
    }
    Ok(())
}

fn append_f64s(buf: &mut Vec<u8>, values: &[f64]) {
    for value in values {
        buf.extend_from_slice(&value.to_le_bytes());
    }
}

fn append_u32s(buf: &mut Vec<u8>, values: &[u32]) {
    for value in values {
        buf.extend_from_slice(&value.to_le_bytes());
    }
}

/// Pack XYCF v1 facts. Returns ``-1`` on length mismatch, ``-2`` when over cap.
pub fn scene_xycf_pack(header: &XycfPackHeader, sidecars: &XycfPackSidecars<'_>) -> Result<Vec<u8>, i32> {
    check_len(sidecars.title.len(), header.title_len as usize)?;
    check_len(sidecars.x_label.len(), header.x_label_len as usize)?;
    check_len(sidecars.y_label.len(), header.y_label_len as usize)?;
    check_len(sidecars.x_format.len(), header.x_format_len as usize)?;
    check_len(sidecars.y_format.len(), header.y_format_len as usize)?;
    check_len(sidecars.x_major.len(), header.x_major_len as usize)?;
    check_len(sidecars.x_minor.len(), header.x_minor_len as usize)?;
    check_len(sidecars.y_major.len(), header.y_major_len as usize)?;
    check_len(sidecars.y_minor.len(), header.y_minor_len as usize)?;
    check_len(sidecars.chrome.len(), header.chrome_len as usize)?;
    check_len(sidecars.legend_loc.len(), header.legend_loc_len as usize)?;
    check_len(sidecars.legend_title.len(), header.legend_title_len as usize)?;
    check_len(sidecars.colorbar_title.len(), header.colorbar_title_len as usize)?;
    check_len(
        sidecars.colorbar_stops_blob.len(),
        header.colorbar_stop_count as usize * 12,
    )?;
    check_len(sidecars.colorbar_ticks.len(), header.colorbar_tick_count as usize)?;
    check_len(sidecars.legend_lens.len(), header.legend_count as usize)?;
    let mut out = vec![0u8; XYCF_HEADER_BYTES];
    write_header_full(&mut out, header)?;
    out.extend_from_slice(sidecars.title);
    out.extend_from_slice(sidecars.x_label);
    out.extend_from_slice(sidecars.y_label);
    out.extend_from_slice(sidecars.x_format);
    out.extend_from_slice(sidecars.y_format);
    append_f64s(&mut out, sidecars.x_major);
    append_f64s(&mut out, sidecars.x_minor);
    append_f64s(&mut out, sidecars.y_major);
    append_f64s(&mut out, sidecars.y_minor);
    out.extend_from_slice(sidecars.x_labels_blob);
    out.extend_from_slice(sidecars.y_labels_blob);
    out.extend_from_slice(sidecars.chrome);
    out.extend_from_slice(sidecars.legend_loc);
    out.extend_from_slice(sidecars.legend_title);
    out.extend_from_slice(sidecars.legend_meta);
    append_u32s(&mut out, sidecars.legend_lens);
    out.extend_from_slice(sidecars.legend_blob);
    out.extend_from_slice(sidecars.colorbar_stops_blob);
    append_f64s(&mut out, sidecars.colorbar_ticks);
    out.extend_from_slice(sidecars.colorbar_title);
    out.extend_from_slice(sidecars.collision_extra);
    if out.len() > SCENE_XYCF_PACK_MAX {
        return Err(-2);
    }
    Ok(out)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn packs_minimal_xycf() {
        let header = XycfPackHeader {
            flags: 1 << 6,
            collision_header: 0,
            width: 400.0,
            height: 300.0,
            margin_left: 0.0,
            margin_right: 0.0,
            margin_top: 0.0,
            margin_bottom: 0.0,
            pad_left: 0.0,
            pad_right: 0.0,
            pad_top: 0.0,
            pad_bottom: 0.0,
            x_scale_kind: 0,
            y_scale_kind: 0,
            x_lo: 0.0,
            x_hi: 1.0,
            x_constant: 1.0,
            y_lo: 0.0,
            y_hi: 1.0,
            y_constant: 1.0,
            x_nonpositive_mask: 0,
            y_nonpositive_mask: 0,
            tick_kinds: 0,
            title_len: 0,
            x_label_len: 0,
            y_label_len: 0,
            x_format_len: 0,
            y_format_len: 0,
            x_major_len: 0,
            x_minor_len: 0,
            y_major_len: 0,
            y_minor_len: 0,
            x_label_count: 0,
            y_label_count: 0,
            chrome_len: 4,
            legend_loc_len: 0,
            legend_title_len: 0,
            legend_ncols: 1,
            legend_font_size: 0.0,
            legend_title_font_size: 0.0,
            legend_flags: 0,
            legend_count: 0,
            legend_text_rgba: [0, 0, 0, 0],
            legend_frame_rgba: [0, 0, 0, 0],
            colorbar_obs: 0,
            colorbar_stop_count: 0,
            colorbar_tick_count: 0,
            colorbar_title_len: 0,
            colorbar_lo: 0.0,
            colorbar_hi: 1.0,
            colorbar_text_rgba: [32, 32, 32, 255],
        };
        let sidecars = XycfPackSidecars {
            title: b"",
            x_label: b"",
            y_label: b"",
            x_format: b"",
            y_format: b"",
            x_major: &[],
            x_minor: &[],
            y_major: &[],
            y_minor: &[],
            x_labels_blob: b"",
            y_labels_blob: b"",
            chrome: b"XYCH",
            legend_loc: b"",
            legend_title: b"",
            legend_meta: b"",
            legend_lens: &[],
            legend_blob: b"",
            colorbar_stops_blob: b"",
            colorbar_ticks: &[],
            colorbar_title: b"",
            collision_extra: b"",
        };
        let packed = scene_xycf_pack(&header, &sidecars).unwrap();
        assert_eq!(&packed[..4], b"XYCF");
        assert_eq!(packed.len(), XYCF_HEADER_BYTES + 4);
    }
}
