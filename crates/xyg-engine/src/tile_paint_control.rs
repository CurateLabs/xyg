//! Store-independent XYDC inventory decoding (dossier §28/§29).
//! Shared by native tile painting and every C ABI wheel target, including Pyodide.

pub const MAX_PAINT_KEYS: usize = 256;

/// Bounded binary XYDC v1 observations. This is inventory, never policy.
pub struct PaintObservation {
    pub generation: u64,
    pub opacity: f64,
    pub level: i32,
    pub keys: Vec<u32>,
}
impl PaintObservation {
    pub fn decode(raw: &[u8]) -> Option<Self> {
        if raw.is_empty() {
            return Some(Self {
                generation: 0,
                opacity: -1.0,
                level: -1,
                keys: Vec::new(),
            });
        }
        if raw.len() < 32
            || &raw[..4] != b"XYDC"
            || u32::from_le_bytes(raw[4..8].try_into().ok()?) != 1
        {
            return None;
        }
        let count = u32::from_le_bytes(raw[28..32].try_into().ok()?) as usize;
        if count > MAX_PAINT_KEYS || raw.len() != 32 + count * 12 {
            return None;
        }
        let generation = u64::from_le_bytes(raw[8..16].try_into().ok()?);
        let opacity = f64::from_le_bytes(raw[16..24].try_into().ok()?);
        let level = i32::from_le_bytes(raw[24..28].try_into().ok()?);
        if !opacity.is_finite() || !(-1.0..=1.0).contains(&opacity) || !(-1..=31).contains(&level) {
            return None;
        }
        Some(Self {
            generation,
            opacity,
            level,
            keys: raw[32..]
                .chunks_exact(4)
                .map(|v| u32::from_le_bytes(v.try_into().unwrap()))
                .collect(),
        })
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn control(count: u32) -> Vec<u8> {
        let mut raw = b"XYDC".to_vec();
        raw.extend(1u32.to_le_bytes());
        raw.extend(7u64.to_le_bytes());
        raw.extend(0.5f64.to_le_bytes());
        raw.extend(2i32.to_le_bytes());
        raw.extend(count.to_le_bytes());
        raw.resize(32 + count as usize * 12, 0);
        raw
    }

    #[test]
    fn bounded_inventory_decodes_without_a_store() {
        let empty = PaintObservation::decode(&[]).unwrap();
        assert_eq!(
            (empty.generation, empty.opacity, empty.level),
            (0, -1.0, -1)
        );
        assert!(empty.keys.is_empty());
        let mut raw = control(MAX_PAINT_KEYS as u32);
        raw[32..36].copy_from_slice(&3u32.to_le_bytes());
        let decoded = PaintObservation::decode(&raw).unwrap();
        assert_eq!(
            (decoded.generation, decoded.opacity, decoded.level),
            (7, 0.5, 2)
        );
        assert_eq!(decoded.keys.len(), MAX_PAINT_KEYS * 3);
        assert_eq!(decoded.keys[0], 3);
        assert!(PaintObservation::decode(&raw[..raw.len() - 1]).is_none());
        raw.push(0);
        assert!(PaintObservation::decode(&raw).is_none());
        assert!(PaintObservation::decode(&control(MAX_PAINT_KEYS as u32 + 1)).is_none());
    }

    #[test]
    fn malformed_inventory_fails_closed() {
        for len in 1..32 {
            assert!(PaintObservation::decode(&control(0)[..len]).is_none());
        }
        for (offset, bytes) in [
            (0, *b"NOPE"),
            (4, 2u32.to_le_bytes()),
            (24, (-2i32).to_le_bytes()),
            (24, 32i32.to_le_bytes()),
        ] {
            let mut raw = control(0);
            raw[offset..offset + 4].copy_from_slice(&bytes);
            assert!(PaintObservation::decode(&raw).is_none());
        }
        for opacity in [f64::NAN, f64::INFINITY, -1.01, 1.01] {
            let mut raw = control(0);
            raw[16..24].copy_from_slice(&opacity.to_le_bytes());
            assert!(PaintObservation::decode(&raw).is_none());
        }
    }
}
