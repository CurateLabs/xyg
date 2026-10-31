//! Kind-qualified element identity for one composed graph document
//! (spec/design/graph-interaction.md §2.1).
//!
//! A composed `XYGF` document addresses elements by dense index, which changes
//! whenever the composition does. [`ElementRef`] names an element by what is
//! stable instead:
//!
//! - a node by its UUID;
//! - a persisted edge by its UUID (a node and an edge may share a UUID, so the
//!   kind is part of the reference);
//! - a derived edge (NIL UUID in the document) by `(result id, layer, path,
//!   order)`, see [`DerivedKey`];
//! - a render-tier aggregate by the render revision that produced it. An
//!   aggregate is only meaningful against a published render, which a session
//!   does not have until the render pipeline lands (S2), so it never resolves
//!   here: [`ResolveError::NeedsRender`].
//!
//! Result ids are compared as exact strings. The session [`ResultTable`] may
//! use a 64-bit hash to find candidates quickly, but identity is the string:
//! two ids with equal hashes stay distinct and a reference whose id is absent
//! resolves to nothing rather than to a hash-equal neighbor.

use std::collections::HashMap;
use std::marker::PhantomData;

use super::compose::NONE_U64;
use super::composed::ComposedDocument;
use super::{uuid_map, GfError, GfResult, Uuid, UuidKey, UuidMap, NIL_UUID};
use crate::graph_interaction_state::{DerivedKey, ElementSet, Focus, GraphEntity};

/// 64-bit hash used only to find result-id candidates quickly.
pub trait ResultHash {
    fn hash(bytes: &[u8]) -> u64;
}

/// FNV-1a, 64-bit.
#[derive(Clone)]
pub struct Fnv1a;

impl ResultHash for Fnv1a {
    fn hash(bytes: &[u8]) -> u64 {
        bytes.iter().fold(0xcbf2_9ce4_8422_2325, |hash, &byte| {
            (hash ^ u64::from(byte)).wrapping_mul(0x0000_0100_0000_01b3)
        })
    }
}

/// Index of the "no result id" entry. A layer without an id is a distinct
/// entry, not the empty string.
pub const NO_RESULT: u32 = 0;

/// Session string table of exact result ids.
#[derive(Clone)]
pub struct ResultTable<H: ResultHash = Fnv1a> {
    strings: Vec<Option<Box<str>>>,
    buckets: HashMap<u64, Vec<u32>>,
    hash: PhantomData<H>,
}

impl<H: ResultHash> Default for ResultTable<H> {
    fn default() -> Self {
        Self {
            strings: vec![None],
            buckets: HashMap::new(),
            hash: PhantomData,
        }
    }
}

impl<H: ResultHash> ResultTable<H> {
    /// Exact lookup: candidates share the hash, the string decides.
    pub fn find(&self, id: Option<&str>) -> Option<u32> {
        let Some(id) = id else {
            return Some(NO_RESULT);
        };
        self.buckets
            .get(&H::hash(id.as_bytes()))?
            .iter()
            .copied()
            .find(|&index| self.strings[index as usize].as_deref() == Some(id))
    }

    pub fn intern(&mut self, id: Option<&str>) -> u32 {
        if let Some(index) = self.find(id) {
            return index;
        }
        let id = id.expect("the absent id is entry 0");
        let index = self.strings.len() as u32;
        self.strings.push(Some(id.into()));
        self.buckets
            .entry(H::hash(id.as_bytes()))
            .or_default()
            .push(index);
        index
    }

    /// The id at `index`: outer `None` when the index is not in the table.
    pub fn get(&self, index: u32) -> Option<Option<&str>> {
        self.strings.get(index as usize).map(|id| id.as_deref())
    }
}

/// A result id inside a derived-edge reference.
#[derive(Clone, Debug, Eq, PartialEq)]
pub enum ResultRef {
    /// Index into the issuing session's [`ResultTable`].
    Local(u32),
    /// The exact id, for refs that cross sessions or hosts.
    Exact(Option<Box<str>>),
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct DerivedRef {
    pub result: ResultRef,
    pub layer: u32,
    pub path: u64,
    pub order: u64,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub struct AggregateRef {
    pub render_revision: u32,
    /// Render node index within that revision.
    pub index: u32,
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub enum ElementRef {
    Node(Uuid),
    Edge(Uuid),
    Derived(DerivedRef),
    Aggregate(AggregateRef),
}

/// Dense composed-document index of a resolved element.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum ElementIndex {
    Node(usize),
    Edge(usize),
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum ResolveError {
    /// No element of this document has that identity.
    Unresolved,
    /// Aggregates resolve against a published render (not available yet).
    NeedsRender,
}

/// Identity planes of one composed document.
#[derive(Clone)]
pub struct GraphIdentity<H: ResultHash = Fnv1a> {
    node_uuid: Vec<Uuid>,
    node_index: UuidMap,
    /// NIL for derived edges.
    edge_uuid: Vec<Uuid>,
    /// Persisted edges only.
    edge_index: UuidMap,
    /// `(layer, path, order)` of each derived edge.
    edge_derived: Vec<Option<(u32, u64, u64)>>,
    derived_index: HashMap<(u32, u64, u64), usize>,
    /// Result-table entry of each layer.
    layer_result: Vec<u32>,
    results: ResultTable<H>,
}

fn invalid(message: &str) -> GfError {
    GfError::new("GF_INTERACTION_INVALID", message)
}

impl<H: ResultHash> GraphIdentity<H> {
    pub fn from_document(doc: &ComposedDocument<'_>) -> GfResult<Self> {
        let node_uuid = doc.uuids("node.uuid")?;
        let edge_uuid = doc.uuids("edge.uuid")?;
        let edge_count = edge_uuid.len();
        let derived = doc.u8s("edge.derived")?;
        let edge_layer = doc.u32s("edge.layer")?;
        let edge_order = doc.i64s("edge.order")?;
        let edge_path = doc.u64s("edge.path")?;
        if [
            derived.len(),
            edge_layer.len(),
            edge_order.len(),
            edge_path.len(),
        ]
        .iter()
        .any(|&len| len != edge_count)
        {
            return Err(invalid("edge identity planes differ in length"));
        }

        let mut results = ResultTable::default();
        let layer_result = (0..doc.layer_count())
            .map(|layer| Ok(results.intern(doc.result_id(layer)?.as_deref())))
            .collect::<GfResult<Vec<_>>>()?;

        let mut node_index = uuid_map(node_uuid.len());
        for (dense, &id) in node_uuid.iter().enumerate() {
            if id == NIL_UUID || node_index.insert(UuidKey(id), dense).is_some() {
                return Err(invalid("node UUIDs must be unique and non-nil"));
            }
        }
        let mut edge_index = uuid_map(edge_count);
        let mut edge_derived = vec![None; edge_count];
        let mut derived_index = HashMap::new();
        let mut layer_rows: HashMap<u32, Vec<u64>> = HashMap::new();
        for edge in 0..edge_count {
            if derived[edge] == 0 {
                let id = edge_uuid[edge];
                if id == NIL_UUID || edge_index.insert(UuidKey(id), edge).is_some() {
                    return Err(invalid("persisted edge UUIDs must be unique and non-nil"));
                }
                continue;
            }
            let layer = edge_layer[edge];
            if edge_uuid[edge] != NIL_UUID || layer as usize >= layer_result.len() {
                return Err(invalid("derived edges carry a NIL UUID and a layer"));
            }
            // Overlay steps are unique by (path, step). Derived pairs have no
            // overlay: their layer's result row is the unique discriminator.
            let order = if edge_path[edge] == NONE_U64 {
                let rows = match layer_rows.entry(layer) {
                    std::collections::hash_map::Entry::Occupied(rows) => rows.into_mut(),
                    std::collections::hash_map::Entry::Vacant(slot) => {
                        slot.insert(doc.edge_rows(layer)?)
                    }
                };
                rows.get(edge)
                    .copied()
                    .filter(|&row| row != NONE_U64)
                    .ok_or_else(|| invalid("a derived edge has no result row"))?
            } else {
                u64::try_from(edge_order[edge])
                    .map_err(|_| invalid("an overlay edge has no step order"))?
            };
            let key = (layer, edge_path[edge], order);
            if derived_index.insert(key, edge).is_some() {
                return Err(invalid("derived edge keys must be unique"));
            }
            edge_derived[edge] = Some(key);
        }
        Ok(Self {
            node_uuid,
            node_index,
            edge_uuid,
            edge_index,
            edge_derived,
            derived_index,
            layer_result,
            results,
        })
    }

    pub fn node_count(&self) -> usize {
        self.node_uuid.len()
    }

    pub fn edge_count(&self) -> usize {
        self.edge_uuid.len()
    }

    pub fn node_uuids(&self) -> &[Uuid] {
        &self.node_uuid
    }

    /// Persisted edge UUIDs in document order (derived edges skipped).
    pub fn persisted_edge_uuids(&self) -> impl Iterator<Item = Uuid> + '_ {
        self.edge_uuid
            .iter()
            .zip(&self.edge_derived)
            .filter(|(_, derived)| derived.is_none())
            .map(|(&id, _)| id)
    }

    /// Whether a composed edge is derived (NIL UUID) rather than persisted.
    pub fn is_derived(&self, edge: usize) -> bool {
        self.edge_derived[edge].is_some()
    }

    pub fn node_index(&self, id: &Uuid) -> Option<usize> {
        self.node_index.get(&UuidKey(*id)).copied()
    }

    pub fn edge_index(&self, id: &Uuid) -> Option<usize> {
        self.edge_index.get(&UuidKey(*id)).copied()
    }

    pub fn node_ref(&self, node: usize) -> ElementRef {
        ElementRef::Node(self.node_uuid[node])
    }

    /// Local reference of a composed edge.
    pub fn edge_ref(&self, edge: usize) -> ElementRef {
        match self.edge_derived[edge] {
            None => ElementRef::Edge(self.edge_uuid[edge]),
            Some((layer, path, order)) => ElementRef::Derived(DerivedRef {
                result: ResultRef::Local(self.layer_result[layer as usize]),
                layer,
                path,
                order,
            }),
        }
    }

    /// State key of a derived edge (`None` for a persisted edge).
    pub fn derived_key(&self, edge: usize) -> Option<DerivedKey> {
        let (layer, path, order) = self.edge_derived[edge]?;
        let result_id = self
            .results
            .get(self.layer_result[layer as usize])
            .flatten()
            .map(Box::from);
        Some(DerivedKey {
            result_id,
            layer,
            path,
            order,
        })
    }

    /// The composed edge a state key names, if this document still has it.
    /// The key's exact result id must equal the layer's current id.
    pub fn resolve_derived_key(&self, key: &DerivedKey) -> Option<usize> {
        let edge = *self.derived_index.get(&(key.layer, key.path, key.order))?;
        let current = self.results.get(self.layer_result[key.layer as usize])?;
        (current == key.result_id.as_deref()).then_some(edge)
    }

    pub fn resolve(&self, element: &ElementRef) -> Result<ElementIndex, ResolveError> {
        match element {
            ElementRef::Node(id) => self
                .node_index(id)
                .map(ElementIndex::Node)
                .ok_or(ResolveError::Unresolved),
            ElementRef::Edge(id) => self
                .edge_index(id)
                .map(ElementIndex::Edge)
                .ok_or(ResolveError::Unresolved),
            ElementRef::Derived(derived) => {
                let result_id = match &derived.result {
                    ResultRef::Local(index) => self.results.get(*index),
                    ResultRef::Exact(id) => self
                        .results
                        .find(id.as_deref())
                        .and_then(|index| self.results.get(index)),
                }
                .ok_or(ResolveError::Unresolved)?;
                self.resolve_derived_key(&DerivedKey {
                    result_id: result_id.map(Box::from),
                    layer: derived.layer,
                    path: derived.path,
                    order: derived.order,
                })
                .map(ElementIndex::Edge)
                .ok_or(ResolveError::Unresolved)
            }
            ElementRef::Aggregate(_) => Err(ResolveError::NeedsRender),
        }
    }

    /// Add the state identity of a resolved element to `set`.
    pub fn insert_into(&self, set: &mut ElementSet, element: ElementIndex) {
        match element {
            ElementIndex::Node(node) => {
                set.nodes.insert(self.node_uuid[node]);
            }
            ElementIndex::Edge(edge) => match self.derived_key(edge) {
                Some(key) => {
                    set.derived.insert(key);
                }
                None => {
                    set.edges.insert(self.edge_uuid[edge]);
                }
            },
        }
    }

    /// Focus target of a resolved element.
    pub fn focus_of(&self, element: ElementIndex) -> Focus {
        match element {
            ElementIndex::Node(node) => Focus::Entity(GraphEntity::Node(self.node_uuid[node])),
            ElementIndex::Edge(edge) => match self.derived_key(edge) {
                Some(key) => Focus::Derived(key),
                None => Focus::Entity(GraphEntity::Edge(self.edge_uuid[edge])),
            },
        }
    }

    /// Add a focus target's identity to `set`.
    pub fn insert_focus(&self, set: &mut ElementSet, focus: &Focus) {
        match focus {
            Focus::Entity(GraphEntity::Node(id)) => {
                set.nodes.insert(*id);
            }
            Focus::Entity(GraphEntity::Edge(id)) => {
                set.edges.insert(*id);
            }
            Focus::Derived(key) => {
                set.derived.insert(key.clone());
            }
        }
    }

    /// Local reference of a focus target; `None` for a derived key this
    /// document no longer resolves.
    pub fn focus_ref(&self, focus: &Focus) -> Option<ElementRef> {
        match focus {
            Focus::Entity(GraphEntity::Node(id)) => Some(ElementRef::Node(*id)),
            Focus::Entity(GraphEntity::Edge(id)) => Some(ElementRef::Edge(*id)),
            Focus::Derived(key) => self
                .resolve_derived_key(key)
                .map(|edge| self.edge_ref(edge)),
        }
    }

    /// Local references of a state set. Derived keys this document no longer
    /// resolves (another generation, a replaced result id) are omitted.
    pub fn refs_of(&self, set: &ElementSet) -> Vec<ElementRef> {
        let nodes = set.nodes.iter().map(|&id| ElementRef::Node(id));
        let edges = set.edges.iter().map(|&id| ElementRef::Edge(id));
        let derived = set
            .derived
            .iter()
            .filter_map(|key| self.resolve_derived_key(key))
            .map(|edge| self.edge_ref(edge));
        nodes.chain(edges).chain(derived).collect()
    }

    /// Rewrite a local derived ref to carry its exact result id so it can
    /// cross sessions; other kinds are already host-independent.
    pub fn to_transport(&self, element: &ElementRef) -> Option<ElementRef> {
        match element {
            ElementRef::Derived(derived) => {
                let ResultRef::Local(index) = derived.result else {
                    return Some(element.clone());
                };
                let id = self.results.get(index)?;
                Some(ElementRef::Derived(DerivedRef {
                    result: ResultRef::Exact(id.map(Box::from)),
                    ..derived.clone()
                }))
            }
            other => Some(other.clone()),
        }
    }
}
