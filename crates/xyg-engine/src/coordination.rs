//! Shared linked-view admission. Payload shape is validated by each controller
//! before this gate; the watermark commits only after the atomic apply succeeds.
use std::collections::HashMap;

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum GateError {
    Invalid,
    SelfEcho,
    Stale,
}

#[derive(Debug, Default)]
pub struct CoordinationGate {
    last: HashMap<u64, u64>,
}

impl CoordinationGate {
    #[inline]
    pub fn validate(
        &self,
        instance: u64,
        group: u64,
        source: u64,
        remote_group: u64,
        sequence: u64,
    ) -> Result<bool, GateError> {
        if source == 0 || sequence == 0 {
            return Err(GateError::Invalid);
        }
        if group == 0 || remote_group != group {
            return Ok(false);
        }
        if source == instance {
            return Err(GateError::SelfEcho);
        }
        if sequence <= self.last.get(&source).copied().unwrap_or(0) {
            return Err(GateError::Stale);
        }
        Ok(true)
    }

    pub fn commit(&mut self, source: u64, sequence: u64) {
        self.last.insert(source, sequence);
    }

    pub fn clear(&mut self) {
        self.last.clear();
    }
}
