//! Canonical base graph from GraphForge entity tables or raw UUID planes (§4.1).
//!
//! Accepted base tables (any mix, in order):
//! - Cypher entity results: struct columns carrying `node_uuid` (nodes),
//!   `edge_uuid` + `src_uuid`/`dst_uuid` (relationships), or `nodes` +
//!   `relationships` lists (paths), including lists of those structs;
//! - flat node tables with a `node_uuid` column;
//! - flat edge tables with `edge_uuid` plus `src_uuid`/`dst_uuid` or
//!   `source_uuid`/`target_uuid`.
//!
//! The same entity may appear in many rows (`RETURN a, r, b`), so identical
//! UUIDs are merged; a relationship seen twice must name the same endpoints.
//! Merges are counted, never silent. The canonical graph is never mutated by
//! any composition layer.
//!
//! A flat node table may carry an optional `parent_uuid` column (the compound
//! hierarchy; same name as the Python `GraphData` mapping default). Parents
//! resolve through the shared [`resolve_parents`] and must form a forest:
//! unknown parents, self-parents, and cycles fail the whole build.

use super::columns::{texts, uuids};
use super::{uuid_map, GfError, GfResult, Uuid, UuidKey, UuidMap, NIL_UUID};
use crate::arrow_ipc::{Column, DataType, Table};
use crate::graph::COSE_NO_PARENT;
use crate::projection::{
    resolve_parents, validate_parent_forest, ParentForestError, ProjectionError,
};

/// Hard bounds on the canonical base graph.
pub const MAX_BASE_NODES: usize = 20_000_000;
pub const MAX_BASE_EDGES: usize = 50_000_000;
/// Name-like node properties, in caption order.
pub const CAPTION_PROPERTIES: [&str; 3] = ["name", "title", "label"];
/// Per-label text bound (display labels are truncated far earlier).
pub const MAX_LABEL_BYTES: usize = 1024;
/// Optional flat-node-table column naming each node's compound parent.
pub const PARENT_FIELD: &str = "parent_uuid";

#[derive(Debug, Default)]
pub struct BaseGraph {
    pub node_uuid: Vec<Uuid>,
    /// Display name: the first non-empty of `name`, `title`, `label`
    /// ([`CAPTION_PROPERTIES`]), bounded.
    pub node_name: Vec<Option<String>>,
    /// First GraphForge label (`labels[0]`).
    pub node_type: Vec<Option<String>>,
    pub node_index: UuidMap,
    pub edge_uuid: Vec<Uuid>,
    pub edge_source: Vec<usize>,
    pub edge_target: Vec<usize>,
    /// Relationship type (`rel_type`).
    pub edge_type: Vec<Option<String>>,
    pub edge_index: UuidMap,
    pub directed: bool,
    /// Rows that repeated an already-collected entity.
    pub merged_entities: u64,
    /// Compound parent per node (dense base index, [`COSE_NO_PARENT`] for
    /// roots). Empty when no node table carried `parent_uuid`.
    pub node_parent: Vec<u64>,
}

#[derive(Default)]
struct Collector {
    graph: BaseGraph,
    /// `(edge uuid, source uuid, target uuid, type)` resolved after all nodes.
    pending_edges: Vec<(Uuid, Uuid, Uuid, Option<String>)>,
    pending_index: UuidMap,
    /// Declared parent per collected node, parallel to `graph.node_uuid`:
    /// `None` no `parent_uuid` row seen, `Some(None)` declared root (null),
    /// `Some(Some(p))` declared under `p`.
    pending_parents: Vec<Option<Option<Uuid>>>,
    /// Whether any node table carried a `parent_uuid` column.
    has_parents: bool,
}

fn bounded_label(text: Option<&str>) -> Option<String> {
    let text = text?;
    if text.len() <= MAX_LABEL_BYTES {
        return Some(text.to_owned());
    }
    let mut end = MAX_LABEL_BYTES;
    while !text.is_char_boundary(end) {
        end -= 1;
    }
    Some(text[..end].to_owned())
}

fn null_identity(field: &str) -> GfError {
    GfError::new(
        "GF_BASE_NULL_IDENTITY",
        format!("base field \"{field}\" contains a null or nil UUID"),
    )
    .with_field(field)
}

impl Collector {
    fn node(&mut self, id: Uuid, name: Option<&str>, kind: Option<&str>) -> GfResult<()> {
        if id == NIL_UUID {
            return Err(null_identity("node_uuid"));
        }
        let next = self.graph.node_uuid.len();
        match self.graph.node_index.entry(UuidKey(id)) {
            std::collections::hash_map::Entry::Occupied(slot) => {
                self.graph.merged_entities += 1;
                let i = *slot.get();
                if self.graph.node_name[i].is_none() {
                    self.graph.node_name[i] = bounded_label(name);
                }
                if self.graph.node_type[i].is_none() {
                    self.graph.node_type[i] = bounded_label(kind);
                }
            }
            std::collections::hash_map::Entry::Vacant(slot) => {
                if next >= MAX_BASE_NODES {
                    return Err(GfError::new(
                        "GF_COMPOSE_TOO_LARGE",
                        "base graph exceeds the node bound",
                    ));
                }
                slot.insert(next);
                self.graph.node_uuid.push(id);
                self.graph.node_name.push(bounded_label(name));
                self.graph.node_type.push(bounded_label(kind));
                self.pending_parents.push(None);
            }
        }
        Ok(())
    }

    /// Record a `parent_uuid` row for the already-collected node `id` (`None`
    /// is an explicit root). Repeated rows must declare the same thing: a root
    /// and a parented declaration conflict, in either order.
    fn parent(&mut self, id: Uuid, parent: Option<Uuid>) -> GfResult<()> {
        let dense = self.graph.node_index[&UuidKey(id)];
        match self.pending_parents[dense] {
            Some(existing) if existing != parent => Err(GfError::new(
                "GF_BASE_PARENT_CONFLICT",
                "a node UUID appears with two different parent declarations",
            )),
            _ => {
                self.pending_parents[dense] = Some(parent);
                Ok(())
            }
        }
    }

    fn edge(&mut self, id: Uuid, source: Uuid, target: Uuid, kind: Option<&str>) -> GfResult<()> {
        if id == NIL_UUID {
            return Err(null_identity("edge_uuid"));
        }
        if source == NIL_UUID || target == NIL_UUID {
            return Err(null_identity("edge endpoint"));
        }
        let next = self.pending_edges.len();
        match self.pending_index.entry(UuidKey(id)) {
            std::collections::hash_map::Entry::Occupied(slot) => {
                let existing = &self.pending_edges[*slot.get()];
                if existing.1 != source || existing.2 != target {
                    return Err(GfError::new(
                        "GF_BASE_EDGE_CONFLICT",
                        "a relationship UUID appears with two different endpoint pairs",
                    ));
                }
                self.graph.merged_entities += 1;
            }
            std::collections::hash_map::Entry::Vacant(slot) => {
                if next >= MAX_BASE_EDGES {
                    return Err(GfError::new(
                        "GF_COMPOSE_TOO_LARGE",
                        "base graph exceeds the edge bound",
                    ));
                }
                slot.insert(next);
                self.pending_edges
                    .push((id, source, target, bounded_label(kind)));
            }
        }
        Ok(())
    }

    /// Optional text child: absent or non-text columns yield no labels.
    #[inline(never)]
    fn optional_text<'a>(column: Option<Column<'_, 'a>>, len: usize) -> Vec<Option<&'a str>> {
        match column {
            Some(column) if matches!(column.field.data_type, DataType::Utf8 { .. }) => {
                texts(&column).unwrap_or_else(|_| vec![None; len])
            }
            _ => vec![None; len],
        }
    }

    /// Per row, the first non-empty text among [`CAPTION_PROPERTIES`]
    /// (`columns` in that order).
    fn captions<'a>(
        columns: [Option<Column<'_, 'a>>; CAPTION_PROPERTIES.len()],
        len: usize,
    ) -> Vec<Option<&'a str>> {
        // Merge one candidate at a time, sharing the text decoder instead of
        // materializing an array of three vectors (also bounds WASM code size).
        let mut captions = vec![None; len];
        for column in columns.into_iter().flatten() {
            for (caption, text) in captions
                .iter_mut()
                .zip(Self::optional_text(Some(column), len))
            {
                if caption.is_none() {
                    *caption = text.filter(|text| !text.is_empty());
                }
            }
        }
        captions
    }

    /// First item of an optional `labels: list<utf8>` child.
    fn first_labels<'a>(column: Option<Column<'_, 'a>>, len: usize) -> Vec<Option<&'a str>> {
        let Some(column) = column else {
            return vec![None; len];
        };
        let is_text_list = matches!(column.field.data_type, DataType::List { .. })
            && matches!(column.field.children[0].data_type, DataType::Utf8 { .. });
        if !is_text_list {
            return vec![None; len];
        }
        let mut out = Vec::with_capacity(len);
        let _ = column.for_each::<()>(|array, row| {
            let first = if array.is_valid(row) {
                let (start, end) = array.list_range(row).unwrap();
                let child = array.list_child().unwrap();
                (start < end && child.is_valid(start))
                    .then(|| std::str::from_utf8(child.var(start).unwrap()).unwrap())
            } else {
                None
            };
            out.push(first);
            Ok(())
        });
        out
    }

    fn node_struct(&mut self, column: &Column<'_, '_>) -> GfResult<()> {
        let ids = uuids(&column.child("node_uuid").unwrap(), true)?;
        let names = Self::captions(CAPTION_PROPERTIES.map(|name| column.child(name)), ids.len());
        let kinds = Self::first_labels(column.child("labels"), ids.len());
        for ((id, name), kind) in ids.into_iter().zip(names).zip(kinds) {
            self.node(id.ok_or_else(|| null_identity("node_uuid"))?, name, kind)?;
        }
        Ok(())
    }

    fn edge_struct(&mut self, column: &Column<'_, '_>) -> GfResult<()> {
        let ids = uuids(&column.child("edge_uuid").unwrap(), true)?;
        let (source, target) = endpoint_names(
            column.field.children.iter().map(|f| f.name.as_str()),
        )
        .ok_or_else(|| {
            GfError::new(
                "GF_BASE_SCHEMA",
                "relationship entities need src_uuid/dst_uuid or source_uuid/target_uuid",
            )
        })?;
        let sources = uuids(&column.child(source).unwrap(), true)?;
        let targets = uuids(&column.child(target).unwrap(), true)?;
        let kinds = Self::optional_text(column.child("rel_type"), ids.len());
        for (((id, s), t), kind) in ids.into_iter().zip(sources).zip(targets).zip(kinds) {
            self.edge(
                id.ok_or_else(|| null_identity("edge_uuid"))?,
                s.ok_or_else(|| null_identity(source))?,
                t.ok_or_else(|| null_identity(target))?,
                kind,
            )?;
        }
        Ok(())
    }

    /// Walk one column for entities; returns whether it held any.
    fn entities(&mut self, column: &Column<'_, '_>, depth: usize) -> GfResult<bool> {
        if depth > 4 {
            return Ok(false);
        }
        match column.field.data_type {
            DataType::List { .. } => {
                let items = column.flatten().unwrap();
                self.entities(&items, depth + 1)
            }
            DataType::Struct => {
                let has = |name: &str| column.field.child(name).is_some();
                if has("node_uuid") {
                    self.node_struct(column)?;
                    Ok(true)
                } else if has("edge_uuid") {
                    self.edge_struct(column)?;
                    Ok(true)
                } else if has("nodes") && has("relationships") {
                    let nodes = self.entities(&column.child("nodes").unwrap(), depth + 1)?;
                    let rels = self.entities(&column.child("relationships").unwrap(), depth + 1)?;
                    Ok(nodes || rels)
                } else {
                    Ok(false)
                }
            }
            _ => Ok(false),
        }
    }

    fn table(&mut self, table: &Table<'_>) -> GfResult<()> {
        let names: Vec<&str> = table
            .schema
            .fields
            .iter()
            .map(|f| f.name.as_str())
            .collect();
        if names.contains(&"edge_uuid") {
            // Flat relationship table.
            let (source, target) = endpoint_names(names.iter().copied()).ok_or_else(|| {
                GfError::new(
                    "GF_BASE_SCHEMA",
                    "a flat edge table needs src_uuid/dst_uuid or source_uuid/target_uuid",
                )
            })?;
            let ids = uuids(&table.column("edge_uuid").unwrap(), true)?;
            let sources = uuids(&table.column(source).unwrap(), true)?;
            let targets = uuids(&table.column(target).unwrap(), true)?;
            let kinds = Self::optional_text(
                table
                    .column("rel_type")
                    .or_else(|| table.column("relationship_type")),
                ids.len(),
            );
            for (((id, s), t), kind) in ids.into_iter().zip(sources).zip(targets).zip(kinds) {
                self.edge(
                    id.ok_or_else(|| null_identity("edge_uuid"))?,
                    s.ok_or_else(|| null_identity(source))?,
                    t.ok_or_else(|| null_identity(target))?,
                    kind,
                )?;
            }
            return Ok(());
        }
        if names.contains(&"node_uuid") {
            // Flat node table.
            let ids = uuids(&table.column("node_uuid").unwrap(), true)?;
            let names = Self::captions(CAPTION_PROPERTIES.map(|name| table.column(name)), ids.len());
            let kinds = Self::first_labels(table.column("labels"), ids.len());
            let parents = match table.column(PARENT_FIELD) {
                Some(column) => {
                    self.has_parents = true;
                    Some(uuids(&column, true)?)
                }
                None => None,
            };
            for (row, ((id, name), kind)) in ids.into_iter().zip(names).zip(kinds).enumerate() {
                let id = id.ok_or_else(|| null_identity("node_uuid"))?;
                self.node(id, name, kind)?;
                if let Some(parents) = &parents {
                    self.parent(id, parents[row])?;
                }
            }
            return Ok(());
        }
        let mut found = false;
        for index in 0..table.schema.fields.len() {
            found |= self.entities(&table.column_at(index), 0)?;
        }
        if !found {
            return Err(GfError::new(
                "GF_BASE_SCHEMA",
                "base table carries no GraphForge node or relationship identity",
            ));
        }
        Ok(())
    }

    /// Resolve and validate the compound hierarchy (all-or-nothing).
    fn resolve_hierarchy(&mut self) -> GfResult<()> {
        if !self.has_parents {
            return Ok(());
        }
        let ids: Vec<Uuid> = self
            .pending_parents
            .iter()
            .map(|parent| parent.flatten().unwrap_or(NIL_UUID))
            .collect();
        let validity: Vec<u8> = self
            .pending_parents
            .iter()
            .map(|parent| u8::from(parent.flatten().is_some()))
            .collect();
        let (parents, validity) = resolve_parents(&ids, &validity, ids.len(), |id| {
            self.graph.node_index.get(&UuidKey(*id)).map(|&i| i as u64)
        })
        .map_err(|error| match error {
            ProjectionError::MissingEndpoint => GfError::new(
                "GF_BASE_PARENT_UNKNOWN",
                "a node names a parent that is absent from the base nodes",
            ),
            ProjectionError::MalformedUuid => null_identity(PARENT_FIELD),
            _ => GfError::new(
                "GF_COMPOSE_REQUEST_INVALID",
                "base parent planes are malformed",
            ),
        })?;
        validate_parent_forest(&parents, &validity).map_err(|error| match error {
            ParentForestError::SelfParent(_) => {
                GfError::new("GF_BASE_PARENT_SELF", "a node names itself as its parent")
            }
            ParentForestError::Cycle(_) => GfError::new(
                "GF_BASE_PARENT_CYCLE",
                "the base node parents contain a cycle",
            ),
        })?;
        self.graph.node_parent = parents
            .iter()
            .zip(&validity)
            .map(|(&parent, &valid)| if valid == 1 { parent } else { COSE_NO_PARENT })
            .collect();
        Ok(())
    }

    fn finish(mut self) -> GfResult<BaseGraph> {
        let mut missing = 0u64;
        let edges = std::mem::take(&mut self.pending_edges);
        self.graph.edge_uuid.reserve(edges.len());
        for (id, source, target, kind) in edges {
            let s = self.graph.node_index.get(&UuidKey(source));
            let t = self.graph.node_index.get(&UuidKey(target));
            match (s, t) {
                (Some(&s), Some(&t)) => {
                    self.graph
                        .edge_index
                        .insert(UuidKey(id), self.graph.edge_uuid.len());
                    self.graph.edge_uuid.push(id);
                    self.graph.edge_source.push(s);
                    self.graph.edge_target.push(t);
                    self.graph.edge_type.push(kind);
                }
                _ => missing += 1,
            }
        }
        if missing > 0 {
            return Err(GfError::new(
                "GF_BASE_ENDPOINT_MISSING",
                format!("{missing} relationship(s) name an endpoint absent from the base nodes"),
            ));
        }
        if self.graph.node_uuid.is_empty() {
            return Err(GfError::new("GF_BASE_EMPTY", "the base graph has no nodes"));
        }
        self.resolve_hierarchy()?;
        Ok(self.graph)
    }
}

fn endpoint_names<'n>(
    names: impl Iterator<Item = &'n str>,
) -> Option<(&'static str, &'static str)> {
    let names: Vec<&str> = names.collect();
    let has = |wanted: &str| names.contains(&wanted);
    if has("src_uuid") && has("dst_uuid") {
        Some(("src_uuid", "dst_uuid"))
    } else if has("source_uuid") && has("target_uuid") {
        Some(("source_uuid", "target_uuid"))
    } else {
        None
    }
}

/// Raw identity planes (hosts that already hold packed UUID columns).
pub struct RawPlanes<'a> {
    pub node_uuid: &'a [Uuid],
    pub edge_uuid: &'a [Uuid],
    pub edge_source: &'a [Uuid],
    pub edge_target: &'a [Uuid],
}

/// Build the canonical base graph from entity tables and/or raw planes.
pub fn build(
    tables: &[Table<'_>],
    planes: Option<RawPlanes<'_>>,
    directed: bool,
) -> GfResult<BaseGraph> {
    let mut collector = Collector {
        graph: BaseGraph {
            node_index: uuid_map(0),
            edge_index: uuid_map(0),
            directed,
            ..Default::default()
        },
        pending_edges: Vec::new(),
        pending_index: uuid_map(0),
        pending_parents: Vec::new(),
        has_parents: false,
    };
    if let Some(planes) = planes {
        if planes.edge_source.len() != planes.edge_uuid.len()
            || planes.edge_target.len() != planes.edge_uuid.len()
        {
            return Err(GfError::new(
                "GF_COMPOSE_REQUEST_INVALID",
                "base edge UUID, source, and target planes differ in length",
            ));
        }
        for &id in planes.node_uuid {
            collector.node(id, None, None)?;
        }
        for i in 0..planes.edge_uuid.len() {
            collector.edge(
                planes.edge_uuid[i],
                planes.edge_source[i],
                planes.edge_target[i],
                None,
            )?;
        }
    }
    for table in tables {
        collector.table(table)?;
    }
    collector.finish()
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::arrow_ipc::read_table;

    fn load(name: &str) -> Vec<u8> {
        std::fs::read(format!(
            "{}/../../tests/fixtures/graphforge/results/{name}.arrow",
            env!("CARGO_MANIFEST_DIR")
        ))
        .unwrap()
    }

    #[test]
    fn cypher_bases_collect_every_entity_once() {
        let nodes = load("base-cyclic-nodes");
        let edges = load("base-cyclic-edges");
        let tables = [read_table(&nodes).unwrap(), read_table(&edges).unwrap()];
        let graph = build(&tables, None, true).unwrap();
        assert_eq!(graph.node_uuid.len(), 4);
        assert_eq!(graph.edge_uuid.len(), 5);
        assert_eq!(graph.node_type[0].as_deref(), Some("Person"));
        assert!(graph.node_name.iter().all(|n| n.is_some()));
        assert_eq!(graph.edge_type[0].as_deref(), Some("KNOWS"));
        assert_eq!(graph.merged_entities, 0);
    }

    #[test]
    fn row_tables_merge_repeated_entities() {
        // `RETURN a, r, b` repeats nodes across rows; paths repeat everything.
        let edges = load("cypher-edges");
        let paths = load("cypher-paths");
        let tables = [read_table(&edges).unwrap(), read_table(&paths).unwrap()];
        let graph = build(&tables, None, true).unwrap();
        assert_eq!(graph.node_uuid.len(), 4);
        assert_eq!(graph.edge_uuid.len(), 5);
        assert!(graph.merged_entities > 0);
    }

    #[test]
    fn edges_without_their_nodes_fail_closed() {
        let edges = load("base-cyclic-edges");
        let tables = [read_table(&edges).unwrap()];
        let error = build(&tables, None, true).unwrap_err();
        assert_eq!(error.code, "GF_BASE_ENDPOINT_MISSING");
        assert!(error.message.starts_with("5 relationship"));
    }

    #[test]
    fn non_entity_tables_are_rejected() {
        let scalars = load("cypher-scalars");
        let tables = [read_table(&scalars).unwrap()];
        assert_eq!(
            build(&tables, None, true).unwrap_err().code,
            "GF_BASE_SCHEMA"
        );
    }

    #[test]
    fn flat_text_uuid_tables_are_accepted() {
        let root = format!(
            "{}/../../tests/fixtures/graphforge",
            env!("CARGO_MANIFEST_DIR")
        );
        let nodes = std::fs::read(format!("{root}/airports_nodes.arrow")).unwrap();
        let edges = std::fs::read(format!("{root}/airports_edges.arrow")).unwrap();
        let tables = [read_table(&nodes).unwrap(), read_table(&edges).unwrap()];
        let graph = build(&tables, None, true).unwrap();
        assert_eq!(graph.node_uuid.len(), 3);
        assert_eq!(graph.edge_uuid.len(), 4);
        let dup = std::fs::read(format!("{root}/airports_edges_missing_endpoint.arrow")).unwrap();
        let tables = [read_table(&nodes).unwrap(), read_table(&dup).unwrap()];
        assert_eq!(
            build(&tables, None, true).unwrap_err().code,
            "GF_BASE_ENDPOINT_MISSING"
        );
    }

    #[test]
    fn flat_node_captions_prefer_name_over_label() {
        // `captions_nodes.arrow` carries both columns (#934): `name` wins, and
        // a row without one falls through to `label`.
        let nodes = std::fs::read(format!(
            "{}/../../tests/fixtures/graphforge/captions_nodes.arrow",
            env!("CARGO_MANIFEST_DIR")
        ))
        .unwrap();
        let graph = build(&[read_table(&nodes).unwrap()], None, true).unwrap();
        assert_eq!(
            graph.node_name,
            [Some("Name A".to_owned()), Some("Label B".to_owned())]
        );
    }

    #[test]
    fn conflicting_relationship_endpoints_fail() {
        let a = [1; 16];
        let b = [2; 16];
        let e = [9; 16];
        let planes = RawPlanes {
            node_uuid: &[a, b],
            edge_uuid: &[e, e],
            edge_source: &[a, b],
            edge_target: &[b, a],
        };
        assert_eq!(
            build(&[], Some(planes), true).unwrap_err().code,
            "GF_BASE_EDGE_CONFLICT"
        );
    }

    fn hierarchy_base(nodes: &str) -> GfResult<BaseGraph> {
        let nodes = std::fs::read(format!(
            "{}/../../tests/fixtures/graphforge/{nodes}.arrow",
            env!("CARGO_MANIFEST_DIR")
        ))
        .unwrap();
        let edges = load("base-dag-edges");
        let tables = [read_table(&nodes).unwrap(), read_table(&edges).unwrap()];
        build(&tables, None, true)
    }

    #[test]
    fn parent_uuid_column_resolves_to_a_dense_forest() {
        let graph = hierarchy_base("hierarchy_dag_nodes").unwrap();
        assert_eq!(graph.node_parent, [COSE_NO_PARENT, 0, 1, COSE_NO_PARENT]);
        // Tables without the column carry no hierarchy plane at all.
        let (nodes, edges) = (load("base-dag-nodes"), load("base-dag-edges"));
        let tables = [read_table(&nodes).unwrap(), read_table(&edges).unwrap()];
        let plain = build(&tables, None, true).unwrap();
        assert!(plain.node_parent.is_empty());
    }

    #[test]
    fn invalid_hierarchies_fail_atomically_with_stable_codes() {
        for (fixture, code) in [
            (
                "hierarchy_dag_nodes_unknown_parent",
                "GF_BASE_PARENT_UNKNOWN",
            ),
            ("hierarchy_dag_nodes_self_parent", "GF_BASE_PARENT_SELF"),
            ("hierarchy_dag_nodes_cycle", "GF_BASE_PARENT_CYCLE"),
        ] {
            assert_eq!(hierarchy_base(fixture).unwrap_err().code, code, "{fixture}");
        }
    }

    #[test]
    fn a_root_and_a_parent_declaration_for_one_node_conflict_in_either_order() {
        let read_fixture = |name: &str| {
            std::fs::read(format!(
                "{}/../../tests/fixtures/graphforge/{name}.arrow",
                env!("CARGO_MANIFEST_DIR")
            ))
            .unwrap()
        };
        let (roots, forest, edges) = (
            read_fixture("hierarchy_dag_roots"),
            read_fixture("hierarchy_dag_nodes"),
            load("base-dag-edges"),
        );
        let build_order = |first: &[u8], second: &[u8]| {
            let tables = [
                read_table(first).unwrap(),
                read_table(second).unwrap(),
                read_table(&edges).unwrap(),
            ];
            build(&tables, None, true)
        };
        for (first, second) in [(&roots, &forest), (&forest, &roots)] {
            assert_eq!(
                build_order(first, second).unwrap_err().code,
                "GF_BASE_PARENT_CONFLICT"
            );
        }
        // Agreeing repeats are not a conflict: null twice is the same root.
        let graph = build_order(&roots, &roots).unwrap();
        assert_eq!(graph.node_parent, [COSE_NO_PARENT; 4]);
    }
}
