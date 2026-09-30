//! Direct-tier canonical Scene for a graph composition (spec §6.3).
//!
//! When a request carries `render.*` sections, Rust lays the composed graph
//! out with the graph mark's default layout (seeded force, seed 0, 300 ticks,
//! over every composed edge), seeded from a `libm`-free circle
//! ([`layout_force_portable`]), and lowers the document's own planes and
//! legend to the canonical semantic graph Scene. The Scene is a pure function
//! of the `XYGF` document and the render options, so native and
//! direct-browser WASM hosts produce identical bytes on every platform, and browser WebGL, SVG, and raster consumers
//! paint the same primitives. Stable IDs follow the semantic Scene: node `i`
//! is `2^32 + i`, edge `j` is `j + 1`.

use super::container::{Container, DOCUMENT_MAGIC};
use super::request::Render;
use super::{GfError, GfResult};
use crate::graph::layout_force_portable;
use crate::graph_style::{
    encode_semantic_graph_scene_with_legend, SemanticGraphSceneInput, SemanticLegendOverride,
    SemanticLegendRow, MAX_SEMANTIC_GRAPH_SCENE_PRIMITIVES, SEMANTIC_GRAPH_SCENE_VERSION,
    THEME_DARK,
};
use crate::scene::SceneError;

/// Stable ID of composed node `i` in the Scene.
pub const NODE_STABLE_ID_BASE: u64 = 1 << 32;
/// Stable ID of composed edge `j` is `EDGE_STABLE_ID_BASE + j`.
pub const EDGE_STABLE_ID_BASE: u64 = 1;
/// Layout seed and ticks: the graph mark's `layout="force"` default.
pub const SCENE_LAYOUT_SEED: u64 = 0;
pub const SCENE_LAYOUT_TICKS: u32 = 300;

/// A rendered Scene plus the node positions it was laid out at.
pub struct RenderedScene {
    pub scene: Vec<u8>,
    pub x: Vec<f64>,
    pub y: Vec<f64>,
}

fn malformed() -> GfError {
    GfError::new(
        "GF_COMPOSE_SCENE_INVALID",
        "the composition document is malformed",
    )
}

pub fn render_graph(document: &[u8], render: &Render<'_>) -> GfResult<RenderedScene> {
    let doc = Container::decode(document, DOCUMENT_MAGIC)?;
    let get = |name: &str| doc.get(name, 0).ok_or_else(malformed);
    let n = get("node.class")?.count;
    let e = get("edge.class")?.count;
    if n + e > MAX_SEMANTIC_GRAPH_SCENE_PRIMITIVES {
        return Err(GfError::new(
            "GF_COMPOSE_SCENE_TOO_LARGE",
            format!(
                "direct-tier Scenes hold at most {MAX_SEMANTIC_GRAPH_SCENE_PRIMITIVES} nodes and edges; this composition has {}. Use the native graph mark (level-of-detail) or select rows",
                n + e
            ),
        ));
    }
    let sources = get("edge.source")?.as_u64("edge.source")?;
    let targets = get("edge.target")?.as_u64("edge.target")?;
    let mut x = vec![0.0; n];
    let mut y = vec![0.0; n];
    if !layout_force_portable(
        n as u64,
        &sources,
        &targets,
        SCENE_LAYOUT_SEED,
        SCENE_LAYOUT_TICKS,
        &mut x,
        &mut y,
    ) {
        return Err(GfError::new(
            "GF_COMPOSE_SCENE_INVALID",
            "the composed graph could not be laid out",
        ));
    }
    let u8s = |name: &str| get(name).and_then(|s| s.as_u8(name).map(<[u8]>::to_vec));
    let u32s = |name: &str| -> GfResult<Vec<u32>> {
        let section = get(name)?;
        Ok(section
            .payload
            .chunks_exact(4)
            .map(|c| u32::from_le_bytes(c.try_into().unwrap()))
            .collect())
    };
    let f64s = |name: &str| get(name).and_then(|s| s.as_f64(name));
    let texts = |name: &str| get(name).and_then(|s| s.as_texts(name));
    let (node_class, node_epistemic, node_status) = (
        u8s("node.class")?,
        u8s("node.epistemic")?,
        u8s("node.status")?,
    );
    let (edge_class, edge_epistemic, edge_status) = (
        u8s("edge.class")?,
        u8s("edge.epistemic")?,
        u8s("edge.status")?,
    );
    let (node_metric, edge_metric) = (f64s("node.metric")?, f64s("edge.metric")?);
    let (node_flags, edge_flags) = (u32s("node.flags")?, u32s("edge.flags")?);
    let node_labels = texts("node.label")?;
    let edge_labels = texts("edge.label")?;
    let legend_text = texts("legend.text")?;
    let legend_shape = u8s("legend.shape")?;
    let palette = u8s(if render.theme == THEME_DARK {
        "legend.rgba_dark"
    } else {
        "legend.rgba_light"
    })?;
    let title = doc
        .get("legend.title", 0)
        .map(|s| s.as_utf8("legend.title"))
        .transpose()?
        .unwrap_or("");
    let rows: Vec<SemanticLegendRow<'_>> = legend_text
        .iter()
        .enumerate()
        .map(|(i, label)| SemanticLegendRow {
            symbol: legend_shape[i],
            color: palette[i * 4..i * 4 + 4].try_into().unwrap(),
            label,
        })
        .collect();
    let input = SemanticGraphSceneInput {
        version: SEMANTIC_GRAPH_SCENE_VERSION,
        width: render.width,
        height: render.height,
        theme: render.theme,
        title: render.title,
        x: &x,
        y: &y,
        node_classes: &node_class,
        node_epistemic: &node_epistemic,
        node_statuses: &node_status,
        node_metric: &node_metric,
        node_flags: &node_flags,
        node_labels: &node_labels,
        sources: &sources,
        targets: &targets,
        edge_classes: &edge_class,
        edge_epistemic: &edge_epistemic,
        edge_statuses: &edge_status,
        edge_metric: &edge_metric,
        edge_flags: &edge_flags,
        edge_labels: &edge_labels,
    };
    let scene = encode_semantic_graph_scene_with_legend(input, SemanticLegendOverride { title, rows: &rows })
        .map_err(|error| match error {
            SceneError::Limit | SceneError::PainterTraceLimit => GfError::new(
                "GF_COMPOSE_SCENE_TOO_LARGE",
                "the composition expands past the direct-tier Scene primitive bound; use the native graph mark or select rows",
            ),
            _ => GfError::new("GF_COMPOSE_SCENE_INVALID", "the composition could not be lowered to a Scene"),
        })?;
    Ok(RenderedScene { scene, x, y })
}
