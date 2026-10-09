//! Reproducible native shared-protocol evidence; no source-wide allocation.
//! stdout is bounded NDJSON metrics, stderr periodic progress. See bench_geo_scale.py.
use std::time::{Duration, Instant};
use xyg_engine::geo_scale_protocol::{execute, read_data, HEADER};
use xyg_engine::geo_source::{GeoSourcePlan, SourceError, MAX_PROCESSOR_BYTES};
use xyg_engine::geo_source_session::GeoProcessorLease;

type Result<T> = std::result::Result<T, SourceError>;
const CHUNK_ROWS: u64 = 65536;
const GENERATION: u64 = u64::MAX;
fn p32(b: &mut [u8], at: usize, n: u32) {
    b[at..at + 4].copy_from_slice(&n.to_le_bytes());
}
fn p64(b: &mut [u8], at: usize, n: u64) {
    b[at..at + 8].copy_from_slice(&n.to_le_bytes());
}
fn u32at(b: &[u8], at: usize) -> u32 {
    u32::from_le_bytes(b[at..at + 4].try_into().unwrap())
}
fn u64at(b: &[u8], at: usize) -> u64 {
    u64::from_le_bytes(b[at..at + 8].try_into().unwrap())
}
fn request(command: u32, handle: u64, sequence: u64, payload: &[u8]) -> Vec<u8> {
    let mut b = vec![0; HEADER + payload.len()];
    b[..4].copy_from_slice(b"XYGQ");
    p32(&mut b, 4, 1);
    p32(&mut b, 8, command);
    p64(&mut b, 16, handle);
    p64(&mut b, 24, sequence);
    p64(&mut b, 232, payload.len() as u64);
    b[HEADER..].copy_from_slice(payload);
    b
}
fn with_budget(mut b: Vec<u8>, rows: u64) -> Vec<u8> {
    p64(&mut b, 32, MAX_PROCESSOR_BYTES as u64);
    p64(&mut b, 40, rows * 4 + CHUNK_ROWS);
    p64(&mut b, 48, rows * 256 + 16 * 1024 * 1024);
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
/// Drop the native copy before releasing its immutable Data capability.
struct Packet {
    bytes: Vec<u8>,
    _handle: Handle,
}
struct Meter {
    rows: u64,
    reads: u64,
    bytes: u64,
    peak_processor: usize,
    progress: Instant,
    phase: &'static str,
}
impl Meter {
    fn sample(&mut self) {
        self.peak_processor = self.peak_processor.max(GeoProcessorLease::live_bytes());
    }
    fn progress(&mut self, completed: u64, total: u64) {
        self.sample();
        if self.progress.elapsed() >= Duration::from_secs(5) {
            let progress = if total == 0 {
                format!("cumulative_reads={completed}")
            } else {
                format!("completed={completed}/{total}")
            };
            eprintln!(
                "rows={} phase={} {progress} live_processor={}",
                self.rows,
                self.phase,
                GeoProcessorLease::live_bytes()
            );
            self.progress = Instant::now();
        }
    }
    fn phase(&mut self, name: &'static str, start: Instant, extra: &str) {
        self.sample();
        println!("{{\"event\":\"phase\",\"name\":\"{name}\",\"ms\":{:.6},\"processor_live_bytes\":{},\"processor_sampled_peak_bytes\":{},\"reads_total\":{},\"read_bytes_total\":{}{extra}}}",start.elapsed().as_secs_f64()*1000.,GeoProcessorLease::live_bytes(),self.peak_processor,self.reads,self.bytes);
    }
    fn run(&mut self, b: &[u8]) -> Result<[u8; HEADER]> {
        let r = execute(b)?;
        self.sample();
        Ok(r)
    }
}
/// Stable generated unordered spatial points, chunk-aligned half-open time windows.
/// Includes canonical f64 XY and full u64 IDs. Only one chunk is ever generated.
fn chunk(first: u64, rows: u32) -> Result<Vec<u8>> {
    let n = rows as usize;
    let padded = (n + 7) & !7;
    let dlen = 64 + n * 16 + padded + n * 8;
    let size = 32 + dlen + n * 18;
    let mut payload = vec![0; size];
    p64(&mut payload, 0, dlen as u64);
    p32(&mut payload, 8, 1);
    p64(&mut payload, 16, n as u64);
    let d = &mut payload[32..32 + dlen];
    d[..4].copy_from_slice(b"XYGD");
    p32(d, 4, 1);
    p32(d, 8, 1);
    p32(d, 12, 4326);
    p32(d, 16, 1);
    p64(d, 24, n as u64);
    p64(d, 32, n as u64);
    for i in 0..n {
        let row = first + i as u64;
        let x = ((row * 48271 + 17) % 1000003) as f64 / 1000003. * 340. - 170.;
        let y = ((row * 69621 + 31) % 1000033) as f64 / 1000033. * 120. - 60.;
        p64(d, 64 + i * 16, x.to_bits());
        p64(d, 72 + i * 16, y.to_bits());
        d[64 + n * 16 + i] = 1;
        p64(d, 64 + n * 16 + padded + i * 8, u64::MAX - row);
    }
    let at = 32 + dlen;
    let time = (first / CHUNK_ROWS) % 4;
    for i in 0..n {
        p64(&mut payload, at + i * 8, time);
        p64(&mut payload, at + n * 8 + i * 8, time + 1);
        payload[at + n * 16 + i] = 1;
        payload[at + n * 17 + i] = 1;
    }
    read_data(&request(20, 0, 0, &payload), MAX_PROCESSOR_BYTES)
}
fn supply(m: &mut Meter, handle: u64, ticket: &[u8]) -> Result<()> {
    let bytes = chunk(u64at(ticket, 48), u32at(ticket, 44))?;
    if bytes.len() as u64 != u64at(ticket, 56) {
        return Err(SourceError::InvalidFrame);
    }
    let mut payload = Vec::with_capacity(96 + bytes.len());
    payload.extend(ticket);
    payload.extend(&bytes);
    let b = request(7, handle, 0, &payload);
    m.run(&b)?;
    m.reads += 1;
    m.bytes += bytes.len() as u64;
    drop(b);
    drop(payload);
    drop(bytes);
    m.run(&request(8, handle, 0, ticket))?;
    Ok(())
}
fn drive(m: &mut Meter, handle: u64, sequence: u64) -> Result<[u8; HEADER]> {
    loop {
        let r = m.run(&with_budget(request(6, handle, sequence, &[]), m.rows))?;
        match u32at(&r, 8) {
            1 => supply(m, handle, &r[64..160])?,
            3 | 4 => return Ok(r),
            _ => return Err(SourceError::InvalidFrame),
        }
        m.progress(m.reads, 0);
    }
}
fn begin(
    m: &mut Meter,
    handle: u64,
    sequence: u64,
    source: &[u8],
    pan: f64,
    zoom: f64,
    time: Option<i64>,
) -> Result<()> {
    let mut b = with_budget(request(5, handle, sequence, &[]), m.rows);
    p32(&mut b, 12, 1);
    p32(&mut b, 64, 4326);
    p32(&mut b, 72, 32768);
    p32(&mut b, 76, 1);
    for (i, n) in [pan, 0., zoom, 800., 600., 0., 0.].iter().enumerate() {
        p64(&mut b, 80 + i * 8, n.to_bits());
    }
    b[136..144].copy_from_slice(&source[40..48]);
    p64(&mut b, 144, GENERATION);
    p64(&mut b, 152, u64::MAX);
    for at in [160, 168, 176, 184, 192] {
        p64(&mut b, at, sequence);
    }
    if let Some(t) = time {
        p32(&mut b, 200, 1);
        p64(&mut b, 208, t as u64);
    }
    p64(&mut b, 224, m.rows * 4 + CHUNK_ROWS);
    m.run(&b)?;
    Ok(())
}
fn packet(m: &mut Meter, handle: u64, sequence: u64, command: u32) -> Result<Packet> {
    let mut style = [0; 48];
    style[..4].copy_from_slice(&[51, 102, 204, 255]);
    p64(&mut style, 16, 6f64.to_bits());
    p64(&mut style, 24, 1f64.to_bits());
    let payload = if command == 11 { &style[..] } else { &[] };
    let r = m.run(&with_budget(
        request(command, handle, sequence, payload),
        m.rows,
    ))?;
    let owned = Handle(u64at(&r, 16));
    let bytes = read_data(&request(23, owned.0, 0, &[]), MAX_PROCESSOR_BYTES)?;
    if bytes.len() as u64 != u64at(&r, 32) {
        return Err(SourceError::InvalidFrame);
    }
    Ok(Packet {
        bytes,
        _handle: owned,
    })
}
fn scene_metrics(
    m: &mut Meter,
    handle: u64,
    sequence: u64,
    name: &'static str,
    start: Instant,
) -> Result<Packet> {
    let p = packet(m, handle, sequence, 11)?;
    let b = &p.bytes;
    let extra=format!(",\"aggregate\":{},\"grid_capped\":{},\"columns\":{},\"grid_rows\":{},\"visible_vertices\":{},\"projected_vertices\":{},\"scene_bytes\":{},\"provenance_bytes\":{},\"packet_bytes\":{}",u32at(b,8)==1,u32at(b,72)==1,u32at(b,64),u32at(b,68),u64at(b,48),u64at(b,56),u64at(b,32),u64at(b,40),b.len());
    m.phase(name, start, &extra);
    Ok(p)
}
/// Native CPU semantic picking, including protocol serialization and owned read.
/// This measures neither browser/GPU picking nor frame scheduling.
fn hit_samples(m: &mut Meter, p: &Packet, sequence: u64) -> Result<()> {
    let start = Instant::now();
    let mut samples = Vec::with_capacity(256);
    let mut hits = 0u64;
    for i in 0..256 {
        let one = Instant::now();
        let mut payload = [0; 80];
        payload[..4].copy_from_slice(&[51, 102, 204, 255]);
        p64(&mut payload, 16, 6f64.to_bits());
        p64(&mut payload, 24, 1f64.to_bits());
        p64(&mut payload, 48, ((i * 73 % 800) as f64 + 0.5).to_bits());
        p64(&mut payload, 56, ((i * 97 % 600) as f64 + 0.5).to_bits());
        p32(&mut payload, 76, 1);
        let r = m.run(&with_budget(
            request(14, p._handle.0, sequence, &payload),
            m.rows,
        ))?;
        let handle = Handle(u64at(&r, 16));
        let bytes = read_data(&request(23, handle.0, 0, &[]), MAX_PROCESSOR_BYTES)?;
        if bytes.len() as u64 != u64at(&r, 32) || u32at(&bytes, 8) != 3 {
            return Err(SourceError::InvalidFrame);
        }
        hits += u64at(&bytes, 32);
        drop(bytes);
        drop(handle);
        samples.push(one.elapsed().as_secs_f64() * 1000.);
    }
    let mut sorted = samples.clone();
    sorted.sort_by(f64::total_cmp);
    m.phase("native_cpu_hit_protocol", start, &format!(",\"samples\":256,\"p50_ms\":{},\"p95_ms\":{},\"hit_count\":{hits},\"sample_ms\":{samples:?},\"query\":\"deterministic CSS pixel Topmost max_hits=1 tolerance=0\"", sorted[127], sorted[243]));
    Ok(())
}
fn membership(m: &mut Meter, source: u64, sequence: u64, p: &Packet) -> Result<()> {
    if u32at(&p.bytes, 8) != 1 {
        println!("{{\"event\":\"unmeasured\",\"name\":\"cell_membership\",\"reason\":\"direct tier has no aggregate cell\"}}");
        return Ok(());
    }
    let at = HEADER + u64at(&p.bytes, 32) as usize;
    let cells = u64at(&p.bytes, 40) as usize / 24;
    let cell = (0..cells)
        .max_by_key(|&i| u64at(&p.bytes, at + i * 24))
        .ok_or(SourceError::InvalidFrame)?;
    let total = u64at(&p.bytes, at + cell * 24);
    let mut cursor = Vec::new();
    let mut returned = 0u64;
    for page in 0..3 {
        let start = Instant::now();
        let mut payload = vec![0; 16 + cursor.len()];
        p32(&mut payload, 0, cell as u32);
        p32(&mut payload, 4, if cursor.is_empty() { 0 } else { 1 });
        p64(&mut payload, 8, m.rows * 2 + CHUNK_ROWS);
        payload[16..].copy_from_slice(&cursor);
        let r = m.run(&with_budget(
            request(12, source, sequence, &payload),
            m.rows,
        ))?;
        let member = Handle(u64at(&r, 16));
        drive(m, member.0, sequence)?;
        let data = packet(m, member.0, sequence, 13)?;
        let rows = u64at(&data.bytes, 32);
        returned += rows;
        let has_next = u32at(&data.bytes, 72) == 1;
        cursor = if has_next {
            data.bytes[256..464].to_vec()
        } else {
            Vec::new()
        };
        m.phase("cell_membership_page",start,&format!(",\"page\":{page},\"cell\":{cell},\"cell_total_count\":{total},\"returned_rows\":{rows},\"returned_total\":{returned},\"has_next\":{has_next},\"rows_examined\":{},\"chunk_read_bytes\":{},\"page_packet_bytes\":{}",u64at(&data.bytes,48),u64at(&data.bytes,56),data.bytes.len()));
        drop(data);
        drop(member);
        if !has_next {
            if returned != total {
                return Err(SourceError::InvalidFrame);
            }
            break;
        }
    }
    Ok(())
}
#[cfg(feature = "raster")]
fn output(m: &mut Meter, p: &Packet) -> Result<()> {
    use xyg_engine::scene::SceneDocument;
    use xyg_engine::{scene_static_export, SceneStaticFormat};
    // The immutable SceneData retains charged semantic authority after its
    // session is disposed. Reserve only the remaining shared processor phase
    // for output scratch; never grant another 128 MiB on top of that authority.
    let available = MAX_PROCESSOR_BYTES
        .checked_sub(GeoProcessorLease::live_bytes())
        .ok_or(SourceError::ResourceLimit)?;
    let lease = GeoProcessorLease::acquire(available)?;
    m.sample();
    let scene = &p.bytes[256..256 + u64at(&p.bytes, 32) as usize];
    let start = Instant::now();
    let document = SceneDocument::decode(scene).map_err(|_| SourceError::InvalidFrame)?;
    let paint = document
        .to_browser_painter(available)
        .map_err(|_| SourceError::ResourceLimit)?;
    m.phase(
        "browser_painter_encode",
        start,
        &format!(",\"painter_bytes\":{}", paint.len()),
    );
    drop(paint);
    drop(document);
    for (name, format) in [
        ("static_svg", SceneStaticFormat::Svg),
        ("static_png", SceneStaticFormat::Png),
    ] {
        let start = Instant::now();
        let bytes = scene_static_export(scene, format, 1., 800, 600, 90)
            .map_err(|_| SourceError::ResourceLimit)?;
        m.phase(name, start, &format!(",\"artifact_bytes\":{}", bytes.len()));
        drop(bytes);
    }
    drop(lease);
    Ok(())
}
fn run(rows: u64) -> Result<()> {
    let plan = GeoSourcePlan::new(rows, CHUNK_ROWS as u32)?;
    let mut m = Meter {
        rows,
        reads: 0,
        bytes: 0,
        peak_processor: 0,
        progress: Instant::now(),
        phase: "ingest",
    };
    let total_start = Instant::now();
    let start = Instant::now();
    let builder = Handle(u64at(&m.run(&request(1, 0, 0, &[]))?, 16));
    let mut canonical_bytes = 0u64;
    for index in 0..plan.chunks {
        let first = index as u64 * CHUNK_ROWS;
        let data = chunk(first, (rows - first).min(CHUNK_ROWS) as u32)?;
        canonical_bytes += data.len() as u64;
        m.run(&request(2, builder.0, 0, &data))?;
        drop(data);
        m.progress(index as u64 + 1, plan.chunks as u64);
    }
    let mut finish = request(3, builder.0, 0, &[]);
    p64(&mut finish, 144, GENERATION);
    m.run(&finish)?;
    let manifest = read_data(&request(21, builder.0, 0, &[]), MAX_PROCESSOR_BYTES)?;
    // The returned manifest copy lives under its own conservative processor charge.
    let manifest_charge = GeoProcessorLease::acquire(manifest.len() * 4 + 4096)?;
    drop(builder);
    m.phase("ingest",start,&format!(",\"source_rows\":{rows},\"chunks\":{},\"canonical_bytes_streamed\":{canonical_bytes},\"manifest_bytes\":{}",plan.chunks,manifest.len()));
    let start = Instant::now();
    m.phase = "validate";
    let source_handle = Handle(u64at(
        &m.run(&with_budget(request(4, 0, 0, &manifest), rows))?,
        16,
    ));
    let source = drive(&mut m, source_handle.0, 0)?;
    m.phase("source_validation", start, "");
    let start = Instant::now();
    m.phase = "first_scene";
    begin(&mut m, source_handle.0, 1, &source, 0., 0., None)?;
    drive(&mut m, source_handle.0, 1)?;
    let mut current = scene_metrics(&mut m, source_handle.0, 1, "first_scene_compute", start)?;
    m.phase("ingest_to_first_computed_scene", total_start, "");
    m.phase = "cpu_hit";
    hit_samples(&mut m, &current, 1)?;
    m.phase = "membership";
    membership(&mut m, source_handle.0, 1, &current)?;
    for (seq, name, pan, zoom, time) in [
        (2, "time_filter", 0., 0., Some(0)),
        (3, "pan", 30., 0., None),
        (4, "zoom", 30., 1., None),
        (5, "revision_update", 30., 1., None),
    ] {
        let start = Instant::now();
        m.phase = name;
        begin(&mut m, source_handle.0, seq, &source, pan, zoom, time)?;
        drive(&mut m, source_handle.0, seq)?;
        let next = scene_metrics(&mut m, source_handle.0, seq, name, start)?;
        drop(current);
        current = next;
    }
    drop(source_handle);
    m.phase = "five_views_validate";
    let start = Instant::now();
    let mut views = Vec::new();
    for _ in 0..5 {
        views.push(Handle(u64at(
            &m.run(&with_budget(request(4, 0, 0, &manifest), rows))?,
            16,
        )));
    }
    // Five retained views share one read cadence: release each ticket before
    // another view may request a chunk. No five hardware threads are implied.
    let mut ready = [false; 5];
    while ready.iter().any(|v| !v) {
        for (i, h) in views.iter().enumerate() {
            if ready[i] {
                continue;
            }
            let r = m.run(&with_budget(request(6, h.0, 0, &[]), rows))?;
            match u32at(&r, 8) {
                1 => {
                    supply(&mut m, h.0, &r[64..160])?;
                    m.progress(m.reads, 0);
                }
                3 => ready[i] = true,
                _ => return Err(SourceError::InvalidFrame),
            }
        }
        m.sample();
    }
    m.phase(
        "five_views_source_validation",
        start,
        ",\"retained_views\":5,\"concurrent_pending_ticket_limit\":1",
    );
    let start = Instant::now();
    m.phase = "five_views_compute";
    for (i, h) in views.iter().enumerate() {
        begin(&mut m, h.0, 1, &source, i as f64 * 5., 0., None)?;
    }
    let mut ready = [false; 5];
    while ready.iter().any(|v| !v) {
        for (i, h) in views.iter().enumerate() {
            if ready[i] {
                continue;
            }
            let r = m.run(&with_budget(request(6, h.0, 1, &[]), rows))?;
            match u32at(&r, 8) {
                1 => {
                    supply(&mut m, h.0, &r[64..160])?;
                    m.progress(m.reads, 0);
                }
                4 => ready[i] = true,
                _ => return Err(SourceError::InvalidFrame),
            }
        }
        m.sample();
    }
    let mut packets = Vec::new();
    for h in &views {
        packets.push(packet(&mut m, h.0, 1, 11)?);
    }
    let packet_bytes: usize = packets.iter().map(|p| p.bytes.len()).sum();
    m.phase("five_views_compute_and_scenes",start,&format!(",\"retained_views\":5,\"simultaneous_scene_packet_bytes\":{packet_bytes},\"cpu_schedule\":\"serial_round_robin\""));
    drop(packets);
    drop(views);
    drop(manifest);
    drop(manifest_charge);
    #[cfg(feature = "raster")]
    output(&mut m, &current)?;
    drop(current);
    m.phase("all_phases", total_start, "");
    println!("{{\"event\":\"completed\",\"source_rows\":{rows},\"processor_live_bytes_after_cleanup\":{},\"unmeasured\":[\"GPU first paint\",\"pan FPS\",\"p95 GPU/controller pick\",\"browser/controller\",\"network tiles\",\"VRAM\",\"incremental source append\",\"retained per-row style/state/scalar attachments\",\"competitor timings\"]}}",GeoProcessorLease::live_bytes());
    Ok(())
}
fn main() {
    let args: Vec<_> = std::env::args().skip(1).collect();
    let rows = args
        .last()
        .and_then(|n| n.parse::<u64>().ok())
        .unwrap_or(1000);
    if args.first().is_some_and(|s| s == "--plan-only") {
        match GeoSourcePlan::new(rows,CHUNK_ROWS as u32){Ok(p)=>println!("{{\"event\":\"planner_only\",\"source_rows\":{},\"chunks\":{},\"manifest_bytes\":{},\"processor_bytes\":{},\"data_rows_generated\":0,\"measured_ingest\":false}}",p.rows,p.chunks,p.manifest_bytes,p.processor_bytes),Err(e)=>{eprintln!("planner error {:?}",e);std::process::exit(3);}}
        return;
    }
    if let Err(e) = run(rows) {
        println!("{{\"event\":\"failed\",\"source_rows\":{rows},\"status\":\"{}\",\"resource_limit\":{},\"error\":\"{:?}\"}}",e.code(),e==SourceError::ResourceLimit,e);
        std::process::exit(3);
    }
}
