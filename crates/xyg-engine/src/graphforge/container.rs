//! Self-describing named-section container shared by the `XYGQ` composition
//! request and the `XYGF` composition document (spec §5).
//!
//! Every section is `(name, index, dtype, count)` over an 8-aligned
//! little-endian payload. Hosts decode sections generically by name and never
//! interpret their meaning; unknown names are ignored, so sections can be
//! added without a version bump. The layout is identical for native C ABI and
//! direct-browser WASM hosts.
//!
//! ```text
//! 0   magic[4]            "XYGQ" | "XYGF"
//! 4   version u32         1
//! 8   entry_count u32
//! 12  names_bytes u32
//! 16  total_bytes u64     == buffer length
//! 24  reserved u64        0
//! 32  entries[entry_count] × 40:
//!       name_offset u32, name_len u32, dtype u32, index u32,
//!       offset u64, count u64, byte_len u64
//! ..  names (ASCII [a-z0-9._]), zero-padded to 8
//! ..  payloads, each 8-aligned, non-overlapping
//! ```

use super::{GfError, GfResult, Uuid};

pub const CONTAINER_VERSION: u32 = 1;
pub const REQUEST_MAGIC: &[u8; 4] = b"XYGQ";
pub const DOCUMENT_MAGIC: &[u8; 4] = b"XYGF";
pub const HEADER_BYTES: usize = 32;
pub const ENTRY_BYTES: usize = 40;
pub const MAX_ENTRIES: usize = 8192;
pub const MAX_NAME_BYTES: usize = 64;

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
#[repr(u32)]
pub enum Dtype {
    U8 = 1,
    U32 = 2,
    U64 = 3,
    I64 = 4,
    F64 = 5,
    Bytes = 6,
    Uuid = 7,
    Utf8 = 8,
    TextList = 9,
}

impl Dtype {
    fn from_u32(value: u32) -> Option<Self> {
        Some(match value {
            1 => Dtype::U8,
            2 => Dtype::U32,
            3 => Dtype::U64,
            4 => Dtype::I64,
            5 => Dtype::F64,
            6 => Dtype::Bytes,
            7 => Dtype::Uuid,
            8 => Dtype::Utf8,
            9 => Dtype::TextList,
            _ => return None,
        })
    }

    /// Element width in bytes (`None` for text lists).
    fn width(self) -> Option<usize> {
        match self {
            Dtype::U8 | Dtype::Bytes | Dtype::Utf8 => Some(1),
            Dtype::U32 => Some(4),
            Dtype::U64 | Dtype::I64 | Dtype::F64 => Some(8),
            Dtype::Uuid => Some(16),
            Dtype::TextList => None,
        }
    }
}

fn valid_name(name: &str) -> bool {
    !name.is_empty()
        && name.len() <= MAX_NAME_BYTES
        && name
            .bytes()
            .all(|b| b.is_ascii_lowercase() || b.is_ascii_digit() || b == b'.' || b == b'_')
}

struct Pending {
    name: &'static str,
    index: u32,
    dtype: Dtype,
    count: u64,
    payload: Vec<u8>,
}

/// Section writer. Names are compile-time constants.
pub struct Builder {
    magic: [u8; 4],
    sections: Vec<Pending>,
}

impl Builder {
    pub fn new(magic: &[u8; 4]) -> Self {
        Self {
            magic: *magic,
            sections: Vec::new(),
        }
    }

    fn push(
        &mut self,
        name: &'static str,
        index: usize,
        dtype: Dtype,
        count: usize,
        payload: Vec<u8>,
    ) {
        debug_assert!(valid_name(name), "section name {name}");
        self.sections.push(Pending {
            name,
            index: index as u32,
            dtype,
            count: count as u64,
            payload,
        });
    }

    pub fn u8s(&mut self, name: &'static str, index: usize, values: &[u8]) {
        self.push(name, index, Dtype::U8, values.len(), values.to_vec());
    }

    pub fn u32s(&mut self, name: &'static str, index: usize, values: &[u32]) {
        let payload = values.iter().flat_map(|v| v.to_le_bytes()).collect();
        self.push(name, index, Dtype::U32, values.len(), payload);
    }

    pub fn u64s(&mut self, name: &'static str, index: usize, values: &[u64]) {
        let payload = values.iter().flat_map(|v| v.to_le_bytes()).collect();
        self.push(name, index, Dtype::U64, values.len(), payload);
    }

    pub fn i64s(&mut self, name: &'static str, index: usize, values: &[i64]) {
        let payload = values.iter().flat_map(|v| v.to_le_bytes()).collect();
        self.push(name, index, Dtype::I64, values.len(), payload);
    }

    pub fn f64s(&mut self, name: &'static str, index: usize, values: &[f64]) {
        let payload = values.iter().flat_map(|v| v.to_le_bytes()).collect();
        self.push(name, index, Dtype::F64, values.len(), payload);
    }

    pub fn bytes(&mut self, name: &'static str, index: usize, value: &[u8]) {
        self.push(name, index, Dtype::Bytes, value.len(), value.to_vec());
    }

    pub fn uuids(&mut self, name: &'static str, index: usize, values: &[Uuid]) {
        self.push(name, index, Dtype::Uuid, values.len(), values.concat());
    }

    pub fn utf8(&mut self, name: &'static str, index: usize, value: &str) {
        self.push(
            name,
            index,
            Dtype::Utf8,
            value.len(),
            value.as_bytes().to_vec(),
        );
    }

    pub fn texts<S: AsRef<str>>(&mut self, name: &'static str, index: usize, values: &[S]) {
        let mut offsets = Vec::with_capacity(values.len() + 1);
        let mut text = Vec::new();
        offsets.push(0u64);
        for value in values {
            text.extend_from_slice(value.as_ref().as_bytes());
            offsets.push(text.len() as u64);
        }
        let mut payload: Vec<u8> = offsets.iter().flat_map(|v| v.to_le_bytes()).collect();
        payload.extend_from_slice(&text);
        self.push(name, index, Dtype::TextList, values.len(), payload);
    }

    pub fn finish(self) -> Vec<u8> {
        let count = self.sections.len();
        let mut names = Vec::new();
        let mut name_spans = Vec::with_capacity(count);
        for section in &self.sections {
            name_spans.push((names.len(), section.name.len()));
            names.extend_from_slice(section.name.as_bytes());
        }
        let names_start = HEADER_BYTES + count * ENTRY_BYTES;
        let mut cursor = align8(names_start + names.len());
        let mut offsets = Vec::with_capacity(count);
        for section in &self.sections {
            offsets.push(cursor);
            cursor = align8(cursor + section.payload.len());
        }
        let mut out = vec![0u8; cursor];
        out[0..4].copy_from_slice(&self.magic);
        out[4..8].copy_from_slice(&CONTAINER_VERSION.to_le_bytes());
        out[8..12].copy_from_slice(&(count as u32).to_le_bytes());
        out[12..16].copy_from_slice(&(names.len() as u32).to_le_bytes());
        out[16..24].copy_from_slice(&(cursor as u64).to_le_bytes());
        for (i, section) in self.sections.iter().enumerate() {
            let at = HEADER_BYTES + i * ENTRY_BYTES;
            let (name_offset, name_len) = name_spans[i];
            out[at..at + 4].copy_from_slice(&(name_offset as u32).to_le_bytes());
            out[at + 4..at + 8].copy_from_slice(&(name_len as u32).to_le_bytes());
            out[at + 8..at + 12].copy_from_slice(&(section.dtype as u32).to_le_bytes());
            out[at + 12..at + 16].copy_from_slice(&section.index.to_le_bytes());
            out[at + 16..at + 24].copy_from_slice(&(offsets[i] as u64).to_le_bytes());
            out[at + 24..at + 32].copy_from_slice(&section.count.to_le_bytes());
            out[at + 32..at + 40].copy_from_slice(&(section.payload.len() as u64).to_le_bytes());
            out[offsets[i]..offsets[i] + section.payload.len()].copy_from_slice(&section.payload);
        }
        out[names_start..names_start + names.len()].copy_from_slice(&names);
        out
    }
}

fn align8(value: usize) -> usize {
    (value + 7) & !7
}

/// One decoded section (borrowed payload).
#[derive(Clone, Copy, Debug)]
pub struct Section<'a> {
    pub dtype: Dtype,
    pub count: usize,
    pub payload: &'a [u8],
}

impl<'a> Section<'a> {
    fn expect(&self, dtype: Dtype, name: &str) -> GfResult<()> {
        if self.dtype == dtype {
            Ok(())
        } else {
            Err(GfError::new(
                "GF_COMPOSE_REQUEST_INVALID",
                format!("section \"{name}\" has the wrong element type"),
            ))
        }
    }

    pub fn as_u8(&self, name: &str) -> GfResult<&'a [u8]> {
        self.expect(Dtype::U8, name)?;
        Ok(self.payload)
    }

    pub fn as_bytes(&self, name: &str) -> GfResult<&'a [u8]> {
        self.expect(Dtype::Bytes, name)?;
        Ok(self.payload)
    }

    pub fn as_u64(&self, name: &str) -> GfResult<Vec<u64>> {
        self.expect(Dtype::U64, name)?;
        Ok(self
            .payload
            .chunks_exact(8)
            .map(|c| u64::from_le_bytes(c.try_into().unwrap()))
            .collect())
    }

    pub fn as_f64(&self, name: &str) -> GfResult<Vec<f64>> {
        self.expect(Dtype::F64, name)?;
        Ok(self
            .payload
            .chunks_exact(8)
            .map(|c| f64::from_le_bytes(c.try_into().unwrap()))
            .collect())
    }

    pub fn as_uuids(&self, name: &str) -> GfResult<Vec<Uuid>> {
        self.expect(Dtype::Uuid, name)?;
        Ok(self
            .payload
            .chunks_exact(16)
            .map(|c| c.try_into().unwrap())
            .collect())
    }

    pub fn as_utf8(&self, name: &str) -> GfResult<&'a str> {
        self.expect(Dtype::Utf8, name)?;
        std::str::from_utf8(self.payload).map_err(|_| {
            GfError::new(
                "GF_COMPOSE_REQUEST_INVALID",
                format!("section \"{name}\" is not UTF-8"),
            )
        })
    }

    pub fn as_texts(&self, name: &str) -> GfResult<Vec<&'a str>> {
        self.expect(Dtype::TextList, name)?;
        let bad = || {
            GfError::new(
                "GF_COMPOSE_REQUEST_INVALID",
                format!("section \"{name}\" is malformed"),
            )
        };
        let head = (self.count + 1) * 8;
        let text = self.payload.get(head..).ok_or_else(bad)?;
        let mut out = Vec::with_capacity(self.count);
        let offset = |i: usize| {
            u64::from_le_bytes(self.payload[i * 8..i * 8 + 8].try_into().unwrap()) as usize
        };
        for i in 0..self.count {
            let (start, end) = (offset(i), offset(i + 1));
            let slice = text
                .get(start..end)
                .filter(|_| start <= end)
                .ok_or_else(bad)?;
            out.push(std::str::from_utf8(slice).map_err(|_| bad())?);
        }
        Ok(out)
    }
}

/// Decoded container: ordered sections keyed by `(name, index)`.
pub struct Container<'a> {
    pub sections: Vec<(&'a str, u32, Section<'a>)>,
}

fn invalid(reason: &str) -> GfError {
    GfError::new("GF_COMPOSE_REQUEST_INVALID", format!("container {reason}"))
}

impl<'a> Container<'a> {
    pub fn decode(bytes: &'a [u8], magic: &[u8; 4]) -> GfResult<Self> {
        let u32_at = |at: usize| u32::from_le_bytes(bytes[at..at + 4].try_into().unwrap());
        let u64_at = |at: usize| u64::from_le_bytes(bytes[at..at + 8].try_into().unwrap());
        if bytes.len() < HEADER_BYTES || &bytes[0..4] != magic {
            return Err(invalid("magic is wrong"));
        }
        if u32_at(4) != CONTAINER_VERSION {
            return Err(GfError::new(
                "GF_COMPOSE_VERSION",
                format!(
                    "container version {} is not supported (expected {CONTAINER_VERSION})",
                    u32_at(4)
                ),
            ));
        }
        let count = u32_at(8) as usize;
        let names_len = u32_at(12) as usize;
        if count > MAX_ENTRIES || u64_at(16) != bytes.len() as u64 || u64_at(24) != 0 {
            return Err(invalid("header is inconsistent"));
        }
        let names_start = HEADER_BYTES + count * ENTRY_BYTES;
        let payload_start = align8(names_start + names_len);
        if payload_start > bytes.len() {
            return Err(invalid("names lie outside the buffer"));
        }
        let names = &bytes[names_start..names_start + names_len];
        let mut sections = Vec::with_capacity(count);
        let mut spans = Vec::with_capacity(count);
        for i in 0..count {
            let at = HEADER_BYTES + i * ENTRY_BYTES;
            let (name_off, name_len) = (u32_at(at) as usize, u32_at(at + 4) as usize);
            let name = names
                .get(
                    name_off
                        ..name_off
                            .checked_add(name_len)
                            .ok_or_else(|| invalid("name overflow"))?,
                )
                .and_then(|b| std::str::from_utf8(b).ok())
                .filter(|n| valid_name(n))
                .ok_or_else(|| invalid("section name is invalid"))?;
            let dtype =
                Dtype::from_u32(u32_at(at + 8)).ok_or_else(|| invalid("dtype is unknown"))?;
            let index = u32_at(at + 12);
            let (offset, count, byte_len) = (u64_at(at + 16), u64_at(at + 24), u64_at(at + 32));
            let end = offset
                .checked_add(byte_len)
                .ok_or_else(|| invalid("section overflow"))?;
            if offset % 8 != 0 || (offset as usize) < payload_start || end > bytes.len() as u64 {
                return Err(invalid("section lies outside the payload"));
            }
            let expected = match dtype.width() {
                Some(width) => count.checked_mul(width as u64),
                None => count.checked_add(1).and_then(|n| n.checked_mul(8)),
            }
            .ok_or_else(|| invalid("section size overflow"))?;
            let consistent = match dtype.width() {
                Some(_) => byte_len == expected,
                None => byte_len >= expected,
            };
            if !consistent {
                return Err(invalid("section size disagrees with its count"));
            }
            let payload = &bytes[offset as usize..end as usize];
            if dtype == Dtype::TextList {
                let text_len = byte_len - expected;
                let mut previous = 0u64;
                for k in 0..=count as usize {
                    let value = u64::from_le_bytes(payload[k * 8..k * 8 + 8].try_into().unwrap());
                    if value < previous || value > text_len || (k == 0 && value != 0) {
                        return Err(invalid("text offsets are malformed"));
                    }
                    previous = value;
                }
                if previous != text_len {
                    return Err(invalid("text offsets are malformed"));
                }
            }
            if sections
                .iter()
                .any(|(n, idx, _): &(&str, u32, Section<'_>)| *n == name && *idx == index)
            {
                return Err(invalid("section appears twice"));
            }
            spans.push((offset, end));
            sections.push((
                name,
                index,
                Section {
                    dtype,
                    count: count as usize,
                    payload,
                },
            ));
        }
        spans.sort_unstable();
        if spans.windows(2).any(|w| w[0].1 > w[1].0) {
            return Err(invalid("sections overlap"));
        }
        Ok(Self { sections })
    }

    pub fn get(&self, name: &str, index: u32) -> Option<Section<'a>> {
        self.sections
            .iter()
            .find(|(n, i, _)| *n == name && *i == index)
            .map(|(_, _, s)| *s)
    }

    /// Every index present for `name`, ascending.
    pub fn indices(&self, name: &str) -> Vec<u32> {
        let mut out: Vec<u32> = self
            .sections
            .iter()
            .filter(|(n, _, _)| *n == name)
            .map(|(_, i, _)| *i)
            .collect();
        out.sort_unstable();
        out
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn round_trips_every_dtype() {
        let mut builder = Builder::new(DOCUMENT_MAGIC);
        builder.u8s("a.u8", 0, &[1, 2, 3]);
        builder.u32s("a.u32", 0, &[7]);
        builder.u64s("a.u64", 2, &[u64::MAX, 0]);
        builder.i64s("a.i64", 0, &[-5]);
        builder.f64s("a.f64", 0, &[f64::NAN, 1.5]);
        builder.bytes("a.bytes", 0, b"xyz");
        builder.uuids("a.uuid", 0, &[[3; 16]]);
        builder.utf8("a.utf8", 0, "héllo");
        builder.texts("a.texts", 0, &["", "b", "<c>"]);
        let bytes = builder.finish();
        assert_eq!(bytes.len() % 8, 0);
        let container = Container::decode(&bytes, DOCUMENT_MAGIC).unwrap();
        assert_eq!(
            container.get("a.u8", 0).unwrap().as_u8("a.u8").unwrap(),
            &[1, 2, 3]
        );
        assert_eq!(
            container.get("a.u64", 2).unwrap().as_u64("x").unwrap(),
            vec![u64::MAX, 0]
        );
        assert!(container.get("a.u64", 0).is_none());
        assert_eq!(
            container.get("a.utf8", 0).unwrap().as_utf8("x").unwrap(),
            "héllo"
        );
        assert_eq!(
            container.get("a.texts", 0).unwrap().as_texts("x").unwrap(),
            vec!["", "b", "<c>"]
        );
        assert_eq!(
            container.get("a.uuid", 0).unwrap().as_uuids("x").unwrap(),
            vec![[3; 16]]
        );
        assert!(Container::decode(&bytes, REQUEST_MAGIC).is_err());
    }

    #[test]
    fn corrupt_containers_fail_closed() {
        let mut builder = Builder::new(REQUEST_MAGIC);
        builder.texts("t", 0, &["ab", "c"]);
        builder.f64s("f", 1, &[1.0, 2.0]);
        let bytes = builder.finish();
        for cut in 0..bytes.len() {
            assert!(Container::decode(&bytes[..cut], REQUEST_MAGIC).is_err());
        }
        let mut state = 0x1234_5678_9abc_def1_u64;
        for _ in 0..5000 {
            state ^= state << 13;
            state ^= state >> 7;
            state ^= state << 17;
            let mut copy = bytes.clone();
            let at = (state as usize) % copy.len();
            copy[at] ^= (state >> 40) as u8 | 1;
            if let Ok(container) = Container::decode(&copy, REQUEST_MAGIC) {
                for (name, _, section) in &container.sections {
                    let _ = section.as_texts(name);
                }
            }
        }
    }
}
