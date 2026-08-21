//! TemporalController and revisioned linked-view coordination (#44).
//!
//! Rust owns range/cursor/window validation and the coordination state machine.
//! Hosts own playback clocks and UI: they submit revisioned commands here and
//! never reimplement filtering policy. Timers live in the host; `tick` is a
//! pure advance given `dt_micros` so tests can use a fake clock.

use std::collections::HashMap;
use std::sync::{Arc, Mutex, OnceLock};

use crate::temporal::TemporalError;

/// Playback direction: −1 reverse, +1 forward.
#[repr(i32)]
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum PlaybackDirection {
    Reverse = -1,
    Forward = 1,
}

impl PlaybackDirection {
    pub fn from_i32(value: i32) -> Option<Self> {
        match value {
            -1 => Some(Self::Reverse),
            1 => Some(Self::Forward),
            _ => None,
        }
    }

    fn as_i64(self) -> i64 {
        self as i32 as i64
    }
}

/// Snapshot of controller state (UTC microseconds, half-open selected range).
#[derive(Clone, Debug, PartialEq)]
pub struct ControllerState {
    pub instance_id: u64,
    pub group_id: u64,
    pub domain_start: i64,
    pub domain_end: i64,
    pub range_start: i64,
    pub range_end: i64,
    pub cursor: i64,
    pub window: i64,
    pub step: i64,
    pub direction: PlaybackDirection,
    /// Playback rate as micros of domain advance per wall microsecond at 1.0.
    /// Stored as milli-rate × 1000 so hosts can round-trip without f64 on the ABI
    /// (rate_milli = round(rate * 1000); 1000 ⇒ 1.0×).
    pub rate_milli: u32,
    pub loop_enabled: bool,
    pub playing: bool,
    pub reduced_motion: bool,
    pub revision: u64,
    pub disposed: bool,
}

/// Opt-in coordination payload. Never carries JSON numbers.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct CoordinationEvent {
    pub group_id: u64,
    pub source_instance: u64,
    pub revision: u64,
    pub range_start: i64,
    pub range_end: i64,
    pub cursor: i64,
    pub window: i64,
}

#[derive(Debug)]
pub struct TemporalController {
    state: ControllerState,
    /// Last applied remote revision per source instance (reject stale).
    last_remote: HashMap<u64, u64>,
    /// Pending outbound event after a local mutation (hosts poll + broadcast).
    outbound: Option<CoordinationEvent>,
}

impl TemporalController {
    #[allow(clippy::too_many_arguments)] // mirrors the C ABI create descriptor
    pub fn create(
        instance_id: u64,
        group_id: u64,
        domain_start: i64,
        domain_end: i64,
        cursor: i64,
        window: i64,
        step: i64,
        direction: PlaybackDirection,
        rate_milli: u32,
        loop_enabled: bool,
        reduced_motion: bool,
    ) -> Result<Self, TemporalError> {
        if instance_id == 0 || domain_start >= domain_end || window < 0 || step <= 0 {
            return Err(TemporalError::InvalidArgument);
        }
        if rate_milli == 0 {
            return Err(TemporalError::InvalidArgument);
        }
        let cursor = clamp(cursor, domain_start, domain_end.saturating_sub(1));
        let (range_start, range_end) = window_around(cursor, window, domain_start, domain_end)?;
        let span = range_end.saturating_sub(range_start);
        let canonical_window = if span == 1 { 0 } else { span };
        Ok(Self {
            state: ControllerState {
                instance_id,
                group_id,
                domain_start,
                domain_end,
                range_start,
                range_end,
                cursor,
                window: canonical_window,
                step,
                direction,
                rate_milli,
                loop_enabled,
                playing: false,
                reduced_motion,
                revision: 1,
                disposed: false,
            },
            last_remote: HashMap::new(),
            outbound: None,
        })
    }

    pub fn state(&self) -> &ControllerState {
        &self.state
    }

    fn ensure_live(&self) -> Result<(), TemporalError> {
        if self.state.disposed {
            Err(TemporalError::Disposed)
        } else {
            Ok(())
        }
    }

    fn bump_and_queue(&mut self) {
        self.state.revision = self.state.revision.saturating_add(1);
        if self.state.group_id != 0 {
            self.outbound = Some(CoordinationEvent {
                group_id: self.state.group_id,
                source_instance: self.state.instance_id,
                revision: self.state.revision,
                range_start: self.state.range_start,
                range_end: self.state.range_end,
                cursor: self.state.cursor,
                window: self.state.window,
            });
        } else {
            self.outbound = None;
        }
    }

    pub fn take_outbound(&mut self) -> Option<CoordinationEvent> {
        self.outbound.take()
    }

    pub fn set_range(&mut self, start: i64, end: i64) -> Result<(), TemporalError> {
        self.ensure_live()?;
        if start >= end {
            return Err(TemporalError::ReversedInterval);
        }
        if start < self.state.domain_start || end > self.state.domain_end {
            return Err(TemporalError::InvalidArgument);
        }
        let span = end.saturating_sub(start);
        let window = if span == 1 { 0 } else { span };
        let cursor = clamp(self.state.cursor, start, end.saturating_sub(1));
        if self.state.range_start == start
            && self.state.range_end == end
            && self.state.window == window
            && self.state.cursor == cursor
        {
            return Ok(());
        }
        self.state.range_start = start;
        self.state.range_end = end;
        self.state.window = window;
        self.state.cursor = cursor;
        self.bump_and_queue();
        Ok(())
    }

    pub fn set_cursor(&mut self, cursor: i64) -> Result<(), TemporalError> {
        self.ensure_live()?;
        let cursor = clamp(
            cursor,
            self.state.domain_start,
            self.state.domain_end.saturating_sub(1),
        );
        let (start, end) = window_around(
            cursor,
            self.state.window,
            self.state.domain_start,
            self.state.domain_end,
        )?;
        if self.state.cursor == cursor
            && self.state.range_start == start
            && self.state.range_end == end
        {
            return Ok(());
        }
        self.state.cursor = cursor;
        self.state.range_start = start;
        self.state.range_end = end;
        self.bump_and_queue();
        Ok(())
    }

    pub fn step(&mut self) -> Result<(), TemporalError> {
        self.ensure_live()?;
        let delta = self
            .state
            .step
            .saturating_mul(self.state.direction.as_i64());
        let mut next = self.state.cursor.saturating_add(delta);
        if next < self.state.domain_start || next >= self.state.domain_end {
            if self.state.loop_enabled {
                next = if delta >= 0 {
                    self.state.domain_start
                } else {
                    self.state.domain_end.saturating_sub(1)
                };
            } else {
                next = clamp(
                    next,
                    self.state.domain_start,
                    self.state.domain_end.saturating_sub(1),
                );
                self.state.playing = false;
            }
        }
        self.set_cursor(next)
    }

    pub fn play(&mut self) -> Result<(), TemporalError> {
        self.ensure_live()?;
        if self.state.reduced_motion {
            // Reduced motion: keep explicit step/range, refuse automatic play.
            self.state.playing = false;
            return Ok(());
        }
        self.state.playing = true;
        Ok(())
    }

    pub fn pause(&mut self) -> Result<(), TemporalError> {
        self.ensure_live()?;
        self.state.playing = false;
        Ok(())
    }

    pub fn set_rate_milli(&mut self, rate_milli: u32) -> Result<(), TemporalError> {
        self.ensure_live()?;
        if rate_milli == 0 {
            return Err(TemporalError::InvalidArgument);
        }
        self.state.rate_milli = rate_milli;
        Ok(())
    }

    pub fn set_direction(&mut self, direction: PlaybackDirection) -> Result<(), TemporalError> {
        self.ensure_live()?;
        self.state.direction = direction;
        Ok(())
    }

    pub fn set_loop(&mut self, enabled: bool) -> Result<(), TemporalError> {
        self.ensure_live()?;
        self.state.loop_enabled = enabled;
        Ok(())
    }

    pub fn set_reduced_motion(&mut self, enabled: bool) -> Result<(), TemporalError> {
        self.ensure_live()?;
        self.state.reduced_motion = enabled;
        if enabled {
            self.state.playing = false;
        }
        Ok(())
    }

    /// Advance playback by wall-clock `dt_micros`. No-op when paused or
    /// reduced-motion. Deterministic: `advance = dt * rate_milli / 1000`.
    pub fn tick(&mut self, dt_micros: i64) -> Result<bool, TemporalError> {
        self.ensure_live()?;
        if !self.state.playing || self.state.reduced_motion || dt_micros <= 0 {
            return Ok(false);
        }
        let advance = (dt_micros.saturating_mul(i64::from(self.state.rate_milli)) / 1000)
            .saturating_mul(self.state.direction.as_i64());
        if advance == 0 {
            return Ok(false);
        }
        let mut next = self.state.cursor.saturating_add(advance);
        if next < self.state.domain_start || next >= self.state.domain_end {
            if self.state.loop_enabled {
                next = if advance >= 0 {
                    self.state.domain_start
                } else {
                    self.state.domain_end.saturating_sub(1)
                };
            } else {
                next = clamp(
                    next,
                    self.state.domain_start,
                    self.state.domain_end.saturating_sub(1),
                );
                self.state.playing = false;
            }
        }
        let moved = next != self.state.cursor;
        self.set_cursor(next)?;
        Ok(moved)
    }

    /// Validate a peer event without mutating state. This split lets group
    /// delivery fail atomically when one eligible peer has a narrower domain.
    fn validate_event(&self, event: &CoordinationEvent) -> Result<bool, TemporalError> {
        self.ensure_live()?;
        validate_event_shape(event)?;
        if self.state.group_id == 0 || event.group_id != self.state.group_id {
            return Ok(false);
        }
        if event.source_instance == self.state.instance_id {
            return Err(TemporalError::SelfEcho);
        }
        let last = self
            .last_remote
            .get(&event.source_instance)
            .copied()
            .unwrap_or(0);
        if event.revision <= last {
            return Err(TemporalError::StaleRevision);
        }
        if event.range_start < self.state.domain_start || event.range_end > self.state.domain_end {
            return Err(TemporalError::InvalidArgument);
        }
        Ok(true)
    }

    /// Apply a peer coordination event. Rejects self-echo and stale revisions.
    pub fn apply_event(&mut self, event: &CoordinationEvent) -> Result<bool, TemporalError> {
        if !self.validate_event(event)? {
            return Ok(false);
        }
        self.last_remote
            .insert(event.source_instance, event.revision);
        self.state.range_start = event.range_start;
        self.state.range_end = event.range_end;
        self.state.window = event.window;
        self.state.cursor = event.cursor;
        // Remote apply does not bump local revision or emit outbound (no echo).
        Ok(true)
    }

    pub fn dispose(&mut self) -> Result<(), TemporalError> {
        if self.state.disposed {
            return Err(TemporalError::Disposed);
        }
        self.state.playing = false;
        self.state.disposed = true;
        self.outbound = None;
        self.last_remote.clear();
        Ok(())
    }
}

fn validate_event_shape(event: &CoordinationEvent) -> Result<(), TemporalError> {
    if event.source_instance == 0 || event.revision == 0 || event.window < 0 {
        return Err(TemporalError::InvalidArgument);
    }
    if event.range_start >= event.range_end {
        return Err(TemporalError::ReversedInterval);
    }
    let span = event.range_end.saturating_sub(event.range_start);
    let canonical_window = if span == 1 { 0 } else { span };
    if event.window != canonical_window
        || event.cursor < event.range_start
        || event.cursor >= event.range_end
    {
        return Err(TemporalError::InvalidArgument);
    }
    Ok(())
}

fn clamp(value: i64, lo: i64, hi: i64) -> i64 {
    value.max(lo).min(hi)
}

fn window_around(
    cursor: i64,
    window: i64,
    domain_start: i64,
    domain_end: i64,
) -> Result<(i64, i64), TemporalError> {
    if window == 0 {
        let end = cursor.saturating_add(1).min(domain_end);
        let start = end.saturating_sub(1).max(domain_start);
        return Ok((start, end));
    }
    let half = window / 2;
    let mut start = cursor.saturating_sub(half);
    let mut end = start.saturating_add(window);
    if start < domain_start {
        start = domain_start;
        end = start.saturating_add(window).min(domain_end);
    }
    if end > domain_end {
        end = domain_end;
        start = end.saturating_sub(window).max(domain_start);
    }
    if start >= end {
        return Err(TemporalError::InvalidArgument);
    }
    Ok((start, end))
}

// -- handle registry ---------------------------------------------------------

type Registry = (u64, HashMap<u64, Arc<Mutex<TemporalController>>>);
static REGISTRY: OnceLock<Mutex<Registry>> = OnceLock::new();

fn registry() -> &'static Mutex<Registry> {
    REGISTRY.get_or_init(|| Mutex::new((0, HashMap::new())))
}

pub fn controller_insert(controller: TemporalController) -> Result<u64, TemporalError> {
    let mut guard = registry()
        .lock()
        .expect("temporal controller registry poisoned");
    if controller.state().group_id != 0
        && guard.1.values().any(|member| {
            let member = member.lock().expect("temporal controller poisoned");
            !member.state().disposed
                && member.state().group_id == controller.state().group_id
                && member.state().instance_id == controller.state().instance_id
        })
    {
        return Err(TemporalError::InvalidArgument);
    }
    guard.0 = guard
        .0
        .checked_add(1)
        .expect("temporal controller handle exhausted");
    let handle = guard.0;
    guard.1.insert(handle, Arc::new(Mutex::new(controller)));
    Ok(handle)
}

pub fn controller_with_mut<R>(
    handle: u64,
    f: impl FnOnce(&mut TemporalController) -> R,
) -> Option<R> {
    let arc = {
        let guard = registry()
            .lock()
            .expect("temporal controller registry poisoned");
        guard.1.get(&handle).cloned()
    };
    arc.map(|value| {
        let mut controller = value.lock().expect("temporal controller poisoned");
        f(&mut controller)
    })
}

pub fn controller_remove(handle: u64) -> bool {
    registry()
        .lock()
        .expect("temporal controller registry poisoned")
        .1
        .remove(&handle)
        .is_some()
}

/// Same-process deliver: apply `event` to every live controller in the group
/// except the source. Returns the number of successful applies.
pub fn coordinate_deliver(event: &CoordinationEvent) -> Result<u32, TemporalError> {
    if event.group_id == 0 {
        return Err(TemporalError::InvalidArgument);
    }
    validate_event_shape(event)?;
    let mut members: Vec<(u64, Arc<Mutex<TemporalController>>)> = {
        let guard = registry()
            .lock()
            .expect("temporal controller registry poisoned");
        guard
            .1
            .iter()
            .map(|(handle, controller)| (*handle, Arc::clone(controller)))
            .collect()
    };
    // Lock in stable handle order. Validate the complete eligible group before
    // applying to any peer so a mixed-domain failure cannot partially update it.
    members.sort_unstable_by_key(|(handle, _)| *handle);
    let mut controllers: Vec<_> = members
        .iter()
        .map(|(_, member)| member.lock().expect("temporal controller poisoned"))
        .collect();
    let mut eligible = Vec::new();
    for (index, controller) in controllers.iter().enumerate() {
        if controller.state().disposed
            || controller.state().group_id != event.group_id
            || controller.state().instance_id == event.source_instance
        {
            continue;
        }
        match controller.validate_event(event) {
            Ok(true) => eligible.push(index),
            Ok(false) | Err(TemporalError::StaleRevision) | Err(TemporalError::SelfEcho) => {}
            Err(error) => return Err(error),
        }
    }
    let mut applied = 0_u32;
    for index in eligible {
        // Prevalidation above guarantees these applies cannot fail unless the
        // validation and mutation contract diverge while all locks are held.
        if controllers[index].apply_event(event)? {
            applied += 1;
        }
    }
    Ok(applied)
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::sync::atomic::{AtomicU64, Ordering};

    static NEXT_TEST_GROUP: AtomicU64 = AtomicU64::new(1_000);

    fn test_group() -> u64 {
        NEXT_TEST_GROUP.fetch_add(1, Ordering::Relaxed)
    }

    fn make(id: u64, group: u64) -> TemporalController {
        TemporalController::create(
            id,
            group,
            0,
            1_000_000,
            100_000,
            50_000,
            10_000,
            PlaybackDirection::Forward,
            1000,
            true,
            false,
        )
        .unwrap()
    }

    #[test]
    fn linked_views_coordinate_once() {
        let mut a = make(1, 7);
        let mut b = make(2, 7);
        let mut c = make(3, 9); // unrelated group
        a.set_cursor(200_000).unwrap();
        let event = a.take_outbound().expect("outbound");
        assert_eq!(event.source_instance, 1);
        assert_eq!(event.revision, 2);
        assert!(b.apply_event(&event).unwrap());
        assert_eq!(b.state().cursor, a.state().cursor);
        // Source must not echo.
        assert_eq!(a.apply_event(&event).unwrap_err(), TemporalError::SelfEcho);
        // Unrelated group ignores.
        assert!(!c.apply_event(&event).unwrap());
        assert_eq!(c.state().cursor, 100_000);
        // Stale replay rejected.
        assert_eq!(
            b.apply_event(&event).unwrap_err(),
            TemporalError::StaleRevision
        );
    }

    #[test]
    fn inbound_event_rejects_noncanonical_identity_window_and_cursor() {
        let mut target = make(2, 7);
        let valid = CoordinationEvent {
            group_id: 7,
            source_instance: 1,
            revision: 2,
            range_start: 100_000,
            range_end: 150_000,
            cursor: 125_000,
            window: 50_000,
        };
        for malformed in [
            CoordinationEvent {
                source_instance: 0,
                ..valid.clone()
            },
            CoordinationEvent {
                revision: 0,
                ..valid.clone()
            },
            CoordinationEvent {
                window: -1,
                ..valid.clone()
            },
            CoordinationEvent {
                window: 40_000,
                ..valid.clone()
            },
            CoordinationEvent {
                cursor: 150_000,
                ..valid.clone()
            },
        ] {
            assert_eq!(
                target.apply_event(&malformed),
                Err(TemporalError::InvalidArgument)
            );
        }
        assert!(target.apply_event(&valid).unwrap());

        let mut single = make(3, 7);
        let single_event = CoordinationEvent {
            range_start: 100_000,
            range_end: 100_001,
            cursor: 100_000,
            window: 1,
            revision: 3,
            ..valid
        };
        assert_eq!(
            single.apply_event(&single_event),
            Err(TemporalError::InvalidArgument)
        );
    }

    #[test]
    fn oversized_authored_window_is_canonicalized_to_domain() {
        let controller = TemporalController::create(
            1,
            0,
            10,
            20,
            15,
            100,
            1,
            PlaybackDirection::Forward,
            1000,
            false,
            false,
        )
        .unwrap();
        assert_eq!(controller.state().range_start, 10);
        assert_eq!(controller.state().range_end, 20);
        assert_eq!(controller.state().window, 10);
    }

    #[test]
    fn disposal_stops_playback_and_rejects_stale() {
        let mut a = make(1, 0);
        a.play().unwrap();
        assert!(a.state().playing);
        a.dispose().unwrap();
        assert!(!a.state().playing);
        assert!(a.state().disposed);
        assert_eq!(a.tick(1_000).unwrap_err(), TemporalError::Disposed);
        assert_eq!(a.set_cursor(1).unwrap_err(), TemporalError::Disposed);
        assert_eq!(a.dispose().unwrap_err(), TemporalError::Disposed);
    }

    #[test]
    fn reduced_motion_blocks_play_keeps_step() {
        let mut a = make(1, 0);
        a.set_reduced_motion(true).unwrap();
        a.play().unwrap();
        assert!(!a.state().playing);
        let before = a.state().cursor;
        a.step().unwrap();
        assert_ne!(a.state().cursor, before);
        assert!(!a.tick(50_000).unwrap());
    }

    #[test]
    fn tick_advances_with_fake_clock() {
        let mut a = make(1, 0);
        a.play().unwrap();
        let before = a.state().cursor;
        assert!(a.tick(20_000).unwrap());
        assert_eq!(a.state().cursor, before + 20_000);

        a.set_loop(false).unwrap();
        a.set_cursor(a.state().domain_end).unwrap();
        a.play().unwrap();
        let revision = a.state().revision;
        assert!(!a.tick(20_000).unwrap());
        assert!(!a.state().playing);
        assert_eq!(a.state().revision, revision);
    }

    #[test]
    fn setters_and_bound_step_are_idempotent() {
        let group = test_group();
        let mut controller = make(50, group);
        let initial = controller.state().clone();
        controller
            .set_range(initial.range_start, initial.range_end)
            .unwrap();
        controller.set_cursor(initial.cursor).unwrap();
        assert_eq!(controller.state().revision, initial.revision);
        assert!(controller.take_outbound().is_none());

        controller
            .set_cursor(controller.state().domain_end)
            .unwrap();
        controller.take_outbound();
        controller.set_loop(false).unwrap();
        let revision = controller.state().revision;
        controller.step().unwrap();
        assert_eq!(controller.state().revision, revision);
        assert!(controller.take_outbound().is_none());

        controller.set_range(100, 101).unwrap();
        assert_eq!(controller.state().window, 0);
    }

    #[test]
    fn same_process_deliver_isolates_groups() {
        let group = test_group();
        let other_group = test_group();
        let a = controller_insert(make(1, group)).unwrap();
        let b = controller_insert(make(2, group)).unwrap();
        let c = controller_insert(make(3, other_group)).unwrap();
        let event = controller_with_mut(a, |ctrl| {
            ctrl.set_cursor(300_000).unwrap();
            ctrl.take_outbound().unwrap()
        })
        .unwrap();
        assert_eq!(coordinate_deliver(&event).unwrap(), 1);
        let b_cursor = controller_with_mut(b, |ctrl| ctrl.state().cursor).unwrap();
        let c_cursor = controller_with_mut(c, |ctrl| ctrl.state().cursor).unwrap();
        assert_eq!(b_cursor, 300_000);
        assert_eq!(c_cursor, 100_000);
        controller_remove(a);
        controller_remove(b);
        controller_remove(c);
    }

    #[test]
    fn mixed_domain_delivery_is_atomic() {
        let group = test_group();
        let source = controller_insert(make(100, group)).unwrap();
        let wide = controller_insert(make(101, group)).unwrap();
        let narrow = controller_insert(
            TemporalController::create(
                102,
                group,
                0,
                250_000,
                100_000,
                50_000,
                10_000,
                PlaybackDirection::Forward,
                1000,
                true,
                false,
            )
            .unwrap(),
        )
        .unwrap();
        let event = controller_with_mut(source, |ctrl| {
            ctrl.set_cursor(300_000).unwrap();
            ctrl.take_outbound().unwrap()
        })
        .unwrap();
        let wide_before = controller_with_mut(wide, |ctrl| ctrl.state().clone()).unwrap();
        let narrow_before = controller_with_mut(narrow, |ctrl| ctrl.state().clone()).unwrap();

        assert_eq!(
            coordinate_deliver(&event),
            Err(TemporalError::InvalidArgument)
        );
        assert_eq!(
            controller_with_mut(wide, |ctrl| ctrl.state().clone()).unwrap(),
            wide_before
        );
        assert_eq!(
            controller_with_mut(narrow, |ctrl| ctrl.state().clone()).unwrap(),
            narrow_before
        );
        controller_remove(source);
        controller_remove(wide);
        controller_remove(narrow);
    }

    #[test]
    fn delivery_rejects_malformed_shape_without_an_eligible_peer() {
        let group = test_group();
        let malformed = CoordinationEvent {
            group_id: group,
            source_instance: 1,
            revision: 1,
            range_start: 10,
            range_end: 20,
            cursor: 20,
            window: 10,
        };
        assert_eq!(
            coordinate_deliver(&malformed),
            Err(TemporalError::InvalidArgument)
        );
    }

    #[test]
    fn exchange_group_instance_ids_are_unique_while_live() {
        let group = test_group();
        let first = controller_insert(make(500, group)).unwrap();
        assert_eq!(
            controller_insert(make(500, group)),
            Err(TemporalError::InvalidArgument)
        );
        // The same identity in an unrelated group does not collide.
        let other = controller_insert(make(500, test_group())).unwrap();
        controller_with_mut(first, |controller| controller.dispose().unwrap()).unwrap();
        let replacement = controller_insert(make(500, group)).unwrap();
        controller_remove(first);
        controller_remove(other);
        controller_remove(replacement);
    }

    #[test]
    fn open_play_dispose_cycles() {
        for i in 0..100 {
            let mut ctrl = make(i + 1, 0);
            ctrl.play().unwrap();
            let _ = ctrl.tick(1_000);
            ctrl.dispose().unwrap();
        }
    }
}
