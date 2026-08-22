use xyg_engine::dashboard::{plan_dashboard_resources, DashboardResource, MAX_DASHBOARD_RESOURCES};

const MAGIC: &[u8; 4] = b"XYDP";
const VERSION: u32 = 1;
const HEADER_BYTES: usize = 32;
const RECORD_BYTES: usize = 32;

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum DashboardError {
    Malformed,
    Limit,
}

fn u32_at(bytes: &[u8], offset: usize) -> Result<u32, DashboardError> {
    Ok(u32::from_le_bytes(
        bytes
            .get(offset..offset + 4)
            .ok_or(DashboardError::Malformed)?
            .try_into()
            .unwrap(),
    ))
}

fn u64_at(bytes: &[u8], offset: usize) -> Result<u64, DashboardError> {
    Ok(u64::from_le_bytes(
        bytes
            .get(offset..offset + 8)
            .ok_or(DashboardError::Malformed)?
            .try_into()
            .unwrap(),
    ))
}

pub fn plan(bytes: &[u8]) -> Result<Vec<u8>, DashboardError> {
    if bytes.len() < HEADER_BYTES
        || bytes.get(..4) != Some(MAGIC)
        || u32_at(bytes, 4)? != VERSION
        || u32_at(bytes, 8)? as usize != HEADER_BYTES
        || bytes[24..32] != [0; 8]
    {
        return Err(DashboardError::Malformed);
    }
    let count = u32_at(bytes, 12)? as usize;
    if count > MAX_DASHBOARD_RESOURCES {
        return Err(DashboardError::Limit);
    }
    let expected = HEADER_BYTES
        .checked_add(
            count
                .checked_mul(RECORD_BYTES)
                .ok_or(DashboardError::Limit)?,
        )
        .ok_or(DashboardError::Limit)?;
    if bytes.len() != expected {
        return Err(DashboardError::Malformed);
    }
    let budget = u64_at(bytes, 16)?;
    let mut resources = Vec::with_capacity(count);
    for index in 0..count {
        let at = HEADER_BYTES + index * RECORD_BYTES;
        if bytes[at + 25..at + 32] != [0; 7] {
            return Err(DashboardError::Malformed);
        }
        resources.push(DashboardResource {
            stable_id: u64_at(bytes, at)?,
            derived_bytes: u64_at(bytes, at + 8)?,
            last_used: u64_at(bytes, at + 16)?,
            flags: bytes[at + 24],
        });
    }
    let result = plan_dashboard_resources(&resources, budget).ok_or(DashboardError::Malformed)?;
    let mut output = Vec::with_capacity(24 + count);
    output.extend_from_slice(b"XYDO");
    output.extend_from_slice(&VERSION.to_le_bytes());
    output.extend_from_slice(&(count as u32).to_le_bytes());
    output.extend_from_slice(&0_u32.to_le_bytes());
    output.extend_from_slice(&result.retained_bytes.to_le_bytes());
    output.extend(result.retained.into_iter().map(u8::from));
    Ok(output)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn packed_plan_preserves_input_order_and_exact_bytes() {
        let mut input = vec![0; HEADER_BYTES];
        input[..4].copy_from_slice(MAGIC);
        input[4..8].copy_from_slice(&VERSION.to_le_bytes());
        input[8..12].copy_from_slice(&(HEADER_BYTES as u32).to_le_bytes());
        input[12..16].copy_from_slice(&2_u32.to_le_bytes());
        input[16..20].copy_from_slice(&50_u32.to_le_bytes());
        for (id, used, flags) in [(8_u64, 9_u64, 0_u8), (7, 1, 1)] {
            input.extend_from_slice(&id.to_le_bytes());
            input.extend_from_slice(&50_u64.to_le_bytes());
            input.extend_from_slice(&used.to_le_bytes());
            input.push(flags);
            input.extend_from_slice(&[0; 7]);
        }
        let output = plan(&input).unwrap();
        assert_eq!(&output[..4], b"XYDO");
        assert_eq!(&output[16..24], &50_u64.to_le_bytes());
        assert_eq!(&output[24..], &[0, 1]);
    }
}
