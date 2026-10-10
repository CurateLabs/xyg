//! Complete local Scope credit through actual hierarchy byte commands.
use super::*;
use crate::geo_scale_protocol::{Entry, hierarchy, registry};
use crate::geo_source_session::GeoProcessorLease;

fn issue(sc: u64, revision: u64, nonce: u64, ids: &[u64]) -> (u64, usize) {
    let mut p = vec![0; 24];
    p64(&mut p, 0, revision);
    p[8..12].copy_from_slice(&[0, 255, 0, 255]);
    p64(&mut p, 16, ids.len() as u64);
    for id in ids {
        p.extend(id.to_le_bytes());
    }
    let wire = with_budget(request(33, sc, nonce, &p));
    (u64_at(&execute(&wire).unwrap(), 16), wire.len() + 128)
}
fn remaining_query(q: u64) -> usize {
    let r = registry().lock().unwrap();
    hierarchy::data_budget(
        &r.entries.iter().find(|(id, _)| *id == q).unwrap().1,
        128 << 20,
    )
    .unwrap()
}
fn assert_live_state(st: u64) {
    let r = registry().lock().unwrap();
    assert!(matches!(
        r.entries.iter().find(|(id, _)| *id == st).unwrap().1,
        Entry::State(_)
    ));
}

#[test]
fn hierarchy_scope_receipt_delta_and_same_arc_not_double_charged() {
    let _serial = test_processor_lock();
    let baseline = GeoProcessorLease::live_bytes();
    let chunks = vec![chunk(u64::MAX, -5, 0.)];
    let (index, sc, m, mut store, _) = selected_index(&chunks, &[u64::MAX]);
    let (st, receipt) = issue(sc, 2, 1, &[u64::MAX]);
    let q = u64_at(&execute(&selected_query(43, index, 3, &m, st)).unwrap(), 16);
    drive_hierarchy(q, 3, &chunks, &mut store);
    let same_arc = remaining_query(q);
    // Equal contents allocate a distinct State Arc; current admission stays original.
    let (equal, _) = issue(sc, 2, 0, &[u64::MAX]);
    assert_eq!(remaining_query(q), same_arc);
    close(equal, 0);
    let ids: Vec<_> = (0..10000).collect();
    let (newer, _) = issue(sc, 3, 0, &ids);
    let before_receipt = remaining_query(q);
    close(newer, 0); // admission retains the newer intent independently.
    let (newer, new_receipt) = issue(sc, 3, 2, &ids);
    assert_eq!(before_receipt - remaining_query(q), new_receipt - receipt);
    let old = selected_data(q, 3);
    let packet = read_data(&request(23, old, 0, &[]), 128 << 20).unwrap();
    assert_eq!(u64_at(footer(&packet), 24), 1);
    assert_eq!(u64_at(footer(&packet), 128), u64::MAX);
    drop(packet);
    close(newer, 0);
    close(index, 2);
    close(old, 0);
    close(sc, 0);
    assert_eq!(GeoProcessorLease::live_bytes(), baseline);
}

fn try_boundary(limit: usize, publication: bool, with_receipt: bool) -> bool {
    let before = GeoProcessorLease::live_bytes();
    let chunks = vec![chunk(u64::MAX, -5, 0.)];
    let (index, sc, m, mut store, _) = selected_index(&chunks, &[u64::MAX]);
    let st = state(sc, &[u64::MAX]);
    let q = u64_at(&execute(&selected_query(43, index, 3, &m, st)).unwrap(), 16);
    drive_hierarchy(q, 3, &chunks, &mut store);
    let old = selected_data(q, 3);
    let (st, _) = issue(sc, 2, if with_receipt { 1 } else { 0 }, &[u64::MAX]);
    let mut begin = selected_query(43, index, 4, &m, st);
    p64(
        &mut begin,
        32,
        if publication { 128 << 20 } else { limit as u64 },
    );
    let held = GeoProcessorLease::live_bytes();
    let accepted = match execute(&begin) {
        Ok(_) => {
            drive_hierarchy(st, 4, &chunks, &mut store);
            if publication {
                let ids: Vec<_> = (0..10000).collect();
                let (newer, _) = issue(sc, 3, if with_receipt { 2 } else { 0 }, &ids);
                let mut data = scene_request(st, 4);
                p32(&mut data, 8, 44);
                p64(&mut data, 32, limit as u64);
                let held = GeoProcessorLease::live_bytes();
                let accepted = match execute(&data) {
                    Ok(_) => true,
                    Err(SourceError::ResourceLimit) => {
                        assert_eq!(GeoProcessorLease::live_bytes(), held);
                        assert_eq!(u32_at(&step(st, 4), 8), 19);
                        false
                    }
                    other => panic!("unexpected {other:?}"),
                };
                close(st, if accepted { 0 } else { 4 });
                close(newer, 0);
                accepted
            } else {
                close(st, 4);
                true
            }
        }
        Err(SourceError::ResourceLimit) => {
            assert_eq!(GeoProcessorLease::live_bytes(), held);
            assert_live_state(st);
            // Failed admission did not advance lane history or consume State.
            p64(&mut begin, 32, 128 << 20);
            execute(&begin).unwrap();
            close(st, 4);
            false
        }
        other => panic!("unexpected {other:?}"),
    };
    let old_packet = read_data(&request(23, old, 0, &[]), 128 << 20).unwrap();
    assert_eq!(u64_at(&old_packet, 16), old);
    drop(old_packet);
    close(old, 0);
    close(index, 2);
    close(sc, 0);
    assert_eq!(GeoProcessorLease::live_bytes(), before);
    accepted
}
fn boundary(publication: bool, receipt: bool) -> usize {
    let mut low = 4096;
    let mut high = 128 << 20;
    while low + 1 < high {
        let mid = (low + high) / 2;
        if try_boundary(mid, publication, receipt) {
            high = mid;
        } else {
            low = mid;
        }
    }
    assert!(try_boundary(high, publication, receipt));
    assert!(!try_boundary(high - 1, publication, receipt));
    high
}
#[test]
fn hierarchy_43_exact_local_boundary_receipt_and_failure_atomicity() {
    let _serial = test_processor_lock();
    let legacy = boundary(false, false);
    let nonce = boundary(false, true);
    assert_eq!(nonce - legacy, 256 + 24 + 8 + 128);
}
#[test]
fn hierarchy_44_newer_intent_receipt_boundary_and_old_data_survives() {
    let _serial = test_processor_lock();
    let legacy = boundary(true, false);
    let nonce = boundary(true, true);
    assert_eq!(nonce - legacy, 256 + 24 + 10000 * 8 + 128);
}
