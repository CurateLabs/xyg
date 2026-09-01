//! Figure-compile XYFS v2 support envelope packing (M2 Push 3A, ABI 319).
//!
//! Hosts marshal figure-level observation flags, per-axis key lists, and
//! per-trace allowlist bits; Rust owns the XYFS v2 byte layout so Python and
//! Node cannot drift on field walks.

pub const SCENE_FIGURE_SUPPORT_PACK_MAX: usize = 1 << 18;

const XYFS_MAGIC: &[u8; 4] = b"XYFS";
const XYFS_VERSION_TRACES: u32 = 2;
const XYFS_AXIS_BYTES: usize = 8;
const XYFS_TRACE_BYTES: usize = 8;
const MAX_XYFS_KIND_BYTES: usize = 32;
const MAX_XYFS_AXES: usize = 8;
const MAX_XYFS_TRACES: usize = 256;
const MAX_XYFS_KEY_BYTES: usize = 256;

const OBS_MASK: u32 = (1 << 10) - 1;
const TRACE_FLAG_MASK: u16 = (1 << 12) - 1;

/// One axis key row for ``scene_figure_support_pack``.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct FigureSupportAxisInput {
    pub axis_code: u8,
    pub keys: Vec<String>,
}

/// One trace allowlist row for ``scene_figure_support_pack``.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct FigureSupportTraceInput {
    pub trace_flags: u16,
    pub kind: String,
}

fn put_keys(buf: &mut Vec<u8>, keys: &[String]) -> Result<(), i32> {
    for key in keys {
        let encoded = key.as_bytes();
        if encoded.is_empty() || encoded.len() > MAX_XYFS_KEY_BYTES || encoded.contains(&0) {
            return Err(-1);
        }
        buf.extend_from_slice(&(encoded.len() as u16).to_le_bytes());
        buf.extend_from_slice(encoded);
    }
    Ok(())
}

fn put_axes(buf: &mut Vec<u8>, axes: &[FigureSupportAxisInput]) -> Result<(), i32> {
    for axis in axes {
        buf.push(axis.axis_code);
        buf.extend_from_slice(&[0, 0, 0]);
        if axis.keys.len() > u32::MAX as usize {
            return Err(-1);
        }
        buf.extend_from_slice(&(axis.keys.len() as u32).to_le_bytes());
        put_keys(buf, &axis.keys)?;
    }
    Ok(())
}

/// Pack XYFS v2 from host-marshaled observations.
///
/// Returns the packed envelope on success. Error codes: ``-1`` invalid args,
/// ``-2`` output would exceed ``SCENE_FIGURE_SUPPORT_PACK_MAX``.
pub fn scene_figure_support_pack(
    flags: u32,
    axes: &[FigureSupportAxisInput],
    traces: &[FigureSupportTraceInput],
) -> Result<Vec<u8>, i32> {
    if flags & !OBS_MASK != 0 || axes.len() > MAX_XYFS_AXES || traces.len() > MAX_XYFS_TRACES {
        return Err(-1);
    }
    for trace in traces {
        if trace.trace_flags & !TRACE_FLAG_MASK != 0 {
            return Err(-1);
        }
        let kind = trace.kind.as_bytes();
        if kind.is_empty() || kind.len() > MAX_XYFS_KIND_BYTES || kind.contains(&0) {
            return Err(-1);
        }
    }
    let mut buf = Vec::with_capacity(
        20usize
            .saturating_add(axes.len().saturating_mul(XYFS_AXIS_BYTES))
            .saturating_add(traces.len().saturating_mul(XYFS_TRACE_BYTES + MAX_XYFS_KIND_BYTES)),
    );
    buf.extend_from_slice(XYFS_MAGIC);
    buf.extend_from_slice(&XYFS_VERSION_TRACES.to_le_bytes());
    buf.extend_from_slice(&flags.to_le_bytes());
    buf.extend_from_slice(&(axes.len() as u32).to_le_bytes());
    buf.extend_from_slice(&(traces.len() as u32).to_le_bytes());
    put_axes(&mut buf, axes)?;
    for trace in traces {
        buf.extend_from_slice(&trace.trace_flags.to_le_bytes());
        let kind = trace.kind.as_bytes();
        buf.push(kind.len() as u8);
        buf.push(0);
        buf.extend_from_slice(&0u32.to_le_bytes());
        buf.extend_from_slice(kind);
    }
    if buf.len() > SCENE_FIGURE_SUPPORT_PACK_MAX {
        return Err(-2);
    }
    Ok(buf)
}

#[cfg(test)]
mod tests {
    use super::*;

    const PRIMARY_XY: [(u8, &[&str; 2]); 2] = [(0, &["label", "side"]), (1, &["label", "side"])];

    #[test]
    fn packs_v2_envelope() {
        let axes = PRIMARY_XY
            .iter()
            .map(|(code, keys)| FigureSupportAxisInput {
                axis_code: *code,
                keys: keys.iter().map(|s| (*s).to_string()).collect(),
            })
            .collect::<Vec<_>>();
        let traces = [FigureSupportTraceInput {
            trace_flags: 0,
            kind: "scatter".to_string(),
        }];
        let packed = scene_figure_support_pack(0, &axes, &traces).unwrap();
        assert_eq!(&packed[..4], b"XYFS");
        assert_eq!(u32::from_le_bytes(packed[4..8].try_into().unwrap()), 2);
    }
}
