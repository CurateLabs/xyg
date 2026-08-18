//! Canonical GraphForge graph projection identity and topology.
//!
//! Hosts expose Arrow buffers at their boundary; this safe engine layer owns
//! copied UUID identity, deterministic dense endpoints, and optional compound
//! parents behind opaque handles. UUIDs are always opaque 16-byte values.

use std::collections::HashMap;
use std::sync::{Arc, Mutex, OnceLock};

pub type Uuid = [u8; 16];

#[repr(i32)]
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum ProjectionError {
    InvalidArgument = -1,
    CapacityExceeded = -2,
    MalformedUuid = -3,
    DuplicateNode = -4,
    DuplicateEdge = -5,
    MissingEndpoint = -6,
    StaleHandle = -7,
    OutputCapacity = -8,
}

#[derive(Debug)]
pub struct GraphProjection {
    node_ids: Vec<Uuid>,
    edge_ids: Vec<Uuid>,
    sources: Vec<u64>,
    targets: Vec<u64>,
    parents: Vec<u64>,
    parent_validity: Vec<u8>,
    directed: bool,
}

impl GraphProjection {
    pub fn new(
        node_ids: &[Uuid],
        edge_ids: &[Uuid],
        source_ids: &[Uuid],
        target_ids: &[Uuid],
        parent_ids: Option<(&[Uuid], &[u8])>,
        directed: bool,
    ) -> Result<Self, ProjectionError> {
        if edge_ids.len() != source_ids.len() || edge_ids.len() != target_ids.len() {
            return Err(ProjectionError::InvalidArgument);
        }
        let mut nodes = HashMap::with_capacity(node_ids.len());
        for (dense, id) in node_ids.iter().copied().enumerate() {
            if id == [0; 16] {
                return Err(ProjectionError::MalformedUuid);
            }
            if nodes.insert(id, dense as u64).is_some() {
                return Err(ProjectionError::DuplicateNode);
            }
        }
        let mut seen_edges = HashMap::with_capacity(edge_ids.len());
        for id in edge_ids.iter().copied() {
            if id == [0; 16] {
                return Err(ProjectionError::MalformedUuid);
            }
            if seen_edges.insert(id, ()).is_some() {
                return Err(ProjectionError::DuplicateEdge);
            }
        }
        let mut sources = Vec::with_capacity(edge_ids.len());
        let mut targets = Vec::with_capacity(edge_ids.len());
        for (source, target) in source_ids.iter().zip(target_ids) {
            sources.push(*nodes.get(source).ok_or(ProjectionError::MissingEndpoint)?);
            targets.push(*nodes.get(target).ok_or(ProjectionError::MissingEndpoint)?);
        }

        let mut parents = vec![0; node_ids.len()];
        let mut parent_validity = vec![0; node_ids.len()];
        if let Some((ids, validity)) = parent_ids {
            if ids.len() != node_ids.len() || validity.len() != node_ids.len() {
                return Err(ProjectionError::InvalidArgument);
            }
            for (i, (&id, &valid)) in ids.iter().zip(validity).enumerate() {
                if valid > 1 {
                    return Err(ProjectionError::InvalidArgument);
                }
                if valid == 1 {
                    if id == [0; 16] {
                        return Err(ProjectionError::MalformedUuid);
                    }
                    parents[i] = *nodes.get(&id).ok_or(ProjectionError::MissingEndpoint)?;
                    parent_validity[i] = 1;
                }
            }
        }
        Ok(Self {
            node_ids: node_ids.to_vec(),
            edge_ids: edge_ids.to_vec(),
            sources,
            targets,
            parents,
            parent_validity,
            directed,
        })
    }

    pub fn node_ids(&self) -> &[Uuid] {
        &self.node_ids
    }
    pub fn edge_ids(&self) -> &[Uuid] {
        &self.edge_ids
    }
    pub fn sources(&self) -> &[u64] {
        &self.sources
    }
    pub fn targets(&self) -> &[u64] {
        &self.targets
    }
    pub fn parents(&self) -> &[u64] {
        &self.parents
    }
    pub fn parent_validity(&self) -> &[u8] {
        &self.parent_validity
    }
    pub fn directed(&self) -> bool {
        self.directed
    }
}

type Registry = (u64, HashMap<u64, Arc<GraphProjection>>);
static REGISTRY: OnceLock<Mutex<Registry>> = OnceLock::new();
fn registry() -> &'static Mutex<Registry> {
    REGISTRY.get_or_init(|| Mutex::new((0, HashMap::new())))
}

pub fn reg_insert(projection: GraphProjection) -> u64 {
    let mut guard = registry().lock().expect("projection registry poisoned");
    guard.0 = guard.0.checked_add(1).expect("projection handle exhausted");
    let handle = guard.0;
    guard.1.insert(handle, Arc::new(projection));
    handle
}

pub fn reg_with<R>(handle: u64, f: impl FnOnce(&GraphProjection) -> R) -> Option<R> {
    let projection = {
        let guard = registry().lock().expect("projection registry poisoned");
        guard.1.get(&handle).cloned()
    };
    projection.map(|value| f(&value))
}

pub fn reg_remove(handle: u64) -> bool {
    registry()
        .lock()
        .expect("projection registry poisoned")
        .1
        .remove(&handle)
        .is_some()
}

#[cfg(test)]
mod tests {
    use super::*;
    fn id(value: u8) -> Uuid {
        [value; 16]
    }

    #[test]
    fn preserves_parallel_edges_and_maps_uuid_endpoints() {
        let graph = GraphProjection::new(
            &[id(1), id(2)],
            &[id(3), id(4)],
            &[id(1), id(1)],
            &[id(2), id(2)],
            Some((&[id(0), id(1)], &[0, 1])),
            true,
        )
        .unwrap();
        assert_eq!(graph.sources(), &[0, 0]);
        assert_eq!(graph.targets(), &[1, 1]);
        assert_eq!(graph.parents(), &[0, 0]);
        assert_eq!(graph.parent_validity(), &[0, 1]);
        assert!(graph.directed());
    }

    #[test]
    fn rejects_invalid_identity_and_topology() {
        assert_eq!(
            GraphProjection::new(&[[0; 16]], &[], &[], &[], None, false).unwrap_err(),
            ProjectionError::MalformedUuid
        );
        assert_eq!(
            GraphProjection::new(&[id(1), id(1)], &[], &[], &[], None, false).unwrap_err(),
            ProjectionError::DuplicateNode
        );
        assert_eq!(
            GraphProjection::new(
                &[id(1)],
                &[id(2), id(2)],
                &[id(1), id(1)],
                &[id(1), id(1)],
                None,
                false
            )
            .unwrap_err(),
            ProjectionError::DuplicateEdge
        );
        assert_eq!(
            GraphProjection::new(&[id(1)], &[id(2)], &[id(1)], &[id(9)], None, false).unwrap_err(),
            ProjectionError::MissingEndpoint
        );
    }

    #[test]
    fn stale_handles_are_refused() {
        let handle =
            reg_insert(GraphProjection::new(&[id(1)], &[], &[], &[], None, false).unwrap());
        assert!(reg_with(handle, |_| ()).is_some());
        assert!(reg_remove(handle));
        assert!(reg_with(handle, |_| ()).is_none());
        assert!(!reg_remove(handle));
    }
}
