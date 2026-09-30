//! GraphForge result compositions (spec/design/graphforge-compositions.md).
//!
//! GraphForge Core computes; XYG composes and renders. Hosts hand this module
//! the raw Arrow IPC bytes GraphForge produced (results and base-graph
//! entities) plus explicit visualization intent and generation identities.
//! Rust alone recognizes result schemas from Arrow metadata, validates field
//! types, joins results onto the base graph by UUID, applies missing/extra
//! identity policy, and lowers the composition to the canonical semantic
//! planes every host paints. No host re-implements any of it.
//!
//! Diagnostics never carry result values, UUIDs, vectors, coordinates, or
//! paths: only schema ids/versions, field names, type names, counts, and
//! stable codes.

pub mod base;
pub mod columns;
pub mod compose;
pub mod container;
pub mod ledger;
pub mod recognize;
pub mod request;

use std::collections::HashMap;
use std::hash::{BuildHasherDefault, Hash, Hasher};

pub use crate::projection::Uuid;

/// A stable, value-free failure. `code` is the host-facing contract.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct GfError {
    pub code: &'static str,
    pub message: String,
    /// Result layer index the failure belongs to, when it has one.
    pub layer: Option<usize>,
    /// Canonical field name involved, when there is one.
    pub field: Option<String>,
}

impl GfError {
    pub fn new(code: &'static str, message: impl Into<String>) -> Self {
        Self {
            code,
            message: message.into(),
            layer: None,
            field: None,
        }
    }

    pub fn with_field(mut self, field: &str) -> Self {
        self.field = Some(field.to_owned());
        self
    }

    pub fn in_layer(mut self, layer: usize) -> Self {
        self.layer.get_or_insert(layer);
        self
    }
}

impl From<crate::arrow_ipc::IpcError> for GfError {
    fn from(error: crate::arrow_ipc::IpcError) -> Self {
        GfError::new(error.code(), error.reason)
    }
}

pub type GfResult<T> = Result<T, GfError>;

/// UUID key with a single mixed-u64 hash. GraphForge UUIDs are v7: the
/// leading bytes are a timestamp shared by every entity minted together, so
/// both halves are folded before the SplitMix64 finalizer.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct UuidKey(pub Uuid);

impl Hash for UuidKey {
    fn hash<H: Hasher>(&self, state: &mut H) {
        let lo = u64::from_le_bytes(self.0[..8].try_into().unwrap());
        let hi = u64::from_le_bytes(self.0[8..].try_into().unwrap());
        let mut z = lo ^ hi.rotate_left(29) ^ 0x9E37_79B9_7F4A_7C15;
        z = (z ^ (z >> 30)).wrapping_mul(0xBF58_476D_1CE4_E5B9);
        z = (z ^ (z >> 27)).wrapping_mul(0x94D0_49BB_1331_11EB);
        state.write_u64(z ^ (z >> 31));
    }
}

/// Pass-through hasher for pre-mixed [`UuidKey`] hashes.
#[derive(Default)]
pub struct MixedHasher(u64);

impl Hasher for MixedHasher {
    fn finish(&self) -> u64 {
        self.0
    }
    fn write(&mut self, bytes: &[u8]) {
        for &b in bytes {
            self.0 = (self.0 ^ u64::from(b)).wrapping_mul(0x0100_0000_01B3);
        }
    }
    fn write_u64(&mut self, value: u64) {
        self.0 = value;
    }
}

/// UUID → dense index.
pub type UuidMap = HashMap<UuidKey, usize, BuildHasherDefault<MixedHasher>>;

pub fn uuid_map(capacity: usize) -> UuidMap {
    UuidMap::with_capacity_and_hasher(capacity, Default::default())
}

pub const NIL_UUID: Uuid = [0; 16];

/// Parse a canonical hyphenated UUID string (any case).
pub fn parse_uuid_text(text: &str) -> Option<Uuid> {
    let bytes = text.as_bytes();
    if bytes.len() != 36 || [8, 13, 18, 23].iter().any(|&i| bytes[i] != b'-') {
        return None;
    }
    let mut out = [0u8; 16];
    let mut nibbles = bytes.iter().filter(|&&b| b != b'-');
    for byte in &mut out {
        let hi = (*nibbles.next()? as char).to_digit(16)?;
        let lo = (*nibbles.next()? as char).to_digit(16)?;
        *byte = (hi * 16 + lo) as u8;
    }
    Some(out)
}
