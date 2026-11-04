//! R2 projection reuse: frozen R1 byte oracle and combined-prefix/suffix proof.
//! The reference below is copied verbatim from the fa6d5e R1 candidate, with only
//! its name and formatting changed. It is test-only and never linked into production artifacts.
use super::*;
use crate::graphforge::compose::COMPOSITION_VERSION;
use crate::graphforge::container::DOCUMENT_MAGIC;

fn r1_projection(
    b: &mut Builder,
    s: &GraphSession,
    state: &GraphInteractionState,
    bytes: &[u8],
    pick: Option<&PickReceipt>,
) -> Result<()> {
    let doc = gf(ComposedDocument::decode(bytes))?;
    let mut refs = transport(s, &s.identity.refs_of(state.selection()))?;
    // The temporal owner may retain derived keys belonging to another
    // composition. refs_of deliberately omits those without mutating the owner.
    if refs.len() > MAX_GRAPH_SELECTION_REFS {
        return bad();
    }
    refs.sort_by(super::coordination::compare);
    let work = doc
        .projection_work(refs.len() + usize::from(pick.is_some_and(|p| p.source.is_some())))
        .ok_or(InteractionStatus::Budget)?;
    if work as u64 > MAX_GRAPH_INTERACTION_WORK {
        return Err(InteractionStatus::Budget);
    }
    let resolved = refs
        .iter()
        .map(|r| {
            s.identity
                .resolve(r)
                .map_err(|_| InteractionStatus::Invalid)
        })
        .collect::<Result<Vec<_>>>()?;
    let planes = gf(doc.projection_layers(s.identity.node_count(), s.identity.edge_count()))?;
    let row = |index: ElementIndex, layer: usize| -> Option<u64> {
        let (plane, i) = match index {
            ElementIndex::Node(i) => (planes[layer].node_rows?, i),
            ElementIndex::Edge(i) => (planes[layer].edge_rows?, i),
        };
        let value = u64_at(plane, i * 8);
        (value != u64::MAX).then_some(value)
    };
    // Count the actual sparse output before allocating it. Reservation above
    // includes builder/final/retry copies (existing cache charge is 3x bytes).
    let count = resolved
        .iter()
        .try_fold(0usize, |sum, &index| {
            sum.checked_add(
                (0..planes.len())
                    .filter(|&layer| row(index, layer).is_some())
                    .count(),
            )
        })
        .ok_or(InteractionStatus::Budget)?;
    let mut indices = Vec::with_capacity(refs.len());
    let mut offsets = Vec::with_capacity(refs.len() + 1);
    let mut layers = Vec::with_capacity(count);
    let mut rows = Vec::with_capacity(count);
    offsets.push(0);
    for index in resolved {
        indices.push(match index {
            ElementIndex::Node(i) | ElementIndex::Edge(i) => i as u64,
        });
        for layer in 0..planes.len() {
            if let Some(value) = row(index, layer) {
                layers.push(layer as u32);
                rows.push(value);
            }
        }
        offsets.push(rows.len() as u64);
    }
    let texts = planes
        .iter()
        .map(|layer| layer.result_id.unwrap_or(""))
        .collect::<Vec<_>>();
    let valid = planes
        .iter()
        .map(|layer| u8::from(layer.result_id.is_some()))
        .collect::<Vec<_>>();
    b.bytes("selection.refs.bytes", 0, &encode_refs(&refs)?);
    b.u64s("selection.indices.u64", 0, &indices);
    b.u64s("selection.layer_offsets.u64", 0, &offsets);
    b.u32s("selection.layers.u32", 0, &layers);
    b.u64s("selection.rows.u64", 0, &rows);
    b.texts("selection.result_ids.texts", 0, &texts);
    b.u8s("selection.result_ids.valid.u8", 0, &valid);
    if let Some(pick) = pick {
        let (kind, render_index) = match pick.target {
            None => (0, 0),
            Some(PickTarget::Node(i)) => (1, i as u64),
            Some(PickTarget::Edge(i)) => (2, i as u64),
        };
        let form = if kind == 0 {
            0
        } else if pick.source.is_some() {
            1
        } else {
            2
        };
        let mut pick_layers = Vec::new();
        let mut pick_rows = Vec::new();
        let mut pick_refs = Vec::new();
        let mut source_index = 0;
        if let Some((index, reference)) = &pick.source {
            // Work was admitted with the selection projection before borrowing
            // planes. Count sparse mappings before allocating output tables.
            let count = (0..planes.len())
                .filter(|&layer| row(*index, layer).is_some())
                .count();
            pick_layers.reserve(count);
            pick_rows.reserve(count);
            for layer in 0..planes.len() {
                if let Some(value) = row(*index, layer) {
                    pick_layers.push(layer as u32);
                    pick_rows.push(value);
                }
            }
            source_index = match index {
                ElementIndex::Node(i) | ElementIndex::Edge(i) => *i as u64,
            };
            pick_refs.push(reference.clone());
        }
        b.u32s(
            "pick.header.u32",
            0,
            &[
                1,
                pick.operation,
                pick.action,
                pick.header.stamp.render_revision,
                kind,
                form,
                0,
                0,
            ],
        );
        b.u64s(
            "pick.query.u64",
            0,
            &[
                pick.header.stamp.instance_id,
                pick.header.op_seq,
                render_index,
                pick.member_count,
                source_index,
            ],
        );
        b.bytes("pick.ref.bytes", 0, &encode_refs(&pick_refs)?);
        b.u32s("pick.layers.u32", 0, &pick_layers);
        b.u64s("pick.rows.u64", 0, &pick_rows);
    }
    Ok(())
}

fn uuid(i: usize) -> Uuid {
    let mut id = [0; 16];
    id[..8].copy_from_slice(&(i as u64 + 1).to_le_bytes());
    id
}

fn document(nodes: usize, layers: usize, rows: bool, poison: bool) -> Vec<u8> {
    let mut b = Builder::new(DOCUMENT_MAGIC);
    b.u32s("status", 0, &[0]);
    b.utf8("kind", 0, "graph");
    b.u32s("composition.version", 0, &[COMPOSITION_VERSION]);
    b.uuids("node.uuid", 0, &(0..nodes).map(uuid).collect::<Vec<_>>());
    let edges = if nodes == 3 { 3 } else { 0 };
    b.uuids("edge.uuid", 0, &vec![[0; 16]; edges]);
    b.u8s("edge.derived", 0, &vec![1; edges]);
    b.u32s("edge.layer", 0, &(0..edges as u32).collect::<Vec<_>>());
    b.i64s("edge.order", 0, &vec![0; edges]);
    b.u64s("edge.path", 0, &vec![0; edges]);
    b.u64s("edge.source", 0, &(0..edges as u64).collect::<Vec<_>>());
    b.u64s(
        "edge.target",
        0,
        &(0..edges as u64).map(|i| (i + 1) % 3).collect::<Vec<_>>(),
    );
    for layer in 0..layers {
        b.utf8("layer.schema", layer, "test");
        match layer {
            0 => {}
            1 => b.utf8("layer.result_id", layer, ""),
            _ => b.utf8("layer.result_id", layer, " λ 空 🦀 "),
        }
        if rows {
            b.u64s(
                "layer.node_rows",
                layer,
                &(0..nodes)
                    .map(|i| {
                        if (i + layer) % 3 == 1 {
                            u64::MAX
                        } else {
                            (1 << 62) + (i * 3 + layer) as u64
                        }
                    })
                    .collect::<Vec<_>>(),
            );
        }
        if edges > 0 {
            let mut values = vec![u64::MAX; edges];
            if layer < edges {
                values[layer] = (1 << 60) + layer as u64;
            }
            b.u64s("layer.edge_rows", layer, &values);
        }
    }
    if poison {
        b.u32s("layer.node_rows", 0, &[123]);
    }
    b.finish()
}

fn session(doc: &[u8], nodes: usize) -> GraphSession {
    GraphSession::create(
        doc,
        SessionLoad {
            x: Some((0..nodes).map(|i| i as f64 * 30.).collect()),
            y: Some(vec![0.; nodes]),
            ..Default::default()
        },
        7,
    )
    .unwrap()
}

fn selected(nodes: usize) -> GraphInteractionState {
    let mut state = GraphInteractionState::default();
    let set = ElementSet {
        nodes: (0..nodes).map(uuid).collect(),
        ..Default::default()
    };
    state.select(SelectMode::Replace, &set).unwrap();
    state
}

fn receipt(
    s: &GraphSession,
    source: Option<ElementIndex>,
    target: Option<PickTarget>,
    action: u32,
) -> PickReceipt {
    PickReceipt {
        header: OpHeader {
            stamp: Stamp {
                instance_id: 7,
                render_revision: 42,
            },
            op_seq: 123,
        },
        operation: 0,
        action,
        target,
        member_count: u64::from(target.is_some()),
        source: source.map(|i| {
            let r = match i {
                ElementIndex::Node(i) => s.identity.node_ref(i),
                ElementIndex::Edge(i) => s.identity.edge_ref(i),
            };
            (i, s.identity.to_transport(&r).unwrap())
        }),
    }
}

fn projected(
    s: &GraphSession,
    state: &GraphInteractionState,
    doc: &[u8],
    pick: Option<&PickReceipt>,
    r1: bool,
) -> Result<Vec<u8>> {
    let mut builder = Builder::new(RESULT_MAGIC);
    if r1 {
        r1_projection(&mut builder, s, state, doc, pick)?;
    } else {
        selection_projection(&mut builder, s, state, doc, pick)?;
    }
    Ok(builder.finish())
}

#[test]
fn r2_projection_matches_frozen_r1_bytes_for_empty_duplicate_miss_group_and_exact_ids() {
    let doc = document(3, 3, true, false);
    let s = session(&doc, 3);
    let picks = [
        None,
        Some(receipt(&s, None, None, 0)),
        Some(receipt(&s, None, None, 1)),
        Some(receipt(&s, None, Some(PickTarget::Node(0)), 0)),
        Some(receipt(&s, None, Some(PickTarget::Edge(0)), 0)),
        Some(receipt(
            &s,
            Some(ElementIndex::Node(0)),
            Some(PickTarget::Node(0)),
            0,
        )),
        Some(receipt(
            &s,
            Some(ElementIndex::Node(2)),
            Some(PickTarget::Node(2)),
            0,
        )),
        Some(receipt(
            &s,
            Some(ElementIndex::Edge(0)),
            Some(PickTarget::Edge(0)),
            0,
        )),
        Some(receipt(
            &s,
            Some(ElementIndex::Edge(1)),
            Some(PickTarget::Edge(1)),
            0,
        )),
        Some(receipt(
            &s,
            Some(ElementIndex::Edge(2)),
            Some(PickTarget::Edge(2)),
            0,
        )),
    ];
    for count in [0, 1, 3] {
        let state = selected(count);
        let without = projected(&s, &state, &doc, None, false).unwrap();
        let prefix = Container::decode(&without, RESULT_MAGIC).unwrap();
        for pick in &picks {
            let actual = projected(&s, &state, &doc, pick.as_ref(), false).unwrap();
            assert_eq!(
                actual,
                projected(&s, &state, &doc, pick.as_ref(), true).unwrap(),
                "selected={count} pick={pick:?}"
            );
            let c = Container::decode(&actual, RESULT_MAGIC).unwrap();
            for (name, index, section) in &prefix.sections {
                let emitted = c.get(name, *index).unwrap();
                assert_eq!(
                    (emitted.dtype, emitted.count, emitted.payload),
                    (section.dtype, section.count, section.payload)
                );
            }
            if let Some(pick) = pick {
                let expected = pick
                    .source
                    .as_ref()
                    .map(|(_, r)| std::slice::from_ref(r))
                    .unwrap_or(&[]);
                assert_eq!(
                    decode_refs(c.get("pick.ref.bytes", 0).unwrap().payload).unwrap(),
                    expected
                );
            }
        }
    }
}

#[test]
fn r2_full_selection_plus_duplicate_query_source_is_not_a_selection_cap_increase() {
    let n = MAX_GRAPH_SELECTION_REFS;
    let doc = document(n, 3, true, false);
    let s = session(&doc, n);
    let state = selected(n);
    let pick = receipt(
        &s,
        Some(ElementIndex::Node(0)),
        Some(PickTarget::Node(0)),
        0,
    );
    let actual = projected(&s, &state, &doc, Some(&pick), false).unwrap();
    assert_eq!(
        actual,
        projected(&s, &state, &doc, Some(&pick), true).unwrap()
    );
    let c = Container::decode(&actual, RESULT_MAGIC).unwrap();
    assert_eq!(
        decode_refs(c.get("selection.refs.bytes", 0).unwrap().payload)
            .unwrap()
            .len(),
        n
    );
    assert_eq!(c.get("selection.indices.u64", 0).unwrap().count, n);
    assert_eq!(
        c.get("selection.layer_offsets.u64", 0).unwrap().count,
        n + 1
    );
    assert_eq!(
        c.get("pick.layers.u32", 0)
            .unwrap()
            .as_u32("layers")
            .unwrap(),
        [0, 2]
    );
    assert_eq!(
        c.get("pick.rows.u64", 0).unwrap().as_u64("rows").unwrap(),
        [1 << 62, (1 << 62) + 2]
    );
    assert_eq!(state.selection().len(), MAX_GRAPH_SELECTION_REFS);
    let overflow = ElementSet {
        nodes: [uuid(n)].into(),
        ..Default::default()
    };
    let mut state = state;
    assert!(state.select(SelectMode::Add, &overflow).is_err());
    assert_eq!(state.selection().len(), MAX_GRAPH_SELECTION_REFS);
}

#[test]
fn r2_combined_work_admission_precedes_projection_descriptors_and_output_allocation() {
    let n = MAX_GRAPH_SELECTION_REFS;
    let doc = document(n, 200, false, false);
    let s = session(&doc, n);
    let state = selected(n - 2);
    let pick = receipt(
        &s,
        Some(ElementIndex::Node(0)),
        Some(PickTarget::Node(0)),
        0,
    );
    let reader = ComposedDocument::decode(&doc).unwrap();
    assert!(reader.projection_work(n - 2).unwrap() as u64 <= MAX_GRAPH_INTERACTION_WORK);
    assert!(reader.projection_work(n - 1).unwrap() as u64 > MAX_GRAPH_INTERACTION_WORK);
    assert!(projected(&s, &state, &doc, None, false).is_ok());
    assert_eq!(
        projected(&s, &state, &doc, Some(&pick), false),
        Err(InteractionStatus::Budget)
    );
    // A malformed borrowed plane would fail Invalid when descriptors are read.
    // Combined work must refuse Budget first, before allocating/reading them or
    // emitting any projection output. No counting allocator or runtime hook.
    let poison = document(n, 200, false, true);
    assert_eq!(
        projected(&s, &state, &poison, None, false),
        Err(InteractionStatus::Invalid)
    );
    let mut b = Builder::new(RESULT_MAGIC);
    let empty = Builder::new(RESULT_MAGIC).finish();
    assert_eq!(
        selection_projection(&mut b, &s, &state, &poison, Some(&pick)),
        Err(InteractionStatus::Budget)
    );
    assert_eq!(b.finish(), empty);
    assert_eq!(state.selection().len(), n - 2);
}
