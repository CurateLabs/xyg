//! Bounded retained geographic point LOD. See spec/design/geo-lod.md.
use crate::geo::{GeoCrs, GeoError, GeoGeometry};
use crate::geo_source::{
    FeatureRef, FeatureView, GeoChunk, GeoChunkReader, GeoSourceManifest, MAX_PROCESSOR_BYTES,
    MembershipPage, QueryBudget, QueryCursor, QuerySpec, SourceError, TimePredicate,
};
use crate::geo_viewport::{
    GeoViewport, GeoViewportRebuildKey, lonlat_to_mercator, mercator_to_lonlat,
};
use crate::lod_plan;
use std::cell::RefCell;

pub const DIRECT_VERTEX_LIMIT: usize = 32_768;
pub const CLUSTER_CELL_LIMIT: usize = 32_768;
pub const DENSITY_CELL_LIMIT: usize = 196_608;
pub const MAX_PROJECTED_VERTICES: u64 = 2_000_000_000;
type Result<T> = std::result::Result<T, SourceError>;
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum GeoReducedKind {
    Cluster,
    Density,
}
#[derive(Debug, Clone, Copy)]
pub struct GeoLodOptions {
    pub kind: GeoReducedKind,
    pub previous_direct: bool,
    pub max_cells: usize,
    /// Remaining non-cache allowance after caller's manifest/request/old-output reservation.
    pub processor_bytes: usize,
    /// Both projection passes charge this total. Raising it is explicit, not a scale claim.
    pub max_projected_vertices: u64,
}
impl Default for GeoLodOptions {
    fn default() -> Self {
        Self {
            kind: GeoReducedKind::Cluster,
            previous_direct: true,
            max_cells: CLUSTER_CELL_LIMIT,
            processor_bytes: MAX_PROCESSOR_BYTES,
            max_projected_vertices: 2_000_000,
        }
    }
}
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct GeoLodIdentity {
    pub source_digest: [u8; 8],
    pub generation: u64,
    pub source_rows: u64,
    pub crs: GeoCrs,
    pub geometry: GeoGeometry,
    pub layer_id: u64,
    pub style_revision: u64,
    pub state_revision: u64,
}
#[derive(Debug, Clone, Copy, PartialEq)]
pub struct GeoLodKey {
    pub identity: GeoLodIdentity,
    pub camera: GeoViewportRebuildKey,
    pub time: TimePredicate,
    pub kind: GeoReducedKind,
    pub direct: bool,
    pub columns: u32,
    pub rows: u32,
}
#[derive(Debug, Clone, Copy, PartialEq)]
pub struct GeoDirectPoint {
    pub identity: FeatureRef,
    pub vertex: u32,
    pub x: f64,
    pub y: f64,
}
#[derive(Debug, Clone, Copy, Default, PartialEq)]
pub struct GeoPointCell {
    pub count: u64,
    pub x: f64,
    pub y: f64,
}
#[derive(Debug)]
pub enum GeoPointOutput {
    Direct(Vec<GeoDirectPoint>),
    /// Top-first full grid. Empty cells have count=0,x=y=0; no representative feature ID.
    Reduced(Vec<GeoPointCell>),
}
#[derive(Debug)]
pub struct GeoPointResult {
    pub key: GeoLodKey,
    pub output: GeoPointOutput,
    pub visible_vertices: u64,
    pub projected_vertices: u64,
    pub grid_capped: bool,
}
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum GeoLodPass {
    Repeat,
    Finished,
}
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum Phase {
    Count,
    Aggregate,
    Finished,
}

pub struct GeoPointLod {
    identity: GeoLodIdentity,
    camera: GeoViewport,
    time: TimePredicate,
    options: GeoLodOptions,
    phase: Phase,
    failed: bool,
    last_row: Option<u64>,
    last_vertex: Option<(u64, u32)>,
    visible: u64,
    aggregate_visible: u64,
    projected: u64,
    direct: Vec<GeoDirectPoint>,
    cells: Vec<GeoPointCell>,
    columns: u32,
    rows: u32,
    grid_capped: bool,
    reserve: usize,
}
fn invalid() -> SourceError {
    SourceError::Geometry(GeoError::InvalidArgument)
}
fn cancel(c: &mut dyn FnMut() -> bool) -> Result<()> {
    if c() {
        Err(SourceError::Cancelled)
    } else {
        Ok(())
    }
}
impl GeoPointLod {
    /// Does not allocate source-sized arrays. Caller authenticates source chunks/order.
    pub fn new(
        identity: GeoLodIdentity,
        camera: GeoViewport,
        time: TimePredicate,
        options: GeoLodOptions,
    ) -> Result<Self> {
        camera.validate()?;
        time.validate()?;
        if !matches!(
            identity.geometry,
            GeoGeometry::Point | GeoGeometry::MultiPoint
        ) || identity.source_rows > 1_000_000_000
        {
            return Err(invalid());
        }
        let reserve = Self::reservation_bytes(options)?;
        Ok(Self {
            identity,
            camera,
            time,
            options,
            phase: Phase::Count,
            failed: false,
            last_row: None,
            last_vertex: None,
            visible: 0,
            aggregate_visible: 0,
            projected: 0,
            direct: Vec::with_capacity(DIRECT_VERTEX_LIMIT),
            cells: Vec::new(),
            columns: 0,
            rows: 0,
            grid_capped: false,
            reserve,
        })
    }
    /// Allocation-free peak admission for the accumulator and output transition.
    /// A session reserves this amount before calling new; source memory is additional.
    pub fn reservation_bytes(options: GeoLodOptions) -> Result<usize> {
        let cap = match options.kind {
            GeoReducedKind::Cluster => CLUSTER_CELL_LIMIT,
            GeoReducedKind::Density => DENSITY_CELL_LIMIT,
        };
        if options.max_cells == 0
            || options.max_cells > cap
            || options.processor_bytes > MAX_PROCESSOR_BYTES
            || options.max_projected_vertices == 0
            || options.max_projected_vertices > MAX_PROJECTED_VERTICES
        {
            return Err(SourceError::ResourceLimit);
        }
        let reserve = DIRECT_VERTEX_LIMIT
            .checked_mul(std::mem::size_of::<GeoDirectPoint>())
            .and_then(|a| {
                options
                    .max_cells
                    .checked_mul(std::mem::size_of::<GeoPointCell>())
                    .and_then(|b| a.checked_add(b))
            })
            .and_then(|n| n.checked_mul(2))
            .and_then(|n| n.checked_add(8192))
            .ok_or(SourceError::ResourceLimit)?;
        if reserve > options.processor_bytes {
            return Err(SourceError::ResourceLimit);
        }
        Ok(reserve)
    }
    /// Allocation-free binding for session pre-I/O and post-output checks. The
    /// Count phase's direct/grid fields are provisional until end_pass.
    pub fn binding_key(&self) -> Result<GeoLodKey> {
        Ok(GeoLodKey {
            identity: self.identity,
            camera: self.camera.rebuild_key()?,
            time: self.time,
            kind: self.options.kind,
            direct: self.columns == 0,
            columns: self.columns,
            rows: self.rows,
        })
    }
    /// Maximum simultaneous output/candidate transition allowance. Source chunk and manifest are additional live memory.
    pub fn reserved_bytes(&self) -> usize {
        self.reserve
    }
    pub fn fold_chunk(
        &mut self,
        chunk: &GeoChunk,
        chunk_index: u32,
        first_row: u64,
        c: &mut dyn FnMut() -> bool,
    ) -> Result<()> {
        if self.failed {
            return Err(SourceError::StaleSource);
        }
        let result = self.fold_chunk_inner(chunk, chunk_index, first_row, c);
        if result.is_err() {
            self.failed = true;
        }
        result
    }
    fn fold_chunk_inner(
        &mut self,
        chunk: &GeoChunk,
        chunk_index: u32,
        first_row: u64,
        c: &mut dyn FnMut() -> bool,
    ) -> Result<()> {
        cancel(c)?;
        if first_row
            .checked_add(chunk.column().len() as u64)
            .is_none_or(|end| end > self.identity.source_rows)
        {
            return Err(SourceError::StaleSource);
        }
        for f in chunk.rows() {
            let r = FeatureRef {
                chunk_index,
                row: f.row as u32,
                source_row: first_row + f.row as u64,
                feature_id: f.column.feature_ids()[f.row],
            };
            self.fold_feature(f, r, c)?;
        }
        cancel(c)
    }
    /// Shared time-first policy for synchronous scans and resumable authenticated sessions.
    pub fn fold_feature(
        &mut self,
        f: FeatureView<'_>,
        r: FeatureRef,
        c: &mut dyn FnMut() -> bool,
    ) -> Result<()> {
        if self.failed {
            return Err(SourceError::StaleSource);
        }
        let result = self.fold_feature_inner(f, r, c);
        if result.is_err() {
            self.failed = true;
        }
        result
    }
    fn fold_feature_inner(
        &mut self,
        f: FeatureView<'_>,
        r: FeatureRef,
        c: &mut dyn FnMut() -> bool,
    ) -> Result<()> {
        cancel(c)?;
        if self.phase == Phase::Finished
            || self.last_row.is_some_and(|v| r.source_row <= v)
            || r.source_row >= self.identity.source_rows
            || f.row >= f.column.len()
            || r.row as usize != f.row
            || r.feature_id != f.column.feature_ids()[f.row]
            || f.column.crs() != self.identity.crs
            || f.column.geometry() != self.identity.geometry
        {
            return Err(SourceError::StaleSource);
        }
        self.last_row = Some(r.source_row);
        if !self.time.matches(f.interval_start, f.interval_end) {
            return Ok(());
        }
        if f.vertices.start > f.vertices.end || f.vertices.end > f.column.vertex_count() {
            return Err(invalid());
        }
        for vertex in f.vertices.clone() {
            let xy = &f.column.xy()[vertex * 2..vertex * 2 + 2];
            self.fold_vertex_inner(
                r,
                vertex as u32,
                [xy[0], xy[1]],
                f.interval_start,
                f.interval_end,
                c,
            )?;
        }
        Ok(())
    }
    /// Private authenticated-index seam. Original chunk-global vertex indices
    /// and source ordering are retained; no host may manufacture this authority.
    pub(crate) fn fold_indexed_vertex(
        &mut self,
        r: FeatureRef,
        vertex: u32,
        xy: [f64; 2],
        start: Option<i64>,
        end: Option<i64>,
        c: &mut dyn FnMut() -> bool,
    ) -> Result<()> {
        if self.failed {
            return Err(SourceError::StaleSource);
        }
        let result = self.fold_vertex_inner(r, vertex, xy, start, end, c);
        if result.is_err() {
            self.failed = true;
        }
        result
    }
    fn fold_vertex_inner(
        &mut self,
        r: FeatureRef,
        vertex: u32,
        xy: [f64; 2],
        start: Option<i64>,
        end: Option<i64>,
        c: &mut dyn FnMut() -> bool,
    ) -> Result<()> {
        cancel(c)?;
        let key = (r.source_row, vertex);
        if self.phase == Phase::Finished
            || r.source_row >= self.identity.source_rows
            || self.last_vertex.is_some_and(|last| key <= last)
        {
            return Err(SourceError::StaleSource);
        }
        self.last_vertex = Some(key);
        if !self.time.matches(start, end) {
            return Ok(());
        }
        self.projected = self
            .projected
            .checked_add(1)
            .ok_or(SourceError::ResourceLimit)?;
        if self.projected > self.options.max_projected_vertices {
            return Err(SourceError::ResourceLimit);
        }
        let (x, y) = project(&self.camera, self.identity.crs, xy[0], xy[1])?;
        if !visible(&self.camera, x, y) {
            return Ok(());
        }
        match self.phase {
            Phase::Count => {
                self.visible = self
                    .visible
                    .checked_add(1)
                    .ok_or(SourceError::ResourceLimit)?;
                if self.visible <= DIRECT_VERTEX_LIMIT as u64 {
                    self.direct.push(GeoDirectPoint {
                        identity: r,
                        vertex,
                        x,
                        y,
                    });
                } else if !self.direct.is_empty() {
                    self.direct = Vec::new();
                }
            }
            Phase::Aggregate => {
                self.aggregate_visible = self
                    .aggregate_visible
                    .checked_add(1)
                    .ok_or(SourceError::ResourceLimit)?;
                let index = cell_index(&self.camera, self.columns, self.rows, x, y);
                let cell = &mut self.cells[index];
                cell.count = cell
                    .count
                    .checked_add(1)
                    .ok_or(SourceError::ResourceLimit)?;
                cell.x += x;
                cell.y += y;
                if !cell.x.is_finite() || !cell.y.is_finite() {
                    return Err(SourceError::ResourceLimit);
                }
            }
            Phase::Finished => return Err(invalid()),
        }
        Ok(())
    }
    pub fn end_pass(&mut self) -> Result<GeoLodPass> {
        if self.failed {
            return Err(SourceError::StaleSource);
        }
        match self.phase {
            Phase::Count => {
                // Enter at floor(limit/1.15), leave at hard limit: hysteresis never expands allocation.
                let plan = lod_plan::plan(
                    self.visible,
                    DIRECT_VERTEX_LIMIT as f64 / lod_plan::DEFAULT_EXIT_FACTOR,
                    self.options.previous_direct,
                    lod_plan::DEFAULT_EXIT_FACTOR,
                    self.camera.width.ceil() as i32,
                    self.camera.height.ceil() as i32,
                    lod_plan::DEFAULT_TARGET_PER_CELL,
                )
                .ok_or_else(invalid)?;
                if plan.exact && self.visible <= DIRECT_VERTEX_LIMIT as u64 {
                    self.phase = Phase::Finished;
                    return Ok(GeoLodPass::Finished);
                }
                self.direct = Vec::new();
                let (mut w, mut h) = (plan.grid_w as usize, plan.grid_h as usize);
                while w.checked_mul(h).ok_or(SourceError::ResourceLimit)? > self.options.max_cells {
                    if w >= h && w > 1 {
                        w = w.div_ceil(2);
                    } else if h > 1 {
                        h = h.div_ceil(2);
                    } else {
                        return Err(SourceError::ResourceLimit);
                    }
                    self.grid_capped = true;
                }
                self.columns = w as u32;
                self.rows = h as u32;
                self.cells = vec![GeoPointCell::default(); w * h];
                self.phase = Phase::Aggregate;
                self.last_row = None;
                self.last_vertex = None;
                Ok(GeoLodPass::Repeat)
            }
            Phase::Aggregate => {
                if self.aggregate_visible != self.visible {
                    return Err(SourceError::StaleSource);
                }
                for cell in &mut self.cells {
                    if cell.count > 0 {
                        cell.x /= cell.count as f64;
                        cell.y /= cell.count as f64;
                    }
                }
                self.phase = Phase::Finished;
                Ok(GeoLodPass::Finished)
            }
            Phase::Finished => Err(invalid()),
        }
    }
    pub fn finish(self) -> Result<GeoPointResult> {
        if self.failed || self.phase != Phase::Finished {
            return Err(invalid());
        }
        let direct = self.columns == 0;
        Ok(GeoPointResult {
            key: GeoLodKey {
                identity: self.identity,
                camera: self.camera.rebuild_key()?,
                time: self.time,
                kind: self.options.kind,
                direct,
                columns: self.columns,
                rows: self.rows,
            },
            output: if direct {
                GeoPointOutput::Direct(self.direct)
            } else {
                GeoPointOutput::Reduced(self.cells)
            },
            visible_vertices: self.visible,
            projected_vertices: self.projected,
            grid_capped: self.grid_capped,
        })
    }
    pub fn output_bytes(output: &GeoPointResult) -> usize {
        std::mem::size_of::<GeoPointResult>()
            + match &output.output {
                GeoPointOutput::Direct(v) => v.capacity() * std::mem::size_of::<GeoDirectPoint>(),
                GeoPointOutput::Reduced(v) => v.capacity() * std::mem::size_of::<GeoPointCell>(),
            }
    }
}
fn project(camera: &GeoViewport, source: GeoCrs, x: f64, y: f64) -> Result<(f64, f64)> {
    let (x, y) = if source == camera.crs {
        (x, y)
    } else if source == GeoCrs::Epsg4326 {
        lonlat_to_mercator(x, y)
    } else {
        mercator_to_lonlat(x, y)
    };
    Ok(camera.project(x, y)?)
}
fn visible(camera: &GeoViewport, x: f64, y: f64) -> bool {
    x.is_finite() && y.is_finite() && x >= 0. && y >= 0. && x < camera.width && y < camera.height
}
fn cell_index(camera: &GeoViewport, w: u32, h: u32, x: f64, y: f64) -> usize {
    let column = ((x / camera.width * w as f64).floor() as usize).min(w as usize - 1);
    let row = ((y / camera.height * h as f64).floor() as usize).min(h as usize - 1);
    row * w as usize + column
}
fn identity(
    m: &GeoSourceManifest,
    layer_id: u64,
    style_revision: u64,
    state_revision: u64,
) -> GeoLodIdentity {
    GeoLodIdentity {
        source_digest: m.digest(),
        generation: m.generation(),
        source_rows: m.rows(),
        crs: m.crs(),
        geometry: m.geometry(),
        layer_id,
        style_revision,
        state_revision,
    }
}
/// Complete bounded synchronous wrapper. All folds are tentative until success.
#[allow(clippy::too_many_arguments)]
pub fn process<R: GeoChunkReader>(
    manifest: &GeoSourceManifest,
    reader: &mut R,
    camera: GeoViewport,
    time: TimePredicate,
    layer_id: u64,
    style_revision: u64,
    state_revision: u64,
    options: GeoLodOptions,
    budget: QueryBudget,
    c: &mut impl FnMut() -> bool,
) -> Result<GeoPointResult> {
    let budget = QueryBudget {
        processor_bytes: budget.processor_bytes.min(options.processor_bytes),
        ..budget
    };
    budget.validate()?;
    let options = GeoLodOptions {
        processor_bytes: budget
            .processor_bytes
            .checked_sub(manifest.metadata_bytes())
            .ok_or(SourceError::ResourceLimit)?,
        ..options
    };
    let mut lod = GeoPointLod::new(
        identity(manifest, layer_id, style_revision, state_revision),
        camera,
        time,
        options,
    )?;
    let q = QuerySpec { bounds: None, time };
    let shared = RefCell::new(c);
    loop {
        manifest.scan_chunks(
            q,
            budget,
            lod.reserved_bytes(),
            reader,
            &mut || (**shared.borrow_mut())(),
            |f, r| lod.fold_feature(f, r, &mut || (**shared.borrow_mut())()),
        )?;
        if lod.end_pass()? == GeoLodPass::Finished {
            break;
        }
    }
    cancel(&mut || (**shared.borrow_mut())())?;
    lod.finish()
}
#[derive(Debug, Clone, Copy, PartialEq)]
pub struct GeoCellCursor {
    pub key: GeoLodKey,
    pub cell: u32,
    pub source: QueryCursor,
}
#[derive(Debug)]
pub struct GeoCellMembership {
    pub page: MembershipPage,
    pub next: Option<GeoCellCursor>,
    pub projected_vertices: u64,
}
fn camera_from_key(k: GeoViewportRebuildKey) -> GeoViewport {
    GeoViewport {
        crs: k.crs,
        center_x: f64::from_bits(k.center_x_bits),
        center_y: f64::from_bits(k.center_y_bits),
        zoom: f64::from_bits(k.zoom_bits),
        width: f64::from_bits(k.width_bits),
        height: f64::from_bits(k.height_bits),
        bearing_deg: f64::from_bits(k.bearing_deg_bits),
        pitch_deg: f64::from_bits(k.pitch_deg_bits),
        world_wrap: k.world_wrap,
    }
}
/// Allocation-free exact reduced-cell predicate shared by synchronous and
/// resumable membership readers. Source readers authenticate chunks first.
pub struct GeoCellQuery {
    key: GeoLodKey,
    cell: u32,
    camera: GeoViewport,
    source_cursor: Option<QueryCursor>,
    max_projected_vertices: u64,
    projected_vertices: u64,
    failed: bool,
}
impl GeoCellQuery {
    pub fn new(
        manifest: &GeoSourceManifest,
        key: GeoLodKey,
        cell: u32,
        cursor: Option<GeoCellCursor>,
        max_projected_vertices: u64,
    ) -> Result<Self> {
        let cap = match key.kind {
            GeoReducedKind::Cluster => CLUSTER_CELL_LIMIT,
            GeoReducedKind::Density => DENSITY_CELL_LIMIT,
        };
        let cells = (key.columns as usize)
            .checked_mul(key.rows as usize)
            .ok_or(SourceError::ResourceLimit)?;
        if key.direct
            || key.columns == 0
            || key.rows == 0
            || cells > cap
            || cell as usize >= cells
            || max_projected_vertices == 0
            || max_projected_vertices > MAX_PROJECTED_VERTICES
            || !matches!(
                key.identity.geometry,
                GeoGeometry::Point | GeoGeometry::MultiPoint
            )
        {
            return Err(invalid());
        }
        if key.identity
            != identity(
                manifest,
                key.identity.layer_id,
                key.identity.style_revision,
                key.identity.state_revision,
            )
            || cursor.is_some_and(|v| v.key != key || v.cell != cell)
        {
            return Err(SourceError::StaleSource);
        }
        let camera = camera_from_key(key.camera);
        camera.validate()?;
        if camera.rebuild_key()? != key.camera {
            return Err(SourceError::StaleSource);
        }
        let query = QuerySpec {
            bounds: None,
            time: key.time,
        };
        query.validate()?;
        if let Some(c) = cursor {
            if c.source.generation != manifest.generation()
                || c.source.source_digest != manifest.digest()
                || c.source.query_digest != query.digest()
            {
                return Err(SourceError::StaleSource);
            }
            let chunk = c.source.chunk_index as usize;
            if chunk > manifest.chunks().len()
                || (chunk == manifest.chunks().len() && c.source.row != 0)
                || (chunk < manifest.chunks().len() && c.source.row > manifest.chunks()[chunk].rows)
            {
                return Err(SourceError::InvalidFrame);
            }
        }
        Ok(Self {
            key,
            cell,
            camera,
            source_cursor: cursor.map(|v| v.source),
            max_projected_vertices,
            projected_vertices: 0,
            failed: false,
        })
    }
    pub fn query_spec(&self) -> QuerySpec {
        QuerySpec {
            bounds: None,
            time: self.key.time,
        }
    }
    pub fn source_cursor(&self) -> Option<QueryCursor> {
        self.source_cursor
    }
    pub fn wrap_cursor(&self, source: QueryCursor) -> GeoCellCursor {
        GeoCellCursor {
            key: self.key,
            cell: self.cell,
            source,
        }
    }
    pub fn projected_vertices(&self) -> u64 {
        self.projected_vertices
    }
    /// One bool per source row: multiple matching vertices never duplicate membership.
    /// Any failure poisons this tentative predicate; a reader must discard its page.
    pub fn matches(&mut self, f: &FeatureView<'_>, c: &mut dyn FnMut() -> bool) -> Result<bool> {
        if self.failed {
            return Err(SourceError::StaleSource);
        }
        let result = self.matches_inner(f, c);
        if result.is_err() {
            self.failed = true;
        }
        result
    }
    fn matches_inner(&mut self, f: &FeatureView<'_>, c: &mut dyn FnMut() -> bool) -> Result<bool> {
        cancel(c)?;
        if f.row >= f.column.len()
            || f.column.crs() != self.key.identity.crs
            || f.column.geometry() != self.key.identity.geometry
        {
            return Err(SourceError::StaleSource);
        }
        if !self.key.time.matches(f.interval_start, f.interval_end)
            || f.column.validity()[f.row] == 0
        {
            return Ok(false);
        }
        if f.vertices.start > f.vertices.end || f.vertices.end > f.column.vertex_count() {
            return Err(invalid());
        }
        for i in f.vertices.clone() {
            cancel(c)?;
            self.projected_vertices = self
                .projected_vertices
                .checked_add(1)
                .ok_or(SourceError::ResourceLimit)?;
            if self.projected_vertices > self.max_projected_vertices {
                return Err(SourceError::ResourceLimit);
            }
            let xy = &f.column.xy()[i * 2..i * 2 + 2];
            let (x, y) = project(&self.camera, f.column.crs(), xy[0], xy[1])?;
            if visible(&self.camera, x, y)
                && cell_index(&self.camera, self.key.columns, self.key.rows, x, y)
                    == self.cell as usize
            {
                return Ok(true);
            }
        }
        Ok(false)
    }
}
/// Exact source-row union for a reduced cell. MultiPoint qualifies once even when
/// several vertices land in that cell; literal duplicate IDs on distinct rows remain.
#[allow(clippy::too_many_arguments)]
pub fn membership_page<R: GeoChunkReader>(
    manifest: &GeoSourceManifest,
    reader: &mut R,
    key: GeoLodKey,
    cell: u32,
    cursor: Option<GeoCellCursor>,
    budget: QueryBudget,
    max_projected_vertices: u64,
    c: &mut impl FnMut() -> bool,
) -> Result<GeoCellMembership> {
    let mut predicate = GeoCellQuery::new(manifest, key, cell, cursor, max_projected_vertices)?;
    let shared = RefCell::new(c);
    let page = manifest.query_page_where(
        predicate.query_spec(),
        predicate.source_cursor(),
        budget,
        reader,
        &mut || (**shared.borrow_mut())(),
        |f| predicate.matches(f, &mut || (**shared.borrow_mut())()),
        |_, _| Ok(()),
    )?;
    let next = page.next.map(|source| predicate.wrap_cursor(source));
    Ok(GeoCellMembership {
        page,
        next,
        projected_vertices: predicate.projected_vertices(),
    })
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::geo::{GeoColumn, GeoDescriptor, GeoLimits};
    use crate::geo_source::{GeoIntervals, GeoManifestBuilder, ReadRequest};
    fn camera() -> GeoViewport {
        GeoViewport::new(GeoCrs::Epsg4326, 0., 0., 0., 800., 600., 0., 0., true).unwrap()
    }
    fn chunk(
        kind: GeoGeometry,
        crs: GeoCrs,
        xy: &[f64],
        offsets: &[u32],
        ids: &[u64],
        time: Option<GeoIntervals<'_>>,
    ) -> GeoChunk {
        let column = GeoColumn::from_descriptor(GeoDescriptor {
            geometry: kind,
            crs,
            xy,
            validity: &vec![1; ids.len()],
            feature_ids: Some(ids),
            offsets0: offsets,
            offsets1: &[],
            offsets2: &[],
            limits: GeoLimits::default(),
        })
        .unwrap();
        GeoChunk::parse(&GeoChunk::encode(&column, time).unwrap(), 96 << 20).unwrap()
    }
    fn source(chunks: &[GeoChunk]) -> (GeoSourceManifest, Vec<Vec<u8>>) {
        let mut b = GeoManifestBuilder::new();
        let mut raw = Vec::new();
        for c in chunks {
            b.push(c).unwrap();
            raw.push(GeoChunk::encode(c.column(), c.intervals()).unwrap());
        }
        (b.finish(9).unwrap(), raw)
    }
    fn execute(
        m: &GeoSourceManifest,
        raw: &[Vec<u8>],
        options: GeoLodOptions,
        time: TimePredicate,
    ) -> GeoPointResult {
        process(
            m,
            &mut |r: ReadRequest| Ok(raw[r.chunk_index as usize].clone()),
            camera(),
            time,
            7,
            8,
            9,
            options,
            QueryBudget::default(),
            &mut || false,
        )
        .unwrap()
    }
    #[test]
    fn direct_preserves_literal_ids_vertex_and_authenticated_chunk_indices() {
        let chunks = [
            chunk(
                GeoGeometry::Point,
                GeoCrs::Epsg4326,
                &[0., 0.],
                &[],
                &[u64::MAX],
                None,
            ),
            chunk(
                GeoGeometry::Point,
                GeoCrs::Epsg4326,
                &[1., 0.],
                &[],
                &[0x8000000000000001],
                None,
            ),
        ];
        let (m, raw) = source(&chunks);
        let r = execute(&m, &raw, GeoLodOptions::default(), TimePredicate::All);
        let GeoPointOutput::Direct(points) = r.output else {
            panic!()
        };
        assert_eq!(points.len(), 2);
        assert_eq!(points[0].identity.feature_id, u64::MAX);
        assert_eq!(points[1].identity.chunk_index, 1);
        assert_eq!(points[1].identity.source_row, 1);
        assert!((points[1].x - (400. + 512. / 360.)).abs() < 1e-9);
    }
    #[test]
    fn time_exclusion_happens_before_projection_and_chunk_read() {
        let chunks = [chunk(
            GeoGeometry::Point,
            GeoCrs::Epsg4326,
            &[179., 85.],
            &[],
            &[u64::MAX],
            Some(GeoIntervals {
                starts: &[0],
                ends: &[10],
                start_validity: &[1],
                end_validity: &[1],
            }),
        )];
        let (m, _) = source(&chunks);
        let mut reads = 0;
        let r = process(
            &m,
            &mut |_r: ReadRequest| {
                reads += 1;
                Err(SourceError::Reader)
            },
            camera(),
            TimePredicate::Instant(10),
            1,
            1,
            1,
            GeoLodOptions::default(),
            QueryBudget::default(),
            &mut || false,
        )
        .unwrap();
        assert_eq!(reads, 0);
        assert_eq!(r.projected_vertices, 0);
        assert_eq!(r.visible_vertices, 0);
        let mut a = GeoPointLod::new(
            identity(&m, 1, 1, 1),
            camera(),
            TimePredicate::Instant(10),
            GeoLodOptions::default(),
        )
        .unwrap();
        a.fold_chunk(&chunks[0], 0, 0, &mut || false).unwrap();
        assert_eq!(a.projected, 0);
    }
    #[test]
    fn crs_conversion_uses_shared_projection_and_half_open_visibility() {
        let chunks = [chunk(
            GeoGeometry::Point,
            GeoCrs::Epsg3857,
            &[111319.49079327358, 0.],
            &[],
            &[u64::MAX],
            None,
        )];
        let (m, raw) = source(&chunks);
        let r = execute(&m, &raw, GeoLodOptions::default(), TimePredicate::All);
        let GeoPointOutput::Direct(points) = r.output else {
            panic!()
        };
        assert!((points[0].x - (400. + 512. / 360.)).abs() < 1e-9);
        assert!(visible(&camera(), 0., 0.));
        assert!(!visible(&camera(), 800., 0.));
        assert!(!visible(&camera(), 0., 600.));
    }
    #[test]
    fn reduced_counts_vertices_but_membership_pages_deduplicate_multipoint_rows() {
        let xy = vec![0.; 32773 * 2];
        let chunks = [chunk(
            GeoGeometry::MultiPoint,
            GeoCrs::Epsg4326,
            &xy,
            &[0, 32769, 32771, 32773],
            &[u64::MAX, u64::MAX, 17],
            None,
        )];
        let (m, raw) = source(&chunks);
        let r = execute(&m, &raw, GeoLodOptions::default(), TimePredicate::All);
        assert_eq!(r.visible_vertices, 32773);
        let GeoPointOutput::Reduced(ref cells) = r.output else {
            panic!()
        };
        assert_eq!(cells.iter().map(|c| c.count).sum::<u64>(), 32773);
        let cell = cells.iter().position(|c| c.count > 0).unwrap() as u32;
        assert_eq!(cells[cell as usize].x, 400.);
        assert_eq!(cells[cell as usize].y, 300.);
        let budget = QueryBudget {
            page_rows: 1,
            ..QueryBudget::default()
        };
        let mut cursor = None;
        let mut members = Vec::new();
        loop {
            let page = membership_page(
                &m,
                &mut |q: ReadRequest| Ok(raw[q.chunk_index as usize].clone()),
                r.key,
                cell,
                cursor,
                budget,
                100_000,
                &mut || false,
            )
            .unwrap();
            members.extend(page.page.features);
            cursor = page.next;
            if cursor.is_none() {
                break;
            }
        }
        assert_eq!(
            members.iter().map(|m| m.source_row).collect::<Vec<_>>(),
            vec![0, 1, 2]
        );
        assert_eq!(
            members.iter().map(|m| m.feature_id).collect::<Vec<_>>(),
            vec![u64::MAX, u64::MAX, 17]
        );
        let first = membership_page(
            &m,
            &mut |q: ReadRequest| Ok(raw[q.chunk_index as usize].clone()),
            r.key,
            cell,
            None,
            budget,
            100_000,
            &mut || false,
        )
        .unwrap();
        for revision in 0..6 {
            let mut changed = r.key;
            match revision {
                0 => changed.identity.style_revision += 1,
                1 => changed.identity.state_revision += 1,
                2 => changed.time = TimePredicate::Instant(0),
                3 => changed.camera.zoom_bits = 1f64.to_bits(),
                4 => changed.kind = GeoReducedKind::Density,
                _ => changed.identity.generation += 1,
            };
            assert!(matches!(
                membership_page(
                    &m,
                    &mut |q: ReadRequest| Ok(raw[q.chunk_index as usize].clone()),
                    changed,
                    cell,
                    first.next,
                    budget,
                    100_000,
                    &mut || false
                ),
                Err(SourceError::StaleSource)
            ));
        }
    }
    #[test]
    fn cancelled_and_resource_failed_accumulator_cannot_publish_partial_output() {
        let c = chunk(
            GeoGeometry::Point,
            GeoCrs::Epsg4326,
            &[0., 0.],
            &[],
            &[u64::MAX],
            None,
        );
        let (m, _) = source(std::slice::from_ref(&c));
        let mut a = GeoPointLod::new(
            identity(&m, 1, 1, 1),
            camera(),
            TimePredicate::All,
            GeoLodOptions::default(),
        )
        .unwrap();
        assert_eq!(
            GeoPointLod::reservation_bytes(GeoLodOptions::default()).unwrap(),
            a.reserved_bytes()
        );
        assert!(matches!(
            a.fold_chunk(&c, 0, 0, &mut || true),
            Err(SourceError::Cancelled)
        ));
        assert!(a.end_pass().is_err());
        assert!(a.finish().is_err());
        let options = GeoLodOptions {
            processor_bytes: 1,
            ..GeoLodOptions::default()
        };
        assert!(matches!(
            GeoPointLod::reservation_bytes(options),
            Err(SourceError::ResourceLimit)
        ));
        assert!(matches!(
            GeoPointLod::new(identity(&m, 1, 1, 1), camera(), TimePredicate::All, options),
            Err(SourceError::ResourceLimit)
        ));
        let options = GeoLodOptions {
            max_projected_vertices: 1,
            ..GeoLodOptions::default()
        };
        let mut a =
            GeoPointLod::new(identity(&m, 1, 1, 1), camera(), TimePredicate::All, options).unwrap();
        a.fold_chunk(&c, 0, 0, &mut || false).unwrap();
        assert!(a.fold_chunk(&c, 0, 0, &mut || false).is_err());
        assert!(a.finish().is_err());
    }
    #[test]
    fn hysteresis_does_not_raise_the_hard_direct_vertex_budget() {
        let c = chunk(
            GeoGeometry::Point,
            GeoCrs::Epsg4326,
            &[0., 0.],
            &[],
            &[1],
            None,
        );
        let (m, _) = source(std::slice::from_ref(&c));
        for (count, previous, expected) in [
            (32768, true, GeoLodPass::Finished),
            (32769, true, GeoLodPass::Repeat),
            (30000, false, GeoLodPass::Repeat),
            (28000, false, GeoLodPass::Finished),
        ] {
            let mut a = GeoPointLod::new(
                identity(&m, 1, 1, 1),
                camera(),
                TimePredicate::All,
                GeoLodOptions {
                    previous_direct: previous,
                    ..GeoLodOptions::default()
                },
            )
            .unwrap();
            // Pure count-planner proof; this does not execute that many source rows.
            a.visible = count;
            assert_eq!(a.end_pass().unwrap(), expected);
        }
        let mut a = GeoPointLod::new(
            identity(&m, 1, 1, 1),
            camera(),
            TimePredicate::All,
            GeoLodOptions::default(),
        )
        .unwrap();
        a.visible = 1_000_000_000;
        assert_eq!(a.end_pass().unwrap(), GeoLodPass::Repeat);
        assert!(a.cells.len() <= CLUSTER_CELL_LIMIT);
        assert!(a.grid_capped);
        assert_eq!(a.projected, 0);
    }
    #[test]
    fn density_is_explicit_grid_cap_and_work_failure_are_recorded() {
        let xy = vec![0.; 32769 * 2];
        let c = chunk(
            GeoGeometry::MultiPoint,
            GeoCrs::Epsg4326,
            &xy,
            &[0, 32769],
            &[u64::MAX],
            None,
        );
        let (m, raw) = source(std::slice::from_ref(&c));
        let options = GeoLodOptions {
            kind: GeoReducedKind::Density,
            max_cells: 1,
            ..GeoLodOptions::default()
        };
        let r = execute(&m, &raw, options, TimePredicate::All);
        assert_eq!(r.key.kind, GeoReducedKind::Density);
        assert!(r.grid_capped);
        assert_eq!((r.key.columns, r.key.rows), (1, 1));
        let GeoPointOutput::Reduced(cells) = r.output else {
            panic!()
        };
        assert_eq!(cells[0].count, 32769);
        let options = GeoLodOptions {
            max_projected_vertices: 2,
            ..GeoLodOptions::default()
        };
        let mut a =
            GeoPointLod::new(identity(&m, 7, 8, 9), camera(), TimePredicate::All, options).unwrap();
        assert_eq!(a.binding_key().unwrap().identity.source_digest, m.digest());
        assert!(matches!(
            a.fold_chunk(&c, 0, 0, &mut || false),
            Err(SourceError::ResourceLimit)
        ));
        assert!(a.end_pass().is_err());
        assert!(a.finish().is_err());
    }
    #[test]
    fn shared_cell_query_checks_binding_before_io_and_time_before_geometry() {
        let c = chunk(
            GeoGeometry::Point,
            GeoCrs::Epsg4326,
            &[0., 0.],
            &[],
            &[u64::MAX],
            Some(GeoIntervals {
                starts: &[0],
                ends: &[10],
                start_validity: &[1],
                end_validity: &[1],
            }),
        );
        let (m, _) = source(std::slice::from_ref(&c));
        let key = GeoLodKey {
            identity: identity(&m, 7, 8, 9),
            camera: camera().rebuild_key().unwrap(),
            time: TimePredicate::Instant(10),
            kind: GeoReducedKind::Cluster,
            direct: false,
            columns: 1,
            rows: 1,
        };
        let mut predicate = GeoCellQuery::new(&m, key, 0, None, 1).unwrap();
        let mut f = c.rows().next().unwrap();
        f.vertices = usize::MAX..usize::MAX;
        assert!(!predicate.matches(&f, &mut || false).unwrap());
        assert_eq!(predicate.projected_vertices(), 0);
        let cursor = QueryCursor {
            generation: m.generation(),
            source_digest: m.digest(),
            query_digest: predicate.query_spec().digest(),
            chunk_index: 0,
            row: 0,
        };
        let wrapped = predicate.wrap_cursor(cursor);
        let resumed = GeoCellQuery::new(&m, key, 0, Some(wrapped), 1).unwrap();
        assert_eq!(resumed.source_cursor(), Some(cursor));
        let mut stale = wrapped;
        stale.source.query_digest = [0; 8];
        assert!(matches!(
            GeoCellQuery::new(&m, key, 0, Some(stale), 1),
            Err(SourceError::StaleSource)
        ));
        let mut invalid_cursor = wrapped;
        invalid_cursor.source.row = 2;
        assert!(matches!(
            GeoCellQuery::new(&m, key, 0, Some(invalid_cursor), 1),
            Err(SourceError::InvalidFrame)
        ));
        let mut invalid_camera = key;
        invalid_camera.camera.zoom_bits = (-0.0f64).to_bits();
        assert!(matches!(
            GeoCellQuery::new(&m, invalid_camera, 0, None, 1),
            Err(SourceError::StaleSource)
        ));
        let live_key = GeoLodKey {
            time: TimePredicate::Instant(5),
            ..key
        };
        let mut live = GeoCellQuery::new(&m, live_key, 0, None, 1).unwrap();
        assert!(
            live.matches(&c.rows().next().unwrap(), &mut || false)
                .unwrap()
        );
        assert_eq!(live.projected_vertices(), 1);
        assert!(matches!(
            live.matches(&c.rows().next().unwrap(), &mut || true),
            Err(SourceError::Cancelled)
        ));
        assert!(matches!(
            live.matches(&c.rows().next().unwrap(), &mut || false),
            Err(SourceError::StaleSource)
        ));
    }
    #[test]
    fn shared_cell_query_cumulative_work_failure_cannot_resume_tentative_page() {
        let c = chunk(
            GeoGeometry::MultiPoint,
            GeoCrs::Epsg4326,
            &[179., 0., 179., 0.],
            &[0, 2],
            &[u64::MAX],
            None,
        );
        let (m, _) = source(std::slice::from_ref(&c));
        let zoomed = GeoViewport {
            zoom: 4.,
            ..camera()
        };
        let key = GeoLodKey {
            identity: identity(&m, 7, 8, 9),
            camera: zoomed.rebuild_key().unwrap(),
            time: TimePredicate::All,
            kind: GeoReducedKind::Cluster,
            direct: false,
            columns: 1,
            rows: 1,
        };
        let mut predicate = GeoCellQuery::new(&m, key, 0, None, 1).unwrap();
        assert!(matches!(
            predicate.matches(&c.rows().next().unwrap(), &mut || false),
            Err(SourceError::ResourceLimit)
        ));
        assert_eq!(predicate.projected_vertices(), 2);
        assert!(matches!(
            predicate.matches(&c.rows().next().unwrap(), &mut || false),
            Err(SourceError::StaleSource)
        ));
    }
}
