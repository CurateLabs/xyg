//! Scene v33 secondary right-hand y axis (`y2`) proofs: wire block, record
//! selector bit, gutter measurement, painting, XYPB v16, and Rust-owned
//! right-only admission.
use crate::scene::{
    validate_scene_batch, AxisScale, AxisSide, ScaleKind, SceneAxisChromeStyle, SceneDocument,
    SceneError, BROWSER_PAINTER_HEADER_BYTES, BROWSER_PAINTER_TRACE_BYTES,
    SCENE_BATCH_HEADER_BYTES, SCENE_BATCH_RECORD_BYTES, SCENE_RECORD_Y2_BIT,
    SCENE_STYLE_RECORD_BYTES, SCENE_VERSION,
};
use crate::scene_annotation_splice::XYAS_HEADER_BYTES;
use crate::scene_chrome::{FLAG_AUTHORED_MARGINS, FLAG_X_MAJOR_AUTO, FLAG_Y_MAJOR_AUTO};
use crate::scene_encode_assembled::{encode_assembled_from_sidecars, EncodeSidecarsCode};
use crate::scene_figure_support_pack::{
    scene_figure_support_pack, FigureSupportAxisInput, FigureSupportTraceInput, AXIS_SIDE_LEFT,
    AXIS_SIDE_OTHER, AXIS_SIDE_RIGHT,
};
use crate::scene_pack::PackedSceneRow;
use crate::scene_trace_sidecars::{
    pack_trace_sidecars, XYNM_HEADER_BYTES, XYNM_MAGIC, XYNM_VERSION,
};
use crate::scene_xycf_pack::XYCF_HEADER_BYTES;
use crate::scene_y2::{SceneY2Axis, SceneY2Domain, SCENE_Y2_FIXED_BYTES};
use crate::{scene_figure_support_reason, tick_layout};

const WIDTH: f64 = 400.0;
const HEIGHT: f64 = 300.0;

fn y2_axis(lo: f64, hi: f64) -> SceneY2Axis {
    SceneY2Axis {
        scale: AxisScale::new(ScaleKind::Linear, lo, hi, HEIGHT, 0.0, 1.0, false).unwrap(),
        axis: SceneAxisChromeStyle::default_style(AxisSide::High),
        major_ticks: None,
        minor_ticks: Vec::new(),
        tick_labels: None,
        title: String::new(),
        format: String::new(),
        tick_strategy: tick_layout::STRATEGY_AUTO as u8,
        tick_anchor: tick_layout::ANCHOR_CENTER as u8,
        tick_anchor_authored: false,
        tick_category: false,
        tick_min_gap: 4.0,
        tick_angle: None,
    }
}

fn chrome_facts(flags: u32, y2: Option<&SceneY2Axis>) -> Vec<u8> {
    let mut facts = vec![0u8; XYCF_HEADER_BYTES];
    facts[..4].copy_from_slice(b"XYCF");
    facts[4..8].copy_from_slice(&1u32.to_le_bytes());
    facts[8..12].copy_from_slice(&flags.to_le_bytes());
    facts[16..24].copy_from_slice(&WIDTH.to_le_bytes());
    facts[24..32].copy_from_slice(&HEIGHT.to_le_bytes());
    facts[112..120].copy_from_slice(&1.0f64.to_le_bytes());
    facts[120..128].copy_from_slice(&1.0f64.to_le_bytes());
    facts[136..144].copy_from_slice(&1.0f64.to_le_bytes());
    facts[144..152].copy_from_slice(&1.0f64.to_le_bytes());
    facts[212..216].copy_from_slice(&1u32.to_le_bytes());
    if let Some(y2) = y2 {
        let payload = y2.encode(SceneY2Domain::Data);
        facts[284..288].copy_from_slice(&(payload.len() as u32).to_le_bytes());
        facts.extend_from_slice(&payload);
    }
    facts
}

fn auto_flags() -> u32 {
    FLAG_X_MAJOR_AUTO | FLAG_Y_MAJOR_AUTO
}

fn empty_xysd() -> Vec<u8> {
    let mut xytt = vec![0u8; 16];
    xytt[..4].copy_from_slice(b"XYTT");
    xytt[4..8].copy_from_slice(&1u32.to_le_bytes());
    let mut xynm = vec![0u8; XYNM_HEADER_BYTES];
    xynm[..4].copy_from_slice(XYNM_MAGIC);
    xynm[4..8].copy_from_slice(&XYNM_VERSION.to_le_bytes());
    pack_trace_sidecars(&xytt, &xynm).unwrap()
}

fn scatter(stable_id: u64, y: f64, y2: bool) -> PackedSceneRow {
    PackedSceneRow {
        kind: 0,
        symbol: 0,
        expansion_mode: 0,
        style_ref: 0,
        stable_id,
        diameter: 6.0,
        x0: 0.5,
        y0: y,
        x1: 0.0,
        y1: 0.0,
        y2,
    }
}

/// XYAS v1 with one solid style and the given rows.
fn xyas(rows: &[PackedSceneRow]) -> Vec<u8> {
    let mut out = b"XYAS".to_vec();
    out.extend_from_slice(&1u32.to_le_bytes());
    out.extend_from_slice(&1u32.to_le_bytes());
    out.extend_from_slice(&(rows.len() as u32).to_le_bytes());
    out.extend_from_slice(&0u32.to_le_bytes());
    out.extend_from_slice(&0u32.to_le_bytes());
    out.extend_from_slice(&[10, 20, 30, 255, 40, 50, 60, 255]);
    out.extend_from_slice(&1.0f64.to_le_bytes());
    for row in rows {
        out.extend_from_slice(&row.to_bytes());
    }
    assert_eq!(
        out.len(),
        XYAS_HEADER_BYTES + SCENE_STYLE_RECORD_BYTES + rows.len() * 56
    );
    out
}

fn encode(rows: &[PackedSceneRow], facts: &[u8]) -> Vec<u8> {
    encode_assembled_from_sidecars(&xyas(rows), facts, &empty_xysd(), &[], &[]).unwrap()
}

fn twin_scene(y2: &SceneY2Axis) -> Vec<u8> {
    encode(
        &[scatter(1, 0.5, false), scatter(2, 50.0, true)],
        &chrome_facts(auto_flags(), Some(y2)),
    )
}

fn f64_at(bytes: &[u8], at: usize) -> f64 {
    f64::from_le_bytes(bytes[at..at + 8].try_into().unwrap())
}

fn u32_at(bytes: &[u8], at: usize) -> u32 {
    u32::from_le_bytes(bytes[at..at + 4].try_into().unwrap())
}

fn record_at(index: usize) -> usize {
    SCENE_BATCH_HEADER_BYTES + SCENE_STYLE_RECORD_BYTES + index * SCENE_BATCH_RECORD_BYTES
}

/// Right gutter of an encoded Scene: viewport width minus the plot's right edge.
fn right_margin(scene: &[u8]) -> f64 {
    f64_at(scene, 32) - f64_at(scene, 64)
}

fn svg_texts(svg: &str, anchor: &str) -> Vec<(f64, String)> {
    let needle = format!("text-anchor=\"{anchor}\"");
    svg.split("<text ")
        .skip(1)
        .filter(|chunk| chunk.contains(&needle) && !chunk.contains("transform="))
        .map(|chunk| {
            let x: f64 = chunk
                .split("x=\"")
                .nth(1)
                .unwrap()
                .split('"')
                .next()
                .unwrap()
                .parse()
                .unwrap();
            let text = chunk
                .split_once('>')
                .unwrap()
                .1
                .split("</text>")
                .next()
                .unwrap()
                .to_owned();
            (x, text)
        })
        .collect()
}

#[test]
fn twin_scene_selects_y2_scale_per_trace_and_round_trips_the_block() {
    let scene = twin_scene(&y2_axis(0.0, 100.0));
    assert_eq!(u32_at(&scene, 4), SCENE_VERSION);
    // Both rows sit at the vertical middle of the plot: 0.5 of 0..1 on y and
    // 50 of 0..100 on y2. A scene that mapped the second row on y would
    // push it off the plot instead.
    let primary = record_at(0);
    let secondary = record_at(1);
    assert_eq!(scene[primary + 3], 0);
    assert_eq!(scene[secondary + 3], SCENE_RECORD_Y2_BIT);
    assert!(scene[secondary + 1] == 1, "y2 record must be visible");
    let (y_primary, y_secondary) = (f64_at(&scene, primary + 24), f64_at(&scene, secondary + 24));
    assert!(
        (y_primary - y_secondary).abs() < 1e-9,
        "{y_primary} vs {y_secondary}"
    );
    validate_scene_batch(&scene).unwrap();
    let document = SceneDocument::decode(&scene).unwrap();
    let records = document.interaction_records();
    assert_eq!((records[0].y2, records[1].y2), (false, true));

    // The block itself is byte-identical across decode -> encode, including a
    // log scale whose transformed domain is not exactly representable.
    let mut log = y2_axis(1.0, 1000.0);
    log.scale = AxisScale::new(ScaleKind::Log, 1.0, 1000.0, HEIGHT, 0.0, 1.0, false).unwrap();
    for axis in [y2_axis(0.0, 100.0), log] {
        let wire = axis.encode(SceneY2Domain::Coordinates);
        let again = SceneY2Axis::decode(&wire, SceneY2Domain::Coordinates, HEIGHT, 0.0).unwrap();
        assert_eq!(again.encode(SceneY2Domain::Coordinates), wire);
    }
}

#[test]
fn old_v32_scene_and_unselected_y2_bits_are_rejected() {
    let scene = twin_scene(&y2_axis(0.0, 100.0));
    let mut old = scene.clone();
    old[4..8].copy_from_slice(&32u32.to_le_bytes());
    assert_eq!(SceneDocument::decode(&old).err(), Some(SceneError::Version));
    assert_eq!(validate_scene_batch(&old).err(), Some(SceneError::Version));

    // A selector bit without a y2 block is a length error in both readers.
    let mut single = encode(&[scatter(1, 0.5, false)], &chrome_facts(auto_flags(), None));
    single[record_at(0) + 3] |= SCENE_RECORD_Y2_BIT;
    assert_eq!(
        SceneDocument::decode(&single).err(),
        Some(SceneError::Length)
    );
    assert_eq!(
        validate_scene_batch(&single).err(),
        Some(SceneError::Length)
    );

    // The packed row bit without an XYY2 sidecar is an encode (payload) error.
    let error = encode_assembled_from_sidecars(
        &xyas(&[scatter(1, 0.5, true)]),
        &chrome_facts(auto_flags(), None),
        &empty_xysd(),
        &[],
        &[],
    )
    .unwrap_err();
    assert_eq!(error.code, EncodeSidecarsCode::Encode);
    // ...and so is one trace straddling both y scales.
    let error = encode_assembled_from_sidecars(
        &xyas(&[scatter(1, 0.5, false), scatter(1, 50.0, true)]),
        &chrome_facts(auto_flags(), Some(&y2_axis(0.0, 100.0))),
        &empty_xysd(),
        &[],
        &[],
    )
    .unwrap_err();
    assert_eq!(error.code, EncodeSidecarsCode::Encode);
}

#[test]
fn selector_bit_survives_packing_and_is_masked_for_annotation_tags() {
    let row = scatter(7, 1.0, true);
    assert_eq!(row.to_bytes()[3], SCENE_RECORD_Y2_BIT);
    assert_eq!(PackedSceneRow::from_bytes(&row.to_bytes()), Some(row));
    let mut reserved = row.to_bytes();
    reserved[3] |= 0x01;
    assert_eq!(PackedSceneRow::from_bytes(&reserved), None);

    // An annotation-tagged record on y2 keeps both its tag and its selector;
    // the same tag on a primary record stays unselected.
    let mut scene = twin_scene(&y2_axis(0.0, 100.0));
    let secondary = record_at(1);
    scene[secondary + 3] = 3 | SCENE_RECORD_Y2_BIT;
    validate_scene_batch(&scene).unwrap();
    let records = SceneDocument::decode(&scene).unwrap();
    let records = records.interaction_records();
    assert_eq!((records[1].annotation_tag, records[1].y2), (3, true));
    let mut primary_tag = twin_scene(&y2_axis(0.0, 100.0));
    let primary = record_at(0);
    primary_tag[primary + 3] = 3;
    // A tagged primary record is only valid in the trailing annotation run;
    // here it precedes the untagged y2 record, so it is rejected, not
    // misread as a selector.
    assert_eq!(
        SceneDocument::decode(&primary_tag).err(),
        Some(SceneError::Length)
    );
    // Only 0x40 is a selector: another reserved bit is not an annotation tag.
    let mut reserved = twin_scene(&y2_axis(0.0, 100.0));
    reserved[record_at(1) + 3] = 0x20 | SCENE_RECORD_Y2_BIT;
    assert_eq!(
        SceneDocument::decode(&reserved).err(),
        Some(SceneError::Length)
    );
}

fn margin_with(mutate: impl FnOnce(&mut SceneY2Axis), flags: u32) -> f64 {
    let mut axis = y2_axis(0.0, 100.0);
    mutate(&mut axis);
    right_margin(&encode(
        &[scatter(2, 50.0, true)],
        &chrome_facts(flags, Some(&axis)),
    ))
}

#[test]
fn gutter_grows_with_styled_ticks_long_labels_and_padding_but_never_below_the_floor() {
    let single = right_margin(&encode(
        &[scatter(1, 0.5, false)],
        &chrome_facts(auto_flags(), None),
    ));
    let base = margin_with(|_| {}, auto_flags());
    assert!(base > single, "y2 ticks need room: {base} vs {single}");

    let styled = margin_with(
        |axis| {
            axis.axis.static_tick_label_size = Some(20.0);
            axis.axis.static_label_size = Some(12.0);
            axis.axis.static_tick_padding = Some(4.0);
        },
        auto_flags(),
    );
    let styled_small = margin_with(
        |axis| {
            axis.axis.static_tick_label_size = Some(10.0);
            axis.axis.static_label_size = Some(12.0);
            axis.axis.static_tick_padding = Some(4.0);
        },
        auto_flags(),
    );
    assert!(styled > styled_small + 5.0, "{styled} vs {styled_small}");

    let padded = margin_with(
        |axis| {
            axis.axis.static_tick_label_size = Some(10.0);
            axis.axis.static_label_size = Some(12.0);
            axis.axis.static_tick_padding = Some(16.0);
        },
        auto_flags(),
    );
    assert!(padded >= styled_small + 11.9, "{padded} vs {styled_small}");

    let labelled = margin_with(
        |axis| {
            axis.major_ticks = Some(vec![50.0]);
            axis.tick_labels = Some(vec!["1,000,000 units".to_owned()]);
        },
        0,
    );
    let advance = crate::scene::scene_text_advance("1,000,000 units", 12.0);
    assert!(labelled >= 8.0 + advance, "{labelled} vs {advance}");

    let titled = margin_with(|axis| axis.title = "Right axis".to_owned(), auto_flags());
    assert!(titled > base + 12.0, "{titled} vs {base}");

    // An authored right margin larger than the measured need is the floor.
    let mut facts = chrome_facts(
        auto_flags() | FLAG_AUTHORED_MARGINS,
        Some(&y2_axis(0.0, 100.0)),
    );
    for (at, value) in [(32, 10.0f64), (40, 150.0), (48, 10.0), (56, 40.0)] {
        facts[at..at + 8].copy_from_slice(&value.to_le_bytes());
    }
    let floored = right_margin(&encode(&[scatter(2, 50.0, true)], &facts));
    assert!((floored - 150.0).abs() < 1e-9, "{floored}");
}

#[test]
fn y2_paints_right_gutter_labels_with_equal_domain_tick_parity() {
    let mut axis = y2_axis(0.0, 1.0);
    axis.title = "Right".to_owned();
    axis.axis.static_text.title_rgba = Some([255, 0, 0, 255]);
    axis.axis.static_text.title_flags = 2;
    axis.axis.static_tick_label_size = Some(14.0);
    axis.axis.static_label_size = Some(16.0);
    axis.axis.static_tick_padding = Some(6.0);
    let scene = encode(
        &[scatter(1, 0.5, false), scatter(2, 0.5, true)],
        &chrome_facts(auto_flags(), Some(&axis)),
    );
    let document = SceneDocument::decode(&scene).unwrap();
    let svg = document.to_svg();
    let right = f64_at(&scene, 64);
    let left_labels = svg_texts(&svg, "end");
    let right_labels = svg_texts(&svg, "start");
    assert!(!right_labels.is_empty());
    // Equal domains share one resolved ladder, in SVG exactly as in the
    // browser painter below.
    let strip = |items: &[(f64, String)]| items.iter().map(|(_, t)| t.clone()).collect::<Vec<_>>();
    let primary_ladder: Vec<String> = strip(&left_labels)
        .into_iter()
        .filter(|t| !t.is_empty())
        .collect();
    assert_eq!(strip(&right_labels), primary_ladder);
    for (x, text) in &right_labels {
        assert!(
            *x > right,
            "label {text} at {x} must sit right of the spine {right}"
        );
        let advance = crate::scene::scene_text_advance(text, 14.0);
        assert!(*x + advance <= WIDTH, "label {text} overflows the canvas");
    }
    assert!(svg.contains("data-xy-chrome=\"y2-label\""));
    assert!(svg.contains("fill=\"rgba(255,0,0,1.000000)\""));
    // Raster/PDF consume the same document.
    let commands = document.to_raster_commands(1.0).unwrap();
    assert!(commands.windows(4).any(|w| w == b"Righ"));

    // XYPB v16+: the y2 axis block, its fixed text record and the y2 ticks.
    let painter = document.to_browser_painter(1 << 24).unwrap();
    assert_eq!(&painter[..4], b"XYPB");
    assert_eq!(u32_at(&painter, 4), crate::scene::BROWSER_PAINTER_VERSION);
    // XYPB v17 pins the resolved per-axis strategy at axis byte 5 (auto without collisions = preserve).
    assert_eq!(crate::scene::BROWSER_PAINTER_VERSION, 17);
    assert_eq!([painter[93], painter[181], painter[269]], [4; 3]);
    assert_eq!(u32_at(&painter, 12) as usize, BROWSER_PAINTER_HEADER_BYTES);
    let y2_block = &painter[264..352];
    assert!(y2_block.iter().any(|byte| *byte != 0));
    assert_eq!(y2_block[0], AxisSide::High as u8);
    assert_eq!(
        f32::from_le_bytes(painter[352..356].try_into().unwrap()),
        14.0
    );
    assert_eq!(
        f32::from_le_bytes(painter[356..360].try_into().unwrap()),
        16.0
    );
    assert_eq!(
        f32::from_le_bytes(painter[360..364].try_into().unwrap()),
        6.0
    );
    assert_eq!(u32_at(&painter, 364), 2 << 2);
    assert_eq!(&painter[372..376], &[255, 0, 0, 255]);
    assert_eq!(painter[376], 0b101);
    assert_eq!(painter[377..384], [0; 7]);
    let y2_ticks = u32_at(&painter, 412) as usize;
    assert!(y2_ticks > 0);
    let x_ticks = u32_at(&painter, 48) as usize;
    let y_ticks = u32_at(&painter, 52) as usize;
    assert_eq!(y_ticks, y2_ticks, "equal domains share one ladder");
    let tick_base = u32_at(&painter, 56) as usize;
    let tick_position = |index: usize| {
        f32::from_le_bytes(
            painter[tick_base + index * 16..tick_base + index * 16 + 4]
                .try_into()
                .unwrap(),
        )
    };
    for index in 0..y_ticks {
        assert_eq!(
            tick_position(x_ticks + index),
            tick_position(x_ticks + y_ticks + index)
        );
    }
    let traces = u32_at(&painter, 20) as usize;
    let axes: Vec<u8> = (0..traces)
        .map(|index| {
            painter[BROWSER_PAINTER_HEADER_BYTES + index * BROWSER_PAINTER_TRACE_BYTES + 3]
        })
        .collect();
    assert_eq!(
        axes.iter().filter(|axis| **axis == 1).count(),
        1,
        "{axes:?}"
    );
    assert_eq!(
        axes.iter().filter(|axis| **axis == 0).count(),
        1,
        "{axes:?}"
    );
}

#[test]
fn unstyled_primary_scene_keeps_a_zero_y2_painter_block() {
    let scene = encode(&[scatter(1, 0.5, false)], &chrome_facts(auto_flags(), None));
    let painter = SceneDocument::decode(&scene)
        .unwrap()
        .to_browser_painter(1 << 24)
        .unwrap();
    assert!(painter[264..384].iter().all(|byte| *byte == 0));
    assert_eq!(u32_at(&painter, 412), 0);
    assert_eq!(painter[BROWSER_PAINTER_HEADER_BYTES + 3], 0);
}

fn xyfs(axes: &[(u8, u8)], traces: &[u16]) -> Vec<u8> {
    let axes: Vec<_> = axes
        .iter()
        .map(|(axis_code, side)| FigureSupportAxisInput {
            axis_code: *axis_code,
            side: *side,
            keys: vec!["label".to_owned()],
        })
        .collect();
    let traces: Vec<_> = traces
        .iter()
        .map(|trace_flags| FigureSupportTraceInput {
            trace_flags: *trace_flags,
            kind: "scatter".to_owned(),
        })
        .collect();
    scene_figure_support_pack(0, &axes, &traces).unwrap()
}

#[test]
fn only_a_right_side_secondary_y_with_a_trace_is_admitted_with_stable_reasons() {
    let y2_trace = 1u16 << 13;
    let reason = |axes: &[(u8, u8)], traces: &[u16]| {
        scene_figure_support_reason(&xyfs(axes, traces)).unwrap()
    };
    assert_eq!(reason(&[(0, 0), (1, 0)], &[0]), "");
    assert_eq!(
        reason(&[(0, 0), (1, 0), (2, AXIS_SIDE_RIGHT)], &[0, y2_trace]),
        ""
    );
    // An unauthored (unobserved, code 0) y2 side is the default right side.
    assert_eq!(reason(&[(0, 0), (1, 0), (2, 0)], &[0, y2_trace]), "");
    assert!(
        reason(&[(0, 0), (1, 0), (2, AXIS_SIDE_LEFT)], &[0, y2_trace])
            .starts_with("XYG_SCENE_UNSUPPORTED_Y2_SIDE")
    );
    assert!(
        reason(&[(0, 0), (1, 0), (2, AXIS_SIDE_OTHER)], &[0, y2_trace])
            .starts_with("XYG_SCENE_UNSUPPORTED_Y2_SIDE")
    );
    assert!(reason(&[(0, 0), (1, 0), (3, AXIS_SIDE_RIGHT)], &[0])
        .starts_with("XYG_SCENE_UNSUPPORTED_X2"));
    assert!(reason(
        &[(0, 0), (1, 0), (2, AXIS_SIDE_RIGHT), (3, 0)],
        &[0, y2_trace]
    )
    .starts_with("XYG_SCENE_UNSUPPORTED_EXTRA_AXES"));
    assert!(reason(&[(0, 0), (1, 0), (2, AXIS_SIDE_RIGHT)], &[0])
        .starts_with("XYG_SCENE_UNSUPPORTED_Y2_TICK_ONLY"));
    // A y2 trace with no declared y2 axis is the existing non-primary reason.
    assert!(reason(&[(0, 0), (1, 0)], &[y2_trace]).contains("primary x/y axes"));
    // Unknown axis ids keep the original diagnostic.
    assert!(reason(&[(0, 0), (1, 0), (255, 0)], &[0]).contains("exactly x/y axes"));
}

#[test]
fn y2_with_polar_is_rejected_by_the_encoder() {
    // Rust refuses the combination even if a host forgets to.
    let mut axis = y2_axis(0.0, 100.0);
    axis.title = "t".to_owned();
    let facts = chrome_facts(auto_flags(), Some(&axis));
    let polar = [1u8; 8];
    assert!(encode_assembled_from_sidecars(
        &xyas(&[scatter(1, 5.0, true)]),
        &facts,
        &empty_xysd(),
        &polar,
        &[],
    )
    .is_err());
}

/// Rotation of the styled raster text command (17) that draws `text`.
fn raster_title_angle(commands: &[u8], text: &[u8]) -> f32 {
    let at = commands
        .windows(text.len())
        .position(|window| window == text)
        .expect("title text in the raster display list");
    // ... angle f32 | flags u8 | reserved u32 | rgba [4] | len u32 | text
    f32::from_le_bytes(commands[at - 17..at - 13].try_into().unwrap())
}

#[test]
fn y2_title_reads_bottom_to_top_like_the_y_title_in_svg_and_raster() {
    let mut axis = y2_axis(0.0, 100.0);
    axis.title = "Right".to_owned();
    axis.axis.static_text.title_flags = 2;
    let scene = encode(
        &[scatter(1, 0.5, false), scatter(2, 50.0, true)],
        &chrome_facts(auto_flags(), Some(&axis)),
    );
    let document = SceneDocument::decode(&scene).unwrap();
    let svg = document.to_svg();
    let title = svg
        .split("data-xy-chrome=\"y2-label\"")
        .nth(1)
        .expect("y2 title group");
    assert!(title.contains("transform=\"rotate(-90 "), "{title}");
    assert!(!svg.contains("rotate(90 "));
    let angle = raster_title_angle(&document.to_raster_commands(1.0).unwrap(), b"Right");
    assert_eq!(angle, -90.0);
    // The rotated ink stays inside the canvas: [x - ascent, x + depth].
    let x: f64 = title
        .split("x=\"")
        .nth(1)
        .unwrap()
        .split('"')
        .next()
        .unwrap()
        .parse()
        .unwrap();
    assert!(x > f64_at(&scene, 64) && x < WIDTH);
}

#[test]
fn non_finite_tick_angle_is_rejected_and_only_nan_means_absent() {
    let decode = |bytes: &[u8]| SceneY2Axis::decode(bytes, SceneY2Domain::Data, HEIGHT, 0.0);
    let mut axis = y2_axis(0.0, 100.0);
    let none = axis.encode(SceneY2Domain::Data);
    assert_eq!(decode(&none).unwrap().tick_angle, None);
    axis.tick_angle = Some(30.0);
    assert_eq!(
        decode(&axis.encode(SceneY2Domain::Data)).unwrap().tick_angle,
        Some(30.0)
    );
    for bad in [f64::INFINITY, f64::NEG_INFINITY] {
        axis.tick_angle = Some(bad);
        assert!(matches!(
            decode(&axis.encode(SceneY2Domain::Data)),
            Err(SceneError::NonFinite)
        ));
    }
}

#[test]
fn y2_block_rejects_non_right_axes_and_noncanonical_bytes() {
    let good = y2_axis(0.0, 100.0).encode(SceneY2Domain::Data);
    assert!(SceneY2Axis::decode(&good, SceneY2Domain::Data, HEIGHT, 0.0).is_ok());
    let decode = |bytes: &[u8]| SceneY2Axis::decode(bytes, SceneY2Domain::Data, HEIGHT, 0.0);
    // Left-side axis record.
    let mut left = good.clone();
    left[36] = AxisSide::Low as u8;
    assert!(decode(&left).is_err());
    // Nonzero reserved bytes and truncated/extended payloads.
    let mut reserved = good.clone();
    reserved[161] = 1;
    assert!(decode(&reserved).is_err());
    assert!(decode(&good[..SCENE_Y2_FIXED_BYTES - 1]).is_err());
    let mut extended = good.clone();
    extended.push(0);
    assert!(decode(&extended).is_err());
}

#[test]
fn formatted_y2_labels_are_measured_before_the_gutter_is_reserved() {
    // `.20f` turns 0, 20, ... 100 into 22-character labels. The gutter must be
    // sized from those, not from the short default labels, or they paint past
    // the canvas.
    let mut axis = y2_axis(0.0, 100.0);
    axis.format = ".20f".to_owned();
    axis.axis.static_tick_label_size = Some(12.0);
    axis.axis.static_label_size = Some(12.0);
    axis.axis.static_tick_padding = Some(4.0);
    let scene = encode(
        &[scatter(1, 0.5, false), scatter(2, 50.0, true)],
        &chrome_facts(auto_flags(), Some(&axis)),
    );
    let svg = SceneDocument::decode(&scene).unwrap().to_svg();
    let labels = svg_texts(&svg, "start");
    assert!(!labels.is_empty());
    assert!(
        labels.iter().all(|(_, text)| text.len() >= 20),
        "format must have been applied: {labels:?}"
    );
    for (x, text) in &labels {
        let advance = crate::scene::scene_text_advance(text, 12.0);
        assert!(
            *x + advance <= WIDTH,
            "formatted label {text} ends at {} past the {WIDTH}px canvas",
            x + advance
        );
    }
    let plain = right_margin(&twin_scene(&y2_axis(0.0, 100.0)));
    assert!(
        right_margin(&scene) > plain + 60.0,
        "{} vs {plain}",
        right_margin(&scene)
    );
}

#[test]
fn a_supported_colorbar_cannot_hide_from_the_y2_prohibition() {
    use crate::scene_figure_support_materialize::{
        scene_figure_support_materialize, FigureSupportAxisObs, FigureSupportTraceObs,
        SceneFigureSupportMaterializeIn,
    };
    let axes =
        [(0u8, 0u8), (1, 0), (2, AXIS_SIDE_RIGHT)].map(|(axis_code, side)| FigureSupportAxisObs {
            axis_code,
            side,
            keys: vec!["label".to_owned()],
            tick_label_strategy: None,
            collision: None,
        });
    let traces = [
        FigureSupportTraceObs {
            kind: "scatter",
            x_axis: "x",
            y_axis: "y",
            ..Default::default()
        },
        FigureSupportTraceObs {
            kind: "scatter",
            x_axis: "x",
            y_axis: "y2",
            ..Default::default()
        },
    ];
    let reason = |has_colorbar: i32| {
        let packed = scene_figure_support_materialize(&SceneFigureSupportMaterializeIn {
            polar: 0,
            // A *supported* colorbar: nothing is unsupported about it.
            colorbar_unsupported: 0,
            has_colorbar,
            has_custom_font: 0,
            has_browser_css: 0,
            has_extra_legends: 0,
            annotations: &[],
            axes: &axes,
            traces: &traces,
        })
        .unwrap();
        scene_figure_support_reason(&packed).unwrap()
    };
    assert_eq!(reason(0), "");
    assert!(reason(1).starts_with("XYG_SCENE_UNSUPPORTED_Y2_COLORBAR"));
}

/// A twin-axis Scene with one default straight-arrow run (annotation tag 5) in
/// its trailing annotation records, returned with the arrow's first record
/// offset. The arrow is pixel-space on the primary plane.
fn twin_scene_with_arrow() -> (Vec<u8>, usize) {
    let mut scene = twin_scene(&y2_axis(0.0, 100.0));
    let records = u64::from_le_bytes(scene[16..24].try_into().unwrap()) as usize;
    let at = record_at(records);
    let mut run = Vec::new();
    for (kind, point) in [
        (1u8, [60.0f64, 100.0]),
        (1, [192.0, 100.0]),
        (4, [200.0, 100.0]),
        (4, [192.0, 104.0]),
        (4, [192.0, 96.0]),
    ] {
        run.extend_from_slice(&[kind, 1, 0, 5]);
        run.extend_from_slice(&0u32.to_le_bytes());
        run.extend_from_slice(&0x5859_0500_0000_0001u64.to_le_bytes());
        for value in [point[0], point[1], 0.0, 0.0, 0.0] {
            run.extend_from_slice(&value.to_le_bytes());
        }
    }
    scene.splice(at..at, run);
    scene[16..24].copy_from_slice(&((records + 5) as u64).to_le_bytes());
    (scene, at)
}

#[test]
fn arrow_run_on_the_secondary_plane_is_rejected_by_both_validators_on_the_same_bytes() {
    let (scene, at) = twin_scene_with_arrow();
    // The unmodified arrow is accepted by both readers.
    validate_scene_batch(&scene).unwrap();
    SceneDocument::decode(&scene).unwrap();
    // Arrows are screen-space and primary-plane: a y2 selector on any record of
    // the run is rejected by the byte validator and the document decoder alike
    // (the byte validator once masked the bit and let the run through).
    for row in 0..5 {
        let mut tampered = scene.clone();
        tampered[at + row * SCENE_BATCH_RECORD_BYTES + 3] |= SCENE_RECORD_Y2_BIT;
        let validator = validate_scene_batch(&tampered);
        let decoder = SceneDocument::decode(&tampered);
        assert_eq!(validator.err(), Some(SceneError::Length), "row {row}");
        assert_eq!(decoder.err(), Some(SceneError::Length), "row {row}");
    }
}

/// XYPB v17: the effective layout mode lands at axis byte 5 (hide arrives as
/// preserve), hidden labels arrive blank, and the authored collision header
/// at bytes 76..80 is zeroed.
#[test]
fn painter_carries_the_resolved_tick_label_mode_and_blanks_hidden_labels() {
    let labels = |painter: &[u8]| -> Vec<String> {
        // Tick table: 16-byte records, then the shared string table.
        let (ticks, strings) = (u32_at(painter, 56) as usize, u32_at(painter, 60) as usize);
        let count = u32_at(painter, 48) as usize;
        let mut at = strings + (u32_at(painter, 384) + u32_at(painter, 388) + u32_at(painter, 392) + u32_at(painter, 396)) as usize;
        (0..count)
            .map(|index| {
                let length = u32_at(painter, ticks + index * 16 + 8) as usize;
                let text = String::from_utf8(painter[at..at + length].to_vec()).unwrap();
                at += length;
                text
            })
            .collect()
    };
    for (strategy, mode) in [(0u8, 4u8), (1, 4), (4, 4), (5, 5), (6, 6)] {
        let mut facts = chrome_facts(auto_flags(), None);
        facts[12] = strategy;
        let scene = encode(&[scatter(1, 0.5, false)], &facts);
        let painter = SceneDocument::decode(&scene).unwrap().to_browser_painter(1 << 24).unwrap();
        assert_eq!(painter[93], mode, "strategy {strategy}");
        assert_eq!(i16::from_le_bytes([painter[94], painter[95]]), 0);
        assert_eq!(painter[181], 4, "the untouched y axis keeps preserve");
        assert_eq!(painter[76..80], [0; 4], "collision header is Rust-internal");
        let shown = labels(&painter).iter().filter(|label| !label.is_empty()).count();
        assert_eq!(shown == 0, mode >= 5, "strategy {strategy}: {shown} labels");
    }
}
