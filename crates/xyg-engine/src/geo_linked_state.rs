//! Sparse, explicitly linked retained-point selection. Dossier §17/§27/§28/§34.
//! State and selected output storage share the existing processor ledger.
use crate::geo::{GeoCrs, GeoError, GeoGeometry};
use crate::geo_lod::{GeoLodIdentity, GeoLodKey, GeoPointOutput, GeoPointResult};
use crate::geo_source::{GeoSourceManifest, SourceError};
use crate::geo_source_session::{GeoOperationSnapshot, GeoProcessorLease};
use std::sync::Arc;

type Result<T> = std::result::Result<T, SourceError>;
pub const MAX_SELECTED_IDS: usize = crate::temporal_controller::MAX_COORDINATED_SELECTION_IDS;
fn invalid() -> SourceError {
    SourceError::Geometry(GeoError::InvalidArgument)
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct GeoStateBinding {
    pub namespace: u64,
    pub source_digest: [u8; 8],
    pub generation: u64,
    pub layer_id: u64,
    pub state_revision: u64,
}
/// Selected fill is explicit straight RGBA8; ordinary style opacity applies once.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct GeoSelectedStyle {
    pub fill: [u8; 4],
}

/// Canonical sorted/deduplicated IDs are intent, including absent or invisible IDs.
/// Namespace/source/layer never follows coincidentally equal IDs implicitly.
#[derive(Debug)]
pub struct GeoLinkedState {
    binding: GeoStateBinding,
    rows: u64,
    crs: GeoCrs,
    geometry: GeoGeometry,
    ids: Vec<u64>,
    style: GeoSelectedStyle,
    fingerprint: [u64; 2],
    lease: GeoProcessorLease,
}
impl GeoLinkedState {
    pub fn new(
        source: &GeoSourceManifest,
        namespace: u64,
        layer_id: u64,
        state_revision: u64,
        ids: &[u64],
        style: GeoSelectedStyle,
    ) -> Result<Arc<Self>> {
        if ids.len() > MAX_SELECTED_IDS
            || !matches!(
                source.geometry(),
                GeoGeometry::Point | GeoGeometry::MultiPoint
            )
        {
            return Err(invalid());
        }
        // Credit precedes the only ID-plane copy/sort and Arc allocation.
        let bytes = ids
            .len()
            .checked_mul(8)
            .and_then(|n| n.checked_add(std::mem::size_of::<Self>() + 128))
            .ok_or(SourceError::ResourceLimit)?;
        let lease = GeoProcessorLease::acquire(bytes)?;
        let ids = crate::temporal_controller::canonical_selection(ids).map_err(|_| invalid())?;
        let binding = GeoStateBinding {
            namespace,
            source_digest: source.digest(),
            generation: source.generation(),
            layer_id,
            state_revision,
        };
        let fingerprint = fingerprint(
            binding,
            source.rows(),
            source.crs(),
            source.geometry(),
            &ids,
            style,
        );
        Ok(Arc::new(Self {
            binding,
            rows: source.rows(),
            crs: source.crs(),
            geometry: source.geometry(),
            ids,
            style,
            fingerprint,
            lease,
        }))
    }
    /// Explicit stable-ID join into a distinct source/layer/namespace. No geometry scan.
    pub fn link_to(
        &self,
        target: &GeoSourceManifest,
        namespace: u64,
        layer_id: u64,
        state_revision: u64,
    ) -> Result<Arc<Self>> {
        Self::new(
            target,
            namespace,
            layer_id,
            state_revision,
            &self.ids,
            self.style,
        )
    }
    pub fn binding(&self) -> GeoStateBinding {
        self.binding
    }
    pub fn selected_ids(&self) -> &[u64] {
        &self.ids
    }
    pub fn style(&self) -> GeoSelectedStyle {
        self.style
    }
    pub fn fingerprint(&self) -> [u64; 2] {
        self.fingerprint
    }
    pub fn contains(&self, id: u64) -> bool {
        self.ids.binary_search(&id).is_ok()
    }
    pub fn is_empty(&self) -> bool {
        self.ids.is_empty()
    }
    pub fn retained_bytes(&self) -> usize {
        self.lease.bytes()
    }
    pub fn validate_identity(&self, identity: GeoLodIdentity) -> Result<()> {
        if self.binding.source_digest != identity.source_digest
            || self.binding.generation != identity.generation
            || self.binding.layer_id != identity.layer_id
            || self.binding.state_revision != identity.state_revision
            || self.rows != identity.source_rows
            || self.crs != identity.crs
            || self.geometry != identity.geometry
        {
            return Err(SourceError::StaleSource);
        }
        Ok(())
    }
    pub fn validate_snapshot(&self, snapshot: GeoOperationSnapshot) -> Result<()> {
        if self.binding.source_digest != snapshot.source_digest
            || self.binding.generation != snapshot.generation
            || self.binding.layer_id != snapshot.layer_id
            || self.binding.state_revision != snapshot.state_revision
        {
            return Err(SourceError::StaleSource);
        }
        Ok(())
    }
    fn same_source(&self, other: &Self) -> bool {
        self.binding.namespace == other.binding.namespace
            && self.binding.source_digest == other.binding.source_digest
            && self.binding.generation == other.binding.generation
            && self.binding.layer_id == other.binding.layer_id
            && self.rows == other.rows
            && self.crs == other.crs
            && self.geometry == other.geometry
    }
    fn same_contents(&self, other: &Self) -> bool {
        self.same_source(other) && self.ids == other.ids && self.style == other.style
    }
}
/// One bounded source/layer coordination slot. Failed admission preserves the old Arc.
#[derive(Default)]
pub struct GeoLinkedStateAdmission {
    current: Option<Arc<GeoLinkedState>>,
}
impl GeoLinkedStateAdmission {
    pub fn current(&self) -> Option<&Arc<GeoLinkedState>> {
        self.current.as_ref()
    }
    pub fn admit(
        &mut self,
        state: Arc<GeoLinkedState>,
        snapshot: GeoOperationSnapshot,
    ) -> Result<bool> {
        state.validate_snapshot(snapshot)?;
        if let Some(old) = &self.current {
            if !state.same_source(old)
                || state.binding.state_revision < old.binding.state_revision
                || (state.binding.state_revision == old.binding.state_revision
                    && !state.same_contents(old))
            {
                return Err(SourceError::StaleSource);
            }
            if state.binding.state_revision == old.binding.state_revision {
                return Ok(false);
            }
        }
        self.current = Some(state);
        Ok(true)
    }
}
// A deterministic identity hint, not a collision-based authorization check.
fn fingerprint(
    binding: GeoStateBinding,
    rows: u64,
    crs: GeoCrs,
    geometry: GeoGeometry,
    ids: &[u64],
    style: GeoSelectedStyle,
) -> [u64; 2] {
    let mut h = [0xcbf29ce484222325_u64, 0x9e3779b97f4a7c15_u64];
    let mut fold = |bytes: &[u8]| {
        for &b in bytes {
            h[0] = (h[0] ^ b as u64).wrapping_mul(0x100000001b3);
            h[1] = (h[1] ^ b as u64).wrapping_mul(0x9e3779b185ebca87);
        }
    };
    fold(b"XYG-linked-selection-v1");
    fold(&binding.source_digest);
    for n in [
        binding.namespace,
        binding.generation,
        binding.layer_id,
        binding.state_revision,
        rows,
        crs as u64,
        geometry as u64,
        ids.len() as u64,
    ] {
        fold(&n.to_le_bytes());
    }
    fold(&style.fill);
    for n in ids {
        fold(&n.to_le_bytes());
    }
    h
}

/// Shared charged authority. Cloning this Arc never copies the counts plane.
#[derive(Debug)]
pub struct GeoPointSelection {
    key: GeoLodKey,
    state: Arc<GeoLinkedState>,
    cells: Vec<u64>,
    visible: u64,
    total_visible: u64,
    lease: GeoProcessorLease,
}
impl GeoPointSelection {
    pub fn state(&self) -> &Arc<GeoLinkedState> {
        &self.state
    }
    pub fn selected_counts(&self) -> &[u64] {
        &self.cells
    }
    pub fn visible_selected_vertices(&self) -> u64 {
        self.visible
    }
    pub fn cell_selected_count(&self, index: usize) -> u64 {
        self.cells.get(index).copied().unwrap_or(0)
    }
    pub fn retained_bytes(&self) -> usize {
        self.lease.bytes()
    }
    pub fn validate_result(&self, result: &GeoPointResult) -> Result<()> {
        self.state.validate_identity(result.key.identity)?;
        if self.key != result.key
            || self.total_visible != result.visible_vertices
            || self.visible > result.visible_vertices
        {
            return Err(SourceError::StaleSource);
        }
        let mut selected = 0u64;
        match &result.output {
            GeoPointOutput::Direct(points) => {
                if !self.cells.is_empty() || points.len() as u64 != self.total_visible {
                    return Err(SourceError::StaleSource);
                }
                for point in points {
                    if self.state.contains(point.identity.feature_id) {
                        selected = selected.checked_add(1).ok_or(SourceError::ResourceLimit)?;
                    }
                }
            }
            GeoPointOutput::Reduced(cells) => {
                if cells.len() != self.key.columns as usize * self.key.rows as usize
                    || (!self.state.is_empty() && self.cells.len() != cells.len())
                    || (self.state.is_empty() && !self.cells.is_empty())
                {
                    return Err(SourceError::StaleSource);
                }
                for (i, cell) in cells.iter().enumerate() {
                    let n = self.cell_selected_count(i);
                    if n > cell.count {
                        return Err(SourceError::StaleSource);
                    }
                    selected = selected.checked_add(n).ok_or(SourceError::ResourceLimit)?;
                }
            }
        }
        if selected != self.visible {
            return Err(SourceError::StaleSource);
        }
        Ok(())
    }
}
pub(crate) struct GeoSelectionAccumulator {
    pub(crate) state: Arc<GeoLinkedState>,
    pub(crate) visible: u64,
    pub(crate) aggregate_visible: u64,
    cells: Vec<u64>,
    lease: GeoProcessorLease,
}
impl GeoSelectionAccumulator {
    pub(crate) fn extra_bytes(max_cells: usize, state: &GeoLinkedState) -> Result<usize> {
        let plane = if state.is_empty() {
            0
        } else {
            max_cells.checked_mul(8).ok_or(SourceError::ResourceLimit)?
        };
        plane
            .checked_add(std::mem::size_of::<GeoPointSelection>() + 256)
            .ok_or(SourceError::ResourceLimit)
    }
    pub(crate) fn new(state: Arc<GeoLinkedState>, base: usize, max_cells: usize) -> Result<Self> {
        let bytes = base
            .checked_add(Self::extra_bytes(max_cells, &state)?)
            .ok_or(SourceError::ResourceLimit)?;
        let lease = GeoProcessorLease::acquire(bytes)?;
        Ok(Self {
            state,
            visible: 0,
            aggregate_visible: 0,
            cells: Vec::new(),
            lease,
        })
    }
    pub(crate) fn selected(&self, id: u64) -> bool {
        self.state.contains(id)
    }
    pub(crate) fn count_visible(&mut self) -> Result<()> {
        self.visible = self
            .visible
            .checked_add(1)
            .ok_or(SourceError::ResourceLimit)?;
        Ok(())
    }
    pub(crate) fn begin_aggregate(&mut self, count: usize) {
        if !self.state.is_empty() {
            self.cells = vec![0; count];
        }
    }
    pub(crate) fn count_cell(&mut self, index: usize) -> Result<()> {
        self.aggregate_visible = self
            .aggregate_visible
            .checked_add(1)
            .ok_or(SourceError::ResourceLimit)?;
        let n = self.cells.get_mut(index).ok_or(SourceError::StaleSource)?;
        *n = n.checked_add(1).ok_or(SourceError::ResourceLimit)?;
        Ok(())
    }
    pub(crate) fn finish(
        mut self,
        key: GeoLodKey,
        base_bytes: usize,
        total_visible: u64,
    ) -> Result<Arc<GeoPointSelection>> {
        let bytes = base_bytes
            .checked_add(self.cells.capacity() * 8)
            .and_then(|n| n.checked_add(std::mem::size_of::<GeoPointSelection>() + 128))
            .ok_or(SourceError::ResourceLimit)?;
        self.lease.resize(bytes)?;
        Ok(Arc::new(GeoPointSelection {
            key,
            state: self.state,
            cells: self.cells,
            visible: self.visible,
            total_visible,
            lease: self.lease,
        }))
    }
}
/// Exact integer weighted RGBA tint. Selected counts/IDs never enter f32.
pub(crate) fn selected_fraction_color(
    base: [u8; 4],
    selected: [u8; 4],
    n: u64,
    total: u64,
) -> [u8; 4] {
    if n == 0 || total == 0 {
        return base;
    }
    debug_assert!(n <= total);
    std::array::from_fn(|i| {
        ((base[i] as u128 * (total - n) as u128
            + selected[i] as u128 * n as u128
            + total as u128 / 2)
            / total as u128) as u8
    })
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::geo::{GeoColumn, GeoDescriptor, GeoLimits};
    use crate::geo_indexed_query_session::{
        GeoIndexedQuerySession, GeoIndexedQueryStep, process_indexed_with_state,
    };
    use crate::geo_layers::GeoStyle;
    use crate::geo_lod::{GeoLodOptions, GeoReducedKind, process, process_with_state};
    use crate::geo_source::{
        GeoChunk, GeoIntervals, GeoManifestBuilder, QueryBudget, ReadRequest, TimePredicate,
    };
    use crate::geo_source_session::test_processor_lock;
    use crate::geo_spatial_build_session::build;
    use crate::geo_spatial_index::{GeoSpatialOptions, ValidatedGeoSpatialIndex};
    use crate::geo_viewport::GeoViewport;
    use crate::scene::SceneDocument;
    use std::collections::BTreeMap;
    const LAYER: u64 = u64::MAX;
    const REV: u64 = 5;
    fn camera() -> GeoViewport {
        GeoViewport::new(GeoCrs::Epsg4326, 0., 0., 0., 128., 96., 0., 0., true).unwrap()
    }
    fn selected_style() -> GeoSelectedStyle {
        GeoSelectedStyle {
            fill: [255, 0, 0, 255],
        }
    }
    #[allow(clippy::too_many_arguments)]
    fn source(
        kind: GeoGeometry,
        xy: &[f64],
        valid: &[u8],
        ids: &[u64],
        offsets: &[u32],
        starts: &[i64],
        ends: &[i64],
        generation: u64,
    ) -> (GeoSourceManifest, Vec<Vec<u8>>) {
        let column = GeoColumn::from_descriptor(GeoDescriptor {
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
        let time_valid = vec![1; ids.len()];
        let time = if starts.is_empty() {
            None
        } else {
            Some(GeoIntervals {
                starts,
                ends,
                start_validity: &time_valid,
                end_validity: &time_valid,
            })
        };
        let bytes = GeoChunk::encode(&column, time).unwrap();
        let chunk = GeoChunk::parse(&bytes, 96 << 20).unwrap();
        let mut builder = GeoManifestBuilder::new();
        builder.push(&chunk).unwrap();
        (builder.finish(generation).unwrap(), vec![bytes])
    }
    fn small() -> (GeoSourceManifest, Vec<Vec<u8>>) {
        source(
            GeoGeometry::Point,
            &[0., 0., 1., 0., 3., 0., 180., 0.],
            &[1, 1, 0, 1, 1],
            &[u64::MAX, u64::MAX, 7, 42, 99],
            &[],
            &[0, 0, 0, 10, 0],
            &[10, 10, 10, 20, 10],
            u64::MAX,
        )
    }
    fn many() -> (GeoSourceManifest, Vec<Vec<u8>>) {
        let n = 32_775;
        source(
            GeoGeometry::MultiPoint,
            &vec![0.; n * 2],
            &[1; 4],
            &[u64::MAX, u64::MAX, 5, 7],
            &[0, 16_385, 32_768, 32_771, n as u32],
            &[0, 0, 0, 10],
            &[10, 10, 10, 20],
            u64::MAX,
        )
    }
    fn state(m: &GeoSourceManifest, ids: &[u64]) -> Arc<GeoLinkedState> {
        GeoLinkedState::new(m, 11, LAYER, REV, ids, selected_style()).unwrap()
    }
    fn execute(
        m: &GeoSourceManifest,
        raw: &[Vec<u8>],
        time: TimePredicate,
        options: GeoLodOptions,
        state: Option<Arc<GeoLinkedState>>,
    ) -> GeoPointResult {
        process_with_state(
            m,
            &mut |r: ReadRequest| Ok(raw[r.chunk_index as usize].clone()),
            camera(),
            time,
            LAYER,
            3,
            REV,
            options,
            QueryBudget::default(),
            state,
            &mut || false,
        )
        .unwrap()
    }
    fn scene(result: &GeoPointResult) -> Vec<u8> {
        crate::geo_lod_scene::compile(
            result,
            GeoStyle {
                fill: [0, 0, 255, 255],
                stroke: [0; 4],
                opacity: 0.5,
                ..GeoStyle::default()
            },
            32 << 20,
        )
        .unwrap()
        .scene
    }
    fn snapshot(m: &GeoSourceManifest, layer: u64, rev: u64) -> GeoOperationSnapshot {
        GeoOperationSnapshot {
            source_digest: m.digest(),
            generation: m.generation(),
            camera: camera().rebuild_key().unwrap(),
            time: TimePredicate::All,
            camera_revision: 1,
            time_revision: 1,
            layer_id: layer,
            layer_revision: 1,
            style_revision: 3,
            state_revision: rev,
        }
    }
    fn index(
        m: &GeoSourceManifest,
        raw: &[Vec<u8>],
    ) -> (Arc<ValidatedGeoSpatialIndex>, BTreeMap<u64, Vec<u8>>) {
        let mut store = BTreeMap::new();
        let index = build(
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
        (Arc::new(index), store)
    }
    #[test]
    fn geo_linked_state_canonical_cap_identity_and_revision_are_atomic() {
        let _guard = test_processor_lock();
        let (m, _) = small();
        let original = state(&m, &[u64::MAX, 7, 7, 0]);
        assert_eq!(original.selected_ids(), &[0, 7, u64::MAX]);
        let mut admission = GeoLinkedStateAdmission::default();
        assert!(
            admission
                .admit(original.clone(), snapshot(&m, LAYER, REV))
                .unwrap()
        );
        let same = state(&m, &[7, 0, u64::MAX]);
        assert_eq!(same.fingerprint(), original.fingerprint());
        assert!(!admission.admit(same, snapshot(&m, LAYER, REV)).unwrap());
        let changed = state(&m, &[u64::MAX]);
        assert!(matches!(
            admission.admit(changed, snapshot(&m, LAYER, REV)),
            Err(SourceError::StaleSource)
        ));
        let profile_change = GeoLinkedState::new(
            &m,
            11,
            LAYER,
            REV,
            original.selected_ids(),
            GeoSelectedStyle { fill: [0; 4] },
        )
        .unwrap();
        assert!(
            admission
                .admit(profile_change, snapshot(&m, LAYER, REV))
                .is_err()
        );
        let next = GeoLinkedState::new(&m, 11, LAYER, REV + 1, &[1], selected_style()).unwrap();
        assert!(admission.admit(next, snapshot(&m, LAYER, REV + 1)).unwrap());
        assert_eq!(original.selected_ids(), &[0, 7, u64::MAX]);
        assert!(
            admission
                .admit(original.clone(), snapshot(&m, LAYER, REV))
                .is_err()
        );
        assert!(
            GeoLinkedState::new(
                &m,
                11,
                LAYER,
                REV,
                &vec![u64::MAX; MAX_SELECTED_IDS + 1],
                selected_style()
            )
            .is_err()
        );
        let full = GeoLinkedState::new(
            &m,
            11,
            LAYER,
            REV,
            &(0..MAX_SELECTED_IDS as u64).collect::<Vec<_>>(),
            selected_style(),
        )
        .unwrap();
        assert_eq!(full.selected_ids().len(), MAX_SELECTED_IDS);
    }
    #[test]
    fn geo_linked_state_time_null_and_offscreen_do_not_erase_selected_intent() {
        let _guard = test_processor_lock();
        let (m, raw) = small();
        let state = state(&m, &[u64::MAX, 7, 42, 99, 12345]);
        let result = execute(
            &m,
            &raw,
            TimePredicate::Window { start: 0, end: 10 },
            GeoLodOptions {
                max_projected_vertices: 3,
                ..GeoLodOptions::default()
            },
            Some(state.clone()),
        );
        assert_eq!(result.visible_vertices, 2);
        assert_eq!(result.projected_vertices, 3);
        assert!(result.key.direct);
        let selected = result.selection.as_ref().unwrap();
        assert_eq!(selected.visible_selected_vertices(), 2);
        assert!(selected.selected_counts().is_empty());
        assert_eq!(state.selected_ids(), &[7, 42, 99, 12345, u64::MAX]);
        let doc = SceneDocument::decode(&scene(&result)).unwrap();
        let records = doc.interaction_records();
        assert_eq!(records.len(), 2);
        for r in records {
            assert_eq!(r.stable_id, u64::MAX);
            assert_eq!(
                doc.interaction_style(r.style_ref).unwrap().0,
                [255, 0, 0, 128]
            );
        }
    }
    #[cfg(feature = "raster")]
    #[test]
    fn geo_linked_state_selected_and_ordinary_fills_render_exact_half_alpha() {
        let _guard = test_processor_lock();
        let (manifest, raw) = source(
            GeoGeometry::Point,
            &[0., 0., 20., 0.],
            &[1, 1],
            &[u64::MAX, 5],
            &[],
            &[],
            &[],
            9,
        );
        let result = execute(
            &manifest,
            &raw,
            TimePredicate::All,
            GeoLodOptions::default(),
            Some(state(&manifest, &[u64::MAX])),
        );
        let document = SceneDocument::decode(&scene(&result)).unwrap();
        let commands = document.to_raster_commands(1.).unwrap();
        let mut pixels = vec![0; 128 * 96 * 4];
        assert!(crate::raster::rasterize_into(
            &commands,
            128,
            96,
            &mut pixels
        ));
        let sample = |x: usize| &pixels[(48 * 128 + x) * 4..(48 * 128 + x) * 4 + 4];
        assert_eq!(sample(64), &[255, 0, 0, 128]);
        assert_eq!(sample(92), &[0, 0, 255, 128]);
    }
    #[test]
    fn geo_linked_state_multipoint_duplicate_ids_have_exact_cluster_and_density_counts() {
        let _guard = test_processor_lock();
        let (m, raw) = many();
        let state = state(&m, &[u64::MAX, 7]);
        for kind in [GeoReducedKind::Cluster, GeoReducedKind::Density] {
            let result = execute(
                &m,
                &raw,
                TimePredicate::Window { start: 0, end: 10 },
                GeoLodOptions {
                    kind,
                    max_cells: 1,
                    ..GeoLodOptions::default()
                },
                Some(state.clone()),
            );
            assert!(!result.key.direct);
            assert_eq!(result.visible_vertices, 32771);
            assert_eq!(result.projected_vertices, 65542);
            let selected = result.selection.as_ref().unwrap();
            assert_eq!(selected.selected_counts(), &[32768]);
            assert_eq!(selected.visible_selected_vertices(), 32768);
            let plain = execute(
                &m,
                &raw,
                TimePredicate::Window { start: 0, end: 10 },
                GeoLodOptions {
                    kind,
                    max_cells: 1,
                    ..GeoLodOptions::default()
                },
                None,
            );
            let expected_base = SceneDocument::decode(&scene(&plain)).unwrap();
            let colored = SceneDocument::decode(&scene(&result)).unwrap();
            let (base, tint) = if kind == GeoReducedKind::Cluster {
                (
                    expected_base.interaction_style(0).unwrap().0,
                    colored.interaction_style(0).unwrap().0,
                )
            } else {
                (
                    expected_base.interaction_image(LAYER).unwrap().rgba[..4]
                        .try_into()
                        .unwrap(),
                    colored.interaction_image(LAYER).unwrap().rgba[..4]
                        .try_into()
                        .unwrap(),
                )
            };
            assert_eq!(
                tint,
                selected_fraction_color(base, [255, 0, 0, 128], 32768, 32771)
            );
            assert_ne!(tint, base);
            assert_eq!(tint[3], 128);
        }
    }
    #[test]
    fn geo_linked_state_explicit_empty_state_preserves_legacy_scene_bytes() {
        let _guard = test_processor_lock();
        for (m, raw) in [small(), many()] {
            for kind in [GeoReducedKind::Cluster, GeoReducedKind::Density] {
                let options = GeoLodOptions {
                    kind,
                    max_cells: 1,
                    ..GeoLodOptions::default()
                };
                let plain = process(
                    &m,
                    &mut |r: ReadRequest| Ok(raw[r.chunk_index as usize].clone()),
                    camera(),
                    TimePredicate::Window { start: 0, end: 10 },
                    LAYER,
                    3,
                    REV,
                    options,
                    QueryBudget::default(),
                    &mut || false,
                )
                .unwrap();
                let empty = execute(
                    &m,
                    &raw,
                    TimePredicate::Window { start: 0, end: 10 },
                    options,
                    Some(state(&m, &[])),
                );
                assert_eq!(plain.key, empty.key);
                assert_eq!(scene(&plain), scene(&empty));
                assert_eq!(empty.selection.unwrap().visible_selected_vertices(), 0);
            }
        }
    }
    #[test]
    fn geo_linked_state_links_only_explicit_namespaces_and_source_layers() {
        let _guard = test_processor_lock();
        let (m, raw) = small();
        let original = state(&m, &[u64::MAX]);
        let (target, other_raw) = source(
            GeoGeometry::Point,
            &[0., 0., 1., 0.],
            &[1, 1],
            &[u64::MAX, 123],
            &[],
            &[],
            &[],
            16,
        );
        let linked = original.link_to(&target, 22, 123, REV).unwrap();
        assert_eq!(linked.selected_ids(), original.selected_ids());
        assert_ne!(linked.binding().namespace, original.binding().namespace);
        assert!(
            original
                .validate_snapshot(snapshot(&target, 123, REV))
                .is_err()
        );
        let mut admission = GeoLinkedStateAdmission::default();
        admission
            .admit(original.clone(), snapshot(&m, LAYER, REV))
            .unwrap();
        assert!(
            admission
                .admit(linked.clone(), snapshot(&target, 123, REV))
                .is_err()
        );
        let a = execute(
            &m,
            &raw,
            TimePredicate::Window { start: 0, end: 10 },
            GeoLodOptions::default(),
            Some(original),
        );
        let b = process_with_state(
            &target,
            &mut |r: ReadRequest| Ok(other_raw[r.chunk_index as usize].clone()),
            camera(),
            TimePredicate::All,
            123,
            3,
            REV,
            GeoLodOptions::default(),
            QueryBudget::default(),
            Some(linked),
            &mut || false,
        )
        .unwrap();
        assert_eq!(a.selection.unwrap().visible_selected_vertices(), 2);
        assert_eq!(b.selection.unwrap().visible_selected_vertices(), 1);
    }
    #[test]
    fn geo_linked_state_indexed_fold_and_scene_match_canonical() {
        let _guard = test_processor_lock();
        for (m, raw) in [small(), many()] {
            let (index, store) = index(&m, &raw);
            for kind in [GeoReducedKind::Cluster, GeoReducedKind::Density] {
                let state = state(&m, &[u64::MAX, 7]);
                let options = GeoLodOptions {
                    kind,
                    max_cells: 1,
                    ..GeoLodOptions::default()
                };
                let a = execute(
                    &m,
                    &raw,
                    TimePredicate::Window { start: 0, end: 10 },
                    options,
                    Some(state.clone()),
                );
                let b = process_indexed_with_state(
                    index.clone(),
                    &mut |r: crate::geo_spatial_index::GeoSpatialRead| Ok(store[&r.page].clone()),
                    camera(),
                    TimePredicate::Window { start: 0, end: 10 },
                    options,
                    LAYER,
                    3,
                    REV,
                    128 << 20,
                    Some(state),
                    &mut || false,
                )
                .unwrap()
                .unwrap();
                assert_eq!(a.key, b.result.key);
                assert_eq!(a.visible_vertices, b.result.visible_vertices);
                assert_eq!(
                    a.selection.as_ref().unwrap().selected_counts(),
                    b.result.selection.as_ref().unwrap().selected_counts()
                );
                assert_eq!(
                    a.selection.as_ref().unwrap().visible_selected_vertices(),
                    b.result
                        .selection
                        .as_ref()
                        .unwrap()
                        .visible_selected_vertices()
                );
                assert_eq!(scene(&a), scene(&b.result));
            }
        }
    }
    #[test]
    fn geo_linked_state_old_result_survives_failure_cancellation_and_shared_clone() {
        let _guard = test_processor_lock();
        let (m, raw) = small();
        let selected = state(&m, &[u64::MAX]);
        let old = execute(
            &m,
            &raw,
            TimePredicate::Window { start: 0, end: 10 },
            GeoLodOptions::default(),
            Some(selected.clone()),
        );
        let before = scene(&old);
        let fail = process_with_state(
            &m,
            &mut |r: ReadRequest| Ok(raw[r.chunk_index as usize].clone()),
            camera(),
            TimePredicate::Window { start: 0, end: 10 },
            LAYER,
            3,
            REV,
            GeoLodOptions {
                max_projected_vertices: 1,
                ..GeoLodOptions::default()
            },
            QueryBudget::default(),
            Some(selected.clone()),
            &mut || false,
        );
        assert!(matches!(fail, Err(SourceError::ResourceLimit)));
        let cancelled = process_with_state(
            &m,
            &mut |r: ReadRequest| Ok(raw[r.chunk_index as usize].clone()),
            camera(),
            TimePredicate::Window { start: 0, end: 10 },
            LAYER,
            3,
            REV,
            GeoLodOptions::default(),
            QueryBudget::default(),
            Some(selected.clone()),
            &mut || true,
        );
        assert!(matches!(cancelled, Err(SourceError::Cancelled)));
        assert_eq!(scene(&old), before);
        let shared = old.selection.as_ref().unwrap().clone();
        let charged = GeoProcessorLease::live_bytes();
        drop(old);
        assert_eq!(GeoProcessorLease::live_bytes(), charged);
        assert_eq!(shared.visible_selected_vertices(), 2);
        drop(shared);
        assert_eq!(GeoProcessorLease::live_bytes(), selected.retained_bytes());
    }
    #[test]
    fn geo_linked_state_admission_before_io_and_global_pressure_recovers() {
        let _guard = test_processor_lock();
        let (m, raw) = small();
        let selected = state(&m, &[u64::MAX]);
        let mut reads = 0;
        let wrong = process_with_state(
            &m,
            &mut |r: ReadRequest| {
                reads += 1;
                Ok(raw[r.chunk_index as usize].clone())
            },
            camera(),
            TimePredicate::All,
            LAYER,
            3,
            REV + 1,
            GeoLodOptions::default(),
            QueryBudget::default(),
            Some(selected.clone()),
            &mut || false,
        );
        assert!(matches!(wrong, Err(SourceError::StaleSource)));
        assert_eq!(reads, 0);
        let live = GeoProcessorLease::live_bytes();
        let pressure =
            GeoProcessorLease::acquire(crate::geo_source::MAX_PROCESSOR_BYTES - live).unwrap();
        assert!(GeoLinkedState::new(&m, 11, LAYER, REV, &[7], selected_style()).is_err());
        let fail = process_with_state(
            &m,
            &mut |r: ReadRequest| {
                reads += 1;
                Ok(raw[r.chunk_index as usize].clone())
            },
            camera(),
            TimePredicate::All,
            LAYER,
            3,
            REV,
            GeoLodOptions::default(),
            QueryBudget::default(),
            Some(selected.clone()),
            &mut || false,
        );
        assert!(matches!(fail, Err(SourceError::ResourceLimit)));
        assert_eq!(reads, 0);
        drop(pressure);
        assert_eq!(GeoProcessorLease::live_bytes(), live);
        drop(execute(
            &m,
            &raw,
            TimePredicate::All,
            GeoLodOptions::default(),
            Some(selected),
        ));
    }
    #[test]
    fn geo_linked_state_indexed_pending_read_cancel_waits_for_ack() {
        let _guard = test_processor_lock();
        let (m, raw) = small();
        let (index, store) = index(&m, &raw);
        let selected = state(&m, &[u64::MAX]);
        let old = execute(
            &m,
            &raw,
            TimePredicate::Window { start: 0, end: 10 },
            GeoLodOptions::default(),
            Some(selected.clone()),
        );
        let before = scene(&old);
        let mut session = GeoIndexedQuerySession::new_with_state(
            index,
            camera(),
            TimePredicate::All,
            GeoLodOptions::default(),
            LAYER,
            3,
            REV,
            128 << 20,
            Some(selected),
        )
        .unwrap()
        .unwrap();
        let ticket = match session.step().unwrap() {
            GeoIndexedQueryStep::NeedRead(t) => t,
            _ => panic!(),
        };
        let borrowed = store[&ticket.request.page].clone();
        let live = GeoProcessorLease::live_bytes();
        session.cancel();
        assert!(session.has_outstanding_io());
        assert!(GeoProcessorLease::live_bytes() < live);
        assert_eq!(
            session.step().unwrap(),
            GeoIndexedQueryStep::AwaitRelease(ticket)
        );
        drop(borrowed);
        session.release_read(ticket).unwrap();
        assert_eq!(session.step().unwrap(), GeoIndexedQueryStep::Cancelled);
        assert!(session.finish().is_err());
        assert_eq!(scene(&old), before);
    }
    #[test]
    fn geo_linked_state_counts_and_rgba_use_checked_full_width_integers() {
        let _guard = test_processor_lock();
        let (m, _) = small();
        let mut accumulator = GeoSelectionAccumulator::new(state(&m, &[u64::MAX]), 0, 1).unwrap();
        accumulator.visible = u64::MAX;
        assert!(matches!(
            accumulator.count_visible(),
            Err(SourceError::ResourceLimit)
        ));
        accumulator.begin_aggregate(1);
        accumulator.cells[0] = u64::MAX;
        assert!(matches!(
            accumulator.count_cell(0),
            Err(SourceError::ResourceLimit)
        ));
        assert_eq!(selected_fraction_color([0; 4], [255; 4], 5, 10), [128; 4]);
        assert_eq!(
            selected_fraction_color([0; 4], [255; 4], u64::MAX, u64::MAX),
            [255; 4]
        );
        assert_eq!(
            selected_fraction_color([17; 4], [255; 4], 0, u64::MAX),
            [17; 4]
        );
    }
}
