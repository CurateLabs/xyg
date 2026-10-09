//! Native cold-build/warm-query evidence; no browser/paint or competitor claim.
use std::{fs, path::PathBuf, sync::Arc, time::Instant};
use xyg_engine::{
    geo::{GeoColumn, GeoCrs, GeoDescriptor, GeoGeometry, GeoLimits},
    geo_indexed_query_session::{GeoIndexDecision, decision, process_indexed},
    geo_layers::GeoStyle,
    geo_lod::{GeoLodOptions, process},
    geo_lod_scene::compile,
    geo_source::{
        GeoChunk, GeoManifestBuilder, QueryBudget, ReadRequest, SourceError, TimePredicate,
    },
    geo_spatial_build_session::build,
    geo_spatial_index::{GeoSpatialOptions, GeoSpatialRead},
    geo_viewport::GeoViewport,
};
const CHUNK_ROWS: u64 = 65_536;
fn mix(mut n: u64) -> u64 {
    n = n.wrapping_add(0x9e3779b97f4a7c15);
    n = (n ^ (n >> 30)).wrapping_mul(0xbf58476d1ce4e5b9);
    n = (n ^ (n >> 27)).wrapping_mul(0x94d049bb133111eb);
    n ^ (n >> 31)
}
fn chunk(first: u64, rows: u64) -> Vec<u8> {
    let mut xy = Vec::with_capacity(rows as usize * 2);
    let mut ids = Vec::with_capacity(rows as usize);
    for i in first..first + rows {
        let a = mix(i);
        let b = mix(i ^ 0xabcdef);
        xy.push((a >> 11) as f64 / ((1u64 << 53) as f64) * 360. - 180.);
        xy.push((b >> 11) as f64 / ((1u64 << 53) as f64) * 160. - 80.);
        ids.push(u64::MAX - i);
    }
    let validity = vec![1u8; rows as usize];
    let col = GeoColumn::from_descriptor(GeoDescriptor {
        geometry: GeoGeometry::Point,
        crs: GeoCrs::Epsg4326,
        xy: &xy,
        validity: &validity,
        feature_ids: Some(&ids),
        offsets0: &[],
        offsets1: &[],
        offsets2: &[],
        limits: GeoLimits::default(),
    })
    .unwrap();
    GeoChunk::encode(&col, None).unwrap()
}
fn main() {
    let args: Vec<_> = std::env::args().collect();
    let rows: u64 = args.get(1).map_or(1_000_000, |s| s.parse().unwrap());
    assert!(rows > 0 && rows <= 100_000_000);
    let grid: u32 = args.get(3).map_or(16, |s| s.parse().unwrap());
    let directory = PathBuf::from(
        args.get(2)
            .expect("caller-owned empty leaf directory required"),
    );
    fs::create_dir_all(&directory).unwrap();
    assert!(fs::read_dir(&directory).unwrap().next().is_none());
    let start = Instant::now();
    let mut builder = GeoManifestBuilder::new();
    for first in (0..rows).step_by(CHUNK_ROWS as usize) {
        let bytes = chunk(first, CHUNK_ROWS.min(rows - first));
        let parsed = GeoChunk::parse(&bytes, 96 << 20).unwrap();
        builder.push(&parsed).unwrap();
    }
    let source = builder.finish(1).unwrap();
    let manifest_ms = start.elapsed().as_secs_f64() * 1000.;
    let budget = QueryBudget {
        max_rows_examined: rows * 2,
        max_read_bytes: rows * 128,
        ..QueryBudget::default()
    };
    let read_source = |r: ReadRequest| Ok(chunk(r.first_row, r.rows as u64));
    let mut disk_bytes = 0u64;
    let start = Instant::now();
    let index = build(
        &source,
        &mut { read_source },
        &mut |t, bytes: &[u8]| {
            fs::write(directory.join(t.request.page.to_string()), bytes)
                .map_err(|_| SourceError::InvalidFrame)?;
            disk_bytes += bytes.len() as u64;
            Ok(())
        },
        GeoSpatialOptions { grid },
        budget,
        rows,
        &mut || false,
    )
    .unwrap();
    let build_ms = start.elapsed().as_secs_f64() * 1000.;
    let page_count = index.page_count();
    let reserved = index.reserved_bytes();
    let index = Arc::new(index);
    let options = GeoLodOptions {
        max_projected_vertices: rows * 2,
        ..GeoLodOptions::default()
    };
    println!(
        "{{\"phase\":\"cold\",\"rows\":{rows},\"manifestMs\":{manifest_ms},\"indexBuildMs\":{build_ms},\"pages\":{page_count},\"leafDiskBytes\":{disk_bytes},\"directoryReservedBytes\":{reserved},\"chunkRows\":{CHUNK_ROWS}}}"
    );
    for (name, lon, zoom) in [("world", 0., 0.), ("zoom", 0., 8.), ("pan", 1., 8.)] {
        let camera =
            GeoViewport::new(GeoCrs::Epsg4326, lon, 0., zoom, 800., 600., 0., 0., true).unwrap();
        if decision(&index, &camera, TimePredicate::All).unwrap()
            == GeoIndexDecision::FullScanFrontier
        {
            println!(
                "{{\"phase\":\"decision\",\"name\":\"{name}\",\"rows\":{rows},\"grid\":{grid},\"fallback\":\"canonical-full-scan\",\"measuredQuery\":false}}"
            );
            continue;
        }
        let start = Instant::now();
        let result = process_indexed(
            index.clone(),
            &mut |r: GeoSpatialRead| {
                let bytes = fs::read(directory.join(r.page.to_string()))
                    .map_err(|_| SourceError::InvalidFrame)?;
                assert_eq!(bytes.len(), r.encoded_bytes);
                Ok(bytes)
            },
            camera,
            TimePredicate::All,
            options,
            1,
            1,
            1,
            rows * 256,
            &mut || false,
        )
        .unwrap()
        .expect("default index frontier");
        let query_ms = start.elapsed().as_secs_f64() * 1000.;
        let scene = compile(&result.result, GeoStyle::default(), 32 << 20).unwrap();
        let mut parity = "not-run";
        let mut reference_ms = 0.;
        if rows <= 1_000_000 {
            let start = Instant::now();
            let ordinary = process(
                &source,
                &mut { read_source },
                camera,
                TimePredicate::All,
                1,
                1,
                1,
                options,
                budget,
                &mut || false,
            )
            .unwrap();
            reference_ms = start.elapsed().as_secs_f64() * 1000.;
            let reference = compile(&ordinary, GeoStyle::default(), 32 << 20).unwrap();
            assert_eq!(scene.scene, reference.scene);
            parity = "exact-scene-bytes";
        }
        println!(
            "{{\"phase\":\"warm-query\",\"name\":\"{name}\",\"rows\":{rows},\"queryMs\":{query_ms},\"pagesRead\":{},\"bytesRead\":{},\"candidates\":{},\"passes\":{},\"visibleVertices\":{},\"sceneBytes\":{},\"referenceMs\":{reference_ms},\"parity\":\"{parity}\"}}",
            result.stats.pages_read,
            result.stats.bytes_read,
            result.stats.candidate_vertices,
            result.stats.passes,
            result.result.visible_vertices,
            scene.scene.len()
        );
    }
}
