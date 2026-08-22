//! Deterministic cross-chart resource admission policy (dossier §18).

pub const DASHBOARD_VISIBLE: u8 = 1;
pub const DASHBOARD_INTERACTING: u8 = 2;
pub const MAX_DASHBOARD_RESOURCES: usize = 4_096;

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub struct DashboardResource {
    pub stable_id: u64,
    pub derived_bytes: u64,
    pub last_used: u64,
    pub flags: u8,
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct DashboardPlan {
    pub retained: Vec<bool>,
    pub retained_bytes: u64,
}

/// Admit whole per-chart derived-resource sets under one global byte budget.
///
/// Interaction outranks visibility, visibility outranks hidden work, recent
/// use breaks ties, and stable identity is the final deterministic order.
/// Canonical CPU columns are outside this derived-resource budget.
pub fn plan_dashboard_resources(
    resources: &[DashboardResource],
    budget_bytes: u64,
) -> Option<DashboardPlan> {
    if resources.len() > MAX_DASHBOARD_RESOURCES
        || resources.iter().any(|resource| resource.flags & !3 != 0)
    {
        return None;
    }
    let mut identities: Vec<u64> = resources
        .iter()
        .map(|resource| resource.stable_id)
        .collect();
    identities.sort_unstable();
    if identities.windows(2).any(|pair| pair[0] == pair[1]) {
        return None;
    }
    let mut order: Vec<usize> = (0..resources.len()).collect();
    order.sort_by_key(|&index| {
        let resource = resources[index];
        (
            std::cmp::Reverse(resource.flags & DASHBOARD_INTERACTING != 0),
            std::cmp::Reverse(resource.flags & DASHBOARD_VISIBLE != 0),
            std::cmp::Reverse(resource.last_used),
            resource.stable_id,
            index,
        )
    });
    let mut retained = vec![false; resources.len()];
    let mut retained_bytes = 0_u64;
    for index in order {
        let resource = resources[index];
        if resource.derived_bytes <= budget_bytes.saturating_sub(retained_bytes) {
            retained[index] = true;
            retained_bytes += resource.derived_bytes;
        }
    }
    Some(DashboardPlan {
        retained,
        retained_bytes,
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn interaction_and_visibility_outrank_hidden_recency() {
        let resources = [
            DashboardResource {
                stable_id: 9,
                derived_bytes: 40,
                last_used: 99,
                flags: 0,
            },
            DashboardResource {
                stable_id: 4,
                derived_bytes: 40,
                last_used: 1,
                flags: DASHBOARD_VISIBLE,
            },
            DashboardResource {
                stable_id: 7,
                derived_bytes: 40,
                last_used: 0,
                flags: DASHBOARD_INTERACTING,
            },
        ];
        let plan = plan_dashboard_resources(&resources, 80).unwrap();
        assert_eq!(plan.retained, [false, true, true]);
        assert_eq!(plan.retained_bytes, 80);
    }

    #[test]
    fn whole_resource_admission_is_stable_and_gap_filling() {
        let resources = [
            DashboardResource {
                stable_id: 2,
                derived_bytes: 80,
                last_used: 5,
                flags: DASHBOARD_VISIBLE,
            },
            DashboardResource {
                stable_id: 1,
                derived_bytes: 120,
                last_used: 5,
                flags: DASHBOARD_VISIBLE,
            },
            DashboardResource {
                stable_id: 3,
                derived_bytes: 20,
                last_used: 4,
                flags: 0,
            },
        ];
        let plan = plan_dashboard_resources(&resources, 100).unwrap();
        assert_eq!(plan.retained, [true, false, true]);
        assert_eq!(plan.retained_bytes, 100);
    }

    #[test]
    fn rejects_unknown_flags() {
        let resources = [DashboardResource {
            stable_id: 1,
            derived_bytes: 1,
            last_used: 0,
            flags: 4,
        }];
        assert!(plan_dashboard_resources(&resources, 1).is_none());
    }

    #[test]
    fn rejects_duplicate_cross_chart_identity() {
        let resources = [
            DashboardResource {
                stable_id: 1,
                derived_bytes: 1,
                last_used: 0,
                flags: 0,
            },
            DashboardResource {
                stable_id: 1,
                derived_bytes: 1,
                last_used: 1,
                flags: DASHBOARD_VISIBLE,
            },
        ];
        assert!(plan_dashboard_resources(&resources, 2).is_none());
    }

    #[test]
    fn direct_engine_call_rejects_more_than_the_public_limit() {
        let resources: Vec<_> = (0..=MAX_DASHBOARD_RESOURCES)
            .map(|index| DashboardResource {
                stable_id: index as u64,
                derived_bytes: 0,
                last_used: 0,
                flags: 0,
            })
            .collect();
        assert!(plan_dashboard_resources(&resources, 0).is_none());
    }
}
