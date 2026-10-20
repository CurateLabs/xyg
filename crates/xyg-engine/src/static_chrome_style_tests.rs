//! Framing, precedence and atomic-validation proofs for the XYCS projection.
use crate::static_chrome_style::{resolve_packed, ChromeStyleError};

#[derive(Clone, Copy)]
enum V<'a> {
    Null,
    Text(&'a str),
    Num(f64),
}

fn text(out: &mut Vec<u8>, value: &str) {
    out.extend_from_slice(&(value.len() as u32).to_le_bytes());
    out.extend_from_slice(value.as_bytes());
}

fn entries(out: &mut Vec<u8>, items: &[(&str, V)]) {
    out.extend_from_slice(&(items.len() as u32).to_le_bytes());
    for (key, value) in items {
        text(out, key);
        match value {
            V::Null => out.extend_from_slice(&0u32.to_le_bytes()),
            V::Text(value) => {
                out.extend_from_slice(&1u32.to_le_bytes());
                text(out, value);
            }
            V::Num(value) => {
                out.extend_from_slice(&2u32.to_le_bytes());
                out.extend_from_slice(&value.to_le_bytes());
            }
        }
    }
}

type Items<'a> = Vec<(&'a str, V<'a>)>;

struct Frame<'a> {
    title: bool,
    legend: bool,
    root: Items<'a>,
    slots: Vec<(&'a str, Items<'a>)>,
    x: (Items<'a>, Items<'a>),
    y: (Items<'a>, Items<'a>),
}

fn frame<'a>() -> Frame<'a> {
    Frame {
        title: true,
        legend: false,
        root: vec![],
        slots: vec![],
        x: (vec![], vec![]),
        y: (vec![], vec![]),
    }
}

impl Frame<'_> {
    fn pack(&self) -> Vec<u8> {
        let mut out = b"XYCS".to_vec();
        out.extend_from_slice(&1u32.to_le_bytes());
        out.extend_from_slice(&(u32::from(self.title) | u32::from(self.legend) << 1).to_le_bytes());
        out.extend_from_slice(&0u32.to_le_bytes());
        entries(&mut out, &self.root);
        out.extend_from_slice(&(self.slots.len() as u32).to_le_bytes());
        for (name, items) in &self.slots {
            text(&mut out, name);
            entries(&mut out, items);
        }
        for (style, minor) in [&self.x, &self.y] {
            entries(&mut out, style);
            entries(&mut out, minor);
        }
        out
    }
}

struct Resolved {
    chrome_text: u32,
    paints: [[u8; 4]; 4],
    title_size: f64,
    title_rgba: [u8; 4],
    metrics: [f64; 6],
    removed: Vec<Vec<String>>,
}

fn parse(bytes: &[u8]) -> Resolved {
    assert_eq!(&bytes[..4], b"XYCO");
    let u32_at = |at: usize| u32::from_le_bytes(bytes[at..at + 4].try_into().unwrap());
    let f64_at = |at: usize| f64::from_le_bytes(bytes[at..at + 8].try_into().unwrap());
    let mut paints = [[0u8; 4]; 4];
    for (index, paint) in paints.iter_mut().enumerate() {
        paint.copy_from_slice(&bytes[16 + 4 * index..20 + 4 * index]);
    }
    let mut metrics = [0.0; 6];
    for (index, metric) in metrics.iter_mut().enumerate() {
        *metric = f64_at(44 + 8 * index);
    }
    let mut at = 92;
    let mut removed = Vec::new();
    for _ in 0..4 {
        let count = u32_at(at) as usize;
        at += 4;
        let mut keys = Vec::new();
        for _ in 0..count {
            let n = u32_at(at) as usize;
            keys.push(String::from_utf8(bytes[at + 4..at + 4 + n].to_vec()).unwrap());
            at += 4 + n;
        }
        removed.push(keys);
    }
    assert_eq!(at, bytes.len());
    Resolved {
        chrome_text: u32_at(12),
        paints,
        title_size: f64_at(32),
        title_rgba: bytes[40..44].try_into().unwrap(),
        metrics,
        removed,
    }
}

fn resolve(frame: &Frame) -> Resolved {
    parse(&resolve_packed(&frame.pack()).unwrap())
}

#[test]
fn legacy_defaults_carry_no_text_facts() {
    let resolved = resolve(&frame());
    assert_eq!(resolved.chrome_text, 0);
    assert_eq!(resolved.paints, [[0; 4]; 4]);
    assert_eq!(resolved.title_size, 14.0);
    assert_eq!(resolved.title_rgba, [0x26, 0x26, 0x26, 255]);
    assert_eq!(resolved.metrics, [12.0, 12.0, 4.0, 12.0, 12.0, 4.0]);
    assert!(resolved.removed.iter().all(Vec::is_empty));
}

#[test]
fn slot_sizes_reach_both_axes() {
    let mut f = frame();
    f.slots = vec![
        ("tick_label", vec![("font-size", V::Text("30px"))]),
        ("axis_title", vec![("font-size", V::Text("17px"))]),
        ("title", vec![("font-size", V::Text("21px"))]),
    ];
    let resolved = resolve(&f);
    assert_eq!(resolved.metrics, [30.0, 17.0, 4.0, 30.0, 17.0, 4.0]);
    assert_eq!(resolved.title_size, 21.0);
}

#[test]
fn precedence_axis_then_slot_then_root_then_default() {
    let mut f = frame();
    f.root = vec![("--chart-text", V::Text("#0000ff"))];
    f.slots = vec![
        (
            "tick_label",
            vec![
                ("font-size", V::Text("30px")),
                ("color", V::Text("#00ff00")),
            ],
        ),
        ("axis_title", vec![("color", V::Text("#ff00ff"))]),
    ];
    // x: authored axis facts win; y: slot facts, then root.
    f.x.0 = vec![
        ("tick_label_size", V::Num(9.0)),
        ("label_color", V::Text("#ff0000")),
        ("tick_label_color", V::Text("#010203")),
    ];
    let resolved = resolve(&f);
    assert_eq!(resolved.metrics[0], 9.0);
    assert_eq!(resolved.metrics[3], 30.0);
    // paints: x tick, y tick, x title, y title
    assert_eq!(resolved.paints[0], [1, 2, 3, 255]);
    assert_eq!(resolved.paints[1], [0, 255, 0, 255]);
    assert_eq!(resolved.paints[2], [255, 0, 0, 255]);
    assert_eq!(resolved.paints[3], [255, 0, 255, 255]);
    assert_eq!(resolved.chrome_text >> 10, 0b1111);
    // root-only paint reaches title and axis text when nothing else is set.
    let mut root_only = frame();
    root_only.root = vec![("--chart-text", V::Text("#0000ff"))];
    let resolved = resolve(&root_only);
    assert_eq!(resolved.title_rgba, [0, 0, 255, 255]);
    assert_eq!(resolved.paints, [[0, 0, 255, 255]; 4]);
}

#[test]
fn absent_null_and_empty_facts_fall_through() {
    let mut f = frame();
    f.root = vec![("--chart-text", V::Text(""))];
    f.slots = vec![(
        "tick_label",
        vec![
            ("font-size", V::Text("")),
            ("color", V::Null),
            ("font-weight", V::Text("")),
            ("font-style", V::Null),
        ],
    )];
    f.x.0 = vec![("tick_label_size", V::Null), ("tick_size", V::Text(""))];
    let resolved = resolve(&f);
    assert_eq!(resolved.chrome_text, 0);
    assert_eq!(resolved.metrics, [12.0, 12.0, 4.0, 12.0, 12.0, 4.0]);
    assert_eq!(resolved.removed[0], ["tick_label_size", "tick_size"]);
}

#[test]
fn tick_size_alias_and_removed_keys() {
    let mut f = frame();
    f.x.0 = vec![("tick_size", V::Num(8.0)), ("tick_padding", V::Num(6.0))];
    f.y.1 = vec![("label_size", V::Num(3.0)), ("grid_color", V::Text("red"))];
    let resolved = resolve(&f);
    assert_eq!(resolved.metrics[0], 8.0);
    assert_eq!(resolved.metrics[2], 6.0);
    assert_eq!(resolved.removed[0], ["tick_size", "tick_padding"]);
    assert_eq!(resolved.removed[3], ["label_size"]);
}

#[test]
fn weight_and_style_pack_per_slot() {
    let mut f = frame();
    f.slots = vec![
        ("title", vec![("font-weight", V::Text("bold"))]),
        (
            "axis_title",
            vec![
                ("font-style", V::Text("italic")),
                ("font-weight", V::Num(700.0)),
            ],
        ),
        ("tick_label", vec![("font-weight", V::Text("400"))]),
    ];
    let bits = resolve(&f).chrome_text;
    assert_eq!(bits & 3, 2); // title bold
    assert_eq!((bits >> 2) & 3, 3); // x title bold italic
    assert_eq!((bits >> 4) & 3, 3); // y title bold italic
    assert_eq!((bits >> 6) & 0xf, 0); // tick labels normal
                                      // flags of an absent title are not emitted.
    f.title = false;
    assert_eq!(resolve(&f).chrome_text & 3, 0);
}

fn reason(frame: &Frame) -> ChromeStyleError {
    resolve_packed(&frame.pack()).unwrap_err()
}

#[test]
fn malformed_style_fails_with_stable_reasons() {
    let slot = |name: &'static str, key: &'static str, value: V<'static>| {
        let mut f = frame();
        f.slots = vec![(name, vec![(key, value)])];
        reason(&f)
    };
    assert_eq!(
        slot("tick_label", "font-size", V::Text("1.5em")),
        ChromeStyleError::FontSize
    );
    assert_eq!(
        slot("tick_label", "font-size", V::Num(12.0)),
        ChromeStyleError::FontSize
    );
    assert_eq!(
        slot("tick_label", "font-size", V::Text("0px")),
        ChromeStyleError::FontSize
    );
    assert_eq!(
        slot("title", "color", V::Text("var(--x)")),
        ChromeStyleError::Color
    );
    assert_eq!(
        slot("title", "color", V::Text("currentColor")),
        ChromeStyleError::Color
    );
    assert_eq!(
        slot("title", "font-weight", V::Text("600")),
        ChromeStyleError::FontWeight
    );
    assert_eq!(
        slot("title", "font-style", V::Text("oblique")),
        ChromeStyleError::FontStyle
    );
    assert_eq!(
        slot("title", "font-family", V::Text("Comic Sans")),
        ChromeStyleError::CustomFont
    );
    assert_eq!(
        slot("title", "text-shadow", V::Text("1px")),
        ChromeStyleError::Slot
    );
    assert_eq!(
        slot("legend", "fontSize", V::Text("12px")),
        ChromeStyleError::Slot
    );
    assert_eq!(
        ChromeStyleError::FontSize.reason(),
        "XYG_STATIC_UNSUPPORTED_CHROME_FONT_SIZE"
    );
}

#[test]
fn malformed_root_and_axis_facts_fail() {
    let mut f = frame();
    f.root = vec![("--chart-text", V::Text("not-a-color"))];
    assert_eq!(reason(&f), ChromeStyleError::Color);
    let mut f = frame();
    f.root = vec![("box-shadow", V::Text("none"))];
    assert_eq!(reason(&f), ChromeStyleError::BrowserCss);
    let mut f = frame();
    f.root = vec![("font-family", V::Text("Papyrus"))];
    assert_eq!(reason(&f), ChromeStyleError::CustomFont);
    let mut f = frame();
    f.x.0 = vec![("label_size", V::Text("wide"))];
    assert_eq!(reason(&f), ChromeStyleError::AxisStyle);
    let mut f = frame();
    f.y.0 = vec![("tick_padding", V::Num(f64::NAN))];
    assert_eq!(reason(&f), ChromeStyleError::AxisStyle);
    let mut f = frame();
    f.y.0 = vec![("label_color", V::Num(3.0))];
    assert_eq!(reason(&f), ChromeStyleError::Color);
}

#[test]
fn legend_slot_is_admitted_only_when_the_host_owns_legend_styling() {
    let mut f = frame();
    f.slots = vec![("legend", vec![("fontSize", V::Text("9px"))])];
    assert_eq!(reason(&f), ChromeStyleError::Slot);
    f.legend = true;
    assert_eq!(resolve(&f).chrome_text, 0);
    f.slots = vec![("legend", vec![("font-size", V::Text("9px"))])];
    assert_eq!(reason(&f), ChromeStyleError::Slot);
}

#[test]
fn one_bad_slot_rejects_the_whole_frame() {
    let mut f = frame();
    f.slots = vec![
        ("title", vec![("font-size", V::Text("20px"))]),
        ("tick_label", vec![("font-weight", V::Text("heavy"))]),
    ];
    assert_eq!(reason(&f), ChromeStyleError::FontWeight);
}

#[test]
fn framing_is_bounded_and_exact() {
    let bytes = frame().pack();
    for cut in [0, 3, 8, bytes.len() - 1] {
        assert!(resolve_packed(&bytes[..cut]).is_err());
    }
    let mut trailing = bytes.clone();
    trailing.push(0);
    assert_eq!(resolve_packed(&trailing), Err(ChromeStyleError::Header));
    let mut bad = bytes.clone();
    bad[..4].copy_from_slice(b"NOPE");
    assert_eq!(resolve_packed(&bad), Err(ChromeStyleError::Header));
    let mut bad = bytes.clone();
    bad[4] = 2;
    assert_eq!(resolve_packed(&bad), Err(ChromeStyleError::Version));
    let mut bad = bytes.clone();
    bad[8] = 4;
    assert_eq!(resolve_packed(&bad), Err(ChromeStyleError::Flags));
    assert_eq!(
        resolve_packed(&vec![0; 300 * 1024]),
        Err(ChromeStyleError::Limit)
    );
    let mut dup = frame();
    dup.slots = vec![("title", vec![]), ("title", vec![])];
    assert_eq!(reason(&dup), ChromeStyleError::Flags);
    let mut dup = frame();
    dup.root = vec![("font-size", V::Null), ("font-size", V::Null)];
    assert_eq!(reason(&dup), ChromeStyleError::Flags);
    let mut huge = frame();
    huge.root = vec![("--chart-text", V::Null); 65];
    assert_eq!(reason(&huge), ChromeStyleError::Limit);
}
