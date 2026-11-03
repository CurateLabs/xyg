//! GPU view validation, precision and transaction refusal regression proofs.
use super::*;

fn section<'a>(bytes: &'a [u8], name: &str, index: usize) -> &'a [u8] {
    Container::decode(bytes, wire::RESULT_MAGIC)
        .unwrap()
        .get(name, index as u32)
        .unwrap()
        .payload
}
fn words(bytes: &[u8], name: &str) -> Vec<u32> {
    section(bytes, name, 0)
        .chunks_exact(4)
        .map(|v| u32::from_le_bytes(v.try_into().unwrap()))
        .collect()
}
fn close(encoded: f32, original: f64, [offset, scale]: [f64; 2]) {
    let relative = (original - offset) * scale;
    let bound = (relative.abs() * 2f64.powi(-23) + 2f64.powi(-149)) / scale
        + 8. * f64::EPSILON * offset.abs().max(original.abs()).max(1.);
    assert!((f64::from(encoded) / scale + offset - original).abs() <= bound);
}
fn inspect(bytes: &[u8]) {
    wire::validate_gpu(bytes).unwrap();
    let p = wire::decode_paint(bytes).unwrap();
    let mut transforms = [[0.; 2]; 3];
    for (i, t) in transforms.iter_mut().enumerate() {
        for (j, v) in section(bytes, "gpu.transform.f64", i)
            .chunks_exact(8)
            .enumerate()
        {
            t[j] = f64::from_le_bytes(v.try_into().unwrap());
        }
    }
    let compare = |name, index, values: Vec<f64>, t| {
        let column = section(bytes, name, index);
        assert_eq!(column.len(), values.len() * 4);
        for (b, v) in column.chunks_exact(4).zip(values) {
            close(f32::from_le_bytes(b.try_into().unwrap()), v, t);
        }
    };
    for i in 0..2 {
        compare(
            "gpu.node.coord.bytes",
            i,
            p.nodes.iter().map(|n| n.center[i]).collect(),
            transforms[i],
        );
    }
    for i in 0..4 {
        compare(
            "gpu.shaft.coord.bytes",
            i,
            p.pieces
                .iter()
                .map(|p| [p.start[0], p.start[1], p.end[0], p.end[1]][i])
                .collect(),
            transforms[i % 2],
        );
        compare(
            "gpu.shaft.attr.bytes",
            i,
            p.pieces
                .iter()
                .map(|p| [p.half_width, p.dash.0, p.dash.1, p.dash_offset][i])
                .collect(),
            if i == 3 { transforms[2] } else { [0., 1.] },
        );
        compare(
            "gpu.frame.coord.bytes",
            i,
            p.frames.iter().map(|f| f.bounds[i]).collect(),
            transforms[i % 2],
        );
    }
    for i in 0..6 {
        compare(
            "gpu.head.coord.bytes",
            i,
            p.pieces
                .iter()
                .filter_map(|p| p.head)
                .map(|h| h[i / 2][i % 2])
                .collect(),
            transforms[i % 2],
        );
    }
    compare(
        "gpu.frame.width.bytes",
        0,
        p.frames.iter().map(|f| f.half_width).collect(),
        [0., 1.],
    );
    for kind in ["node", "edge"] {
        assert_eq!(
            section(bytes, &format!("gpu.{kind}.style.bytes"), 0),
            section(bytes, &format!("paint.{kind}.style.bytes"), 0)
        );
    }
}

#[test]
fn gpu_precision_retains_clipping_heads_routes_frames_and_cpu_index() {
    let base = handmade_ends(
        COMPOSITION_VERSION,
        &[id(1), id(2), id(3)],
        &[
            E::Persisted(id(11)),
            E::Persisted(id(12)),
            E::Persisted(id(13)),
            E::Persisted(id(14)),
        ],
        &[],
        Some((&[0, 0, 0], &[0, 1, 1])),
        Some(&[(0, 1), (0, 1), (1, 1), (1, 2)]),
    );
    let mut b = Builder::new(DOCUMENT_MAGIC);
    b.extend_from(&Container::decode(&base, DOCUMENT_MAGIC).unwrap());
    b.u8s("node.class", 0, &[1, 2, 3]);
    b.u8s("node.epistemic", 0, &[1, 2, 3]);
    b.u8s("edge.status", 0, &[1, 2, 3, 1]);
    b.u8s("edge.epistemic", 0, &[1, 2, 3, 1]);
    b.u8s("graph.directed", 0, &[1]);
    let mut s = WireSession::open(&open_doc(&b.finish()), 16 * 1024 * 1024, 0).unwrap();
    let reply = s
        .execute(
            &request(2, 0, wire::RENDER, |b| {
                b.f64s("camera.f64", 0, &[1., 100., 20., 100., 200., 200., 2.])
            }),
            0,
            None,
        )
        .unwrap()
        .to_vec();
    inspect(&reply);
    let paint = wire::decode_paint(&reply).unwrap();
    assert!(paint.pieces.iter().any(|p| p.head.is_some()));
    assert!(paint.pieces.iter().any(|p| p.dash_offset > 0.));
    assert!(paint.pieces.iter().any(|p| p.dash.1 > 0.));
    assert!(paint.pieces.iter().filter(|p| p.edge == 2).count() > 1);
    assert!(!paint.frames.is_empty());
    for name in ["gpu.head.piece.u32", "gpu.frame.node.u32"] {
        let off = section(&reply, name, 0).as_ptr() as usize - reply.as_ptr() as usize;
        let mut bad_ref = reply.clone();
        bad_ref[off..off + 4].copy_from_slice(&u32::MAX.to_le_bytes());
        assert_eq!(
            wire::validate_gpu(&bad_ref),
            Err(InteractionStatus::Invalid)
        );
    }
    let before = s.session().published().unwrap().clone();
    let rev = before.revision;
    let again = s
        .execute(
            &request(3, rev, wire::RENDER, |b| {
                b.f64s("camera.f64", 0, &[1., 100., 20., 100., 200., 200., 2.])
            }),
            0,
            None,
        )
        .unwrap()
        .to_vec();
    assert_eq!(s.session().published().unwrap(), &before);
    assert_eq!(wire::decode_paint(&again).unwrap(), paint);
    inspect(&again);
    // Encoding is a pure read of the already published paint/index/membership.
    let mut builder = Builder::new(wire::RESULT_MAGIC);
    crate::graphforge::interaction::gpu::encode(&mut builder, &before).unwrap();
    assert_eq!(s.session().published().unwrap(), &before);
}

#[test]
fn gpu_offset_preserves_small_deltas_and_normalizes_extreme_finite_domains() {
    let doc = handmade(&[id(1), id(2), id(3)], &[], &[]);
    for x in [[1e12, 1e12 + 0.25, 1e12 + 0.5], [1e308, 1.1e308, 1.2e308]] {
        let opening = request(1, 0, wire::OPEN, |b| {
            b.bytes("document.bytes", 0, &doc);
            b.f64s("load.x.f64", 0, &x);
            b.f64s("load.y.f64", 0, &[-1e200, 0., 1e200]);
        });
        let mut s = WireSession::open(&opening, 16 * 1024 * 1024, 0).unwrap();
        let reply = s
            .execute(&request(2, 0, wire::RENDER, |_| {}), 0, None)
            .unwrap();
        inspect(reply);
        let encoded: Vec<_> = section(reply, "gpu.node.coord.bytes", 0)
            .chunks_exact(4)
            .map(|v| f32::from_le_bytes(v.try_into().unwrap()))
            .collect();
        assert!(encoded.windows(2).all(|w| w[0] < w[1]));
    }
}

#[test]
fn gpu_view_rejects_missing_planes_bad_types_counts_refs_flags_nan_and_reserved() {
    let mut s = opened();
    let reply = s
        .execute(&request(2, 0, wire::RENDER, |_| {}), 0, None)
        .unwrap()
        .to_vec();
    inspect(&reply);
    for (name, index, at, value) in [
        ("gpu.header.u32", 0, 0, 2),
        ("gpu.header.u32", 0, 4, 1),
        ("gpu.header.u32", 0, 28, 1),
        ("gpu.shaft.edge.u32", 0, 0, 255),
        ("gpu.shaft.flags.u8", 0, 0, 2),
        ("gpu.node.style.bytes", 0, 57, 1),
        ("gpu.node.style.bytes", 0, 24, 255),
        ("gpu.node.style.bytes", 0, 25, 255),
        ("gpu.node.style.bytes", 0, 26, 255),
        ("gpu.node.style.bytes", 0, 27, 255),
        ("gpu.node.state.u8", 0, 1, 16),
        ("gpu.node.state.u8", 0, 2, 8),
        ("gpu.node.state.u8", 0, 3, 1),
    ] {
        let plane = section(&reply, name, index);
        let off = plane.as_ptr() as usize - reply.as_ptr() as usize;
        let mut malformed = reply.clone();
        malformed[off + at] = value;
        assert_eq!(
            wire::validate_gpu(&malformed),
            Err(InteractionStatus::Invalid),
            "{name}@{at}"
        );
    }
    for name in [
        "gpu.node.coord.bytes",
        "gpu.node.style.bytes",
        "gpu.transform.f64",
    ] {
        let plane = section(&reply, name, 0);
        let off = plane.as_ptr() as usize - reply.as_ptr() as usize;
        let mut malformed = reply.clone();
        if name == "gpu.transform.f64" {
            malformed[off..off + 8].copy_from_slice(&f64::NAN.to_le_bytes());
        } else {
            let at = if name == "gpu.node.style.bytes" {
                12
            } else {
                0
            };
            malformed[off + at..off + at + 4].copy_from_slice(&f32::NAN.to_le_bytes());
        }
        assert_eq!(
            wire::validate_gpu(&malformed),
            Err(InteractionStatus::Invalid)
        );
    }
    let c = Container::decode(&reply, wire::RESULT_MAGIC).unwrap();
    for replacement in 0..4 {
        let mut b = Builder::new(wire::RESULT_MAGIC);
        for (name, index, sec) in &c.sections {
            if *name != "gpu.node.coord.bytes" || *index != 0 {
                let mut one = Container::decode(&reply, wire::RESULT_MAGIC).unwrap();
                one.sections.retain(|(n, i, _)| n == name && i == index);
                b.extend_from(&one);
            } else {
                match replacement {
                    0 => {}
                    1 => b.u8s(name, 0, sec.payload),
                    2 => b.bytes(name, 0, &sec.payload[4..]),
                    _ => b.bytes(name, 1, sec.payload),
                }
            }
        }
        assert!(wire::validate_gpu(&b.finish()).is_err());
    }
}

#[test]
fn gpu_added_admission_refuses_before_candidate_and_keeps_exact_retry_delivery() {
    let mut s = opened();
    assert!(Container::decode(s.reply(), wire::RESULT_MAGIC)
        .unwrap()
        .get("gpu.header.u32", 0)
        .is_none());
    let reply = s
        .execute(&request(2, 0, wire::RENDER, |_| {}), 0, None)
        .unwrap()
        .to_vec();
    let rev = s.session().render_revision();
    let snapshot = s.session().published().unwrap().clone();
    let work = s.session().work();
    let candidate = request(3, rev, 11, |b| {
        b.bytes(
            "refs.bytes",
            0,
            &wire::encode_refs(&[ElementRef::Node(id(1))]).unwrap(),
        )
    });
    let old_limit = s.max_bytes;
    // This would fit the S4 envelope but excludes the new source-based GPU
    // reserve. A post-allocation reply-length check cannot satisfy this proof.
    s.max_bytes = s.retained_budget() + candidate.len() * 128 - (16_384 + 3 * 2048 + 2 * 8192);
    assert_eq!(
        s.execute(&candidate, 0, None),
        Err(InteractionStatus::Budget)
    );
    assert_eq!(s.reply(), reply);
    assert_eq!(s.session().published().unwrap(), &snapshot);
    assert_eq!(s.session().work(), work);
    assert!(s.session().selection().unwrap().is_empty());
    assert!(s.session().pending_outbound().is_none());
    s.max_bytes = old_limit;
    let success = s.execute(&candidate, 0, None).unwrap().to_vec();
    inspect(&success);
    assert_eq!(words(&success, "outcome.u32"), [1, 1, 1, 0]);
    assert_eq!(s.execute(&candidate, usize::MAX, None).unwrap(), success);
    assert_eq!(s.session().pending_outbound().unwrap().revision, 1);
    let stale = request(4, rev.wrapping_sub(1), 4, |_| {});
    assert_eq!(s.execute(&stale, 0, None), Err(InteractionStatus::Stale));
    assert_eq!(s.reply(), success);
    assert_eq!(s.execute(&candidate, 0, None).unwrap(), success);
}
