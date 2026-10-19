//! Cross-host browser-painter admission parity (#1007).
//!
//! The same canonical Scene bytes and byte budget go through the native C seam
//! that Python, Node, and Pyodide call (`xyg_core::xyg_scene_browser_painter`)
//! and the WASM Worker ABI (`xyg_wasm_scene_prepare`, compiled natively here).
//! Both must publish byte-identical painter output, or reject with the same
//! stable `scene::PainterRejection` diagnostic and no partial output.
//!
//! The committed `tests/fixtures/painter_admission_cross_host.json` records
//! these Rust-classified outcomes as compact recipes so Python, Node (native
//! koffi plus the real wasm32 artifact), and the browser Worker consume one
//! contract instead of re-deriving policy. Regenerate it with:
//!
//! ```text
//! XYG_WRITE_PAINTER_ADMISSION_FIXTURE=1 \
//!   cargo test -p xyg-wasm --test painter_admission_parity
//! ```
#![cfg(not(target_arch = "wasm32"))]

use std::path::PathBuf;

use xyg_engine::scene::{
    self, AxisScale, PainterRejection, PlotLayout, ScaleKind, SceneBatch, SceneRecordKind,
    MAX_BROWSER_PAINTER_TRACES,
};
use xyg_wasm::{
    xyg_wasm_arena_len, xyg_wasm_arena_ptr, xyg_wasm_arena_resize, xyg_wasm_cancel,
    xyg_wasm_instance_dispose, xyg_wasm_instance_new, xyg_wasm_last_error_len,
    xyg_wasm_last_error_ptr, xyg_wasm_output_len, xyg_wasm_output_ptr, xyg_wasm_scene_prepare,
    STATUS_CANCELLED, STATUS_MALFORMED_SCENE, STATUS_OK, STATUS_RESOURCE_LIMIT,
    STATUS_SCENE_VERSION, STATUS_STALE_SEQUENCE,
};

const FIXTURE: &str = "tests/fixtures/painter_admission_cross_host.json";
const ONE_MIB: usize = 1 << 20;

#[derive(Clone, Copy)]
enum Mutation {
    None,
    TruncateLastByte,
    NextSceneVersion,
}

impl Mutation {
    fn name(self) -> &'static str {
        match self {
            Self::None => "none",
            Self::TruncateLastByte => "truncate_last_byte",
            Self::NextSceneVersion => "next_scene_version",
        }
    }
}

#[derive(Clone, Copy)]
enum Budget {
    Bytes(usize),
    /// Exactly the Scene length: the smallest budget a Worker can stage.
    SceneLength,
    /// Offset from the exact painter length the Scene needs.
    PainterDelta(isize),
}

/// A compact, host-reproducible Scene recipe. Every host builds it through its
/// Rust-backed `scene_batch_encode`; `scene_sha256` proves identical bytes.
#[derive(Clone, Copy)]
struct Case {
    name: &'static str,
    kind: SceneRecordKind,
    count: usize,
    /// Distinct stable identity per record (one Polyline run per record).
    distinct_ids: bool,
    /// Alternate scatter symbols 0/1 per record (per-instance paint only).
    alternate_symbols: bool,
    mutation: Mutation,
    budget: Budget,
}

const fn case(
    name: &'static str,
    kind: SceneRecordKind,
    count: usize,
    distinct_ids: bool,
    alternate_symbols: bool,
    budget: Budget,
) -> Case {
    Case {
        name,
        kind,
        count,
        distinct_ids,
        alternate_symbols,
        mutation: Mutation::None,
        budget,
    }
}

fn cases() -> Vec<Case> {
    use SceneRecordKind::{Polyline, Scatter};
    let limit = MAX_BROWSER_PAINTER_TRACES;
    vec![
        case(
            "trace_runs_just_below",
            Polyline,
            limit - 1,
            true,
            false,
            Budget::Bytes(ONE_MIB),
        ),
        case(
            "trace_runs_exact",
            Polyline,
            limit,
            true,
            false,
            Budget::Bytes(ONE_MIB),
        ),
        case(
            "trace_runs_just_above",
            Polyline,
            limit + 1,
            true,
            false,
            Budget::Bytes(ONE_MIB),
        ),
        case(
            "trace_runs_far_above",
            Polyline,
            4 * limit,
            true,
            false,
            Budget::Bytes(ONE_MIB),
        ),
        // Run discovery precedes byte admission, so the trace diagnostic is
        // deterministic even under a budget the output could never meet.
        case(
            "trace_runs_above_with_scene_sized_budget",
            Polyline,
            limit + 1,
            true,
            false,
            Budget::SceneLength,
        ),
        case(
            "trace_runs_exact_with_scene_sized_budget",
            Polyline,
            limit,
            true,
            false,
            Budget::SceneLength,
        ),
        // #945: ordinary Scatter records batch into one kind-8 trace across
        // symbol changes; alternating symbols are not run fragmentation.
        case(
            "packed_symbols_above_trace_count",
            Scatter,
            limit + 1,
            false,
            true,
            Budget::Bytes(ONE_MIB),
        ),
        case(
            "bytes_just_below",
            Scatter,
            4,
            false,
            true,
            Budget::PainterDelta(-1),
        ),
        case(
            "bytes_exact",
            Scatter,
            4,
            false,
            true,
            Budget::PainterDelta(0),
        ),
        case(
            "bytes_just_above",
            Scatter,
            4,
            false,
            true,
            Budget::PainterDelta(1),
        ),
        Case {
            mutation: Mutation::TruncateLastByte,
            ..case(
                "malformed_truncated",
                Scatter,
                4,
                false,
                true,
                Budget::Bytes(ONE_MIB),
            )
        },
        Case {
            mutation: Mutation::NextSceneVersion,
            ..case(
                "incompatible_version",
                Scatter,
                4,
                false,
                true,
                Budget::Bytes(ONE_MIB),
            )
        },
    ]
}

fn scene_bytes(case: &Case) -> Vec<u8> {
    let n = case.count;
    let scatter = case.kind == SceneRecordKind::Scatter;
    let layout = PlotLayout::new(120.0, 100.0, 10.0, 10.0, 10.0, 10.0).unwrap();
    let sx = AxisScale::new(ScaleKind::Linear, 0.0, 1.0, 10.0, 110.0, 1.0, false).unwrap();
    let sy = AxisScale::new(ScaleKind::Linear, 0.0, 1.0, 90.0, 10.0, 1.0, false).unwrap();
    let ids: Vec<u64> = if case.distinct_ids {
        (0..n as u64).collect()
    } else {
        vec![7; n]
    };
    let symbols: Vec<u8> = (0..n)
        .map(|index| u8::from(case.alternate_symbols && index % 2 == 1))
        .collect();
    let mut bytes = SceneBatch::new(
        layout,
        1,
        2,
        sx,
        sy,
        &vec![case.kind as u8; n],
        &ids,
        &vec![0; n],
        &[57, 135, 229, 255],
        &[0, 0, 0, 0],
        &[0.0],
        &vec![if scatter { 4.0 } else { 0.0 }; n],
        &symbols,
        &vec![0.5; n],
        &vec![0.5; n],
        &vec![0.0; n],
        &vec![0.0; n],
    )
    .unwrap()
    .encode();
    match case.mutation {
        Mutation::None => {}
        Mutation::TruncateLastByte => {
            bytes.pop();
        }
        Mutation::NextSceneVersion => {
            bytes[4..8].copy_from_slice(&(scene::SCENE_VERSION + 1).to_le_bytes());
        }
    }
    bytes
}

fn budget(case: &Case, scene: &[u8]) -> usize {
    match case.budget {
        Budget::Bytes(bytes) => bytes,
        Budget::SceneLength => scene.len(),
        Budget::PainterDelta(delta) => {
            let exact = scene::browser_painter_from_scene(scene, usize::MAX)
                .expect("byte-boundary recipe lowers")
                .len();
            exact.checked_add_signed(delta).unwrap()
        }
    }
}

/// Native C seam outcome, decoded exactly as Python/Node do.
fn native(scene: &[u8], max_bytes: usize) -> Result<Vec<u8>, String> {
    let mut capacity = 256.max(scene.len() * 3);
    loop {
        let mut out = vec![0xA5u8; capacity];
        let written = unsafe {
            xyg_core::xyg_scene_browser_painter(
                scene.as_ptr(),
                scene.len(),
                max_bytes,
                out.as_mut_ptr(),
                capacity,
            )
        };
        if written == usize::MAX {
            let end = out
                .iter()
                .position(|byte| *byte == 0)
                .expect("NUL-terminated diagnostic");
            return Err(String::from_utf8(out[..end].to_vec()).unwrap());
        }
        if written <= capacity {
            out.truncate(written);
            return Ok(out);
        }
        capacity = written;
    }
}

fn stage(handle: u32, bytes: &[u8]) {
    assert_eq!(xyg_wasm_arena_resize(handle, bytes.len()), STATUS_OK);
    unsafe {
        std::ptr::copy_nonoverlapping(
            bytes.as_ptr(),
            xyg_wasm_arena_ptr(handle) as *mut u8,
            bytes.len(),
        );
    }
}

fn wasm_output(handle: u32) -> Vec<u8> {
    let length = xyg_wasm_output_len(handle);
    if length == 0 {
        return Vec::new();
    }
    unsafe { std::slice::from_raw_parts(xyg_wasm_output_ptr(handle) as *const u8, length).to_vec() }
}

fn wasm_error(handle: u32) -> String {
    let length = xyg_wasm_last_error_len(handle);
    let bytes =
        unsafe { std::slice::from_raw_parts(xyg_wasm_last_error_ptr(handle) as *const u8, length) };
    String::from_utf8(bytes.to_vec()).unwrap()
}

/// WASM Worker ABI outcome for one prepare on a fresh instance whose single
/// byte budget bounds both staging and painter output.
fn wasm(scene: &[u8], max_bytes: usize) -> (i32, Result<Vec<u8>, String>) {
    // A Worker stages the Scene inside the same budget, so every fixture
    // budget is at least the Scene length.
    assert!(max_bytes >= scene.len());
    let handle = xyg_wasm_instance_new(max_bytes);
    assert!(handle > 0);
    stage(handle, scene);
    let status = xyg_wasm_scene_prepare(handle, 1, 0, scene.len());
    let outcome = if status == STATUS_OK {
        Ok(wasm_output(handle))
    } else {
        assert_eq!(xyg_wasm_output_len(handle), 0, "no partial painter state");
        Err(wasm_error(handle))
    };
    assert_eq!(xyg_wasm_arena_len(handle), 0, "staging is released");
    assert_eq!(xyg_wasm_instance_dispose(handle), STATUS_OK);
    (status, outcome)
}

fn expected_status(rejection: PainterRejection) -> i32 {
    match rejection {
        PainterRejection::TraceLimit | PainterRejection::ByteLimit => STATUS_RESOURCE_LIMIT,
        PainterRejection::Version => STATUS_SCENE_VERSION,
        PainterRejection::Malformed => STATUS_MALFORMED_SCENE,
    }
}

fn sha256_hex(bytes: &[u8]) -> String {
    // Dependency-free FIPS 180-4 SHA-256 for fixture identity only.
    const K: [u32; 64] = [
        0x428a2f98, 0x71374491, 0xb5c0fbcf, 0xe9b5dba5, 0x3956c25b, 0x59f111f1, 0x923f82a4,
        0xab1c5ed5, 0xd807aa98, 0x12835b01, 0x243185be, 0x550c7dc3, 0x72be5d74, 0x80deb1fe,
        0x9bdc06a7, 0xc19bf174, 0xe49b69c1, 0xefbe4786, 0x0fc19dc6, 0x240ca1cc, 0x2de92c6f,
        0x4a7484aa, 0x5cb0a9dc, 0x76f988da, 0x983e5152, 0xa831c66d, 0xb00327c8, 0xbf597fc7,
        0xc6e00bf3, 0xd5a79147, 0x06ca6351, 0x14292967, 0x27b70a85, 0x2e1b2138, 0x4d2c6dfc,
        0x53380d13, 0x650a7354, 0x766a0abb, 0x81c2c92e, 0x92722c85, 0xa2bfe8a1, 0xa81a664b,
        0xc24b8b70, 0xc76c51a3, 0xd192e819, 0xd6990624, 0xf40e3585, 0x106aa070, 0x19a4c116,
        0x1e376c08, 0x2748774c, 0x34b0bcb5, 0x391c0cb3, 0x4ed8aa4a, 0x5b9cca4f, 0x682e6ff3,
        0x748f82ee, 0x78a5636f, 0x84c87814, 0x8cc70208, 0x90befffa, 0xa4506ceb, 0xbef9a3f7,
        0xc67178f2,
    ];
    let mut h: [u32; 8] = [
        0x6a09e667, 0xbb67ae85, 0x3c6ef372, 0xa54ff53a, 0x510e527f, 0x9b05688c, 0x1f83d9ab,
        0x5be0cd19,
    ];
    let mut message = bytes.to_vec();
    message.push(0x80);
    while message.len() % 64 != 56 {
        message.push(0);
    }
    message.extend_from_slice(&((bytes.len() as u64) * 8).to_be_bytes());
    for block in message.chunks_exact(64) {
        let mut w = [0u32; 64];
        for (index, word) in block.chunks_exact(4).enumerate() {
            w[index] = u32::from_be_bytes(word.try_into().unwrap());
        }
        for index in 16..64 {
            let s0 = w[index - 15].rotate_right(7)
                ^ w[index - 15].rotate_right(18)
                ^ (w[index - 15] >> 3);
            let s1 = w[index - 2].rotate_right(17)
                ^ w[index - 2].rotate_right(19)
                ^ (w[index - 2] >> 10);
            w[index] = w[index - 16]
                .wrapping_add(s0)
                .wrapping_add(w[index - 7])
                .wrapping_add(s1);
        }
        let [mut a, mut b, mut c, mut d, mut e, mut f, mut g, mut hh] = h;
        for index in 0..64 {
            let s1 = e.rotate_right(6) ^ e.rotate_right(11) ^ e.rotate_right(25);
            let choose = (e & f) ^ (!e & g);
            let t1 = hh
                .wrapping_add(s1)
                .wrapping_add(choose)
                .wrapping_add(K[index])
                .wrapping_add(w[index]);
            let s0 = a.rotate_right(2) ^ a.rotate_right(13) ^ a.rotate_right(22);
            let majority = (a & b) ^ (a & c) ^ (b & c);
            let t2 = s0.wrapping_add(majority);
            hh = g;
            g = f;
            f = e;
            e = d.wrapping_add(t1);
            d = c;
            c = b;
            b = a;
            a = t1.wrapping_add(t2);
        }
        for (slot, value) in h.iter_mut().zip([a, b, c, d, e, f, g, hh]) {
            *slot = slot.wrapping_add(value);
        }
    }
    h.iter().map(|word| format!("{word:08x}")).collect()
}

fn render_fixture() -> String {
    let mut rows = Vec::new();
    for case in cases() {
        let scene_bytes = scene_bytes(&case);
        let max_bytes = budget(&case, &scene_bytes);
        let reference = scene::browser_painter_from_scene(&scene_bytes, max_bytes);
        let native = native(&scene_bytes, max_bytes);
        let (status, wasm) = wasm(&scene_bytes, max_bytes);
        let common = format!(
            concat!(
                "\"name\":\"{}\",\"kind\":{},\"count\":{},\"distinct_ids\":{},",
                "\"alternate_symbols\":{},\"diameter\":{},\"mutation\":\"{}\",",
                "\"scene_bytes\":{},\"scene_sha256\":\"{}\",\"max_bytes\":{}"
            ),
            case.name,
            case.kind as u8,
            case.count,
            case.distinct_ids,
            case.alternate_symbols,
            if case.kind == SceneRecordKind::Scatter {
                "4.0"
            } else {
                "0.0"
            },
            case.mutation.name(),
            scene_bytes.len(),
            sha256_hex(&scene_bytes),
            max_bytes,
        );
        let outcome = match reference {
            Ok(painter) => {
                assert_eq!(native.as_deref(), Ok(painter.as_slice()), "{}", case.name);
                assert_eq!(status, STATUS_OK, "{}", case.name);
                assert_eq!(wasm.as_deref(), Ok(painter.as_slice()), "{}", case.name);
                let traces = u32::from_le_bytes(painter[20..24].try_into().unwrap());
                format!(
                    "\"outcome\":\"ok\",\"traces\":{},\"painter_bytes\":{},\"painter_sha256\":\"{}\"",
                    traces,
                    painter.len(),
                    sha256_hex(&painter)
                )
            }
            Err(rejection) => {
                let diagnostic = rejection.diagnostic();
                assert!(diagnostic.starts_with(&format!("{}: ", rejection.code())));
                assert_eq!(native, Err(diagnostic.to_owned()), "{}", case.name);
                assert_eq!(status, expected_status(rejection), "{}", case.name);
                assert_eq!(wasm, Err(diagnostic.to_owned()), "{}", case.name);
                format!(
                    "\"outcome\":\"rejected\",\"code\":\"{}\",\"wasm_status\":{},\"diagnostic\":\"{}\"",
                    rejection.code(),
                    status,
                    diagnostic
                )
            }
        };
        rows.push(format!("    {{{common},{outcome}}}"));
    }
    format!(
        concat!(
            "{{\n",
            "  \"schema\": \"xyg.painter-admission-cross-host/v1\",\n",
            "  \"authority\": \"crates/xyg-engine/src/scene.rs (PainterRejection, to_browser_painter)\",\n",
            "  \"generator\": \"crates/xyg-wasm/tests/painter_admission_parity.rs\",\n",
            "  \"scene_version\": {},\n",
            "  \"painter_version\": {},\n",
            "  \"max_traces\": {},\n",
            "  \"recipe\": {{\"viewport\":[120,100],\"margins\":[10,10,10,10],",
            "\"x_axis\":{{\"id\":1,\"domain\":[0,1]}},\"y_axis\":{{\"id\":2,\"domain\":[0,1]}},",
            "\"style\":{{\"fill_rgba\":[57,135,229,255],\"stroke_rgba\":[0,0,0,0],\"stroke_width\":0}},",
            "\"style_ref\":0,\"x0\":0.5,\"y0\":0.5,\"x1\":0,\"y1\":0,",
            "\"stable_ids\":\"index when distinct_ids else 7\",",
            "\"symbols\":\"index % 2 when alternate_symbols else 0\"}},\n",
            "  \"cases\": [\n{}\n  ]\n",
            "}}\n"
        ),
        scene::SCENE_VERSION,
        scene::BROWSER_PAINTER_VERSION,
        MAX_BROWSER_PAINTER_TRACES,
        rows.join(",\n"),
    )
}

#[test]
fn native_and_wasm_hosts_agree_on_the_committed_admission_fixture() {
    let path = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("../..")
        .join(FIXTURE);
    let rendered = render_fixture();
    if std::env::var_os("XYG_WRITE_PAINTER_ADMISSION_FIXTURE").is_some() {
        std::fs::write(&path, &rendered).unwrap();
        return;
    }
    let committed = std::fs::read_to_string(&path).expect("read committed admission fixture");
    assert_eq!(
        committed, rendered,
        "painter admission fixture is stale; regenerate it (see module docs)"
    );
}

fn polyline_runs(count: usize) -> Vec<u8> {
    scene_bytes(&case(
        "runs",
        SceneRecordKind::Polyline,
        count,
        true,
        false,
        Budget::Bytes(ONE_MIB),
    ))
}

#[test]
fn rejected_cancelled_and_stale_requests_never_publish_and_retry_is_deterministic() {
    let valid = polyline_runs(MAX_BROWSER_PAINTER_TRACES);
    let fragmented = polyline_runs(MAX_BROWSER_PAINTER_TRACES + 1);
    let reference = scene::browser_painter_from_scene(&valid, ONE_MIB).unwrap();
    let handle = xyg_wasm_instance_new(ONE_MIB);
    assert!(handle > 0);

    stage(handle, &valid);
    assert_eq!(xyg_wasm_scene_prepare(handle, 1, 0, valid.len()), STATUS_OK);
    assert_eq!(wasm_output(handle), reference);

    // A rejection clears the earlier success: no stale or partial painter.
    stage(handle, &fragmented);
    assert_eq!(
        xyg_wasm_scene_prepare(handle, 2, 0, fragmented.len()),
        STATUS_RESOURCE_LIMIT
    );
    assert_eq!(xyg_wasm_output_len(handle), 0);
    assert_eq!(xyg_wasm_arena_len(handle), 0);
    assert_eq!(
        wasm_error(handle),
        PainterRejection::TraceLimit.diagnostic()
    );
    assert_eq!(
        native(&fragmented, ONE_MIB),
        Err(PainterRejection::TraceLimit.diagnostic().to_owned())
    );

    // Retrying the same sequence is stale even with admissible bytes.
    stage(handle, &valid);
    assert_eq!(
        xyg_wasm_scene_prepare(handle, 2, 0, valid.len()),
        STATUS_STALE_SEQUENCE
    );
    assert_eq!(xyg_wasm_output_len(handle), 0);

    // A cancelled sequence is refused before lowering.
    assert_eq!(xyg_wasm_cancel(handle, 3), STATUS_OK);
    stage(handle, &valid);
    assert_eq!(
        xyg_wasm_scene_prepare(handle, 3, 0, valid.len()),
        STATUS_CANCELLED
    );
    assert_eq!(xyg_wasm_output_len(handle), 0);
    assert_eq!(xyg_wasm_arena_len(handle), 0);

    // A fresh retry after rejection and cancellation is byte-identical to the
    // first success and to the native seam.
    stage(handle, &valid);
    assert_eq!(xyg_wasm_scene_prepare(handle, 4, 0, valid.len()), STATUS_OK);
    assert_eq!(wasm_output(handle), reference);
    assert_eq!(native(&valid, ONE_MIB), Ok(reference));
    assert_eq!(xyg_wasm_instance_dispose(handle), STATUS_OK);
}

#[test]
fn native_seam_reports_diagnostics_only_when_the_buffer_can_hold_them() {
    let fragmented = polyline_runs(MAX_BROWSER_PAINTER_TRACES + 1);
    let diagnostic = PainterRejection::TraceLimit.diagnostic().as_bytes();
    // Too small for the diagnostic: the sentinel still reports failure and the
    // caller's buffer is untouched (no partial painter or message bytes).
    let mut small = vec![0xA5u8; diagnostic.len()];
    let written = unsafe {
        xyg_core::xyg_scene_browser_painter(
            fragmented.as_ptr(),
            fragmented.len(),
            ONE_MIB,
            small.as_mut_ptr(),
            small.len(),
        )
    };
    assert_eq!(written, usize::MAX);
    assert!(small.iter().all(|byte| *byte == 0xA5));
    // A null output still fails closed.
    let written = unsafe {
        xyg_core::xyg_scene_browser_painter(
            fragmented.as_ptr(),
            fragmented.len(),
            ONE_MIB,
            std::ptr::null_mut(),
            0,
        )
    };
    assert_eq!(written, usize::MAX);
    // A capacity probe for an admissible Scene reports the exact length and
    // writes nothing until the caller supplies it.
    let valid = polyline_runs(MAX_BROWSER_PAINTER_TRACES);
    let exact = scene::browser_painter_from_scene(&valid, ONE_MIB)
        .unwrap()
        .len();
    let mut probe = vec![0xA5u8; 16];
    let written = unsafe {
        xyg_core::xyg_scene_browser_painter(
            valid.as_ptr(),
            valid.len(),
            ONE_MIB,
            probe.as_mut_ptr(),
            probe.len(),
        )
    };
    assert_eq!(written, exact);
    assert!(probe.iter().all(|byte| *byte == 0xA5));
}
