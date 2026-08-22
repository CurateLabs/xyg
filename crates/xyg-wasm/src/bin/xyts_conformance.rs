//! Generate the canonical XYTS cross-host fixture from the Rust authority.
//!
//! The committed JSON is deliberately generated here, beside the only XYTS
//! decoder. Native Python/Node/Pyodide consume the resulting Scene v11 bytes;
//! they do not grow a second XYTS policy implementation.

use std::{env, fs, path::PathBuf};

use xyg_engine::scene::{self, SceneDocument};
use xyg_wasm::compile::*;

#[derive(Clone)]
struct Series {
    kind: u32,
    x: Vec<f64>,
    y: Vec<f64>,
    y0: Option<Vec<f64>>,
    y1: Option<Vec<f64>>,
    stable_base: Option<u64>,
    stable_ids: Option<Vec<u64>>,
}

fn put_u32(out: &mut [u8], offset: usize, value: u32) {
    out[offset..offset + 4].copy_from_slice(&value.to_le_bytes());
}

fn put_u64(out: &mut [u8], offset: usize, value: u64) {
    out[offset..offset + 8].copy_from_slice(&value.to_le_bytes());
}

fn put_f64(out: &mut [u8], offset: usize, value: f64) {
    out[offset..offset + 8].copy_from_slice(&value.to_le_bytes());
}

fn pack(series: &[Series], x_domain: [f64; 2], y_domain: [f64; 2]) -> Vec<u8> {
    let data_start = COMPILE_HEADER_BYTES + series.len() * SERIES_DESCRIPTOR_BYTES;
    let records: usize = series.iter().map(|value| value.x.len()).sum();
    let mut out = vec![0; data_start];
    out[..4].copy_from_slice(SERIES_MAGIC);
    put_u32(&mut out, HEADER_VERSION, SERIES_VERSION);
    put_u32(&mut out, HEADER_HEADER_BYTES, COMPILE_HEADER_BYTES as u32);
    put_u32(&mut out, HEADER_FLAGS, HEADER_FLAG_AUTO_MARGINS);
    put_u32(&mut out, HEADER_SERIES_COUNT, series.len() as u32);
    put_u32(&mut out, HEADER_RECORD_COUNT, records as u32);
    put_f64(&mut out, HEADER_WIDTH, 320.0);
    put_f64(&mut out, HEADER_HEIGHT, 240.0);
    put_u64(&mut out, HEADER_X_AXIS_ID, 1);
    put_u64(&mut out, HEADER_Y_AXIS_ID, 2);
    put_f64(&mut out, HEADER_X_LO, x_domain[0]);
    put_f64(&mut out, HEADER_X_HI, x_domain[1]);
    put_f64(&mut out, HEADER_X_CONSTANT, 1.0);
    put_f64(&mut out, HEADER_Y_LO, y_domain[0]);
    put_f64(&mut out, HEADER_Y_HI, y_domain[1]);
    put_f64(&mut out, HEADER_Y_CONSTANT, 1.0);

    let mut cursor = data_start;
    for (index, value) in series.iter().enumerate() {
        assert_eq!(value.x.len(), value.y.len());
        let descriptor = COMPILE_HEADER_BYTES + index * SERIES_DESCRIPTOR_BYTES;
        put_u32(&mut out, descriptor + DESCRIPTOR_KIND, value.kind);
        put_u32(
            &mut out,
            descriptor + DESCRIPTOR_RECORD_COUNT,
            value.x.len() as u32,
        );
        put_f64(&mut out, descriptor + DESCRIPTOR_DIAMETER, f64::NAN);
        put_f64(&mut out, descriptor + DESCRIPTOR_STROKE_WIDTH, f64::NAN);
        let mut flags = 0;
        if value.y0.is_some() {
            flags |= DESCRIPTOR_FLAG_Y0;
        }
        if value.y1.is_some() {
            flags |= DESCRIPTOR_FLAG_Y1;
        }
        if let Some(base) = value.stable_base {
            flags |= DESCRIPTOR_FLAG_STABLE_ID_BASE;
            put_u64(&mut out, descriptor + DESCRIPTOR_STABLE_ID_BASE, base);
        }
        if value.stable_ids.is_some() {
            flags |= DESCRIPTOR_FLAG_STABLE_IDS;
        }
        put_u32(&mut out, descriptor + DESCRIPTOR_FLAGS, flags);

        for (field, column) in [
            (DESCRIPTOR_X, Some(&value.x)),
            (DESCRIPTOR_Y, Some(&value.y)),
            (DESCRIPTOR_Y0, value.y0.as_ref()),
            (DESCRIPTOR_Y1, value.y1.as_ref()),
        ] {
            if let Some(column) = column {
                put_u32(&mut out, descriptor + field, cursor as u32);
                for item in column {
                    out.extend_from_slice(&item.to_le_bytes());
                    cursor += 8;
                }
            }
        }
        if let Some(ids) = &value.stable_ids {
            assert_eq!(ids.len(), value.x.len());
            put_u32(&mut out, descriptor + DESCRIPTOR_STABLE_IDS, cursor as u32);
            for item in ids {
                out.extend_from_slice(&item.to_le_bytes());
                cursor += 8;
            }
        }
    }
    out
}

fn hex(bytes: &[u8]) -> String {
    const DIGITS: &[u8; 16] = b"0123456789abcdef";
    let mut out = String::with_capacity(bytes.len() * 2);
    for byte in bytes {
        out.push(DIGITS[(byte >> 4) as usize] as char);
        out.push(DIGITS[(byte & 15) as usize] as char);
    }
    out
}

fn escaped(value: &str) -> String {
    value.replace('\\', "\\\\").replace('"', "\\\"")
}

fn success(name: &str, request: Vec<u8>) -> String {
    let compiled = compile_scene_request(&request, usize::MAX).expect("canonical case compiles");
    scene::validate_scene_batch(&compiled.bytes).expect("canonical Scene validates");
    let painter = SceneDocument::decode(&compiled.bytes)
        .expect("canonical Scene decodes")
        .to_browser_painter(16 * 1024 * 1024)
        .expect("canonical painter lowers");
    format!(
        "    {{\"name\":\"{}\",\"request_hex\":\"{}\",\"scene_hex\":\"{}\",\"painter_hex\":\"{}\",\"records\":{},\"styles\":{}}}",
        escaped(name), hex(&request), hex(&compiled.bytes), hex(&painter), compiled.records, compiled.styles
    )
}

fn failure(name: &str, request: Vec<u8>) -> String {
    let error = compile_scene_request(&request, usize::MAX).expect_err("negative case fails");
    format!(
        "    {{\"name\":\"{}\",\"request_hex\":\"{}\",\"rust_error\":\"{}\"}}",
        escaped(name),
        hex(&request),
        escaped(&format!("{error:?}"))
    )
}

fn render() -> String {
    let annotation_prefix = 0x5859_0100_0000_0000;
    let all_marks = pack(
        &[
            Series {
                kind: KIND_SCATTER,
                x: vec![1.0, 2.0],
                y: vec![2.0, 3.0],
                y0: None,
                y1: None,
                stable_base: None,
                stable_ids: Some(vec![annotation_prefix, 91]),
            },
            Series {
                kind: KIND_LINE,
                x: vec![4.0, 2.0, 1.0],
                y: vec![1.0, 4.0, 2.0],
                y0: None,
                y1: None,
                stable_base: Some(0x8000_0000_0000_0001),
                stable_ids: None,
            },
            Series {
                kind: KIND_BAR,
                x: vec![4.0, 2.0, 1.0],
                y: vec![3.0, 2.0, 4.0],
                y0: None,
                y1: None,
                stable_base: None,
                stable_ids: None,
            },
            Series {
                kind: KIND_AREA,
                x: vec![1.0, 2.0],
                y: vec![2.5, 3.5],
                y0: Some(vec![-1.0, -2.0]),
                y1: None,
                stable_base: Some(700),
                stable_ids: None,
            },
        ],
        [5.0, -5.0],
        [-3.0, 5.0],
    );
    let singleton_bar = pack(
        &[Series {
            kind: KIND_BAR,
            x: vec![7.0],
            y: vec![3.0],
            y0: None,
            y1: None,
            stable_base: Some(44),
            stable_ids: None,
        }],
        [10.0, 0.0],
        [0.0, 5.0],
    );
    let explicit_bounds = pack(
        &[Series {
            kind: KIND_AREA,
            x: vec![0.0, 1.0],
            y: vec![3.0, 4.0],
            y0: Some(vec![1.0, 2.0]),
            y1: Some(vec![5.0, 6.0]),
            stable_base: Some(800),
            stable_ids: None,
        }],
        [0.0, 1.0],
        [0.0, 6.0],
    );

    let mut wrong_version = singleton_bar.clone();
    put_u32(&mut wrong_version, HEADER_VERSION, SERIES_VERSION - 1);
    let mut unsupported_kind = singleton_bar.clone();
    put_u32(
        &mut unsupported_kind,
        COMPILE_HEADER_BYTES + DESCRIPTOR_KIND,
        99,
    );
    let overflow = pack(
        &[Series {
            kind: KIND_LINE,
            x: vec![0.0, 1.0],
            y: vec![0.0, 1.0],
            y0: None,
            y1: None,
            stable_base: Some(u64::MAX),
            stable_ids: None,
        }],
        [0.0, 1.0],
        [0.0, 1.0],
    );
    let mut nonfinite = singleton_bar.clone();
    let x_offset = u32::from_le_bytes(
        nonfinite[COMPILE_HEADER_BYTES + DESCRIPTOR_X..COMPILE_HEADER_BYTES + DESCRIPTOR_X + 4]
            .try_into()
            .unwrap(),
    ) as usize;
    put_f64(&mut nonfinite, x_offset, f64::INFINITY);

    format!(
        concat!(
            "{{\n",
            "  \"schema\": \"xyg.xyts-conformance/v1\",\n",
            "  \"authority\": \"crates/xyg-wasm/src/compile.rs\",\n",
            "  \"scene_version\": {},\n",
            "  \"painter_version\": {},\n",
            "  \"successful\": [\n{}\n  ],\n",
            "  \"failures\": [\n{}\n  ]\n",
            "}}\n"
        ),
        scene::SCENE_VERSION,
        scene::BROWSER_PAINTER_VERSION,
        [
            success("all_marks_reversed_domain", all_marks),
            success("singleton_bar_reversed_domain", singleton_bar),
            success("area_explicit_bounds", explicit_bounds)
        ]
        .join(",\n"),
        [
            failure("wrong_version", wrong_version),
            failure("unsupported_kind", unsupported_kind),
            failure("stable_id_overflow", overflow),
            failure("nonfinite_geometry", nonfinite)
        ]
        .join(",\n")
    )
}

fn main() {
    let root = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../..");
    let target = root.join("tests/fixtures/xyts_cross_host.json");
    let rendered = render();
    if env::args().any(|value| value == "--check") {
        let current = fs::read_to_string(&target).expect("read committed XYTS fixture");
        assert_eq!(current, rendered, "XYTS fixture is stale; regenerate it");
    } else {
        fs::write(&target, rendered).expect("write XYTS fixture");
        println!("wrote {}", target.display());
    }
}
