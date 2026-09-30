//! Rust-owned GraphForge result composition (spec §4) and the `XYGF`
//! composition document (spec §5.2).
//!
//! [`compose_bytes`] is the single entry point every host calls (native C ABI
//! and direct-browser WASM): request bytes in, document bytes out. Failures
//! are documents too (`status = 1` with a stable code), so both hosts decode
//! one format and native/WASM equivalence is a byte comparison.

use std::collections::{BTreeMap, HashMap};

use super::base::{self, BaseGraph, RawPlanes};
use super::columns::{f64s, i64s, texts, uuids};
use super::container::{Builder, DOCUMENT_MAGIC};
use super::ledger::{self, Composition, Intent, Role, SchemaEntry};
use super::recognize::{recognize, Recognized};
use super::request::{self, ExtraPolicy, LayerRequest, MissingPolicy, Request};
use super::{GfError, GfResult, UuidKey};
use crate::arrow_ipc::{read_table, DataType, Table};
use crate::graph_style::{semantic_palette, FLAG_DISABLED, THEME_DARK, THEME_LIGHT};

/// Version of the composition semantics carried by `XYGF` documents. Bumps
/// when a plane's meaning changes; added sections do not bump it.
pub const COMPOSITION_VERSION: u32 = 1;
/// Absent row / index sentinel in u64 planes.
pub const NONE_U64: u64 = u64::MAX;
/// Absent layer sentinel in u32 planes.
pub const NONE_U32: u32 = u32::MAX;

/// Node status codes (combined across layers by maximum).
pub const NODE_STATUS_MEMBER: u8 = 1;
/// Node property columns carried per layer (canonical fields included).
pub const MAX_PROPERTY_COLUMNS: usize = 32;
/// Class codes available to group layers before bucketing.
const GROUP_CODES: usize = 7;

/// Legend row side.
pub const LEGEND_NODE: u8 = 0;
pub const LEGEND_EDGE: u8 = 1;
/// Legend row field: 0 class, 1 epistemic, 2 status (semantic planes), 3 the
/// disabled context state.
pub const LEGEND_FIELD_CONTEXT: u8 = 3;

/// A recorded, value-free composition decision (never silent; §28).
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Decision {
    pub code: &'static str,
    pub layer: Option<usize>,
    pub count: u64,
}

struct Layer<'a> {
    index: usize,
    request: &'a LayerRequest<'a>,
    table: Table<'a>,
    recognized: Recognized,
    missing: MissingPolicy,
    extra: ExtraPolicy,
    /// Result rows to compose, in order.
    rows: Vec<usize>,
}

impl Layer<'_> {
    fn entry(&self) -> &'static SchemaEntry {
        self.recognized.entry
    }

    fn field(&self, role: Role) -> Option<&'static str> {
        self.entry()
            .fields
            .iter()
            .find(|f| f.role == role)
            .map(|f| f.name)
    }

    fn column_f64(&self, name: &str) -> GfResult<Vec<f64>> {
        let values = f64s(&self.table.column(name).unwrap())?;
        Ok(values.into_iter().map(|v| v.unwrap_or(f64::NAN)).collect())
    }
}

#[derive(Default)]
struct LayerOut {
    value_names: Vec<String>,
    /// Text property columns (node layers) and their row-major values.
    text_names: Vec<String>,
    node_texts: Option<Vec<String>>,
    node_values: Option<Vec<f64>>,
    edge_values: Option<Vec<f64>>,
    node_rows: Option<Vec<u64>>,
    edge_rows: Option<Vec<u64>>,
    matched: u64,
    missing: u64,
    extra: u64,
}

struct Planes<'b> {
    base: &'b BaseGraph,
    node_class: Vec<u8>,
    node_epistemic: Vec<u8>,
    node_status: Vec<u8>,
    node_metric: Vec<f64>,
    node_flags: Vec<u32>,
    node_label: Vec<Option<String>>,
    node_priority: Vec<f64>,
    node_hidden: Vec<bool>,
    edge_class: Vec<u8>,
    edge_epistemic: Vec<u8>,
    edge_status: Vec<u8>,
    edge_metric: Vec<f64>,
    edge_flags: Vec<u32>,
    edge_hidden: Vec<bool>,
    edge_reversed: Vec<bool>,
    owners: HashMap<&'static str, usize>,
    legend: BTreeMap<(u8, u8, u8), String>,
    decisions: Vec<Decision>,
    layers: Vec<LayerOut>,
}

fn layer_error(code: &'static str, layer: usize, message: String) -> GfError {
    GfError::new(code, message).in_layer(layer)
}

impl<'b> Planes<'b> {
    fn new(base: &'b BaseGraph) -> Self {
        let n = base.node_uuid.len();
        let e = base.edge_uuid.len();
        Self {
            base,
            node_class: vec![0; n],
            node_epistemic: vec![0; n],
            node_status: vec![0; n],
            node_metric: vec![f64::NAN; n],
            node_flags: vec![0; n],
            node_label: base.node_name.clone(),
            node_priority: vec![0.0; n],
            node_hidden: vec![false; n],
            edge_class: vec![0; e],
            edge_epistemic: vec![0; e],
            edge_status: vec![0; e],
            edge_metric: vec![f64::NAN; e],
            edge_flags: vec![0; e],
            edge_hidden: vec![false; e],
            edge_reversed: vec![false; e],
            owners: HashMap::new(),
            legend: BTreeMap::new(),
            decisions: Vec::new(),
            layers: Vec::new(),
        }
    }

    fn decide(&mut self, code: &'static str, layer: Option<usize>, count: u64) {
        if count > 0 {
            self.decisions.push(Decision { code, layer, count });
        }
    }

    /// Exclusive ownership of one paint channel; a second writer fails closed.
    fn claim(&mut self, channel: &'static str, layer: &Layer<'_>) -> GfResult<()> {
        if let Some(&owner) = self.owners.get(channel) {
            return Err(layer_error(
                "GF_COMPOSE_CHANNEL_CONFLICT",
                layer.index,
                format!(
                    "{} is already written by result layer {owner}; compose one {} layer per channel",
                    channel.replace('.', " "),
                    layer.entry().id
                ),
            ));
        }
        self.owners.insert(channel, layer.index);
        Ok(())
    }

    fn legend(&mut self, side: u8, field: u8, value: u8, text: String) {
        self.legend.entry((side, field, value)).or_insert(text);
    }

    // -- joins ---------------------------------------------------------------

    /// Result rows → base node index. Duplicate rows and null identities fail;
    /// extra identities follow the layer's policy.
    fn join_nodes(&mut self, layer: &Layer<'_>, field: &str) -> GfResult<Vec<(usize, usize)>> {
        let ids = uuids(&layer.table.column(field).unwrap(), false)
            .map_err(|e| e.in_layer(layer.index))?;
        let mut seen = vec![false; self.base.node_uuid.len()];
        let mut joined = Vec::with_capacity(layer.rows.len());
        let mut extra = 0u64;
        let mut edge_ids = 0u64;
        for &row in &layer.rows {
            let id = ids[row].ok_or_else(|| {
                layer_error(
                    "GF_RESULT_NULL_IDENTITY",
                    layer.index,
                    format!("field \"{field}\" contains a null UUID"),
                )
                .with_field(field)
            })?;
            match self.base.node_index.get(&UuidKey(id)) {
                Some(&node) => {
                    if std::mem::replace(&mut seen[node], true) {
                        return Err(layer_error(
                            "GF_COMPOSE_DUPLICATE_ID",
                            layer.index,
                            format!(
                                "{} results name one node in more than one row",
                                layer.entry().id
                            ),
                        ));
                    }
                    joined.push((row, node));
                }
                None => {
                    extra += 1;
                    if self.base.edge_index.contains_key(&UuidKey(id)) {
                        edge_ids += 1;
                    }
                }
            }
        }
        if edge_ids > 0 {
            return Err(layer_error(
                "GF_COMPOSE_IDENTITY_KIND",
                layer.index,
                format!("{edge_ids} node identities in field \"{field}\" name base relationships"),
            )
            .with_field(field));
        }
        self.extra(layer, extra, "nodes")?;
        Ok(joined)
    }

    fn extra(&mut self, layer: &Layer<'_>, extra: u64, what: &str) -> GfResult<()> {
        if extra == 0 {
            return Ok(());
        }
        match layer.extra {
            ExtraPolicy::Error => Err(layer_error(
                "GF_COMPOSE_EXTRA_IDS",
                layer.index,
                format!(
                    "{extra} of {} result rows name {what} absent from the base graph; the base graph is stale or incompatible (pass extra: \"drop\" to drop them)",
                    layer.rows.len()
                ),
            )),
            ExtraPolicy::Drop => {
                self.decide("GF_COMPOSE_EXTRA_DROPPED", Some(layer.index), extra);
                Ok(())
            }
        }
    }

    /// Apply the missing-identity policy to base nodes the layer skipped.
    fn missing_nodes(&mut self, layer: &Layer<'_>, covered: &[bool]) -> GfResult<u64> {
        let missing: Vec<usize> = (0..covered.len()).filter(|&i| !covered[i]).collect();
        let count = missing.len() as u64;
        match layer.missing {
            MissingPolicy::Error if count > 0 => {
                return Err(layer_error(
                    "GF_COMPOSE_MISSING_IDS",
                    layer.index,
                    format!("{count} base nodes have no {} result row", layer.entry().id),
                ))
            }
            MissingPolicy::Dim => {
                for &i in &missing {
                    self.node_flags[i] |= FLAG_DISABLED;
                }
                if count > 0 {
                    self.legend(LEGEND_NODE, LEGEND_FIELD_CONTEXT, 0, "not in result".into());
                }
                self.decide("GF_COMPOSE_MISSING_DIMMED", Some(layer.index), count);
            }
            MissingPolicy::Hide => {
                for &i in &missing {
                    self.node_hidden[i] = true;
                }
                self.decide("GF_COMPOSE_MISSING_HIDDEN", Some(layer.index), count);
            }
            _ => self.decide("GF_COMPOSE_MISSING_KEPT", Some(layer.index), count),
        }
        Ok(count)
    }

    fn missing_edges(&mut self, layer: &Layer<'_>, covered: &[bool]) -> GfResult<u64> {
        let missing: Vec<usize> = (0..covered.len()).filter(|&i| !covered[i]).collect();
        let count = missing.len() as u64;
        match layer.missing {
            MissingPolicy::Error if count > 0 => {
                return Err(layer_error(
                    "GF_COMPOSE_MISSING_IDS",
                    layer.index,
                    format!(
                        "{count} base relationships have no {} result row",
                        layer.entry().id
                    ),
                ))
            }
            MissingPolicy::Dim => {
                for &i in &missing {
                    self.edge_flags[i] |= FLAG_DISABLED;
                }
                if count > 0 {
                    self.legend(LEGEND_EDGE, LEGEND_FIELD_CONTEXT, 0, "not in result".into());
                }
                self.decide("GF_COMPOSE_MISSING_DIMMED", Some(layer.index), count);
            }
            MissingPolicy::Hide => {
                for &i in &missing {
                    self.edge_hidden[i] = true;
                }
                self.decide("GF_COMPOSE_MISSING_HIDDEN", Some(layer.index), count);
            }
            _ => self.decide("GF_COMPOSE_MISSING_KEPT", Some(layer.index), count),
        }
        Ok(count)
    }

    /// Group ids → class codes: the six largest groups (ties by ascending id)
    /// get codes 1..=6 and the rest share code 7, unless at most seven groups
    /// exist. Negative ids are "unassigned" (code 0).
    fn group_codes(
        &mut self,
        layer: &Layer<'_>,
        side: u8,
        noun: &str,
        values: &[(usize, Option<i64>)],
    ) -> Vec<(usize, u8)> {
        let mut sizes: BTreeMap<i64, u64> = BTreeMap::new();
        let mut unassigned = 0u64;
        let mut nulls = 0u64;
        for &(_, value) in values {
            match value {
                Some(v) if v >= 0 => *sizes.entry(v).or_default() += 1,
                Some(_) => unassigned += 1,
                None => nulls += 1,
            }
        }
        let mut ranked: Vec<(i64, u64)> = sizes.into_iter().collect();
        ranked.sort_by(|a, b| b.1.cmp(&a.1).then(a.0.cmp(&b.0)));
        let bucket = ranked.len() > GROUP_CODES;
        let named = if bucket {
            GROUP_CODES - 1
        } else {
            ranked.len()
        };
        let mut codes: HashMap<i64, u8> = HashMap::with_capacity(ranked.len());
        for (rank, &(group, _)) in ranked.iter().enumerate() {
            let code = if rank < named {
                rank as u8 + 1
            } else {
                GROUP_CODES as u8
            };
            codes.insert(group, code);
            if rank < named {
                self.legend(side, 0, code, format!("{noun} {group}"));
            }
        }
        if bucket {
            let others = (ranked.len() - named) as u64;
            self.legend(
                side,
                0,
                GROUP_CODES as u8,
                format!("other {} ({others})", plural(noun)),
            );
            self.decide("GF_COMPOSE_GROUPS_BUCKETED", Some(layer.index), others);
        }
        if unassigned + nulls > 0 {
            self.legend(side, 0, 0, format!("no {noun}"));
        }
        self.decide("GF_COMPOSE_UNASSIGNED_GROUP", Some(layer.index), unassigned);
        self.decide("GF_COMPOSE_NULL_VALUES", Some(layer.index), nulls);
        values
            .iter()
            .map(|&(element, value)| {
                (
                    element,
                    value.and_then(|v| codes.get(&v).copied()).unwrap_or(0),
                )
            })
            .collect()
    }

    fn null_values(&mut self, layer: &Layer<'_>, values: &[f64], joined: &[(usize, usize)]) {
        let nulls = joined
            .iter()
            .filter(|&&(row, _)| values[row].is_nan())
            .count();
        self.decide("GF_COMPOSE_NULL_VALUES", Some(layer.index), nulls as u64);
    }

    // -- node layers ---------------------------------------------------------

    fn node_layer(&mut self, layer: &Layer<'_>) -> GfResult<()> {
        let n = self.base.node_uuid.len();
        let node_field = layer
            .field(Role::Node)
            .expect("node layers carry node_uuid");
        let joined = self.join_nodes(layer, node_field)?;
        let mut out = LayerOut::default();
        let mut rows = vec![NONE_U64; n];
        let mut covered = vec![false; n];
        for &(row, node) in &joined {
            rows[node] = row as u64;
            covered[node] = true;
        }
        let composition = layer.entry().composition;
        // Canonical value fields, then the node properties rank/cluster/find
        // results append (numeric as values, text as texts), for tooltips and
        // table linking. Properties are display data, never diagnostics.
        let mut value_fields: Vec<String> = layer
            .entry()
            .fields
            .iter()
            .filter(|f| matches!(f.role, Role::Metric | Role::Group | Role::Order))
            .map(|f| f.name.to_owned())
            .collect();
        let mut text_fields: Vec<String> = Vec::new();
        for field in layer
            .table
            .schema
            .fields
            .iter()
            .filter(|f| !layer.entry().fields.iter().any(|spec| spec.name == f.name))
        {
            if value_fields.len() + text_fields.len() >= MAX_PROPERTY_COLUMNS {
                self.decide("GF_COMPOSE_PROPERTIES_TRUNCATED", Some(layer.index), 1);
                break;
            }
            match field.data_type {
                DataType::Float { .. } | DataType::Int { .. } => {
                    value_fields.push(field.name.clone())
                }
                DataType::Utf8 { .. } => text_fields.push(field.name.clone()),
                _ => {}
            }
        }
        let mut values = vec![f64::NAN; n * value_fields.len()];
        for (k, name) in value_fields.iter().enumerate() {
            let column = layer
                .column_f64(name)
                .map_err(|e| e.in_layer(layer.index))?;
            for &(row, node) in &joined {
                values[node * value_fields.len() + k] = column[row];
            }
        }
        let mut texts_out = vec![String::new(); n * text_fields.len()];
        for (k, name) in text_fields.iter().enumerate() {
            let column =
                texts(&layer.table.column(name).unwrap()).map_err(|e| e.in_layer(layer.index))?;
            for &(row, node) in &joined {
                texts_out[node * text_fields.len() + k] = column[row].unwrap_or("").to_owned();
            }
        }
        match composition {
            Composition::NodeScore | Composition::NodeSearch => {
                let score = layer.field(Role::Metric).unwrap();
                self.claim("node.metric", layer)?;
                let column = layer
                    .column_f64(score)
                    .map_err(|e| e.in_layer(layer.index))?;
                self.null_values(layer, &column, &joined);
                // Label priority follows the score unless an order layer owns labels.
                let prioritize = !self.owners.contains_key("node.label");
                for &(row, node) in &joined {
                    self.node_metric[node] = column[row];
                    if prioritize {
                        self.node_priority[node] = if column[row].is_finite() {
                            column[row]
                        } else {
                            f64::NEG_INFINITY
                        };
                    }
                }
                if composition == Composition::NodeSearch {
                    for &(_, node) in &joined {
                        self.node_status[node] = self.node_status[node].max(NODE_STATUS_MEMBER);
                    }
                    if !joined.is_empty() {
                        self.legend(LEGEND_NODE, 2, NODE_STATUS_MEMBER, "search hit".into());
                    }
                }
            }
            Composition::NodeGroup => {
                let group = layer.field(Role::Group).unwrap();
                self.claim("node.class", layer)?;
                let ids = i64s(&layer.table.column(group).unwrap())
                    .map_err(|e| e.in_layer(layer.index))?;
                let noun = if group == "community_id" {
                    "community"
                } else {
                    group
                };
                let pairs: Vec<(usize, Option<i64>)> =
                    joined.iter().map(|&(row, node)| (node, ids[row])).collect();
                for (node, code) in self.group_codes(layer, LEGEND_NODE, noun, &pairs) {
                    self.node_class[node] = code;
                }
            }
            Composition::NodeOrder | Composition::NodeTraversal => {
                let order = layer.field(Role::Order).unwrap();
                self.claim("node.label", layer)?;
                let orders = i64s(&layer.table.column(order).unwrap())
                    .map_err(|e| e.in_layer(layer.index))?;
                let mut nulls = 0u64;
                for &(row, node) in &joined {
                    match orders[row] {
                        Some(value) => {
                            self.node_label[node] = Some(value.to_string());
                            self.node_priority[node] = -(value as f64);
                        }
                        None => nulls += 1,
                    }
                }
                self.decide("GF_COMPOSE_NULL_VALUES", Some(layer.index), nulls);
                if composition == Composition::NodeTraversal {
                    let depth = layer.field(Role::Metric).unwrap();
                    self.claim("node.metric", layer)?;
                    let column = layer
                        .column_f64(depth)
                        .map_err(|e| e.in_layer(layer.index))?;
                    for &(row, node) in &joined {
                        self.node_metric[node] = column[row];
                    }
                }
            }
            Composition::NodeSet => {
                for &(_, node) in &joined {
                    self.node_status[node] = self.node_status[node].max(NODE_STATUS_MEMBER);
                }
                if !joined.is_empty() {
                    let text = match layer.recognized.algorithm {
                        "articulation_points" => "articulation point".to_string(),
                        other => format!("{} member", other.replace('_', " ")),
                    };
                    self.legend(LEGEND_NODE, 2, NODE_STATUS_MEMBER, text);
                }
            }
            _ => unreachable!("node_layer dispatch"),
        }
        out.matched = joined.len() as u64;
        out.extra = layer.rows.len() as u64 - out.matched;
        out.missing = self.missing_nodes(layer, &covered)?;
        out.value_names = value_fields;
        out.text_names = text_fields;
        out.node_texts = Some(texts_out);
        out.node_values = Some(values);
        out.node_rows = Some(rows);
        self.layers.push(out);
        Ok(())
    }

    // -- edge layers ---------------------------------------------------------

    fn edge_layer(&mut self, layer: &Layer<'_>) -> GfResult<()> {
        let e = self.base.edge_uuid.len();
        let edge_field = layer
            .field(Role::Edge)
            .expect("edge layers carry edge_uuid");
        let ids = uuids(&layer.table.column(edge_field).unwrap(), false)
            .map_err(|e| e.in_layer(layer.index))?;
        let endpoints = match (layer.field(Role::Source), layer.field(Role::Target)) {
            (Some(s), Some(t)) => Some((
                uuids(&layer.table.column(s).unwrap(), false)
                    .map_err(|e| e.in_layer(layer.index))?,
                uuids(&layer.table.column(t).unwrap(), false)
                    .map_err(|e| e.in_layer(layer.index))?,
            )),
            _ => None,
        };
        let directional = matches!(
            layer.entry().composition,
            Composition::EdgeOverlay { directional: true }
        );
        let mut joined = Vec::with_capacity(layer.rows.len());
        let mut seen = vec![false; e];
        let mut extra = 0u64;
        let mut node_ids = 0u64;
        let mut mismatched = 0u64;
        let mut reversed = 0u64;
        let mut shared = 0u64;
        for &row in &layer.rows {
            let id = ids[row].ok_or_else(|| {
                layer_error(
                    "GF_RESULT_NULL_IDENTITY",
                    layer.index,
                    format!("field \"{edge_field}\" contains a null UUID"),
                )
                .with_field(edge_field)
            })?;
            let Some(&edge) = self.base.edge_index.get(&UuidKey(id)) else {
                extra += 1;
                if self.base.node_index.contains_key(&UuidKey(id)) {
                    node_ids += 1;
                }
                continue;
            };
            if std::mem::replace(&mut seen[edge], true) {
                // k spanning trees may share an edge: the first row (lowest
                // tree) paints it and the overlap is recorded.
                if layer.field(Role::Group).is_some()
                    && layer.entry().composition != Composition::EdgeGroup
                {
                    shared += 1;
                    continue;
                }
                return Err(layer_error(
                    "GF_COMPOSE_DUPLICATE_ID",
                    layer.index,
                    format!(
                        "{} results name one relationship in more than one row",
                        layer.entry().id
                    ),
                ));
            }
            if let Some((sources, targets)) = &endpoints {
                let (Some(s), Some(t)) = (sources[row], targets[row]) else {
                    return Err(layer_error(
                        "GF_RESULT_NULL_IDENTITY",
                        layer.index,
                        "an edge endpoint is null".into(),
                    ));
                };
                let base_s = self.base.node_uuid[self.base.edge_source[edge]];
                let base_t = self.base.node_uuid[self.base.edge_target[edge]];
                if (s, t) == (base_s, base_t) {
                } else if (s, t) == (base_t, base_s) {
                    reversed += 1;
                    if directional {
                        self.edge_reversed[edge] = true;
                    }
                } else {
                    mismatched += 1;
                }
            }
            joined.push((row, edge));
        }
        if node_ids > 0 {
            return Err(layer_error(
                "GF_COMPOSE_IDENTITY_KIND",
                layer.index,
                format!(
                    "{node_ids} relationship identities in field \"{edge_field}\" name base nodes"
                ),
            )
            .with_field(edge_field));
        }
        if mismatched > 0 {
            return Err(layer_error(
                "GF_COMPOSE_EDGE_ENDPOINT_MISMATCH",
                layer.index,
                format!("{mismatched} relationships have different endpoints in the result than in the base graph; the base graph is stale or incompatible"),
            ));
        }
        self.extra(layer, extra, "relationships")?;
        self.decide("GF_COMPOSE_SHARED_MEMBERSHIP", Some(layer.index), shared);
        self.decide(
            if directional {
                "GF_COMPOSE_EDGE_REORIENTED"
            } else {
                "GF_COMPOSE_EDGE_REVERSED"
            },
            Some(layer.index),
            reversed,
        );
        let mut rows = vec![NONE_U64; e];
        let mut covered = vec![false; e];
        for &(row, edge) in &joined {
            rows[edge] = row as u64;
            covered[edge] = true;
        }
        let value_fields: Vec<&'static str> = layer
            .entry()
            .fields
            .iter()
            .filter(|f| matches!(f.role, Role::Metric | Role::Group | Role::Cost))
            .map(|f| f.name)
            .collect();
        let mut values = vec![f64::NAN; e * value_fields.len()];
        for (k, name) in value_fields.iter().enumerate() {
            let column = layer
                .column_f64(name)
                .map_err(|e| e.in_layer(layer.index))?;
            for &(row, edge) in &joined {
                values[edge * value_fields.len() + k] = column[row];
            }
        }
        self.claim("edge.class", layer)?;
        let noun = match layer.recognized.algorithm {
            "edge_coloring" => "edge color",
            _ => "tree",
        };
        if let Some(group) = layer.field(Role::Group) {
            let ids =
                i64s(&layer.table.column(group).unwrap()).map_err(|e| e.in_layer(layer.index))?;
            let pairs: Vec<(usize, Option<i64>)> =
                joined.iter().map(|&(row, edge)| (edge, ids[row])).collect();
            for (edge, code) in self.group_codes(layer, LEGEND_EDGE, noun, &pairs) {
                self.edge_class[edge] = code;
            }
        } else {
            for &(_, edge) in &joined {
                self.edge_class[edge] = 1;
            }
            if !joined.is_empty() {
                self.legend(
                    LEGEND_EDGE,
                    0,
                    1,
                    edge_member_text(layer.recognized.algorithm),
                );
            }
        }
        if directional {
            self.claim("edge.status", layer)?;
            // Status 1 shares the membership color and adds the arrowhead;
            // the class row already names these edges.
            for &(_, edge) in &joined {
                self.edge_status[edge] = 1;
            }
        }
        if let Some(metric) = layer.field(Role::Metric) {
            self.claim("edge.metric", layer)?;
            let column = layer
                .column_f64(metric)
                .map_err(|e| e.in_layer(layer.index))?;
            self.null_values(layer, &column, &joined);
            for &(row, edge) in &joined {
                self.edge_metric[edge] = column[row];
            }
        }
        let mut out = LayerOut {
            matched: joined.len() as u64,
            extra,
            ..Default::default()
        };
        out.missing = self.missing_edges(layer, &covered)?;
        out.value_names = value_fields.iter().map(|s| (*s).to_owned()).collect();
        out.edge_values = Some(values);
        out.edge_rows = Some(rows);
        self.layers.push(out);
        Ok(())
    }
}

fn plural(noun: &str) -> String {
    match noun.strip_suffix('y') {
        Some(stem) => format!("{stem}ies"),
        None => format!("{noun}s"),
    }
}

fn edge_member_text(algorithm: &str) -> String {
    match algorithm {
        "minimum_spanning_tree" | "maximum_spanning_tree" => "spanning tree edge".into(),
        "min_steiner_tree" | "prize_collecting_steiner_tree" => "Steiner tree edge".into(),
        "max_weight_matching" | "max_cardinality_matching" | "max_bipartite_matching" => {
            "matched edge".into()
        }
        "bridges" => "bridge".into(),
        "max_flow_edges" | "min_cost_max_flow_edges" => "flow edge".into(),
        "min_cut_edges" => "cut edge".into(),
        other => format!("{} edge", other.replace('_', " ")),
    }
}

/// Default missing-identity policy for a composition.
fn default_missing(composition: Composition) -> MissingPolicy {
    match composition {
        c if c.covers_base() => MissingPolicy::Dim,
        Composition::EdgeOverlay { .. } | Composition::EdgeGroup => MissingPolicy::Dim,
        _ => MissingPolicy::Keep,
    }
}

fn prepare_layer<'a>(index: usize, request: &'a LayerRequest<'a>) -> GfResult<Layer<'a>> {
    let table = read_table(request.result).map_err(|e| GfError::from(e).in_layer(index))?;
    let recognized = recognize(&table.schema).map_err(|e| e.in_layer(index))?;
    let composition = recognized.entry.composition;
    if !composition.intents().contains(&request.intent) {
        let allowed: Vec<_> = composition.intents().iter().map(|i| i.name()).collect();
        return Err(layer_error(
            "GF_COMPOSE_INTENT_UNSUPPORTED",
            index,
            format!(
                "{} results support the {} intent(s), not {}",
                recognized.entry.id,
                allowed.join(", "),
                request.intent.name()
            ),
        ));
    }
    let rows = match &request.rows {
        None => (0..table.rows).collect(),
        Some(selected) => {
            let mut seen = std::collections::HashSet::with_capacity(selected.len());
            let mut rows = Vec::with_capacity(selected.len());
            for &row in selected {
                if row >= table.rows as u64 || !seen.insert(row) {
                    return Err(layer_error(
                        "GF_COMPOSE_REQUEST_INVALID",
                        index,
                        "selected rows must be unique and within the result".into(),
                    ));
                }
                rows.push(row as usize);
            }
            rows
        }
    };
    Ok(Layer {
        index,
        request,
        missing: request
            .missing
            .unwrap_or_else(|| default_missing(composition)),
        extra: request.extra.unwrap_or(ExtraPolicy::Error),
        table,
        recognized,
        rows,
    })
}

/// Result generation must match the base generation, or both are absent.
fn check_generation(
    request: &Request<'_>,
    layer: &Layer<'_>,
    decisions: &mut Vec<Decision>,
) -> GfResult<()> {
    match (request.base_generation, layer.request.generation) {
        (Some(base), Some(result)) if base != result => Err(layer_error(
            "GF_COMPOSE_GENERATION_STALE",
            layer.index,
            "the result was computed at a different graph generation than the base graph".into(),
        )),
        (Some(_), None) | (None, Some(_)) => Err(layer_error(
            "GF_COMPOSE_GENERATION_MISSING",
            layer.index,
            "the base graph and the result must both name a generation, or neither".into(),
        )),
        (None, None) => {
            decisions.push(Decision {
                code: "GF_COMPOSE_GENERATION_UNVERIFIED",
                layer: Some(layer.index),
                count: 1,
            });
            Ok(())
        }
        _ => Ok(()),
    }
}

fn graph_document(request: &Request<'_>) -> GfResult<Vec<u8>> {
    let layers = request
        .layers
        .iter()
        .enumerate()
        .map(|(i, l)| prepare_layer(i, l))
        .collect::<GfResult<Vec<_>>>()?;
    if layers.iter().any(|l| l.request.intent != Intent::Graph) {
        if layers.len() != 1 {
            return Err(GfError::new(
                "GF_COMPOSE_INTENT_CONFLICT",
                "table, chart, and embedding intents compose exactly one result layer",
            ));
        }
        return Err(layer_error(
            "GF_COMPOSE_UNSUPPORTED_COMPOSITION",
            0,
            format!(
                "the {} intent is not composed by this engine yet",
                layers[0].request.intent.name()
            ),
        ));
    }
    if request.base_tables.is_empty() && request.base_planes.is_none() {
        return Err(GfError::new(
            "GF_COMPOSE_BASE_REQUIRED",
            "graph compositions join results onto a base graph; pass the base graph's entity tables",
        ));
    }
    let mut decisions = Vec::new();
    for layer in &layers {
        check_generation(request, layer, &mut decisions)?;
    }
    let tables = request
        .base_tables
        .iter()
        .map(|bytes| read_table(bytes).map_err(GfError::from))
        .collect::<GfResult<Vec<_>>>()?;
    let planes = request.base_planes.as_ref().map(|p| RawPlanes {
        node_uuid: &p.node_uuid,
        edge_uuid: &p.edge_uuid,
        edge_source: &p.edge_source,
        edge_target: &p.edge_target,
    });
    let base = base::build(&tables, planes, request.directed)?;
    let mut planes = Planes::new(&base);
    planes.decisions = decisions;
    planes.decide("GF_BASE_MERGED_ENTITIES", None, base.merged_entities);
    for layer in &layers {
        match layer.entry().composition {
            Composition::NodeScore
            | Composition::NodeGroup
            | Composition::NodeOrder
            | Composition::NodeTraversal
            | Composition::NodeSet
            | Composition::NodeSearch => planes.node_layer(layer)?,
            Composition::EdgeOverlay { .. } | Composition::EdgeGroup => planes.edge_layer(layer)?,
            other => {
                return Err(layer_error(
                    "GF_COMPOSE_UNSUPPORTED_COMPOSITION",
                    layer.index,
                    format!(
                        "{} compositions are not composed by this engine yet",
                        other.name()
                    ),
                ))
            }
        }
    }
    Ok(encode_graph(&planes, request, &layers))
}

fn encode_graph(planes: &Planes<'_>, request: &Request<'_>, layers: &[Layer<'_>]) -> Vec<u8> {
    let base = planes.base;
    // Hidden nodes take their incident relationships with them.
    let mut edge_hidden = planes.edge_hidden.clone();
    let mut cascaded = 0u64;
    for i in 0..base.edge_uuid.len() {
        if !edge_hidden[i]
            && (planes.node_hidden[base.edge_source[i]] || planes.node_hidden[base.edge_target[i]])
        {
            edge_hidden[i] = true;
            cascaded += 1;
        }
    }
    let nodes: Vec<usize> = (0..base.node_uuid.len())
        .filter(|&i| !planes.node_hidden[i])
        .collect();
    let edges: Vec<usize> = (0..base.edge_uuid.len())
        .filter(|&i| !edge_hidden[i])
        .collect();
    let mut remap = vec![NONE_U64; base.node_uuid.len()];
    for (dense, &node) in nodes.iter().enumerate() {
        remap[node] = dense as u64;
    }
    let pick_u8 = |plane: &[u8], rows: &[usize]| rows.iter().map(|&i| plane[i]).collect::<Vec<_>>();
    let pick_f64 =
        |plane: &[f64], rows: &[usize]| rows.iter().map(|&i| plane[i]).collect::<Vec<_>>();
    let pick_u32 =
        |plane: &[u32], rows: &[usize]| rows.iter().map(|&i| plane[i]).collect::<Vec<_>>();
    let text = |value: &Option<String>| value.clone().unwrap_or_default();

    let mut out = Builder::new(DOCUMENT_MAGIC);
    out.u32s("status", 0, &[0]);
    out.utf8("kind", 0, "graph");
    out.u32s("composition.version", 0, &[COMPOSITION_VERSION]);
    out.u32s("ledger.version", 0, &[ledger::LEDGER_VERSION]);
    out.u8s("graph.directed", 0, &[u8::from(base.directed)]);
    if let Some(generation) = request.base_generation {
        out.uuids("base.generation", 0, &[generation]);
    }
    out.u64s(
        "base.counts",
        0,
        &[base.node_uuid.len() as u64, base.edge_uuid.len() as u64],
    );

    out.uuids(
        "node.uuid",
        0,
        &nodes.iter().map(|&i| base.node_uuid[i]).collect::<Vec<_>>(),
    );
    out.u64s(
        "node.base_row",
        0,
        &nodes.iter().map(|&i| i as u64).collect::<Vec<_>>(),
    );
    out.texts(
        "node.name",
        0,
        &nodes
            .iter()
            .map(|&i| text(&base.node_name[i]))
            .collect::<Vec<_>>(),
    );
    out.texts(
        "node.type",
        0,
        &nodes
            .iter()
            .map(|&i| text(&base.node_type[i]))
            .collect::<Vec<_>>(),
    );
    out.u8s("node.class", 0, &pick_u8(&planes.node_class, &nodes));
    out.u8s(
        "node.epistemic",
        0,
        &pick_u8(&planes.node_epistemic, &nodes),
    );
    out.u8s("node.status", 0, &pick_u8(&planes.node_status, &nodes));
    out.f64s("node.metric", 0, &pick_f64(&planes.node_metric, &nodes));
    out.u32s("node.flags", 0, &pick_u32(&planes.node_flags, &nodes));
    out.texts(
        "node.label",
        0,
        &nodes
            .iter()
            .map(|&i| text(&planes.node_label[i]))
            .collect::<Vec<_>>(),
    );
    out.f64s(
        "node.label_priority",
        0,
        &pick_f64(&planes.node_priority, &nodes),
    );

    let (mut sources, mut targets) = (
        Vec::with_capacity(edges.len()),
        Vec::with_capacity(edges.len()),
    );
    for &i in &edges {
        let (mut s, mut t) = (base.edge_source[i], base.edge_target[i]);
        if planes.edge_reversed[i] {
            std::mem::swap(&mut s, &mut t);
        }
        sources.push(remap[s]);
        targets.push(remap[t]);
    }
    out.uuids(
        "edge.uuid",
        0,
        &edges.iter().map(|&i| base.edge_uuid[i]).collect::<Vec<_>>(),
    );
    out.u64s(
        "edge.base_row",
        0,
        &edges.iter().map(|&i| i as u64).collect::<Vec<_>>(),
    );
    out.u64s("edge.source", 0, &sources);
    out.u64s("edge.target", 0, &targets);
    out.texts(
        "edge.type",
        0,
        &edges
            .iter()
            .map(|&i| text(&base.edge_type[i]))
            .collect::<Vec<_>>(),
    );
    out.u8s("edge.derived", 0, &vec![0; edges.len()]);
    out.u32s("edge.layer", 0, &vec![NONE_U32; edges.len()]);
    out.u8s("edge.class", 0, &pick_u8(&planes.edge_class, &edges));
    out.u8s(
        "edge.epistemic",
        0,
        &pick_u8(&planes.edge_epistemic, &edges),
    );
    out.u8s("edge.status", 0, &pick_u8(&planes.edge_status, &edges));
    out.f64s("edge.metric", 0, &pick_f64(&planes.edge_metric, &edges));
    out.u32s("edge.flags", 0, &pick_u32(&planes.edge_flags, &edges));

    for (i, (layer, result)) in layers.iter().zip(&planes.layers).enumerate() {
        let entry = layer.entry();
        out.utf8("layer.schema", i, entry.id);
        out.u32s("layer.schema_version", i, &[entry.version]);
        out.utf8("layer.verb", i, layer.recognized.verb);
        out.utf8("layer.algorithm", i, layer.recognized.algorithm);
        out.utf8("layer.disposition", i, entry.disposition.name());
        out.utf8("layer.composition", i, entry.composition.name());
        out.utf8("layer.intent", i, layer.request.intent.name());
        out.utf8("layer.missing_policy", i, layer.missing.name());
        out.utf8("layer.extra_policy", i, layer.extra.name());
        if let Some(id) = layer.request.result_id {
            out.utf8("layer.result_id", i, id);
        }
        if let Some(generation) = layer.request.generation {
            out.uuids("layer.generation", i, &[generation]);
        }
        if let Some(kind) = entry.derived_type {
            out.utf8("layer.derived_type", i, kind);
        }
        out.u64s(
            "layer.counts",
            i,
            &[
                layer.table.rows as u64,
                layer.rows.len() as u64,
                result.matched,
                result.missing,
                result.extra,
            ],
        );
        out.texts("layer.value_names", i, &result.value_names);
        let k = result.value_names.len();
        if let (Some(values), Some(rows)) = (&result.node_values, &result.node_rows) {
            let mut picked = Vec::with_capacity(nodes.len() * k);
            for &node in &nodes {
                picked.extend_from_slice(&values[node * k..node * k + k]);
            }
            out.f64s("layer.node_values", i, &picked);
            if let Some(texts) = &result.node_texts {
                let t = result.text_names.len();
                if t > 0 {
                    let mut picked = Vec::with_capacity(nodes.len() * t);
                    for &node in &nodes {
                        picked.extend(texts[node * t..node * t + t].iter().map(String::as_str));
                    }
                    out.texts("layer.text_names", i, &result.text_names);
                    out.texts("layer.node_texts", i, &picked);
                }
            }
            out.u64s(
                "layer.node_rows",
                i,
                &nodes.iter().map(|&n| rows[n]).collect::<Vec<_>>(),
            );
        }
        if let (Some(values), Some(rows)) = (&result.edge_values, &result.edge_rows) {
            let mut picked = Vec::with_capacity(edges.len() * k);
            for &edge in &edges {
                picked.extend_from_slice(&values[edge * k..edge * k + k]);
            }
            out.f64s("layer.edge_values", i, &picked);
            out.u64s(
                "layer.edge_rows",
                i,
                &edges.iter().map(|&e| rows[e]).collect::<Vec<_>>(),
            );
        }
    }

    encode_legend(&mut out, planes, &nodes, &edges);

    let mut decisions = planes.decisions.clone();
    if cascaded > 0 {
        decisions.push(Decision {
            code: "GF_COMPOSE_EDGES_HIDDEN_WITH_NODES",
            layer: None,
            count: cascaded,
        });
    }
    out.texts(
        "decision.code",
        0,
        &decisions.iter().map(|d| d.code).collect::<Vec<_>>(),
    );
    out.u32s(
        "decision.layer",
        0,
        &decisions
            .iter()
            .map(|d| d.layer.map_or(NONE_U32, |l| l as u32))
            .collect::<Vec<_>>(),
    );
    out.u64s(
        "decision.count",
        0,
        &decisions.iter().map(|d| d.count).collect::<Vec<_>>(),
    );
    out.finish()
}

/// Legend rows for the values actually painted, side then field then code,
/// with both theme palettes so hosts only pick one.
fn encode_legend(out: &mut Builder, planes: &Planes<'_>, nodes: &[usize], edges: &[usize]) {
    let present = |plane: &[u8], rows: &[usize]| {
        let mut seen = [false; 8];
        for &i in rows {
            seen[plane[i] as usize] = true;
        }
        seen
    };
    let mut rows: Vec<(u8, u8, u8, &String)> = Vec::new();
    let node_fields = [
        (0u8, present(&planes.node_class, nodes)),
        (1, present(&planes.node_epistemic, nodes)),
        (2, present(&planes.node_status, nodes)),
    ];
    let edge_fields = [
        (0u8, present(&planes.edge_class, edges)),
        (1, present(&planes.edge_epistemic, edges)),
        (2, present(&planes.edge_status, edges)),
    ];
    for (side, fields, flags, members) in [
        (LEGEND_NODE, node_fields, &planes.node_flags, nodes),
        (LEGEND_EDGE, edge_fields, &planes.edge_flags, edges),
    ] {
        for (field, seen) in fields {
            for value in 0..8u8 {
                if seen[value as usize] {
                    if let Some(text) = planes.legend.get(&(side, field, value)) {
                        rows.push((side, field, value, text));
                    }
                }
            }
        }
        if members.iter().any(|&i| flags[i] & FLAG_DISABLED != 0) {
            if let Some(text) = planes.legend.get(&(side, LEGEND_FIELD_CONTEXT, 0)) {
                rows.push((side, LEGEND_FIELD_CONTEXT, 0, text));
            }
        }
    }
    let light = semantic_palette(THEME_LIGHT).unwrap();
    let dark = semantic_palette(THEME_DARK).unwrap();
    let color = |palette: &[[u8; 4]; 8], field: u8, value: u8| {
        if field == LEGEND_FIELD_CONTEXT {
            // Disabled context: the neutral color at the resolver's 0.28 opacity.
            let mut c = palette[0];
            c[3] = 71;
            c
        } else {
            palette[value as usize]
        }
    };
    out.utf8("legend.title", 0, "GraphForge result");
    out.u8s(
        "legend.side",
        0,
        &rows.iter().map(|r| r.0).collect::<Vec<_>>(),
    );
    out.u8s(
        "legend.field",
        0,
        &rows.iter().map(|r| r.1).collect::<Vec<_>>(),
    );
    out.u8s(
        "legend.value",
        0,
        &rows.iter().map(|r| r.2).collect::<Vec<_>>(),
    );
    out.texts(
        "legend.text",
        0,
        &rows.iter().map(|r| r.3.as_str()).collect::<Vec<_>>(),
    );
    out.u8s(
        "legend.shape",
        0,
        &rows
            .iter()
            .map(|r| {
                if r.0 == LEGEND_NODE && r.1 == 0 {
                    r.2 % 6
                } else {
                    0
                }
            })
            .collect::<Vec<_>>(),
    );
    out.u8s(
        "legend.rgba_light",
        0,
        &rows
            .iter()
            .flat_map(|r| color(light, r.1, r.2))
            .collect::<Vec<_>>(),
    );
    out.u8s(
        "legend.rgba_dark",
        0,
        &rows
            .iter()
            .flat_map(|r| color(dark, r.1, r.2))
            .collect::<Vec<_>>(),
    );
}

/// Encode a failure as an `XYGF` document.
pub fn error_document(error: &GfError) -> Vec<u8> {
    let mut out = Builder::new(DOCUMENT_MAGIC);
    out.u32s("status", 0, &[1]);
    out.u32s("composition.version", 0, &[COMPOSITION_VERSION]);
    out.utf8("error.code", 0, error.code);
    out.utf8("error.message", 0, &error.message);
    out.u32s(
        "error.layer",
        0,
        &[error.layer.map_or(NONE_U32, |l| l as u32)],
    );
    if let Some(field) = &error.field {
        out.utf8("error.field", 0, field);
    }
    out.finish()
}

/// Compose a decoded request. Deterministic for identical input bytes.
pub fn compose(request: &Request<'_>) -> GfResult<Vec<u8>> {
    graph_document(request)
}

/// Request bytes → `XYGF` document bytes; `Err` carries an error document.
pub fn compose_bytes(request: &[u8]) -> Result<Vec<u8>, Vec<u8>> {
    request::decode(request)
        .and_then(|decoded| compose(&decoded))
        .map_err(|error| error_document(&error))
}

#[cfg(test)]
mod tests;
