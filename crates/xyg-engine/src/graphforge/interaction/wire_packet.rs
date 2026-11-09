//! Exact lossless retry ownership. Canonical source columns remain separate;
//! only the redundant ingress/retry byte cache is packed. No hashes stand in
//! for byte equality, and no numeric value is narrowed or omitted.
use super::*;
pub struct RetryPacket {
    len: usize,
    bytes: Vec<u8>,
    packed: bool,
}
// Bounded literal/run blocks: literal tag 0..127 means 1..128 bytes;
// run tag 128..255 means 3..130 identical bytes. Worst-case raw caching wins.
fn blocks(input: &[u8], emit: &mut dyn FnMut(u8, &[u8])) {
    let run = |at: usize| {
        let mut n = 1;
        while n < 130 && at + n < input.len() && input[at + n] == input[at] {
            n += 1;
        }
        n
    };
    let mut at = 0;
    while at < input.len() {
        let n = run(at);
        if n >= 3 {
            emit(128 + (n - 3) as u8, &input[at..at + 1]);
            at += n;
        } else {
            let start = at;
            at += n;
            while at < input.len() && at - start < 128 {
                let n = run(at);
                if n >= 3 || at - start + n > 128 {
                    break;
                }
                at += n;
            }
            emit((at - start - 1) as u8, &input[start..at]);
        }
    }
}
impl RetryPacket {
    pub fn raw(bytes: &[u8]) -> Arc<Self> {
        Arc::new(Self {
            len: bytes.len(),
            bytes: bytes.to_vec(),
            packed: false,
        })
    }
    pub(super) fn certified(
        bytes: &[u8],
        _request: &super::wire::Request<'_>,
        _source: &GraphSession,
    ) -> Arc<Self> {
        let mut size = Some(0usize);
        blocks(bytes, &mut |_, payload| {
            size = size.and_then(|n| n.checked_add(1 + payload.len()))
        });
        let size = size.expect("bounded retry length");
        if size >= bytes.len() {
            return Self::raw(bytes);
        }
        let mut packed = Vec::with_capacity(size);
        blocks(bytes, &mut |tag, payload| {
            packed.push(tag);
            packed.extend_from_slice(payload);
        });
        assert_eq!(packed.len(), size);
        Arc::new(Self {
            len: bytes.len(),
            bytes: packed,
            packed: true,
        })
    }
    pub fn len(&self) -> usize {
        self.len
    }
    pub fn is_empty(&self) -> bool {
        self.len == 0
    }
    fn visit(&self, emit: &mut dyn FnMut(usize, &[u8])) {
        if !self.packed {
            emit(0, &self.bytes);
            return;
        }
        let (mut at, mut plain) = (0, 0);
        while at < self.bytes.len() {
            let tag = self.bytes[at];
            at += 1;
            if tag >= 128 {
                let n = (tag as usize & 127) + 3;
                let data = [self.bytes[at]; 130];
                at += 1;
                emit(plain, &data[..n]);
                plain += n;
            } else {
                let n = tag as usize + 1;
                emit(plain, &self.bytes[at..at + n]);
                at += n;
                plain += n;
            }
        }
        debug_assert_eq!(plain, self.len);
    }
    pub fn matches(&self, bytes: &[u8]) -> bool {
        if bytes.len() != self.len {
            return false;
        }
        let mut equal = true;
        self.visit(&mut |at, data| equal &= bytes.get(at..at + data.len()) == Some(data));
        equal
    }
    pub(super) fn range(&self, range: std::ops::Range<usize>) -> Vec<u8> {
        let mut out = vec![0; range.len()];
        self.visit(&mut |at, data| {
            let lo = at.max(range.start);
            let hi = (at + data.len()).min(range.end);
            if lo < hi {
                out[lo - range.start..hi - range.start].copy_from_slice(&data[lo - at..hi - at]);
            }
        });
        out
    }
    pub(super) fn owned_bytes(&self, _source: &GraphSession) -> Option<usize> {
        self.bytes
            .capacity()
            .checked_add(std::mem::size_of::<Self>())
    }
}
