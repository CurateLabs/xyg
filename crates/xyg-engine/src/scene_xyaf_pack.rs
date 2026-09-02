//! Per-annotation XYAF v1 record packing (M2 Push 3A, ABI 319).
//!
//! Hosts marshal validated annotation facts and style bytes; Rust owns the
//! XYAF v1 header layout and text tail concat.

pub const SCENE_XYAF_PACK_MAX_RECORD: usize = 1 << 16;

const XYAF_MAGIC: &[u8; 4] = b"XYAF";
const XYAF_VERSION: u32 = 1;
const XYAF_V1_HEADER_BYTES: usize = 232;

/// Host-marshaled XYAF record for ``scene_xyaf_pack``.
#[derive(Clone, Debug)]
pub struct XyafPackInput<'a> {
    pub index: u32,
    pub kind_code: u8,
    pub axis_code: u8,
    pub symbol: u8,
    pub anchor: u8,
    pub facts: u32,
    pub style_bits: u32,
    pub linecap: u8,
    pub dash_count: u8,
    pub nums: [f64; 18],
    pub color: [u8; 4],
    pub stroke: [u8; 4],
    pub label_color: [u8; 4],
    pub label_fill: [u8; 4],
    pub label_border: [u8; 4],
    pub dash: [f32; 8],
    pub text: &'a [u8],
}

/// Pack one XYAF v1 record. Returns ``-1`` invalid, ``-2`` text too long.
pub fn scene_xyaf_pack(input: &XyafPackInput<'_>) -> Result<Vec<u8>, i32> {
    if input.kind_code > 5
        || input.axis_code > 2
        || input.dash_count > 8
        || (input.linecap != 255 && input.linecap != 0 && input.linecap != 2)
        || (input.anchor != 255 && input.anchor > 2)
        || input.text.len() > 4096
        || input.text.contains(&0)
    {
        return Err(-1);
    }
    let total = XYAF_V1_HEADER_BYTES
        .checked_add(input.text.len())
        .ok_or(-2)?;
    if total > SCENE_XYAF_PACK_MAX_RECORD {
        return Err(-2);
    }
    let mut out = vec![0u8; total];
    out[..4].copy_from_slice(XYAF_MAGIC);
    out[4..8].copy_from_slice(&XYAF_VERSION.to_le_bytes());
    out[8..12].copy_from_slice(&input.index.to_le_bytes());
    out[12] = input.kind_code;
    out[13] = input.axis_code;
    out[14] = input.symbol;
    out[15] = input.anchor;
    out[16..20].copy_from_slice(&input.facts.to_le_bytes());
    out[20..24].copy_from_slice(&input.style_bits.to_le_bytes());
    out[24] = input.linecap;
    out[25] = input.dash_count;
    out[26] = 0;
    out[27] = 0;
    out[28..32].copy_from_slice(&(input.text.len() as u32).to_le_bytes());
    for (i, value) in input.nums.iter().enumerate() {
        let at = 32 + i * 8;
        out[at..at + 8].copy_from_slice(&value.to_le_bytes());
    }
    out[176..180].copy_from_slice(&input.color);
    out[180..184].copy_from_slice(&input.stroke);
    out[184..188].copy_from_slice(&input.label_color);
    out[188..192].copy_from_slice(&input.label_fill);
    out[192..196].copy_from_slice(&input.label_border);
    out[196..200].copy_from_slice(&[0, 0, 0, 0]);
    for (i, value) in input.dash.iter().enumerate() {
        let at = 200 + i * 4;
        out[at..at + 4].copy_from_slice(&value.to_le_bytes());
    }
    out[XYAF_V1_HEADER_BYTES..].copy_from_slice(input.text);
    Ok(out)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn packs_text_annotation() {
        let mut nums = [f64::NAN; 18];
        nums[0] = 0.5;
        nums[1] = 0.25;
        let packed = scene_xyaf_pack(&XyafPackInput {
            index: 0,
            kind_code: 0,
            axis_code: 0,
            symbol: 0,
            anchor: 255,
            facts: (1 << 5) | (1 << 6) | (1 << 1),
            style_bits: 1,
            linecap: 255,
            dash_count: 0,
            nums,
            color: [102, 112, 133, 255],
            stroke: [0; 4],
            label_color: [0; 4],
            label_fill: [0; 4],
            label_border: [0; 4],
            dash: [0.0; 8],
            text: b"hi",
        })
        .unwrap();
        assert_eq!(&packed[..4], b"XYAF");
        assert_eq!(&packed[XYAF_V1_HEADER_BYTES..], b"hi");
    }
}
