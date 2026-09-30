//! `XYGQ` composition request decoding (spec §5.1).
//!
//! Hosts only frame bytes they already hold: GraphForge Arrow IPC results and
//! base tables, generation UUIDs, and enumerated intent/policy words. Rust
//! validates every section; unknown sections fail closed because hosts and
//! the engine ship together.

use super::container::{Container, REQUEST_MAGIC};
use super::ledger::Intent;
use super::{GfError, GfResult, Uuid, NIL_UUID};

/// Result layers per composition.
pub const MAX_LAYERS: usize = 16;
/// Base tables per composition.
pub const MAX_BASE_TABLES: usize = 64;
/// Caller result ids are opaque tokens echoed for selection routing.
pub const MAX_RESULT_ID_BYTES: usize = 128;

/// Base elements a result layer does not cover.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum MissingPolicy {
    /// Paint uncovered base elements as disabled context (visible, faded).
    Dim,
    /// Leave uncovered elements out of the composition.
    Hide,
    /// Paint uncovered elements normally.
    Keep,
    /// Fail with `GF_COMPOSE_MISSING_IDS`.
    Error,
}

impl MissingPolicy {
    pub fn name(self) -> &'static str {
        match self {
            MissingPolicy::Dim => "dim",
            MissingPolicy::Hide => "hide",
            MissingPolicy::Keep => "keep",
            MissingPolicy::Error => "error",
        }
    }
    fn parse(text: &str) -> Option<Self> {
        [Self::Dim, Self::Hide, Self::Keep, Self::Error]
            .into_iter()
            .find(|p| p.name() == text)
    }
}

/// Result identities absent from the base graph.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum ExtraPolicy {
    /// Fail with `GF_COMPOSE_EXTRA_IDS` (default: the base is likely stale).
    Error,
    /// Drop those rows and record the count.
    Drop,
}

impl ExtraPolicy {
    pub fn name(self) -> &'static str {
        match self {
            ExtraPolicy::Error => "error",
            ExtraPolicy::Drop => "drop",
        }
    }
    fn parse(text: &str) -> Option<Self> {
        [Self::Error, Self::Drop]
            .into_iter()
            .find(|p| p.name() == text)
    }
}

#[derive(Debug)]
pub struct LayerRequest<'a> {
    pub result: &'a [u8],
    pub result_id: Option<&'a str>,
    pub generation: Option<Uuid>,
    pub intent: Intent,
    pub missing: Option<MissingPolicy>,
    pub extra: Option<ExtraPolicy>,
    /// Explicit result rows to compose (ordered overlays); all rows if absent.
    pub rows: Option<Vec<u64>>,
    /// Caller-provided 2D coordinates (Arrow IPC: `node_uuid`, `x`, `y`).
    pub coordinates: Option<&'a [u8]>,
}

#[derive(Debug)]
pub struct BasePlanes {
    pub node_uuid: Vec<Uuid>,
    pub edge_uuid: Vec<Uuid>,
    pub edge_source: Vec<Uuid>,
    pub edge_target: Vec<Uuid>,
}

/// Optional direct-tier Scene rendering of a graph composition (spec §6.3).
#[derive(Debug, Clone)]
pub struct Render<'a> {
    pub width: f64,
    pub height: f64,
    /// `graph_style::THEME_LIGHT` or `THEME_DARK`.
    pub theme: u8,
    pub title: &'a str,
}

#[derive(Debug)]
pub struct Request<'a> {
    pub base_tables: Vec<&'a [u8]>,
    pub base_planes: Option<BasePlanes>,
    pub base_generation: Option<Uuid>,
    pub directed: bool,
    pub layers: Vec<LayerRequest<'a>>,
    pub render: Option<Render<'a>>,
    /// Node or relationship UUIDs to paint in the selected state.
    pub selected: Vec<Uuid>,
}

const KNOWN: &[&str] = &[
    "base.table",
    "base.node_uuid",
    "base.edge_uuid",
    "base.edge_source_uuid",
    "base.edge_target_uuid",
    "base.generation",
    "base.directed",
    "layer.result",
    "layer.result_id",
    "layer.generation",
    "layer.intent",
    "layer.missing",
    "layer.extra",
    "layer.rows",
    "layer.coordinates",
    "render.width",
    "render.height",
    "render.theme",
    "render.title",
    "select.uuid",
];

fn invalid(message: impl Into<String>) -> GfError {
    GfError::new("GF_COMPOSE_REQUEST_INVALID", message)
}

fn generation(container: &Container<'_>, name: &str, index: u32) -> GfResult<Option<Uuid>> {
    let Some(section) = container.get(name, index) else {
        return Ok(None);
    };
    let ids = section.as_uuids(name)?;
    match ids.as_slice() {
        [id] if *id != NIL_UUID => Ok(Some(*id)),
        _ => Err(invalid(format!(
            "\"{name}\" must hold exactly one non-nil UUID"
        ))),
    }
}

fn contiguous(indices: &[u32], name: &str) -> GfResult<usize> {
    if indices.iter().enumerate().any(|(i, &v)| v as usize != i) {
        return Err(invalid(format!(
            "\"{name}\" indices must be contiguous from zero"
        )));
    }
    Ok(indices.len())
}

pub fn decode(bytes: &[u8]) -> GfResult<Request<'_>> {
    let container = Container::decode(bytes, REQUEST_MAGIC)?;
    if let Some((name, _, _)) = container
        .sections
        .iter()
        .find(|(name, _, _)| !KNOWN.contains(name))
    {
        let shown: String = name.chars().take(64).collect();
        return Err(invalid(format!("unknown request section \"{shown}\"")));
    }
    let table_count = contiguous(&container.indices("base.table"), "base.table")?;
    if table_count > MAX_BASE_TABLES {
        return Err(GfError::new("GF_COMPOSE_TOO_LARGE", "too many base tables"));
    }
    let base_tables = (0..table_count as u32)
        .map(|i| {
            container
                .get("base.table", i)
                .unwrap()
                .as_bytes("base.table")
        })
        .collect::<GfResult<Vec<_>>>()?;
    for name in [
        "base.node_uuid",
        "base.edge_uuid",
        "base.edge_source_uuid",
        "base.edge_target_uuid",
    ] {
        if container.indices(name).iter().any(|&i| i != 0) {
            return Err(invalid(format!("\"{name}\" is a single section")));
        }
    }
    let plane = |name: &str| -> GfResult<Option<Vec<Uuid>>> {
        container.get(name, 0).map(|s| s.as_uuids(name)).transpose()
    };
    let node_uuid = plane("base.node_uuid")?;
    let edge_uuid = plane("base.edge_uuid")?;
    let edge_source = plane("base.edge_source_uuid")?;
    let edge_target = plane("base.edge_target_uuid")?;
    let base_planes = match (node_uuid, edge_uuid, edge_source, edge_target) {
        (None, None, None, None) => None,
        (Some(node_uuid), edge_uuid, edge_source, edge_target) => {
            let edge_uuid = edge_uuid.unwrap_or_default();
            let edge_source = edge_source.unwrap_or_default();
            let edge_target = edge_target.unwrap_or_default();
            if edge_source.len() != edge_uuid.len() || edge_target.len() != edge_uuid.len() {
                return Err(invalid("base edge planes must be provided together"));
            }
            Some(BasePlanes {
                node_uuid,
                edge_uuid,
                edge_source,
                edge_target,
            })
        }
        _ => return Err(invalid("base edge planes need base.node_uuid")),
    };
    let directed = match container.get("base.directed", 0) {
        None => true,
        Some(section) => match section.as_u8("base.directed")? {
            [0] => false,
            [1] => true,
            _ => return Err(invalid("\"base.directed\" must be one byte, 0 or 1")),
        },
    };
    let layer_count = contiguous(&container.indices("layer.result"), "layer.result")?;
    if layer_count > MAX_LAYERS {
        return Err(GfError::new(
            "GF_COMPOSE_TOO_LARGE",
            "too many result layers",
        ));
    }
    for name in KNOWN.iter().filter(|n| n.starts_with("layer.")) {
        if container
            .indices(name)
            .iter()
            .any(|&i| i as usize >= layer_count)
        {
            return Err(invalid(format!(
                "\"{name}\" names a layer without a result"
            )));
        }
    }
    let mut layers = Vec::with_capacity(layer_count);
    for i in 0..layer_count as u32 {
        let text = |name: &str| -> GfResult<Option<&str>> {
            container.get(name, i).map(|s| s.as_utf8(name)).transpose()
        };
        let layer_error = |e: GfError| e.in_layer(i as usize);
        let intent_text = text("layer.intent").map_err(layer_error)?.ok_or_else(|| {
            GfError::new(
                "GF_COMPOSE_INTENT_REQUIRED",
                "every result layer needs an explicit visualization intent",
            )
            .in_layer(i as usize)
        })?;
        let intent = Intent::parse(intent_text).ok_or_else(|| {
            GfError::new("GF_COMPOSE_INTENT_INVALID", "unknown visualization intent")
                .in_layer(i as usize)
        })?;
        let missing = text("layer.missing")
            .map_err(layer_error)?
            .map(|t| {
                MissingPolicy::parse(t).ok_or_else(|| invalid("unknown missing-identity policy"))
            })
            .transpose()
            .map_err(layer_error)?;
        let extra = text("layer.extra")
            .map_err(layer_error)?
            .map(|t| ExtraPolicy::parse(t).ok_or_else(|| invalid("unknown extra-identity policy")))
            .transpose()
            .map_err(layer_error)?;
        let result_id = text("layer.result_id").map_err(layer_error)?;
        if let Some(id) = result_id {
            let ok = !id.is_empty()
                && id.len() <= MAX_RESULT_ID_BYTES
                && id
                    .bytes()
                    .all(|b| b.is_ascii_alphanumeric() || b"-_.:".contains(&b));
            if !ok {
                return Err(
                    invalid("result ids are 1-128 characters of [A-Za-z0-9._:-]")
                        .in_layer(i as usize),
                );
            }
        }
        layers.push(LayerRequest {
            result: container
                .get("layer.result", i)
                .unwrap()
                .as_bytes("layer.result")
                .map_err(layer_error)?,
            result_id,
            generation: generation(&container, "layer.generation", i).map_err(layer_error)?,
            intent,
            missing,
            extra,
            rows: container
                .get("layer.rows", i)
                .map(|s| s.as_u64("layer.rows"))
                .transpose()
                .map_err(layer_error)?,
            coordinates: container
                .get("layer.coordinates", i)
                .map(|s| s.as_bytes("layer.coordinates"))
                .transpose()
                .map_err(layer_error)?,
        });
    }
    if layers.is_empty() {
        return Err(invalid("a composition needs at least one result layer"));
    }
    let render = decode_render(&container)?;
    if container.indices("select.uuid").iter().any(|&i| i != 0) {
        return Err(invalid("\"select.uuid\" is a single section"));
    }
    let selected = container
        .get("select.uuid", 0)
        .map(|s| s.as_uuids("select.uuid"))
        .transpose()?
        .unwrap_or_default();
    if selected.len() > super::base::MAX_BASE_NODES {
        return Err(GfError::new(
            "GF_COMPOSE_TOO_LARGE",
            "the selection exceeds the node bound",
        ));
    }
    Ok(Request {
        render,
        selected,
        base_tables,
        base_planes,
        base_generation: generation(&container, "base.generation", 0)?,
        directed,
        layers,
    })
}

fn decode_render<'a>(container: &Container<'a>) -> GfResult<Option<Render<'a>>> {
    let names = [
        "render.width",
        "render.height",
        "render.theme",
        "render.title",
    ];
    if names.iter().all(|n| container.get(n, 0).is_none()) {
        return Ok(None);
    }
    if names
        .iter()
        .any(|n| container.indices(n).iter().any(|&i| i != 0))
    {
        return Err(invalid("render sections are single sections"));
    }
    let scalar = |name: &str| -> GfResult<f64> {
        match container
            .get(name, 0)
            .map(|s| s.as_f64(name))
            .transpose()?
            .as_deref()
        {
            Some([value]) => Ok(*value),
            _ => Err(invalid(format!("\"{name}\" must hold one f64"))),
        }
    };
    let (width, height) = (scalar("render.width")?, scalar("render.height")?);
    let viewport = crate::graph_style::MAX_SEMANTIC_GRAPH_VIEWPORT;
    if !(160.0..=viewport).contains(&width) || !(120.0..=viewport).contains(&height) {
        return Err(invalid(format!(
            "render viewports are 160..{viewport} by 120..{viewport} CSS pixels"
        )));
    }
    let theme = match container.get("render.theme", 0) {
        None => crate::graph_style::THEME_LIGHT,
        Some(section) => match section.as_utf8("render.theme")? {
            "light" => crate::graph_style::THEME_LIGHT,
            "dark" => crate::graph_style::THEME_DARK,
            _ => return Err(invalid("render.theme must be light or dark")),
        },
    };
    let title = match container.get("render.title", 0) {
        None => "",
        Some(section) => section.as_utf8("render.title")?,
    };
    if title.len() > 4096 || title.contains('\0') {
        return Err(invalid("render.title exceeds the Scene text bound"));
    }
    Ok(Some(Render {
        width,
        height,
        theme,
        title,
    }))
}
