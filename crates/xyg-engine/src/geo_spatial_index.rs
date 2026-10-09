//! Authenticated derived point sidecar. Dossier §27/§28; geo-spatial-index.md.
use crate::geo::{GeoCrs, GeoGeometry};
use crate::geo_source::{FeatureRef, GeoSourceManifest, SourceError, TimePredicate};
use crate::geo_source_session::GeoProcessorLease;
use crate::geo_viewport::{GeoViewport, WEB_MERCATOR_MAX, lonlat_to_mercator};
use crate::transition::Blake2s8;
pub(crate) type Result<T> = std::result::Result<T, SourceError>;
pub const PAGE_BYTES: usize = 65_536;
pub(crate) const PAGE_HEADER: usize = 64;
pub(crate) const RECORD_BYTES: usize = 80;
pub const PAGE_RECORDS: usize = (PAGE_BYTES - PAGE_HEADER) / RECORD_BYTES;
pub const DIRECTORY_BYTES: usize = 32 << 20;
pub(crate) const ENTRY_BYTES: usize = 96;
pub(crate) const HEADER: usize = 128;
pub const MAX_FRONTIER: usize = 256;
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct GeoSpatialOptions {
    pub grid: u32,
}
impl Default for GeoSpatialOptions {
    fn default() -> Self {
        Self { grid: 16 }
    }
}
impl GeoSpatialOptions {
    pub fn validate(self) -> Result<()> {
        if self.grid == 0 || self.grid > 256 || !self.grid.is_power_of_two() {
            return Err(SourceError::InvalidFrame);
        }
        Ok(())
    }
}
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct GeoSpatialRead {
    pub page: u64,
    pub encoded_bytes: usize,
    pub digest: [u8; 8],
}
pub trait GeoSpatialReader {
    fn read(&mut self, request: GeoSpatialRead) -> Result<Vec<u8>>;
}
impl<F: FnMut(GeoSpatialRead) -> Result<Vec<u8>>> GeoSpatialReader for F {
    fn read(&mut self, request: GeoSpatialRead) -> Result<Vec<u8>> {
        self(request)
    }
}
#[derive(Debug, Clone, Copy)]
pub(crate) struct Vertex {
    pub identity: FeatureRef,
    pub vertex: u32,
    pub xy: [f64; 2],
    pub start: Option<i64>,
    pub end: Option<i64>,
    pub value: Option<f64>,
}
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub(crate) struct Page {
    pub read: GeoSpatialRead,
    pub chunk: u32,
    pub cell: u32,
    pub count: u32,
    pub first: u64,
    pub last: u64,
    pub start: Option<i64>,
    pub end: Option<i64>,
}
impl Page {
    pub(crate) fn time_matches(self, time: TimePredicate) -> bool {
        time.matches(self.start, self.end)
    }
}
/// Owned directory bytes retain their global processor credit until dropped.
pub struct GeoSpatialDirectory {
    bytes: Vec<u8>,
    _lease: GeoProcessorLease,
}
impl GeoSpatialDirectory {
    pub fn as_slice(&self) -> &[u8] {
        &self.bytes
    }
    pub fn len(&self) -> usize {
        self.bytes.len()
    }
    pub fn is_empty(&self) -> bool {
        self.bytes.is_empty()
    }
}
impl std::ops::Deref for GeoSpatialDirectory {
    type Target = [u8];
    fn deref(&self) -> &Self::Target {
        self.as_slice()
    }
}
/// Private fields prevent imported hashes/summaries alone acquiring pruning authority.
/// Storage must retain immutable exact page bytes until this capability is dropped.
pub struct ValidatedGeoSpatialIndex {
    pub(crate) source: GeoSourceManifest,
    pub(crate) options: GeoSpatialOptions,
    pub(crate) pages: Vec<Page>,
    pub(crate) lease: GeoProcessorLease,
}
impl ValidatedGeoSpatialIndex {
    pub fn source(&self) -> &GeoSourceManifest {
        &self.source
    }
    pub fn options(&self) -> GeoSpatialOptions {
        self.options
    }
    pub fn page_count(&self) -> usize {
        self.pages.len()
    }
    pub fn reserved_bytes(&self) -> usize {
        self.lease.bytes()
    }
    /// Encoded bytes retain a conservative three-copy reservation until dropped.
    pub fn encoded_len(&self) -> usize {
        HEADER + self.pages.len() * ENTRY_BYTES
    }
    pub fn encode(&self) -> Result<GeoSpatialDirectory> {
        let wire = GeoProcessorLease::acquire(
            self.encoded_len()
                .checked_mul(3)
                .ok_or(SourceError::ResourceLimit)?,
        )?;
        let mut b = vec![0; self.encoded_len()];
        b[..4].copy_from_slice(b"XYIX");
        put32(&mut b, 4, 1);
        put32(&mut b, 8, self.options.grid);
        put32(&mut b, 12, self.source.crs() as u32);
        put32(&mut b, 16, self.source.geometry() as u32);
        put64(&mut b, 24, self.source.generation());
        put64(&mut b, 32, self.source.rows());
        b[40..48].copy_from_slice(&self.source.digest());
        put64(&mut b, 48, self.pages.len() as u64);
        for (i, p) in self.pages.iter().enumerate() {
            let a = HEADER + i * ENTRY_BYTES;
            put64(&mut b, a, p.read.page);
            put32(&mut b, a + 8, p.chunk);
            put32(&mut b, a + 12, p.cell);
            put32(&mut b, a + 16, p.read.encoded_bytes as u32);
            put32(&mut b, a + 20, p.count);
            b[a + 24..a + 32].copy_from_slice(&p.read.digest);
            put64(&mut b, a + 32, p.first);
            put64(&mut b, a + 40, p.last);
            put32(
                &mut b,
                a + 48,
                u32::from(p.start.is_some()) | (u32::from(p.end.is_some()) << 1),
            );
            put64(&mut b, a + 56, p.start.unwrap_or(0) as u64);
            put64(&mut b, a + 64, p.end.unwrap_or(0) as u64);
        }
        Ok(GeoSpatialDirectory {
            bytes: b,
            _lease: wire,
        })
    }
}
pub(crate) fn hash(bytes: &[u8]) -> [u8; 8] {
    let mut h = Blake2s8::new();
    h.update(b"xyg-spatial-page-v1");
    h.update(bytes);
    h.finish()
}
pub(crate) fn cell(crs: GeoCrs, xy: [f64; 2], options: GeoSpatialOptions) -> u32 {
    let [x, y] = xy;
    // Nonprojectable canonical coordinates remain unconditional candidates:
    // an eligible row must still produce the same shared projection error.
    if (crs == GeoCrs::Epsg4326 && (x.abs() > 180. || y.abs() > 90.))
        || (crs == GeoCrs::Epsg3857 && (x.abs() > WEB_MERCATOR_MAX || y.abs() > WEB_MERCATOR_MAX))
    {
        return u32::MAX;
    }
    let (x, y) = if crs == GeoCrs::Epsg4326 {
        lonlat_to_mercator(x, y)
    } else {
        (x, y)
    };
    let n = options.grid;
    let col =
        (((x + WEB_MERCATOR_MAX) / (2. * WEB_MERCATOR_MAX) * n as f64).floor() as u32).min(n - 1);
    let row =
        (((y + WEB_MERCATOR_MAX) / (2. * WEB_MERCATOR_MAX) * n as f64).floor() as u32).min(n - 1);
    row * n + col
}
pub(crate) fn candidate(
    cell: u32,
    options: GeoSpatialOptions,
    camera: &GeoViewport,
    bounds: Option<[f64; 4]>,
) -> bool {
    if cell == u32::MAX {
        return true;
    }
    let Some([x0, y0, x1, y1]) = bounds else {
        return true;
    };
    let step = 2. * WEB_MERCATOR_MAX / options.grid as f64;
    let left = -WEB_MERCATOR_MAX + (cell % options.grid) as f64 * step;
    let bottom = -WEB_MERCATOR_MAX + (cell / options.grid) as f64 * step;
    if bottom > y1 || bottom + step < y0 {
        return false;
    }
    let intersects = |left: f64| {
        if !camera.world_wrap {
            return left <= x1 && left + step >= x0;
        }
        let world = 2. * WEB_MERCATOR_MAX;
        // A periodic copy intersects iff an integer shift lies in this interval.
        ((x0 - left - step) / world).ceil() <= ((x1 - left) / world).floor()
    };
    // Cross-CRS conversion can normalize -180 to +180. Either seam column
    // therefore admits the union of both seam footprints, including no-wrap.
    // Distant viewports need neither column; latitude pruning still applies.
    let column = cell % options.grid;
    intersects(left)
        || (column == 0 && intersects(WEB_MERCATOR_MAX - step))
        || (column == options.grid - 1 && intersects(-WEB_MERCATOR_MAX))
}
pub(crate) fn write_vertex(b: &mut [u8], a: usize, r: Vertex) {
    put64(b, a, r.identity.source_row);
    put64(b, a + 8, r.identity.feature_id);
    put32(b, a + 16, r.identity.chunk_index);
    put32(b, a + 20, r.identity.row);
    put32(b, a + 24, r.vertex);
    put32(
        b,
        a + 28,
        u32::from(r.start.is_some())
            | (u32::from(r.end.is_some()) << 1)
            | (u32::from(r.value.is_some()) << 2),
    );
    put64(b, a + 32, r.xy[0].to_bits());
    put64(b, a + 40, r.xy[1].to_bits());
    put64(b, a + 48, r.start.unwrap_or(0) as u64);
    put64(b, a + 56, r.end.unwrap_or(0) as u64);
    put64(b, a + 64, r.value.unwrap_or(0.).to_bits());
}
pub(crate) fn decode_page(page: Page, b: &[u8]) -> Result<Vec<Vertex>> {
    if b.len() != page.read.encoded_bytes
        || b.len() < PAGE_HEADER
        || b.len() > PAGE_BYTES
        || hash(b) != page.read.digest
        || &b[..4] != b"XYIP"
        || get32(b, 4) != 1
        || get64(b, 8) != page.read.page
        || get32(b, 16) != page.chunk
        || get32(b, 20) != page.cell
        || get32(b, 24) != page.count
        || b[28..64].iter().any(|&v| v != 0)
        || b.len() != PAGE_HEADER + page.count as usize * RECORD_BYTES
    {
        return Err(SourceError::StaleSource);
    }
    let mut out = Vec::with_capacity(page.count as usize);
    for r in b[PAGE_HEADER..].chunks_exact(RECORD_BYTES) {
        let flags = get32(r, 28);
        if flags & !7 != 0 || r[72..80].iter().any(|&v| v != 0) {
            return Err(SourceError::InvalidFrame);
        }
        out.push(Vertex {
            identity: FeatureRef {
                source_row: get64(r, 0),
                feature_id: get64(r, 8),
                chunk_index: get32(r, 16),
                row: get32(r, 20),
            },
            vertex: get32(r, 24),
            xy: [f64::from_bits(get64(r, 32)), f64::from_bits(get64(r, 40))],
            start: (flags & 1 != 0).then(|| get64(r, 48) as i64),
            end: (flags & 2 != 0).then(|| get64(r, 56) as i64),
            value: (flags & 4 != 0).then(|| f64::from_bits(get64(r, 64))),
        });
    }
    Ok(out)
}
pub(crate) fn put32(b: &mut [u8], a: usize, v: u32) {
    b[a..a + 4].copy_from_slice(&v.to_le_bytes());
}
pub(crate) fn put64(b: &mut [u8], a: usize, v: u64) {
    b[a..a + 8].copy_from_slice(&v.to_le_bytes());
}
pub(crate) fn get32(b: &[u8], a: usize) -> u32 {
    u32::from_le_bytes(b[a..a + 4].try_into().unwrap())
}
pub(crate) fn get64(b: &[u8], a: usize) -> u64 {
    u64::from_le_bytes(b[a..a + 8].try_into().unwrap())
}
pub(crate) fn supported(source: &GeoSourceManifest) -> Result<()> {
    if !matches!(
        source.geometry(),
        GeoGeometry::Point | GeoGeometry::MultiPoint
    ) {
        return Err(SourceError::InvalidFrame);
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::geo::{GeoColumn, GeoDescriptor, GeoLimits};
    use crate::geo_indexed_query_session::{
        GeoIndexDecision, GeoIndexedQuerySession, GeoIndexedQueryStep, decision, process_indexed,
    };
    use crate::geo_lod::{GeoLodOptions, GeoPointOutput, GeoPointResult, GeoReducedKind, process};
    use crate::geo_source::{GeoChunk, GeoIntervals, GeoManifestBuilder, QueryBudget, ReadRequest};
    use crate::geo_source_session::test_processor_lock;
    use crate::geo_spatial_build_session::{
        GeoSpatialBuildSession, GeoSpatialBuildStep, build, validate_import,
    };
    use std::{collections::BTreeMap, sync::Arc};
    fn camera(x: f64, zoom: f64, pitch: f64) -> GeoViewport {
        GeoViewport::new(GeoCrs::Epsg4326, x, 0., zoom, 800., 600., 27., pitch, true).unwrap()
    }
    fn chunk(
        kind: GeoGeometry,
        xy: &[f64],
        offsets: &[u32],
        valid: &[u8],
        ids: &[u64],
        time: Option<GeoIntervals<'_>>,
    ) -> GeoChunk {
        let col = GeoColumn::from_descriptor(GeoDescriptor {
            geometry: kind,
            crs: GeoCrs::Epsg4326,
            xy,
            validity: valid,
            feature_ids: Some(ids),
            offsets0: offsets,
            offsets1: &[],
            offsets2: &[],
            limits: GeoLimits::default(),
        })
        .unwrap();
        GeoChunk::parse(&GeoChunk::encode(&col, time).unwrap(), 96 << 20).unwrap()
    }
    fn source(chunks: &[GeoChunk]) -> (GeoSourceManifest, Vec<Vec<u8>>) {
        let mut m = GeoManifestBuilder::new();
        let mut raw = vec![];
        for c in chunks {
            m.push(c).unwrap();
            raw.push(GeoChunk::encode_with_values(c.column(), c.intervals(), c.values()).unwrap());
        }
        (m.finish(u64::MAX).unwrap(), raw)
    }
    fn index(
        m: &GeoSourceManifest,
        raw: &[Vec<u8>],
    ) -> (Arc<ValidatedGeoSpatialIndex>, BTreeMap<u64, Vec<u8>>) {
        let mut store = BTreeMap::new();
        let i = build(
            m,
            &mut |r: ReadRequest| Ok(raw[r.chunk_index as usize].clone()),
            &mut |t, b: &[u8]| {
                store.insert(t.request.page, b.to_vec());
                Ok(())
            },
            GeoSpatialOptions::default(),
            QueryBudget::default(),
            1_000_000,
            &mut || false,
        )
        .unwrap();
        (Arc::new(i), store)
    }
    fn equal(a: &GeoPointResult, b: &GeoPointResult) {
        assert_eq!(a.key, b.key);
        assert_eq!(a.visible_vertices, b.visible_vertices);
        assert_eq!(a.grid_capped, b.grid_capped);
        let _paint = GeoProcessorLease::acquire(32 << 20).unwrap();
        let style = crate::geo_layers::GeoStyle::default();
        assert_eq!(
            crate::geo_lod_scene::compile(a, style, 32 << 20)
                .unwrap()
                .scene,
            crate::geo_lod_scene::compile(b, style, 32 << 20)
                .unwrap()
                .scene
        );

        match (&a.output, &b.output) {
            (GeoPointOutput::Direct(a), GeoPointOutput::Direct(b)) => assert_eq!(a, b),
            (GeoPointOutput::Reduced(a), GeoPointOutput::Reduced(b)) => {
                assert_eq!(a.len(), b.len());
                for (a, b) in a.iter().zip(b) {
                    assert_eq!(
                        (a.count, a.x.to_bits(), a.y.to_bits()),
                        (b.count, b.x.to_bits(), b.y.to_bits())
                    );
                }
            }
            _ => panic!("tier differs"),
        }
    }
    fn compare(
        m: &GeoSourceManifest,
        raw: &[Vec<u8>],
        i: Arc<ValidatedGeoSpatialIndex>,
        store: &BTreeMap<u64, Vec<u8>>,
        camera: GeoViewport,
        time: TimePredicate,
        options: GeoLodOptions,
    ) {
        let ordinary = process(
            m,
            &mut |r: ReadRequest| Ok(raw[r.chunk_index as usize].clone()),
            camera,
            time,
            u64::MAX,
            u64::MAX,
            u64::MAX,
            options,
            QueryBudget::default(),
            &mut || false,
        )
        .unwrap();
        let indexed = process_indexed(
            i,
            &mut |r: GeoSpatialRead| Ok(store[&r.page].clone()),
            camera,
            time,
            options,
            u64::MAX,
            u64::MAX,
            u64::MAX,
            128 << 20,
            &mut || false,
        )
        .unwrap()
        .unwrap();
        equal(&ordinary, &indexed.result);
    }
    #[test]
    fn geo_index_distant_view_does_not_read_seam_columns() {
        let options = GeoSpatialOptions::default();
        for wrap in [false, true] {
            let camera =
                GeoViewport::new(GeoCrs::Epsg4326, 0., 0., 8., 800., 600., 0., 0., wrap).unwrap();
            let bounds = camera.point_index_bounds().unwrap();
            for row in 0..options.grid {
                assert!(!candidate(row * options.grid, options, &camera, bounds));
                assert!(!candidate(
                    row * options.grid + options.grid - 1,
                    options,
                    &camera,
                    bounds
                ));
            }
        }
    }
    #[test]
    fn geo_index_exact_direct_nulls_dateline_pitch_and_full_identity() {
        let _guard = test_processor_lock();
        let chunks = [
            chunk(
                GeoGeometry::Point,
                &[-179., 0., 179., 0.],
                &[],
                &[1, 0, 1],
                &[u64::MAX, 1 << 63, u64::MAX],
                None,
            ),
            chunk(
                GeoGeometry::Point,
                &[179.1, 0., 0., 0.],
                &[],
                &[1, 1],
                &[0x8000000000000001, 9007199254740993],
                None,
            ),
        ];
        let (m, raw) = source(&chunks);
        let (i, store) = index(&m, &raw);
        for pitch in [0., 40., 60.] {
            compare(
                &m,
                &raw,
                i.clone(),
                &store,
                camera(179., 4., pitch),
                TimePredicate::All,
                GeoLodOptions::default(),
            );
        }
    }
    #[test]
    fn geo_index_multipoint_time_half_open_preserves_original_vertices() {
        let _guard = test_processor_lock();
        let starts = [i64::MIN, 0, 10];
        let ends = [0, 10, i64::MAX];
        let valid = [1, 1, 1];
        let c = chunk(
            GeoGeometry::MultiPoint,
            &[
                -179., 0., 179., 0., 0., 0., 0.001, 0., 179.2, 0., -179.2, 0.,
            ],
            &[0, 2, 4, 6],
            &valid,
            &[u64::MAX, u64::MAX, 1 << 63],
            Some(GeoIntervals {
                starts: &starts,
                ends: &ends,
                start_validity: &valid,
                end_validity: &valid,
            }),
        );
        let (m, raw) = source(&[c]);
        let (i, store) = index(&m, &raw);
        for time in [
            TimePredicate::All,
            TimePredicate::Instant(i64::MIN),
            TimePredicate::Instant(0),
            TimePredicate::Instant(10),
            TimePredicate::Window { start: 0, end: 10 },
        ] {
            compare(
                &m,
                &raw,
                i.clone(),
                &store,
                camera(0., 0., 40.),
                time,
                GeoLodOptions::default(),
            );
        }
    }
    #[test]
    fn geo_index_reduced_cluster_density_centroids_are_source_order_bit_exact() {
        let _guard = test_processor_lock();
        let n = 40_000;
        let mut xy = Vec::with_capacity(2 * n);
        for row in 0..n {
            xy.extend([
                ((row * 48271) % 100003) as f64 / 100003. * 20. - 10.,
                ((row * 69621) % 100019) as f64 / 100019. * 20. - 10.,
            ]);
        }
        let c = chunk(
            GeoGeometry::Point,
            &xy,
            &[],
            &vec![1; n],
            &(0..n as u64).map(|r| u64::MAX - r).collect::<Vec<_>>(),
            None,
        );
        let (m, raw) = source(&[c]);
        let (i, store) = index(&m, &raw);
        for kind in [GeoReducedKind::Cluster, GeoReducedKind::Density] {
            compare(
                &m,
                &raw,
                i.clone(),
                &store,
                camera(0., 1., 40.),
                TimePredicate::All,
                GeoLodOptions {
                    kind,
                    ..Default::default()
                },
            );
        }
    }
    #[test]
    fn geo_index_warm_narrow_reads_only_spatial_candidates() {
        let _guard = test_processor_lock();
        let mut xy = vec![0., 0.];
        for r in 1..256 {
            xy.extend([if r % 2 == 0 { 100. } else { -100. }, r as f64 / 10. - 13.]);
        }
        let (m, raw) = source(&[chunk(
            GeoGeometry::Point,
            &xy,
            &[],
            &vec![1; 256],
            &(0..256).collect::<Vec<_>>(),
            None,
        )]);
        let (i, store) = index(&m, &raw);
        let total = i.page_count();
        let result = process_indexed(
            i,
            &mut |r: GeoSpatialRead| Ok(store[&r.page].clone()),
            camera(0., 12., 0.),
            TimePredicate::All,
            GeoLodOptions::default(),
            1,
            0,
            0,
            128 << 20,
            &mut || false,
        )
        .unwrap()
        .unwrap();
        assert_eq!(result.result.visible_vertices, 1);
        assert_eq!(result.stats.candidate_vertices, 1);
        assert!(result.stats.pages_read < total as u64);
        assert!(result.stats.bytes_read < raw[0].len() as u64);
    }
    #[test]
    fn geo_index_import_audits_every_leaf_and_omission_even_if_not_visible() {
        let _guard = test_processor_lock();
        let (m, raw) = source(&[chunk(
            GeoGeometry::Point,
            &[0., 0., 150., 0.],
            &[],
            &[1, 1],
            &[u64::MAX, 1],
            None,
        )]);
        let (i, store) = index(&m, &raw);
        let directory = i.encode().unwrap();
        let imported = validate_import(
            &m,
            &directory,
            &mut |r: ReadRequest| Ok(raw[r.chunk_index as usize].clone()),
            &mut |r: GeoSpatialRead| Ok(store[&r.page].clone()),
            QueryBudget::default(),
            1000,
            &mut || false,
        )
        .unwrap();
        assert_eq!(imported.encode().unwrap().as_slice(), directory.as_slice());
        drop(imported);
        let mut false_directory = directory.as_slice().to_vec();
        false_directory[HEADER + 12..HEADER + 16].copy_from_slice(&0u32.to_le_bytes());
        assert!(
            validate_import(
                &m,
                &false_directory,
                &mut |r: ReadRequest| Ok(raw[r.chunk_index as usize].clone()),
                &mut |r: GeoSpatialRead| Ok(store[&r.page].clone()),
                QueryBudget::default(),
                1000,
                &mut || false
            )
            .is_err()
        );
        let mut omitted = directory[..directory.len() - ENTRY_BYTES].to_vec();
        let n = get64(&omitted, 48) - 1;
        put64(&mut omitted, 48, n);
        assert!(
            validate_import(
                &m,
                &omitted,
                &mut |r: ReadRequest| Ok(raw[r.chunk_index as usize].clone()),
                &mut |r: GeoSpatialRead| Ok(store[&r.page].clone()),
                QueryBudget::default(),
                1000,
                &mut || false
            )
            .is_err()
        );
        assert!(
            validate_import(
                &m,
                &directory,
                &mut |r: ReadRequest| Ok(raw[r.chunk_index as usize].clone()),
                &mut |r: GeoSpatialRead| {
                    let mut b = store[&r.page].clone();
                    b[PAGE_HEADER + 8] ^= 1;
                    Ok(b)
                },
                QueryBudget::default(),
                1000,
                &mut || false
            )
            .is_err()
        );
    }
    #[test]
    fn geo_index_build_cancel_and_ack_keep_private_loans_no_partial_publish() {
        let _guard = test_processor_lock();
        let before = GeoProcessorLease::live_bytes();
        let (m, raw) = source(&[chunk(
            GeoGeometry::Point,
            &[0., 0.],
            &[],
            &[1],
            &[u64::MAX],
            None,
        )]);
        let mut s = GeoSpatialBuildSession::new(
            &m,
            GeoSpatialOptions::default(),
            QueryBudget::default(),
            100,
        )
        .unwrap();
        let GeoSpatialBuildStep::NeedRead(t) = s.step().unwrap() else {
            panic!()
        };
        let loan = GeoProcessorLease::live_bytes();
        assert!(s.finish().is_err());
        assert_eq!(GeoProcessorLease::live_bytes(), loan);
        s.cancel();
        assert!(s.has_outstanding_io());
        assert_eq!(s.step().unwrap(), GeoSpatialBuildStep::AwaitReadRelease(t));
        assert!(s.supply(t, &raw[0], &mut || false).is_err());
        assert_eq!(GeoProcessorLease::live_bytes(), loan);
        s.release_read(t).unwrap();
        assert!(GeoProcessorLease::live_bytes() < loan);
        drop(s);
        assert_eq!(GeoProcessorLease::live_bytes(), before);
        let mut s = GeoSpatialBuildSession::new(
            &m,
            GeoSpatialOptions::default(),
            QueryBudget::default(),
            100,
        )
        .unwrap();
        let GeoSpatialBuildStep::NeedRead(t) = s.step().unwrap() else {
            panic!()
        };
        s.supply(t, &raw[0], &mut || false).unwrap();
        s.release_read(t).unwrap();
        let GeoSpatialBuildStep::NeedWrite(w) = s.step().unwrap() else {
            panic!()
        };
        assert_eq!(s.write_bytes(w).unwrap().len(), w.request.encoded_bytes);
        s.cancel();
        assert_eq!(s.step().unwrap(), GeoSpatialBuildStep::AwaitWriteRelease(w));
        assert!(s.finish().is_err());
        s.acknowledge_write(w).unwrap();
        assert!(!s.has_outstanding_io());
        drop(s);
        assert_eq!(GeoProcessorLease::live_bytes(), before);
    }
    #[test]
    fn geo_index_async_query_cancel_stale_read_corruption_and_budget_are_atomic() {
        let _guard = test_processor_lock();
        let (m, raw) = source(&[chunk(
            GeoGeometry::Point,
            &[0., 0., 1., 1.],
            &[],
            &[1, 1],
            &[u64::MAX, 1],
            None,
        )]);
        let (i, store) = index(&m, &raw);
        let mut s = GeoIndexedQuerySession::new(
            i.clone(),
            camera(0., 0., 0.),
            TimePredicate::All,
            GeoLodOptions::default(),
            1,
            0,
            0,
            128 << 20,
        )
        .unwrap()
        .unwrap();
        let GeoIndexedQueryStep::NeedRead(t) = s.step().unwrap() else {
            panic!()
        };
        let mut old = t;
        old.session += 1;
        assert_eq!(
            s.supply(old, &store[&t.request.page], &mut || false),
            Err(SourceError::StaleSource)
        );
        assert_eq!(s.step().unwrap(), GeoIndexedQueryStep::NeedRead(t));
        s.cancel();
        let held = GeoProcessorLease::live_bytes();
        assert!(s.finish().is_err());
        assert_eq!(GeoProcessorLease::live_bytes(), held);
        assert!(s.has_outstanding_io());
        s.release_read(t).unwrap();
        assert!(GeoProcessorLease::live_bytes() < held);
        drop(s);
        let mut s = GeoIndexedQuerySession::new(
            i.clone(),
            camera(0., 0., 0.),
            TimePredicate::All,
            GeoLodOptions::default(),
            1,
            0,
            0,
            1,
        )
        .unwrap()
        .unwrap();
        assert_eq!(s.step(), Err(SourceError::ResourceLimit));
        drop(s);
        let old = process_indexed(
            i.clone(),
            &mut |r: GeoSpatialRead| Ok(store[&r.page].clone()),
            camera(0., 0., 0.),
            TimePredicate::All,
            GeoLodOptions::default(),
            1,
            0,
            0,
            128 << 20,
            &mut || false,
        )
        .unwrap()
        .unwrap();
        assert!(
            process_indexed(
                i,
                &mut |r: GeoSpatialRead| {
                    let mut b = store[&r.page].clone();
                    b[PAGE_HEADER + 8] ^= 1;
                    Ok(b)
                },
                camera(0., 0., 0.),
                TimePredicate::All,
                GeoLodOptions::default(),
                1,
                0,
                0,
                128 << 20,
                &mut || false
            )
            .is_err()
        );
        assert_eq!(old.result.visible_vertices, 2);
    }
    #[test]
    fn geo_index_compacts_across_chunks_and_frontier_counts_leaf_streams() {
        let _guard = test_processor_lock();
        let chunks = (0..257)
            .map(|r| chunk(GeoGeometry::Point, &[0., 0.], &[], &[1], &[r], None))
            .collect::<Vec<_>>();
        let (m, raw) = source(&chunks);
        let (i, store) = index(&m, &raw);
        assert_eq!(i.page_count(), 1);
        assert_eq!(
            decision(&i, &camera(0., 0., 0.), TimePredicate::All).unwrap(),
            GeoIndexDecision::Indexed
        );
        compare(
            &m,
            &raw,
            i,
            &store,
            camera(0., 0., 0.),
            TimePredicate::All,
            GeoLodOptions::default(),
        );
        let mut xy = Vec::new();
        for row in 0..32 {
            for col in 0..32 {
                let (x, y) = crate::geo_viewport::mercator_to_lonlat(
                    -WEB_MERCATOR_MAX + (col as f64 + 0.5) * 2. * WEB_MERCATOR_MAX / 32.,
                    -WEB_MERCATOR_MAX + (row as f64 + 0.5) * 2. * WEB_MERCATOR_MAX / 32.,
                );
                xy.extend([x, y]);
            }
        }
        let (m, raw) = source(&[chunk(
            GeoGeometry::Point,
            &xy,
            &[],
            &vec![1; 1024],
            &(0..1024).collect::<Vec<_>>(),
            None,
        )]);
        let mut store = BTreeMap::new();
        let i = Arc::new(
            build(
                &m,
                &mut |r: ReadRequest| Ok(raw[r.chunk_index as usize].clone()),
                &mut |t, b: &[u8]| {
                    store.insert(t.request.page, b.to_vec());
                    Ok(())
                },
                GeoSpatialOptions { grid: 32 },
                QueryBudget::default(),
                2000,
                &mut || false,
            )
            .unwrap(),
        );
        assert_eq!(
            decision(&i, &camera(0., 0., 0.), TimePredicate::All).unwrap(),
            GeoIndexDecision::FullScanFrontier
        );
        assert!(
            process_indexed(
                i,
                &mut |_r: GeoSpatialRead| panic!("fallback must not read pages"),
                camera(0., 0., 0.),
                TimePredicate::All,
                GeoLodOptions::default(),
                1,
                0,
                0,
                128 << 20,
                &mut || false
            )
            .unwrap()
            .is_none()
        );
    }
    #[test]
    fn geo_index_global_admission_rejects_before_io_and_recovers() {
        let _guard = test_processor_lock();
        let (m, raw) = source(&[chunk(GeoGeometry::Point, &[0., 0.], &[], &[1], &[0], None)]);
        let (i, _store) = index(&m, &raw);
        let baseline = GeoProcessorLease::live_bytes();
        let pressure =
            GeoProcessorLease::acquire(crate::geo_source::MAX_PROCESSOR_BYTES - baseline).unwrap();
        assert!(
            GeoIndexedQuerySession::new(
                i.clone(),
                camera(0., 0., 0.),
                TimePredicate::All,
                GeoLodOptions::default(),
                1,
                0,
                0,
                128 << 20
            )
            .is_err()
        );
        assert!(
            GeoSpatialBuildSession::new(
                &m,
                GeoSpatialOptions::default(),
                QueryBudget::default(),
                100
            )
            .is_err()
        );
        drop(pressure);
        assert!(
            GeoIndexedQuerySession::new(
                i,
                camera(0., 0., 0.),
                TimePredicate::All,
                GeoLodOptions::default(),
                1,
                0,
                0,
                128 << 20
            )
            .unwrap()
            .is_some()
        );
    }
    #[test]
    fn geo_index_cross_crs_no_wrap_antimeridian_alias_and_polar_pitch() {
        let _guard = test_processor_lock();
        for crs in [GeoCrs::Epsg4326, GeoCrs::Epsg3857] {
            let (a, b) = if crs == GeoCrs::Epsg4326 {
                (-180., 180.)
            } else {
                (-WEB_MERCATOR_MAX, WEB_MERCATOR_MAX)
            };
            let col = GeoColumn::from_descriptor(GeoDescriptor {
                geometry: GeoGeometry::Point,
                crs,
                xy: &[a, 0., b, 0.],
                validity: &[1, 1],
                feature_ids: Some(&[u64::MAX, 1 << 63]),
                offsets0: &[],
                offsets1: &[],
                offsets2: &[],
                limits: GeoLimits::default(),
            })
            .unwrap();
            let c = GeoChunk::parse(&GeoChunk::encode(&col, None).unwrap(), 96 << 20).unwrap();
            let (m, raw) = source(&[c]);
            let (i, store) = index(&m, &raw);
            for camera_crs in [GeoCrs::Epsg4326, GeoCrs::Epsg3857] {
                for wrap in [false, true] {
                    for pitch in [-60., 0., 60.] {
                        let center = if camera_crs == GeoCrs::Epsg4326 {
                            180.
                        } else {
                            -WEB_MERCATOR_MAX
                        };
                        let camera = GeoViewport::new(
                            camera_crs, center, 0., 10., 800., 600., 31., pitch, wrap,
                        )
                        .unwrap();
                        compare(
                            &m,
                            &raw,
                            i.clone(),
                            &store,
                            camera,
                            TimePredicate::All,
                            GeoLodOptions::default(),
                        );
                    }
                }
            }
        }
    }
    #[test]
    fn geo_index_time_precedes_projection_work_and_null_endpoint_zones() {
        let _guard = test_processor_lock();
        let starts = [0, 1];
        let ends = [1, 0];
        let sv = [0, 1];
        let ev = [1, 0];
        let c = chunk(
            GeoGeometry::Point,
            &[0., 0., 0., 0.],
            &[],
            &[1, 1],
            &[u64::MAX, 1],
            Some(GeoIntervals {
                starts: &starts,
                ends: &ends,
                start_validity: &sv,
                end_validity: &ev,
            }),
        );
        let (m, raw) = source(&[c]);
        let (i, store) = index(&m, &raw);
        for instant in [i64::MIN, 0, 1, i64::MAX] {
            compare(
                &m,
                &raw,
                i.clone(),
                &store,
                camera(0., 8., 40.),
                TimePredicate::Instant(instant),
                GeoLodOptions {
                    max_projected_vertices: 1,
                    ..Default::default()
                },
            );
        }
    }
    #[test]
    fn geo_index_cancel_during_last_feed_cannot_publish_or_destroy_old_result() {
        let _guard = test_processor_lock();
        let (m, raw) = source(&[chunk(
            GeoGeometry::Point,
            &[0., 0., 1., 1.],
            &[],
            &[1, 1],
            &[u64::MAX, 1],
            None,
        )]);
        let (i, store) = index(&m, &raw);
        let old = process_indexed(
            i.clone(),
            &mut |r: GeoSpatialRead| Ok(store[&r.page].clone()),
            camera(0., 0., 0.),
            TimePredicate::All,
            GeoLodOptions::default(),
            1,
            0,
            0,
            128 << 20,
            &mut || false,
        )
        .unwrap()
        .unwrap();
        let mut s = GeoIndexedQuerySession::new(
            i,
            camera(0., 0., 0.),
            TimePredicate::All,
            GeoLodOptions::default(),
            1,
            0,
            0,
            128 << 20,
        )
        .unwrap()
        .unwrap();
        while let GeoIndexedQueryStep::NeedRead(t) = s.step().unwrap() {
            s.supply(t, &store[&t.request.page], &mut || false).unwrap();
            s.release_read(t).unwrap();
            let mut calls = 0;
            let result = s.step_with_cancel(&mut || {
                calls += 1;
                calls > 1
            });
            if result == Err(SourceError::Cancelled) {
                break;
            }
        }
        assert!(s.finish().is_err());
        assert_eq!(old.result.visible_vertices, 2);
    }
    #[test]
    fn geo_index_compacted_pages_span_chunks_preserve_scalar_bits_and_order() {
        let _guard = test_processor_lock();
        let mut chunks = Vec::new();
        let mut expected = Vec::new();
        for part in 0..3 {
            let xy: Vec<f64> = (0..600)
                .flat_map(|row| [if row % 2 == 0 { 0.01 } else { -0.01 }, 0.01])
                .collect();
            let ids: Vec<u64> = (0..600)
                .map(|row| u64::MAX - (part * 600 + row) as u64)
                .collect();
            let base = chunk(GeoGeometry::Point, &xy, &[], &vec![1; 600], &ids, None);
            let values: Vec<f64> = (0..600)
                .map(|row| match row % 3 {
                    0 => -0.0,
                    1 => f64::from_bits(0x7ff8000000000042),
                    _ => f64::INFINITY,
                })
                .collect();
            expected.extend(values.iter().map(|v| v.to_bits()));
            chunks.push(
                GeoChunk::parse(
                    &GeoChunk::encode_with_values(base.column(), None, Some(&values)).unwrap(),
                    96 << 20,
                )
                .unwrap(),
            );
        }
        let (m, raw) = source(&chunks);
        let (i, store) = index(&m, &raw);
        assert_eq!(i.page_count(), 4); // two cells, each 900 vertices: full page + tail.
        let mut seen = Vec::new();
        for page in &i.pages {
            let vertices = decode_page(*page, &store[&page.read.page]).unwrap();
            for v in vertices {
                assert_eq!(
                    v.identity.chunk_index as u64 * 600 + v.identity.row as u64,
                    v.identity.source_row
                );
                assert_eq!(v.identity.feature_id, u64::MAX - v.identity.source_row);
                seen.push((v.identity.source_row, v.value.unwrap().to_bits()));
            }
        }
        seen.sort_unstable_by_key(|v| v.0);
        assert_eq!(seen.iter().map(|v| v.1).collect::<Vec<_>>(), expected);
        compare(
            &m,
            &raw,
            i.clone(),
            &store,
            camera(0., 8., 40.),
            TimePredicate::All,
            GeoLodOptions::default(),
        );
        let imported = validate_import(
            &m,
            &i.encode().unwrap(),
            &mut |r: ReadRequest| Ok(raw[r.chunk_index as usize].clone()),
            &mut |r: GeoSpatialRead| Ok(store[&r.page].clone()),
            QueryBudget::default(),
            1_000_000,
            &mut || false,
        )
        .unwrap();
        assert_eq!(
            imported.encode().unwrap().as_slice(),
            i.encode().unwrap().as_slice()
        );
    }
    #[test]
    fn geo_index_synchronous_adapter_cancels_inside_final_fold() {
        let _guard = test_processor_lock();
        let xy: Vec<f64> = (0..100).flat_map(|_| [0., 0.]).collect();
        let (m, raw) = source(&[chunk(
            GeoGeometry::Point,
            &xy,
            &[],
            &[1; 100],
            &[u64::MAX; 100],
            None,
        )]);
        let (i, store) = index(&m, &raw);
        let armed = std::cell::Cell::new(false);
        let checks = std::cell::Cell::new(0);
        let result = process_indexed(
            i,
            &mut |r: GeoSpatialRead| {
                armed.set(true);
                Ok(store[&r.page].clone())
            },
            camera(0., 0., 0.),
            TimePredicate::All,
            GeoLodOptions::default(),
            1,
            0,
            0,
            128 << 20,
            &mut || {
                if !armed.get() {
                    return false;
                }
                checks.set(checks.get() + 1);
                checks.get() > 20
            },
        );
        assert!(matches!(result, Err(SourceError::Cancelled)));
        assert!(checks.get() > 20);
    }
    #[test]
    fn geo_index_directory_outputs_keep_global_credit_and_recover_on_drop() {
        let _guard = test_processor_lock();
        let (m, raw) = source(&[chunk(
            GeoGeometry::Point,
            &[0., 0.],
            &[],
            &[1],
            &[u64::MAX],
            None,
        )]);
        let (index, _) = index(&m, &raw);
        let baseline = GeoProcessorLease::live_bytes();
        let first = index.encode().unwrap();
        let credit = 3 * first.len();
        assert_eq!(GeoProcessorLease::live_bytes(), baseline + credit);
        let second = index.encode().unwrap();
        assert_eq!(first.as_slice(), second.as_slice());
        assert_eq!(GeoProcessorLease::live_bytes(), baseline + 2 * credit);
        let pressure = GeoProcessorLease::acquire((128 << 20) - baseline - 2 * credit).unwrap();
        assert!(matches!(index.encode(), Err(SourceError::ResourceLimit)));
        drop(first);
        let recovered = index.encode().unwrap();
        assert_eq!(recovered.as_slice(), second.as_slice());
        drop(recovered);
        drop(pressure);
        drop(second);
        assert_eq!(GeoProcessorLease::live_bytes(), baseline);
    }
}
