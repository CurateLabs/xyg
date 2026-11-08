//! Safe index-only hash storage. Keys stay in the caller's canonical plane.
//! Each caller reserves its checked maximum population before inserting; no
//! table resize or copied key plane can overlap a publication/force phase.
#[derive(Clone)]
pub(crate) struct IndexSlots {
    slots: Vec<u8>,
    #[cfg(target_pointer_width = "64")]
    width: usize,
}
pub(crate) fn mixed_words(lo: u64, hi: u64) -> u64 {
    let mut z = lo ^ hi.rotate_left(29) ^ 0x9E37_79B9_7F4A_7C15;
    z = (z ^ (z >> 30)).wrapping_mul(0xBF58_476D_1CE4_E5B9);
    z = (z ^ (z >> 27)).wrapping_mul(0x94D0_49BB_1331_11EB);
    z ^ (z >> 31)
}
impl IndexSlots {
    pub(crate) fn capacity_bytes(count: usize) -> Option<usize> {
        if count == 0 {
            return Some(0);
        }
        let width = if usize::BITS == 32 || count < u32::MAX as usize {
            4
        } else {
            8
        };
        count
            .checked_mul(8)?
            .checked_add(6)?
            .checked_div(7)?
            .max(4)
            .checked_next_power_of_two()?
            .checked_mul(width)
    }
    pub(crate) fn new(count: usize) -> Option<Self> {
        let slots = vec![255; Self::capacity_bytes(count)?];
        Some(Self {
            slots,
            #[cfg(target_pointer_width = "64")]
            width: if count < u32::MAX as usize { 4 } else { 8 },
        })
    }
    pub(crate) fn bytes(&self) -> usize {
        self.slots.capacity()
    }
    fn width(&self) -> usize {
        #[cfg(target_pointer_width = "32")]
        {
            4
        }
        #[cfg(target_pointer_width = "64")]
        {
            self.width
        }
    }
    fn at(&self, slot: usize) -> Option<usize> {
        let at = slot * self.width();
        if self.width() == 4 {
            let v = u32::from_le_bytes(self.slots[at..at + 4].try_into().unwrap());
            (v != u32::MAX).then_some(v as usize)
        } else {
            let v = u64::from_le_bytes(self.slots[at..at + 8].try_into().unwrap());
            (v != u64::MAX).then_some(v as usize)
        }
    }
    fn count(&self) -> usize {
        self.slots.len() / self.width()
    }
    pub(crate) fn find(
        &self,
        key: [u64; 2],
        key_at: &dyn Fn(usize) -> [u64; 2],
    ) -> Option<(usize, Option<usize>)> {
        self.find_hashed(mixed_words(key[0], key[1]), &|i| key_at(i) == key)
    }
    pub(crate) fn find_hashed(
        &self,
        hash: u64,
        equal: &dyn Fn(usize) -> bool,
    ) -> Option<(usize, Option<usize>)> {
        if self.slots.is_empty() {
            return None;
        }
        let mask = self.count() - 1;
        let mut slot = hash as usize & mask;
        loop {
            match self.at(slot) {
                None => return Some((slot, None)),
                Some(i) if equal(i) => return Some((slot, Some(i))),
                _ => slot = (slot + 1) & mask,
            }
        }
    }
    pub(crate) fn set(&mut self, slot: usize, index: usize) {
        let width = self.width();
        let at = slot * width;
        self.slots[at..at + width].copy_from_slice(&(index as u64).to_le_bytes()[..width]);
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn checked_capacity_and_collision_equality_keep_every_dense_index() {
        assert_eq!(IndexSlots::capacity_bytes(0), Some(0));
        assert_eq!(IndexSlots::capacity_bytes(usize::MAX), None);
        for n in [1usize, 4, 7, 8, 31, 64, 1000] {
            let mut table = IndexSlots::new(n).unwrap();
            let keys: Vec<_> = (0..n)
                .map(|i| [i as u64, (i as u64).rotate_left(17)])
                .collect();
            for i in 0..n {
                let (slot, old) = table.find(keys[i], &|j| keys[j]).unwrap();
                assert_eq!(old, None);
                table.set(slot, i);
            }
            for i in 0..n {
                assert_eq!(table.find(keys[i], &|j| keys[j]).unwrap().1, Some(i));
            }
            assert_eq!(
                table.find([u64::MAX, u64::MAX], &|j| keys[j]).unwrap().1,
                None
            );
            assert_eq!(table.bytes(), IndexSlots::capacity_bytes(n).unwrap());
        }
    }
}

/// Stable first-occurrence ranks and group sizes, with canonical keys borrowed.
/// The table and owner map die before the caller paints or integrates forces.
pub(crate) fn stable_ranks(
    n: usize,
    key: &dyn Fn(usize) -> [u64; 2],
) -> Option<(Vec<usize>, Vec<usize>)> {
    let mut slots = IndexSlots::new(n)?;
    let mut first = vec![0usize; n];
    let mut rank = vec![0usize; n];
    let mut size = vec![0usize; n];
    for i in 0..n {
        let (slot, found) = slots.find(key(i), key)?;
        let owner = found.unwrap_or(i);
        if found.is_none() {
            slots.set(slot, i);
        }
        first[i] = owner;
        rank[i] = size[owner];
        size[owner] = size[owner].checked_add(1)?;
    }
    for i in 0..n {
        size[i] = size[first[i]];
    }
    Some((rank, size))
}

#[cfg(test)]
mod rank_tests {
    #[test]
    fn stable_ranks_match_independent_group_lists() {
        let keys: Vec<_> = (0..1000)
            .map(|i| [(i % 17) as u64, (i % 3) as u64])
            .collect();
        let mut groups = std::collections::BTreeMap::<[u64; 2], Vec<usize>>::new();
        for (i, &key) in keys.iter().enumerate() {
            groups.entry(key).or_default().push(i);
        }
        let (rank, size) = super::stable_ranks(keys.len(), &|i| keys[i]).unwrap();
        for members in groups.values() {
            for (r, &i) in members.iter().enumerate() {
                assert_eq!(rank[i], r);
                assert_eq!(size[i], members.len());
            }
        }
    }
}
