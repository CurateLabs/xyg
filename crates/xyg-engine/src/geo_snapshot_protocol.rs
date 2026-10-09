//! Fixed mutation / leased immutable read seam for retained-frame export.
//! XYGJ/XYGW v1; full provenance lives in XYGX v2. No I/O or host policy.
use crate::geo_snapshot::{
    GeoFrozenArtifact, GeoFrozenFormat, GeoFrozenSnapshot, GeoSnapshotError,
    MAX_FROZEN_ARTIFACT_BYTES, MAX_FROZEN_BYTES, MAX_FROZEN_PEAK,
};
use crate::geo_source::SourceError;
use crate::geo_tile_cache::{GeoTileCache, GeoTileLimits, TILE_CACHE_PROCESS_BYTES};
use std::sync::{Mutex, OnceLock};

pub const HEADER: usize = 256;
pub const MAX_REQUEST: usize = HEADER;
pub const MAX_HANDLES: usize = 16;
pub const MAX_SNAPSHOTS: usize = 8;
pub const MAX_ARTIFACTS: usize = 8;
type Result<T> = std::result::Result<T, GeoSnapshotError>;
enum Entry {
    Snapshot {
        value: Box<GeoFrozenSnapshot>,
        #[cfg_attr(not(feature = "raster"), allow(dead_code))]
        sequence: u64,
        reads: u8,
    },
    #[cfg_attr(not(feature = "raster"), allow(dead_code))]
    Artifact {
        value: Box<GeoFrozenArtifact>,
        artifact_reads: u8,
        companion_reads: u8,
    },
}
struct Registry {
    next: u64,
    entries: Vec<(u64, Entry)>,
    cache: Option<GeoTileCache>,
}
static REGISTRY: OnceLock<Mutex<Registry>> = OnceLock::new();
fn registry() -> &'static Mutex<Registry> {
    REGISTRY.get_or_init(|| {
        Mutex::new(Registry {
            next: 1,
            entries: Vec::new(),
            cache: None,
        })
    })
}
fn u32at(b: &[u8], at: usize) -> u32 {
    u32::from_le_bytes(b[at..at + 4].try_into().unwrap())
}
fn u64at(b: &[u8], at: usize) -> u64 {
    u64::from_le_bytes(b[at..at + 8].try_into().unwrap())
}
fn put32(b: &mut [u8], at: usize, v: u32) {
    b[at..at + 4].copy_from_slice(&v.to_le_bytes());
}
fn put64(b: &mut [u8], at: usize, v: u64) {
    b[at..at + 8].copy_from_slice(&v.to_le_bytes());
}
fn frame(b: &[u8]) -> Result<u32> {
    if b.len() != HEADER
        || &b[..4] != b"XYGJ"
        || u32at(b, 4) != 1
        || b[12..16].iter().any(|n| *n != 0)
        || b[56..HEADER].iter().any(|n| *n != 0)
    {
        return Err(GeoSnapshotError::Invalid);
    }
    let command = u32at(b, 8);
    if !matches!(command,1..=6|20..=22)
        || (!matches!(command, 1 | 4 | 5 | 6) && u64at(b, 24) != 0)
        || (command != 2 && b[40..56].iter().any(|n| *n != 0))
        || (command == 3 && u64at(b, 32) != 0)
    {
        return Err(GeoSnapshotError::Invalid);
    }
    if matches!(command, 1 | 4 | 5 | 6)
        && (u64at(b, 24) == 0 || u64at(b, 32) > MAX_FROZEN_PEAK as u64)
    {
        return Err(GeoSnapshotError::Invalid);
    }
    if command == 2
        && (u64at(b, 32) > TILE_CACHE_PROCESS_BYTES as u64
            || !f64::from_bits(u64at(b, 48)).is_finite())
    {
        return Err(GeoSnapshotError::Invalid);
    }
    if matches!(command, 20..=22) && u64at(b, 32) != 0 {
        return Err(GeoSnapshotError::Invalid);
    }
    Ok(command)
}
fn reply(handle: u64, sequence: u64, kind: u32, bytes: usize, companion: usize) -> [u8; HEADER] {
    let mut b = [0; HEADER];
    b[..4].copy_from_slice(b"XYGW");
    put32(&mut b, 4, 1);
    put32(&mut b, 8, kind);
    put64(&mut b, 16, handle);
    put64(&mut b, 24, sequence);
    put64(&mut b, 32, bytes as u64);
    put64(&mut b, 40, companion as u64);
    b
}
fn cache(r: &mut Registry) -> Result<&GeoTileCache> {
    if r.cache.is_none() {
        r.cache = Some(
            GeoTileCache::new(GeoTileLimits::default(), 0).map_err(|_| GeoSnapshotError::Limit)?,
        );
    }
    Ok(r.cache.as_ref().unwrap())
}
fn insert(r: &mut Registry, entry: Entry) -> Result<u64> {
    if r.entries.len() >= MAX_HANDLES || r.next == u64::MAX {
        return Err(GeoSnapshotError::Limit);
    }
    let id = r.next;
    r.next += 1;
    r.entries.push((id, entry));
    Ok(id)
}
fn source_error(e: SourceError) -> GeoSnapshotError {
    match e {
        SourceError::ResourceLimit => GeoSnapshotError::Limit,
        SourceError::StaleSource => GeoSnapshotError::Stale,
        _ => GeoSnapshotError::Invalid,
    }
}
/// Registry order is snapshot -> source -> derived ledger. The source callback
/// only borrows immutable storage and may not reenter the source registry.
pub fn execute(b: &[u8]) -> Result<[u8; HEADER]> {
    let command = frame(b)?;
    if !matches!(command, 1..=6) {
        return Err(GeoSnapshotError::Invalid);
    }
    let handle = u64at(b, 16);
    let sequence = u64at(b, 24);
    let mut r = registry().lock().map_err(|_| GeoSnapshotError::Limit)?;
    if command == 3 {
        let at = r
            .entries
            .iter()
            .position(|(id, _)| *id == handle)
            .ok_or(GeoSnapshotError::Stale)?;
        r.entries.remove(at);
        if r.entries.is_empty() {
            r.cache = None;
        }
        return Ok(reply(handle, 0, 0, 0, 0));
    }
    if r.entries.len() >= MAX_HANDLES || r.next == u64::MAX {
        return Err(GeoSnapshotError::Limit);
    }
    let result = (|| {
        if matches!(command, 1 | 4 | 5 | 6) {
            if r.entries
                .iter()
                .filter(|(_, e)| matches!(e, Entry::Snapshot { .. }))
                .count()
                >= MAX_SNAPSHOTS
            {
                return Err(GeoSnapshotError::Limit);
            }
            let budget = usize::try_from(u64at(b, 32)).map_err(|_| GeoSnapshotError::Limit)?;
            let value = if command == 6 {
                crate::geo_scale_protocol::with_overview_data(
                    handle,
                    sequence,
                    |scene, result, camera| {
                        crate::geo_snapshot::overview_admission(scene, result, camera, budget)
                            .map_err(|e| match e {
                                GeoSnapshotError::Limit => SourceError::ResourceLimit,
                                GeoSnapshotError::Stale => SourceError::StaleSource,
                                _ => SourceError::InvalidFrame,
                            })?;
                        GeoFrozenSnapshot::freeze_overview(
                            cache(&mut r).map_err(|_| SourceError::ResourceLimit)?,
                            scene,
                            result,
                            camera,
                            budget,
                        )
                        .map_err(|e| match e {
                            GeoSnapshotError::Limit => SourceError::ResourceLimit,
                            GeoSnapshotError::Stale => SourceError::StaleSource,
                            _ => SourceError::InvalidFrame,
                        })
                    },
                )
                .map_err(source_error)?
            } else if command == 5 {
                crate::geo_mixed_protocol::with_source_scene(
                    handle,
                    sequence,
                    |frame, foreground| {
                        GeoFrozenSnapshot::freeze_mixed(cache(&mut r)?, frame, foreground, budget)
                    },
                )
                .map_err(source_error)??
            } else if command == 4 {
                crate::geo_tile_protocol::with_frame_data(handle, sequence, |view| {
                    GeoFrozenSnapshot::freeze_tile(cache(&mut r)?, &view, budget)
                })
                .map_err(|e| match e {
                    crate::geo_tile_protocol::TileProtocolError::Geo(
                        crate::geo::GeoError::ResourceLimit,
                    ) => GeoSnapshotError::Limit,
                    crate::geo_tile_protocol::TileProtocolError::Geo(
                        crate::geo::GeoError::StaleHandle,
                    ) => GeoSnapshotError::Stale,
                    _ => GeoSnapshotError::Invalid,
                })??
            } else {
                crate::geo_scale_protocol::with_scene_data(handle, sequence, |view| {
                    if view.source.digest() != view.result.key.identity.source_digest
                        || view.source.generation() != view.result.key.identity.generation
                        || view.source.rows() != view.result.key.identity.source_rows
                    {
                        return Err(GeoSnapshotError::Stale);
                    }
                    GeoFrozenSnapshot::freeze_lod(
                        cache(&mut r)?,
                        view.scene,
                        view.result,
                        view.snapshot,
                        view.style,
                        budget,
                    )
                })
                .map_err(source_error)??
            };
            let size = value.bytes().len();
            let id = insert(
                &mut r,
                Entry::Snapshot {
                    value: Box::new(value),
                    sequence,
                    reads: 0,
                },
            )?;
            return Ok(reply(id, sequence, 0, size, 0));
        }
        let format = GeoFrozenFormat::from_code(u32at(b, 40))?;
        let quality = u32at(b, 44) as i32;
        let scale = f64::from_bits(u64at(b, 48));
        if !(1..=100).contains(&quality) || scale <= 0. {
            return Err(GeoSnapshotError::Invalid);
        }
        if r.entries
            .iter()
            .filter(|(_, e)| matches!(e, Entry::Artifact { .. }))
            .count()
            >= MAX_ARTIFACTS
        {
            return Err(GeoSnapshotError::Limit);
        }
        #[cfg(not(feature = "raster"))]
        {
            let _ = (format, quality, scale);
            Err(GeoSnapshotError::Unsupported)
        }
        #[cfg(feature = "raster")]
        {
            let budget = usize::try_from(u64at(b, 32)).map_err(|_| GeoSnapshotError::Limit)?;
            let Entry::Snapshot {
                value, sequence, ..
            } = &r
                .entries
                .iter()
                .find(|(id, _)| *id == handle)
                .ok_or(GeoSnapshotError::Stale)?
                .1
            else {
                return Err(GeoSnapshotError::Stale);
            };
            let sequence = *sequence;
            let artifact = value.export(
                r.cache.as_ref().ok_or(GeoSnapshotError::Stale)?,
                value.identity(),
                format,
                scale,
                quality,
                budget,
            )?;
            let size = artifact.bytes().len();
            let paired = artifact.snapshot().len();
            let id = insert(
                &mut r,
                Entry::Artifact {
                    value: Box::new(artifact),
                    artifact_reads: 0,
                    companion_reads: 0,
                },
            )?;
            let mut out = reply(id, sequence, 1, size, paired);
            put32(&mut out, 48, format as u32);
            put32(&mut out, 52, quality as u32);
            put64(&mut out, 56, scale.to_bits());
            Ok(out)
        }
    })();
    if result.is_err() && r.entries.is_empty() {
        r.cache = None;
    }
    result
}
fn bytes(entry: &Entry, command: u32) -> Result<&[u8]> {
    match (entry, command) {
        (Entry::Snapshot { value, .. }, 20) => Ok(value.bytes()),
        (Entry::Artifact { value, .. }, 21) => Ok(value.snapshot()),
        (Entry::Artifact { value, .. }, 22) => Ok(value.bytes()),
        _ => Err(GeoSnapshotError::Stale),
    }
}
fn admission(b: &[u8], budget: usize) -> Result<u32> {
    let command = frame(b)?;
    if !matches!(command, 20..=22) || budget > TILE_CACHE_PROCESS_BYTES || budget < HEADER {
        return Err(GeoSnapshotError::Invalid);
    }
    Ok(command)
}
pub fn data_len(b: &[u8], budget: usize) -> Result<usize> {
    let command = admission(b, budget)?;
    let r = registry().lock().map_err(|_| GeoSnapshotError::Limit)?;
    let e = &r
        .entries
        .iter()
        .find(|(id, _)| *id == u64at(b, 16))
        .ok_or(GeoSnapshotError::Stale)?
        .1;
    let length = bytes(e, command)?.len();
    let cap = if command == 22 {
        MAX_FROZEN_ARTIFACT_BYTES
    } else {
        MAX_FROZEN_BYTES
    };
    if length > cap
        || length
            .checked_mul(4)
            .and_then(|n| n.checked_add(HEADER))
            .is_none_or(|n| n > budget)
    {
        return Err(GeoSnapshotError::Limit);
    }
    Ok(length)
}
pub fn read_data(b: &[u8], budget: usize) -> Result<Vec<u8>> {
    let command = admission(b, budget)?;
    let mut r = registry().lock().map_err(|_| GeoSnapshotError::Limit)?;
    let entry = &mut r
        .entries
        .iter_mut()
        .find(|(id, _)| *id == u64at(b, 16))
        .ok_or(GeoSnapshotError::Stale)?
        .1;
    let length = bytes(entry, command)?.len();
    let cap = if command == 22 {
        MAX_FROZEN_ARTIFACT_BYTES
    } else {
        MAX_FROZEN_BYTES
    };
    if length > cap
        || length
            .checked_mul(4)
            .and_then(|n| n.checked_add(HEADER))
            .is_none_or(|n| n > budget)
    {
        return Err(GeoSnapshotError::Limit);
    }
    let counter = match (&mut *entry, command) {
        (Entry::Snapshot { reads, .. }, 20) => reads,
        (
            Entry::Artifact {
                companion_reads, ..
            },
            21,
        ) => companion_reads,
        (Entry::Artifact { artifact_reads, .. }, 22) => artifact_reads,
        _ => return Err(GeoSnapshotError::Stale),
    };
    if *counter >= 2 {
        return Err(GeoSnapshotError::Limit);
    }
    *counter += 1;
    Ok(bytes(entry, command)?.to_vec())
}

#[cfg(test)]
mod tests {
    use crate::geo::{GeoColumn, GeoCrs, GeoDescriptor, GeoGeometry, GeoLimits};
    use crate::geo_scale_protocol::{data_len, execute, read_data, HEADER};
    use crate::geo_source::{GeoChunk, GeoIntervals, GeoSourceManifest, SourceError};
    use crate::geo_source_session::test_processor_lock;
    fn u32_at(b: &[u8], at: usize) -> u32 {
        u32::from_le_bytes(b[at..at + 4].try_into().unwrap())
    }
    fn u64_at(b: &[u8], at: usize) -> u64 {
        u64::from_le_bytes(b[at..at + 8].try_into().unwrap())
    }
    fn p32(b: &mut [u8], at: usize, x: u32) {
        b[at..at + 4].copy_from_slice(&x.to_le_bytes());
    }
    fn p64(b: &mut [u8], at: usize, x: u64) {
        b[at..at + 8].copy_from_slice(&x.to_le_bytes());
    }
    fn request(command: u32, handle: u64, sequence: u64, payload: &[u8]) -> Vec<u8> {
        let mut b = vec![0; HEADER];
        b[..4].copy_from_slice(b"XYGQ");
        p32(&mut b, 4, 1);
        p32(&mut b, 8, command);
        p64(&mut b, 16, handle);
        p64(&mut b, 24, sequence);
        p64(&mut b, 232, payload.len() as u64);
        b.extend(payload);
        b
    }
    fn with_budget(mut b: Vec<u8>) -> Vec<u8> {
        p64(&mut b, 32, 128 << 20);
        p64(&mut b, 40, 1_000_000);
        p64(&mut b, 48, 128 << 20);
        p32(&mut b, 56, 65536);
        p32(&mut b, 60, 4096);
        b
    }
    struct Handle(u64);
    impl Drop for Handle {
        fn drop(&mut self) {
            let _ = execute(&request(10, self.0, 0, &[]));
        }
    }
    fn builder() -> Handle {
        Handle(u64_at(&execute(&request(1, 0, 0, &[])).unwrap(), 16))
    }
    fn chunk(id: u64, start: i64, x: f64) -> Vec<u8> {
        let c = GeoColumn::from_descriptor(GeoDescriptor {
            geometry: GeoGeometry::Point,
            crs: GeoCrs::Epsg4326,
            xy: &[x, 0.],
            validity: &[1],
            feature_ids: Some(&[id]),
            offsets0: &[],
            offsets1: &[],
            offsets2: &[],
            limits: GeoLimits::default(),
        })
        .unwrap();
        GeoChunk::encode(
            &c,
            Some(GeoIntervals {
                starts: &[start],
                ends: &[start + 10],
                start_validity: &[1],
                end_validity: &[1],
            }),
        )
        .unwrap()
    }
    fn finish_manifest(chunks: &[Vec<u8>]) -> (Handle, Vec<u8>) {
        let h = builder();
        for c in chunks {
            execute(&request(2, h.0, 0, c)).unwrap();
        }
        let mut b = request(3, h.0, 0, &[]);
        p64(&mut b, 144, u64::MAX);
        execute(&b).unwrap();
        let bytes = read_data(&request(21, h.0, 0, &[]), 128 << 20).unwrap();
        (h, bytes)
    }
    fn begin(
        h: u64,
        seq: u64,
        manifest: &GeoSourceManifest,
        instant: Option<i64>,
        work: u64,
    ) -> Vec<u8> {
        let mut b = with_budget(request(5, h, seq, &[]));
        p32(&mut b, 12, 1);
        p32(&mut b, 64, 4326);
        p32(&mut b, 72, 32768);
        p32(&mut b, 76, 1);
        for (at, v) in [
            (80, 0f64),
            (88, 0.),
            (96, 0.),
            (104, 800.),
            (112, 600.),
            (120, 0.),
            (128, 0.),
        ] {
            p64(&mut b, at, v.to_bits());
        }
        b[136..144].copy_from_slice(&manifest.digest());
        p64(&mut b, 144, manifest.generation());
        p64(&mut b, 152, u64::MAX);
        for at in [160, 168, 176, 184, 192] {
            p64(&mut b, at, seq);
        }
        if let Some(t) = instant {
            p32(&mut b, 200, 1);
            p64(&mut b, 208, t as u64);
        }
        p64(&mut b, 224, work);
        b
    }
    fn step(h: u64, seq: u64) -> [u8; HEADER] {
        execute(&request(6, h, seq, &[])).unwrap()
    }
    fn ticket(reply: &[u8]) -> Vec<u8> {
        reply[64..160].to_vec()
    }
    fn supply(h: u64, _seq: u64, t: &[u8], bytes: &[u8]) -> Result<[u8; HEADER], SourceError> {
        let mut p = t.to_vec();
        p.extend(bytes);
        execute(&request(7, h, 0, &p))
    }
    fn release(h: u64, _seq: u64, t: &[u8]) {
        execute(&request(8, h, 0, t)).unwrap();
    }
    fn drive(h: u64, seq: u64, chunks: &[Vec<u8>]) -> (u32, Vec<u32>) {
        let mut reads = Vec::new();
        loop {
            let s = step(h, seq);
            let code = u32_at(&s, 8);
            if code != 1 {
                return (code, reads);
            }
            let t = ticket(&s);
            let i = u32_at(&t, 40);
            reads.push(i);
            supply(h, seq, &t, &chunks[i as usize]).unwrap();
            assert_eq!(u32_at(&step(h, seq), 8), 2);
            release(h, seq, &t);
        }
    }
    fn scene_request(h: u64, seq: u64) -> Vec<u8> {
        let mut style = vec![0; 48];
        style[..4].copy_from_slice(&[255, 0, 0, 255]);
        p64(&mut style, 16, 6f64.to_bits());
        p64(&mut style, 24, 1f64.to_bits());
        with_budget(request(11, h, seq, &style))
    }
    struct SceneFixture {
        bytes: Vec<u8>,
        _handle: Handle,
    }
    fn scene_data(h: u64, seq: u64) -> Result<SceneFixture, SourceError> {
        let fixed = execute(&scene_request(h, seq))?;
        let data = Handle(u64_at(&fixed, 16));
        for _ in 0..4 {
            assert_eq!(
                data_len(&request(23, data.0, 0, &[]), 128 << 20)?,
                u64_at(&fixed, 32) as usize
            );
        }
        let bytes = read_data(&request(23, data.0, 0, &[]), 128 << 20)?;
        assert_eq!(u64_at(&fixed, 32), bytes.len() as u64);
        assert_eq!(u64_at(&fixed, 40), h);
        Ok(SceneFixture {
            bytes,
            _handle: data,
        })
    }

    fn export_request(command: u32, handle: u64, sequence: u64, budget: u64) -> Vec<u8> {
        let mut b = vec![0; 256];
        b[..4].copy_from_slice(b"XYGJ");
        p32(&mut b, 4, 1);
        p32(&mut b, 8, command);
        p64(&mut b, 16, handle);
        p64(&mut b, 24, sequence);
        p64(&mut b, 32, budget);
        b
    }
    #[test]
    fn immutable_frame_freeze_reads_and_phase_admission_survive_source_disposal() {
        let _guard = test_processor_lock();
        let chunks = [chunk(u64::MAX, i64::MIN, 0.)];
        let (builder, bytes) = finish_manifest(&chunks);
        let manifest = GeoSourceManifest::validate(
            &bytes,
            &mut |r: crate::geo_source::ReadRequest| Ok(chunks[r.chunk_index as usize].clone()),
            &mut || false,
        )
        .unwrap();
        let session = Handle(u64_at(
            &execute(&with_budget(request(4, 0, 0, &bytes))).unwrap(),
            16,
        ));
        assert_eq!(drive(session.0, 0, &chunks).0, 3);
        execute(&begin(session.0, u64::MAX, &manifest, Some(i64::MIN), 100)).unwrap();
        assert_eq!(drive(session.0, u64::MAX, &chunks).0, 4);
        let frame = scene_data(session.0, u64::MAX).unwrap();
        assert_eq!(&frame.bytes[..4], b"XYGZ");
        drop(session);
        drop(builder);
        let transport = crate::geo_transport::GeoTransportLease::acquire().unwrap();
        let tiny = transport
            .with_phase(256, |phase| {
                crate::geo_retained_painter::prepare_frame_painter(frame._handle.0, u64::MAX, phase)
            })
            .unwrap();
        assert!(matches!(tiny, Err(SourceError::ResourceLimit)));
        let painter = transport
            .with_phase(128 << 20, |phase| {
                crate::geo_retained_painter::prepare_frame_painter(frame._handle.0, u64::MAX, phase)
            })
            .unwrap()
            .unwrap();
        assert_eq!(painter.records, 1);
        assert_eq!(painter.styles, 1);
        assert_eq!(&painter.bytes[..4], b"XYPB");
        drop(painter);
        drop(transport);
        let fixed =
            super::execute(&export_request(1, frame._handle.0, u64::MAX, 128 << 20)).unwrap();
        let frozen = u64_at(&fixed, 16);
        drop(frame);
        let q = export_request(20, frozen, 0, 0);
        for _ in 0..4 {
            assert_eq!(
                super::data_len(&q, 128 << 20).unwrap(),
                u64_at(&fixed, 32) as usize
            );
        }
        let bytes = super::read_data(&q, 128 << 20).unwrap();
        assert_eq!(&bytes[..4], b"XYGX");
        assert_eq!(u32_at(&bytes, 4), 2);
        let _second = super::read_data(&q, 128 << 20).unwrap();
        assert!(matches!(
            super::read_data(&q, 128 << 20),
            Err(crate::geo_snapshot::GeoSnapshotError::Limit)
        ));
        for at in [12, 56, 255] {
            let mut bad = export_request(3, frozen, 0, 0);
            bad[at] = 1;
            assert!(super::execute(&bad).is_err());
        }
        assert!(super::execute(&export_request(1, frozen, 1, 128 << 20)).is_err());
        #[cfg(feature = "raster")]
        for format in 0..6 {
            let mut q = export_request(2, frozen, 0, 384 << 20);
            p32(&mut q, 40, format);
            p32(&mut q, 44, 90);
            p64(&mut q, 48, 1f64.to_bits());
            let fixed = super::execute(&q).unwrap();
            let artifact = u64_at(&fixed, 16);
            let data = super::read_data(&export_request(22, artifact, 0, 0), 384 << 20).unwrap();
            let paired = super::read_data(&export_request(21, artifact, 0, 0), 384 << 20).unwrap();
            let cache = crate::geo_tile_cache::GeoTileCache::new(
                crate::geo_tile_cache::GeoTileLimits::default(),
                0,
            )
            .unwrap();
            let snapshot =
                crate::geo_snapshot::GeoFrozenSnapshot::decode(&cache, &paired, 128 << 20).unwrap();
            snapshot.verify_artifact(&data).unwrap();
            assert_eq!(snapshot.direct()[0].feature_id, u64::MAX);
            assert_eq!(snapshot.identity().time_revision, u64::MAX);
            drop(snapshot);
            drop(cache);
            drop(data);
            drop(paired);
            super::execute(&export_request(3, artifact, 0, 0)).unwrap();
        }
        #[cfg(not(feature = "raster"))]
        {
            let mut q = export_request(2, frozen, 0, 384 << 20);
            p32(&mut q, 44, 90);
            p64(&mut q, 48, 1f64.to_bits());
            assert!(matches!(
                super::execute(&q),
                Err(crate::geo_snapshot::GeoSnapshotError::Unsupported)
            ));
        }
        drop(bytes);
        drop(_second);
        super::execute(&export_request(3, frozen, 0, 0)).unwrap();
        assert!(super::data_len(&q, 128 << 20).is_err());
    }
}
