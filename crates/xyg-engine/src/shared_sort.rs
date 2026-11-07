//! One stable-sort body per record type in the size-bounded browser module.
//! Native keeps the original comparator specialization. Ordering, stability,
//! allocation and the standard-library sorting algorithm are unchanged.
use std::cmp::Ordering;
pub(crate) fn by<T>(values: &mut [T], compare: impl FnMut(&T, &T) -> Ordering) {
    #[cfg(target_arch = "wasm32")]
    {
        let mut compare = compare;
        erased(values, &mut compare);
    }
    #[cfg(not(target_arch = "wasm32"))]
    values.sort_by(compare);
}
pub(crate) fn by_key<T, K: Ord>(values: &mut [T], key: impl FnMut(&T) -> K) {
    #[cfg(target_arch = "wasm32")]
    {
        let mut key = key;
        erased(values, &mut |a, b| key(a).cmp(&key(b)));
    }
    #[cfg(not(target_arch = "wasm32"))]
    values.sort_by_key(key);
}
#[cfg(target_arch = "wasm32")]
#[inline(never)]
fn erased<T>(values: &mut [T], compare: &mut dyn FnMut(&T, &T) -> Ordering) {
    values.sort_by(compare);
}
