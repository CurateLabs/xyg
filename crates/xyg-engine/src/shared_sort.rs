//! One stable-sort body per record type in the size-bounded browser module.
//! Native keeps the original comparator specialization. Ordering, stability,
//! allocation and the standard-library sorting algorithm are unchanged.
use std::cmp::Ordering;

/// Arithmetic key for two derived u32 ordinals. Unsigned order is exactly
/// lexicographic pair order; no canonical u64 source/feature ID is narrowed.
pub(crate) fn pair_u32(first: u32, second: u32) -> u64 {
    (u64::from(first) << 32) | u64::from(second)
}
pub(crate) fn unpair_u32(key: u64) -> (u32, u32) {
    ((key >> 32) as u32, key as u32)
}
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

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn derived_u32_pair_keys_preserve_order_duplicates_and_full_halves() {
        let halves = [0, 1, (1 << 31) - 1, 1 << 31, u32::MAX];
        let mut expected = Vec::new();
        let mut keys = Vec::new();
        for &first in halves.iter().rev() {
            for &second in halves.iter().rev() {
                let key = pair_u32(first, second);
                assert_eq!(unpair_u32(key), (first, second));
                expected.extend([(first, second), (first, second)]);
                keys.extend([key, key]);
            }
        }
        expected.sort_unstable();
        expected.dedup();
        keys.sort_unstable();
        keys.dedup();
        assert_eq!(
            keys.into_iter().map(unpair_u32).collect::<Vec<_>>(),
            expected
        );
    }
}
