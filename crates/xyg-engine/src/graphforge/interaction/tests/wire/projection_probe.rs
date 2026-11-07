//! Test-only phase/probe counts; no allocator or product-policy hook.
use std::cell::Cell;
#[derive(Clone, Copy, Debug, Default, PartialEq, Eq)]
pub(crate) struct Counts {
    pub targets: usize,
    pub admissions: usize,
    pub borrows: usize,
    pub rows: usize,
    pub outputs: usize,
    pub mappings: usize,
}
thread_local! { static COUNTS: Cell<Counts> = Cell::new(Counts::default()); }
fn change(f: impl FnOnce(&mut Counts)) {
    COUNTS.with(|cell| {
        let mut c = cell.get();
        f(&mut c);
        cell.set(c);
    });
}
pub(super) fn admit(n: usize) {
    change(|c| {
        c.targets = n;
        c.admissions += 1;
    });
}
pub(super) fn borrow() {
    change(|c| c.borrows += 1);
}
pub(super) fn row() {
    change(|c| c.rows += 1);
}
pub(super) fn output(n: usize) {
    change(|c| {
        c.outputs += 1;
        c.mappings = n;
    });
}
pub(crate) fn reset() {
    COUNTS.with(|c| c.set(Counts::default()));
}
pub(crate) fn counts() -> Counts {
    COUNTS.with(Cell::get)
}
