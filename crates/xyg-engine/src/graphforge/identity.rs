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

use std::marker::PhantomData;

use super::compose::NONE_U64;
use super::composed::ComposedDocument;
use super::{GfError, GfResult, Uuid, NIL_UUID};
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
    buckets: crate::index_slots::IndexSlots,
    reserved: usize,
    hash: PhantomData<H>,
}

impl<H: ResultHash> Default for ResultTable<H> {
    fn default() -> Self {
        Self {
            strings: vec![None],
            buckets: crate::index_slots::IndexSlots::new(0).unwrap(),
            reserved: 0,
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
            .find_hashed(H::hash(id.as_bytes()), &|index| {
                self.strings[index].as_deref() == Some(id)
            })?
            .1
            .map(|i| i as u32)
    }

    pub fn intern(&mut self, id: Option<&str>) -> u32 {
        if let Some(index) = self.find(id) {
            return index;
        }
        let id = id.expect("the absent id is entry 0");
        if self.strings.len() >= self.reserved {
            self.reserved = self
                .strings
                .len()
                .checked_add(1)
                .and_then(usize::checked_next_power_of_two)
                .expect("result capacity")
                .max(4);
            self.buckets =
                crate::index_slots::IndexSlots::new(self.reserved).expect("result capacity");
            for i in 1..self.strings.len() {
                let key = self.strings[i].as_deref().unwrap();
                let (slot, _) = self
                    .buckets
                    .find_hashed(H::hash(key.as_bytes()), &|j| {
                        self.strings[j].as_deref() == Some(key)
                    })
                    .unwrap();
                self.buckets.set(slot, i);
            }
        }
        self.insert_reserved(id)
    }
    fn insert_reserved(&mut self, id: &str) -> u32 {
        let index = self.strings.len();
        let (slot, prior) = self
            .buckets
            .find_hashed(H::hash(id.as_bytes()), &|j| {
                self.strings[j].as_deref() == Some(id)
            })
            .unwrap();
        debug_assert_eq!(prior, None);
        self.strings.push(Some(id.into()));
        self.buckets.set(slot, index);
        index as u32
    }
    fn for_layers(count: usize) -> GfResult<Self> {
        if count == 0 {
            return Ok(Self::default());
        }
        if count > super::container::MAX_ENTRIES {
            return Err(invalid("result capacity overflow"));
        }
        let reserved = count
            .checked_add(1)
            .ok_or_else(|| invalid("result capacity overflow"))?;
        let mut strings = Vec::with_capacity(reserved);
        strings.push(None);
        Ok(Self {
            strings,
            buckets: crate::index_slots::IndexSlots::new(reserved)
                .ok_or_else(|| invalid("result capacity overflow"))?,
            reserved,
            hash: PhantomData,
        })
    }
    fn intern_layer(&mut self, id: Option<&str>) -> u32 {
        if let Some(index) = self.find(id) {
            return index;
        }
        // One source-owned entry per layer was reserved before decoding IDs.
        assert!(self.strings.len() < self.reserved);
        self.insert_reserved(id.unwrap())
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
    node_index: UuidIndex,
    /// NIL for derived edges.
    edge_uuid: Vec<Uuid>,
    /// Persisted edges only.
    edge_index: UuidIndex,
    /// `(layer, path, order)` of each derived edge.
    edge_derived: Vec<Option<(u32, u64, u64)>>,
    derived_index: crate::index_slots::IndexSlots,
    /// Result-table entry of each layer.
    layer_result: Vec<u32>,
    results: ResultTable<H>,
}

fn invalid(message: &str) -> GfError {
    GfError::new("GF_INTERACTION_INVALID", message)
}

#[derive(Clone)]
struct UuidIndex(crate::index_slots::IndexSlots);
fn uuid_words(id: &Uuid) -> [u64; 2] {
    [
        u64::from_le_bytes(id[..8].try_into().unwrap()),
        u64::from_le_bytes(id[8..].try_into().unwrap()),
    ]
}
impl UuidIndex {
    fn new(count: usize) -> GfResult<Self> {
        crate::index_slots::IndexSlots::new(count)
            .map(Self)
            .ok_or_else(|| invalid("identity capacity overflow"))
    }
    fn insert(&mut self, index: usize, ids: &[Uuid]) -> bool {
        let (slot, prior) = self
            .0
            .find(uuid_words(&ids[index]), &|i| uuid_words(&ids[i]))
            .expect("reserved identity index");
        if prior.is_some() {
            return false;
        }
        self.0.set(slot, index);
        true
    }
    fn get(&self, id: &Uuid, ids: &[Uuid]) -> Option<usize> {
        self.0
            .find(uuid_words(id), &|i| uuid_words(&ids[i]))
            .and_then(|(_, i)| i)
    }
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

        let mut results = ResultTable::for_layers(doc.layer_count())?;
        let layer_result = (0..doc.layer_count())
            .map(|layer| Ok(results.intern_layer(doc.result_id(layer)?.as_deref())))
            .collect::<GfResult<Vec<_>>>()?;

        let mut node_index = UuidIndex::new(node_uuid.len())?;
        for (dense, id) in node_uuid.iter().enumerate() {
            if *id == NIL_UUID || !node_index.insert(dense, &node_uuid) {
                return Err(invalid("node UUIDs must be unique and non-nil"));
            }
        }
        let mut edge_index = UuidIndex::new(edge_count)?;
        let mut edge_derived = if derived.iter().any(|&d| d != 0) {
            vec![None; edge_count]
        } else {
            Vec::new()
        };
        let mut derived_index = crate::index_slots::IndexSlots::new(if edge_derived.is_empty() {
            0
        } else {
            edge_count
        })
        .ok_or_else(|| invalid("derived capacity overflow"))?;
        let mut layer_rows: Vec<Option<&[u8]>> = vec![None; layer_result.len()];
        for edge in 0..edge_count {
            if derived[edge] == 0 {
                let id = edge_uuid[edge];
                if id == NIL_UUID {
                    return Err(invalid("persisted edge UUIDs must be unique and non-nil"));
                }
                if !edge_index.insert(edge, &edge_uuid) {
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
                let rows = match layer_rows[layer as usize] {
                    Some(rows) => rows,
                    None => {
                        let rows = doc
                            .rows(layer, false, edge_count)?
                            .ok_or_else(|| invalid("a derived edge has no result rows"))?;
                        layer_rows[layer as usize] = Some(rows);
                        rows
                    }
                };
                let row = u64::from_le_bytes(rows[edge * 8..edge * 8 + 8].try_into().unwrap());
                if row == NONE_U64 {
                    return Err(invalid("a derived edge has no result row"));
                }
                row
            } else {
                u64::try_from(edge_order[edge])
                    .map_err(|_| invalid("an overlay edge has no step order"))?
            };
            let key = (layer, edge_path[edge], order);
            let (slot, prior) = derived_index
                .find_hashed(
                    crate::index_slots::mixed_words(key.1, key.2) ^ u64::from(key.0),
                    &|i| edge_derived[i] == Some(key),
                )
                .unwrap();
            if prior.is_some() {
                return Err(invalid("derived edge keys must be unique"));
            }
            edge_derived[edge] = Some(key);
            derived_index.set(slot, edge);
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

    pub(crate) fn plain_retained_bytes(&self) -> Option<usize> {
        if !self.edge_derived.is_empty()
            || !self.layer_result.is_empty()
            || self.derived_index.bytes() != 0
        {
            return None;
        }
        self.node_uuid
            .capacity()
            .checked_add(self.edge_uuid.capacity())?
            .checked_mul(16)?
            .checked_add(
                self.node_index
                    .0
                    .bytes()
                    .checked_add(self.edge_index.0.bytes())?,
            )
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
        self.edge_uuid.iter().copied().filter(|id| *id != NIL_UUID)
    }

    /// Whether a composed edge is derived (NIL UUID) rather than persisted.
    pub fn is_derived(&self, edge: usize) -> bool {
        self.edge_derived.get(edge).is_some_and(Option::is_some)
    }

    pub fn node_index(&self, id: &Uuid) -> Option<usize> {
        self.node_index.get(id, &self.node_uuid)
    }

    pub fn edge_index(&self, id: &Uuid) -> Option<usize> {
        self.edge_index.get(id, &self.edge_uuid)
    }

    pub fn node_ref(&self, node: usize) -> ElementRef {
        ElementRef::Node(self.node_uuid[node])
    }

    /// Local reference of a composed edge.
    pub fn edge_ref(&self, edge: usize) -> ElementRef {
        match self.edge_derived.get(edge).copied().flatten() {
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
        let (layer, path, order) = self.edge_derived.get(edge).copied().flatten()?;
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
        let exact = (key.layer, key.path, key.order);
        let edge = self
            .derived_index
            .find_hashed(
                crate::index_slots::mixed_words(key.path, key.order) ^ u64::from(key.layer),
                &|i| self.edge_derived[i] == Some(exact),
            )?
            .1?;
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
