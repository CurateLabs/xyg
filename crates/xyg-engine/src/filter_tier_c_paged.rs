//! Native issued-XYGC source leases for the shared count/membership kernels.
//! A lease owns no canonical-sized numeric vector and never uses the viewport
//! generation or LRU. Dimensions explicitly name an issued source and x/y plane.
use super::*;
use crate::chunked_columns::{
    self, CanonicalLease, CANONICAL_PAGE_OVERHEAD, MAX_CANONICAL_PAGE_ROWS,
};

pub(super) struct PagedSource {
    readers: Vec<CanonicalLease>,
    mapping: Vec<usize>,
    page_rows: usize,
    bytes: usize,
}
impl std::fmt::Debug for PagedSource {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.debug_struct("PagedSource")
            .field("readers", &self.readers.len())
            .field("mapping", &self.mapping)
            .field("page_rows", &self.page_rows)
            .finish()
    }
}
impl PagedSource {
    pub fn read(b: &[u8]) -> Result<Source> {
        let dimensions = usize_at(b, 56)?;
        let rows = usize_at(b, 64)?;
        let first = u64_at(b, 72)?;
        if dimensions == 0
            || dimensions > MAX_DIMS
            || u64_at(b, 24)? == 0
            || u64_at(b, 32)? == 0
            || u64_at(b, 40)? != 1
            || u64_at(b, 80)? != 0
            || u64_at(b, 88)? != 0
            || b.len() != add(HEADER, mul(dimensions, 16)?)?
            || first.checked_add(rows as u64).is_none()
        {
            return Err(Error::Malformed);
        }
        let mut readers = Vec::<CanonicalLease>::new();
        readers
            .try_reserve_exact(dimensions)
            .map_err(|_| Error::Allocation)?;
        let mut mapping = Vec::new();
        mapping
            .try_reserve_exact(dimensions)
            .map_err(|_| Error::Allocation)?;
        for dim in 0..dimensions {
            let reader = chunked_columns::reg_get(u64_at(b, HEADER + dim * 16)?)
                .ok_or(Error::Source)?
                .canonical_lease();
            let plane = usize_at(b, HEADER + dim * 16 + 8)?;
            if plane > 1 || reader.rows() != rows as u64 {
                return Err(Error::Source);
            }
            let slot = if let Some(slot) = readers.iter().position(|r| r.same_backing(&reader)) {
                slot
            } else {
                readers.push(reader);
                readers.len() - 1
            };
            mapping.push(slot * 2 + plane);
        }
        // A fixed 2 MiB read envelope bounds each turn independently of the
        // canonical row count. More physical sources reduce page length.
        let page_rows = ((2 * 1024 * 1024 - readers.len() * 144) / (readers.len() * 32))
            .min(MAX_CANONICAL_PAGE_ROWS as usize)
            .max(1);
        let mut bytes = add(
            128,
            add(mul(readers.capacity(), 64)?, mul(mapping.capacity(), 8)?)?,
        )?;
        for reader in &readers {
            bytes = add(
                bytes,
                usize::try_from(reader.immutable_bytes()).map_err(|_| Error::Budget)?,
            )?;
        }
        Ok(Source {
            id: u64_at(b, 24)?,
            epoch: u64_at(b, 32)?,
            revision: 1,
            first,
            rows,
            columns: Vec::new(),
            paged: Some(Self {
                readers,
                mapping,
                page_rows,
                bytes,
            }),
        })
    }
    pub fn dimensions(&self) -> usize {
        self.mapping.len()
    }
    pub fn bytes(&self) -> usize {
        self.bytes
    }
    pub fn workspace(&self, rows: usize) -> Result<usize> {
        // Conservative coexistence of all decoded pages, each raw read buffer,
        // fixed read slots and the outer column descriptors. No cached pages.
        mul(
            self.readers.len(),
            add(mul(rows.min(self.page_rows), 32)?, 144)?,
        )
    }
    pub fn visit(
        &self,
        start: usize,
        end: usize,
        cancelled: &(impl Fn() -> bool + ?Sized),
        work: &mut impl RowKernel,
    ) -> Result<()> {
        let mut first = start;
        while first < end {
            if cancelled() {
                return Err(Error::Cancelled);
            }
            let n = (end - first).min(self.page_rows);
            let mut columns = Vec::new();
            columns
                .try_reserve_exact(self.readers.len() * 2)
                .map_err(|_| Error::Allocation)?;
            for reader in &self.readers {
                let page = reader
                    .canonical_rows(
                        first as u64,
                        n as u32,
                        n as u64 * 32 + CANONICAL_PAGE_OVERHEAD,
                        || !cancelled(),
                    )
                    .map_err(|error| match error {
                        chunked_columns::Error::Cancelled => Error::Cancelled,
                        chunked_columns::Error::BudgetExceeded { .. } => Error::Budget,
                        chunked_columns::Error::Io(error)
                            if error.kind() == std::io::ErrorKind::OutOfMemory =>
                        {
                            Error::Allocation
                        }
                        _ => Error::Source,
                    })?;
                columns.push(page.x);
                columns.push(page.y);
            }
            let block = RowBlock {
                origin: first,
                columns: &columns,
                mapping: Some(&self.mapping),
            };
            for row in first..first + n {
                if (row - first) % 4096 == 0 && cancelled() {
                    return Err(Error::Cancelled);
                }
                work.row(&block, row)?;
            }
            first += n;
        }
        if cancelled() {
            return Err(Error::Cancelled);
        }
        Ok(())
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::time::{SystemTime, UNIX_EPOCH};

    const FIRST: u64 = (1 << 63) + 17;
    fn packet(op: u32, seq: u64, budget: u64, args: [u64; 3], payload: &[u8]) -> Vec<u8> {
        let mut b = vec![0; HEADER];
        b[..4].copy_from_slice(b"XYFC");
        b[4..8].copy_from_slice(&(if op == 16 { 2u32 } else { 1 }).to_le_bytes());
        b[8..12].copy_from_slice(&op.to_le_bytes());
        for (i, v) in [seq, 7, 1, 1, budget, args[0], args[1], args[2]]
            .iter()
            .enumerate()
        {
            put(&mut b, 16 + i * 8, *v);
        }
        b.extend_from_slice(payload);
        b
    }
    fn word(out: &mut Vec<u8>, value: u64) {
        out.extend_from_slice(&value.to_le_bytes());
    }
    fn checked(session: &mut FilterTierCSession, b: &[u8]) -> Vec<u8> {
        let out = session.execute(b, 1 << 20, || false).unwrap();
        assert_eq!(u32_at(&out, 8), Ok(0));
        out
    }
    fn same(mut a: Vec<u8>, mut b: Vec<u8>) {
        // Physical source ownership and page workspace differ; semantic fields,
        // complete count/paint planes, hashes and membership must not differ.
        a[80..96].fill(0);
        b[80..96].fill(0);
        assert_eq!(a, b);
    }

    #[test]
    fn filter_tier_c_issued_pages_match_resident_build_scan_membership_and_recovery() {
        let path = std::env::temp_dir().join(format!(
            "xyg-filter-pages-{}-{}",
            std::process::id(),
            SystemTime::now()
                .duration_since(UNIX_EPOCH)
                .unwrap()
                .as_nanos()
        ));
        let n = 140_003;
        let x: Vec<_> = (0..n)
            .map(|i| if i % 1009 == 0 { f64::NAN } else { i as f64 })
            .collect();
        let y: Vec<_> = (0..n)
            .map(|i| {
                if i % 997 == 0 {
                    f64::INFINITY
                } else {
                    (i % 37) as f64 - 18.
                }
            })
            .collect();
        chunked_columns::ChunkedColumns::create(
            &path,
            x.iter().copied().zip(y.iter().copied()),
            8192,
        )
        .unwrap();
        let handle = chunked_columns::reg_open(&path).unwrap();
        let independent = chunked_columns::reg_get(handle).unwrap();
        independent.set_generation(999);
        let warm = independent
            .read_page(0., (n - 1) as f64, None, 16 << 20, 999, 0)
            .unwrap();
        assert!(warm.read.resident_bytes > 0);
        drop(warm);
        let budget = 16 << 20;
        let mut dimensions = Vec::new();
        for plane in [0, 1, 1] {
            word(&mut dimensions, handle);
            word(&mut dimensions, plane);
        }
        let mut disk = FilterTierCSession::default();
        let mut resident = FilterTierCSession::default();
        let open = packet(16, 1, budget, [3, n as u64, FIRST], &dimensions);
        assert_eq!(disk.execute(&open, 0, || false), Err(REPLY_HEADER));
        assert!(disk.source.is_none());
        let mut open = open;
        put(&mut open, 16, 2);
        let mut columns = Vec::new();
        for c in [&x, &y, &y] {
            for v in c {
                word(&mut columns, v.to_bits());
            }
        }
        let mut ingested = checked(
            &mut resident,
            &packet(1, 2, budget, [3, n as u64, FIRST], &columns),
        );
        assert_eq!(u64_at(&ingested, 96), Ok(n as u64));
        put(&mut ingested, 96, 0);
        same(checked(&mut disk, &open), ingested);
        let pinned = disk.source.as_ref().unwrap().paged.as_ref().unwrap();
        assert_eq!(pinned.readers.len(), 1);
        assert_eq!(pinned.mapping, [0, 1, 1]);
        assert!(disk.retained_bytes() < 65536);
        assert!(chunked_columns::reg_remove(handle));
        assert!(independent.is_current(999));
        let viewport = std::sync::Arc::downgrade(&independent);
        drop(independent);
        assert!(viewport.upgrade().is_none());
        let mut config = Vec::new();
        word(&mut config, 3);
        for cut in [35000f64, 70000., 105000.] {
            word(&mut config, cut.to_bits());
        }
        for view in 1..=5 {
            word(&mut config, view);
            word(&mut config, 0);
            word(&mut config, 1 + view % 2);
            config.extend_from_slice(&8u32.to_le_bytes());
            config.extend_from_slice(&8u32.to_le_bytes());
            for v in [-1., n as f64 + 1., -19., 19.] {
                word(&mut config, v.to_bits());
            }
            config.extend_from_slice(&[0; 16]);
        }
        let build = packet(10, 3, budget, [1, 0, 5], &config);
        same(checked(&mut disk, &build), checked(&mut resident, &build));
        let mut query = packet(5, 4, budget, [0; 3], &[]);
        query[12..16].copy_from_slice(&1u32.to_le_bytes());
        put(&mut query, 80, 25000f64.to_bits());
        put(&mut query, 88, 80000f64.to_bits());
        let a = checked(&mut disk, &query);
        assert_eq!(u64_at(&a, 64), Ok(2));
        assert_eq!(u64_at(&a, 96), Ok(n as u64));
        assert_eq!(
            u64_at(&a, 128),
            Ok(x.iter().filter(|v| **v >= 25000. && **v <= 80000.).count() as u64)
        );
        same(a, checked(&mut resident, &query));
        let mut paint = packet(11, 5, budget, [0; 3], &[]);
        paint[12..16].copy_from_slice(&1u32.to_le_bytes());
        same(checked(&mut disk, &paint), checked(&mut resident, &paint));
        let membership = packet(9, 6, budget, [FIRST + 65520, 500, 0], &[]);
        let a = checked(&mut disk, &membership);
        same(a, checked(&mut resident, &membership));
        let evict = packet(6, 7, budget, [0; 3], &[]);
        same(checked(&mut disk, &evict), checked(&mut resident, &evict));
        let rebuild = packet(4, 8, budget, [0; 3], &[]);
        let calls = Cell::new(0);
        let cancelled = disk
            .execute(&rebuild, 1 << 20, || {
                calls.set(calls.get() + 1);
                calls.get() > 10
            })
            .unwrap();
        assert_eq!(u32_at(&cancelled, 8), Ok(Error::Cancelled as u32));
        assert_eq!(disk.revision, 7);
        assert!(disk.index.is_none());
        let prior = disk.fingerprint();
        let retained = disk.retained_bytes();
        let rebuild = packet(4, 9, budget, [0; 3], &[]);
        assert!(matches!(
            disk.begin_cooperative(&rebuild, 1 << 20, || false),
            Ok(CooperativeReply::Pending { .. })
        ));
        let calls = Cell::new(0);
        let cancelled = disk
            .advance_cooperative(9, 1 << 20, || {
                calls.set(calls.get() + 1);
                calls.get() > 7
            })
            .unwrap();
        assert!(
            matches!(cancelled,CooperativeReply::Complete(ref b) if u32_at(b,8)==Ok(Error::Cancelled as u32))
        );
        assert_eq!(disk.fingerprint(), prior);
        assert_eq!(disk.revision, 7);
        assert!(disk.pending.is_none());
        assert!(disk.index.is_none());
        assert_eq!(disk.retained_bytes(), retained);
        let rebuild = packet(4, 10, budget, [0; 3], &[]);
        let mut response = disk.begin_cooperative(&rebuild, 1 << 20, || false).unwrap();
        let mut turns = 0;
        let actual = loop {
            match response {
                CooperativeReply::Complete(b) => break b,
                CooperativeReply::Pending { token, rows, .. } => {
                    assert_eq!(disk.revision, 7);
                    assert!(disk.index.is_none());
                    assert!(rows <= 140_003);
                    turns += 1;
                    response = disk.advance_cooperative(token, 1 << 20, || false).unwrap();
                }
            }
        };
        assert!(turns > 50);
        same(actual, checked(&mut resident, &rebuild));
        // Indexed queries survive loss of backing bytes: they read no rows.
        std::fs::OpenOptions::new()
            .write(true)
            .open(&path)
            .unwrap()
            .set_len(0)
            .unwrap();
        let mut query = packet(5, 11, budget, [0; 3], &[]);
        put(&mut query, 80, 35000f64.to_bits());
        put(&mut query, 88, 69999f64.to_bits());
        let a = checked(&mut disk, &query);
        assert_eq!(u64_at(&a, 64), Ok(3));
        assert_eq!(u64_at(&a, 96), Ok(0));
        same(a, checked(&mut resident, &query));
        let prior = disk.fingerprint();
        put(&mut query, 16, 12);
        query[12..16].copy_from_slice(&1u32.to_le_bytes());
        put(&mut query, 80, 35000.25f64.to_bits());
        let failed = disk.execute(&query, 1 << 20, || false).unwrap();
        assert_eq!(u32_at(&failed, 8), Ok(Error::Source as u32));
        assert_eq!(disk.fingerprint(), prior);
        assert_eq!(disk.revision, 11);
        drop(disk);
        std::fs::remove_file(path).unwrap();
    }
}
