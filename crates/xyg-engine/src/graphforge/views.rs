//! Non-graph GraphForge compositions (spec §4.7): tables for scalar and
//! category results, bar charts for category results, and honest embedding
//! views. None of these is forced into a graph, and an embedding's first two
//! dimensions are never plotted as coordinates unless the embedding is itself
//! two-dimensional and the caller asked for coordinates.

use super::base::{self, BaseGraph, RawPlanes};
use super::columns::{bools, f64s, int_texts, texts, uuids, vectors};
use super::compose::{
    check_generation, document_header, encode_decisions, layer_error, layer_provenance, Decision,
    Layer, NONE_U64,
};
use super::container::{Builder, DOCUMENT_MAGIC};
use super::ledger::{Composition, Intent, Kind, Role};
use super::request::{ExtraPolicy, MissingPolicy, Request};
use super::{uuid_map, GfError, GfResult, Uuid, UuidKey};
use crate::arrow_ipc::{read_table, DataType};

/// Cells in one table composition.
pub const MAX_TABLE_CELLS: usize = 1_000_000;
/// Values in one embedding view (rows × dimensions).
pub const MAX_EMBEDDING_VALUES: usize = 20_000_000;

pub(super) fn document(request: &Request<'_>, layer: &Layer<'_>) -> GfResult<Vec<u8>> {
    let mut decisions = Vec::new();
    let base = if request.base_tables.is_empty() && request.base_planes.is_none() {
        None
    } else {
        check_generation(request, layer, &mut decisions)?;
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
        Some(base::build(&tables, planes, request.directed)?)
    };
    match (layer.entry().composition, layer.request.intent) {
        (Composition::Scalar | Composition::Category, Intent::Table) => table(layer, decisions),
        (Composition::Category, Intent::BarChart) => bar_chart(layer, decisions),
        (Composition::Embedding, Intent::ParallelCoordinates) => {
            parallel_coordinates(layer, base.as_ref(), decisions)
        }
        (Composition::Embedding, Intent::EmbeddingCoordinates) => {
            coordinates(layer, base.as_ref(), decisions)
        }
        (other, intent) => Err(layer_error(
            "GF_COMPOSE_INTENT_UNSUPPORTED",
            layer.index,
            format!(
                "{} compositions do not support the {} intent",
                other.name(),
                intent.name()
            ),
        )),
    }
}

fn counts(out: &mut Builder, layer: &Layer<'_>, matched: usize, missing: u64, extra: u64) {
    out.u64s(
        "layer.counts",
        0,
        &[
            layer.table.rows as u64,
            layer.rows.len() as u64,
            matched as u64,
            missing,
            extra,
        ],
    );
}

fn decide(decisions: &mut Vec<Decision>, code: &'static str, layer: &Layer<'_>, count: u64) {
    if count > 0 {
        decisions.push(Decision {
            code,
            layer: Some(layer.index),
            count,
        });
    }
}

/// Shortest round-trip text for a float (identical on every host).
fn float_text(value: f64) -> String {
    if value.is_nan() {
        "NaN".into()
    } else {
        format!("{value}")
    }
}

// -- tables ------------------------------------------------------------------

fn table(layer: &Layer<'_>, mut decisions: Vec<Decision>) -> GfResult<Vec<u8>> {
    let fields = layer.entry().fields;
    if layer.rows.len().saturating_mul(fields.len()) > MAX_TABLE_CELLS {
        return Err(layer_error(
            "GF_COMPOSE_TOO_LARGE",
            layer.index,
            format!("table compositions hold at most {MAX_TABLE_CELLS} cells; select rows"),
        ));
    }
    let mut columns: Vec<(Vec<String>, Vec<f64>, Vec<u8>)> = Vec::with_capacity(fields.len());
    let mut nulls = 0u64;
    for spec in fields {
        let column = layer.table.column(spec.name).unwrap();
        let (text, value): (Vec<Option<String>>, Vec<f64>) = match spec.kind {
            Kind::Bool => {
                let values = bools(&column).map_err(|e| e.in_layer(layer.index))?;
                (
                    values.iter().map(|v| v.map(|b| b.to_string())).collect(),
                    values
                        .iter()
                        .map(|v| v.map_or(f64::NAN, |b| f64::from(u8::from(b))))
                        .collect(),
                )
            }
            Kind::Int => {
                // Exact decimal text, including UInt64 counts above i64::MAX.
                let values = int_texts(&column).map_err(|e| e.in_layer(layer.index))?;
                (
                    values
                        .iter()
                        .map(|v| v.as_ref().map(|(t, _)| t.clone()))
                        .collect(),
                    values
                        .iter()
                        .map(|v| v.as_ref().map_or(f64::NAN, |(_, f)| *f))
                        .collect(),
                )
            }
            Kind::Float => {
                let values = f64s(&column).map_err(|e| e.in_layer(layer.index))?;
                (
                    values.iter().map(|v| v.map(float_text)).collect(),
                    values.iter().map(|v| v.unwrap_or(f64::NAN)).collect(),
                )
            }
            Kind::Utf8 => {
                let values = texts(&column).map_err(|e| e.in_layer(layer.index))?;
                (
                    values.iter().map(|v| v.map(str::to_owned)).collect(),
                    vec![f64::NAN; values.len()],
                )
            }
            other => {
                return Err(layer_error(
                    "GF_COMPOSE_INTENT_UNSUPPORTED",
                    layer.index,
                    format!("{} fields are not tabulated", other.name()),
                ))
            }
        };
        let mut cells = Vec::with_capacity(layer.rows.len());
        let mut values = Vec::with_capacity(layer.rows.len());
        let mut valid = Vec::with_capacity(layer.rows.len());
        for &row in &layer.rows {
            valid.push(u8::from(text[row].is_some()));
            nulls += u64::from(text[row].is_none());
            cells.push(text[row].clone().unwrap_or_default());
            values.push(value[row]);
        }
        columns.push((cells, values, valid));
    }
    decide(&mut decisions, "GF_COMPOSE_NULL_VALUES", layer, nulls);
    let mut out = Builder::new(DOCUMENT_MAGIC);
    document_header(&mut out, "table");
    layer_provenance(&mut out, 0, layer);
    counts(&mut out, layer, layer.rows.len(), 0, 0);
    out.texts(
        "table.columns",
        0,
        &fields.iter().map(|f| f.name).collect::<Vec<_>>(),
    );
    out.texts(
        "table.kinds",
        0,
        &fields.iter().map(|f| f.kind.name()).collect::<Vec<_>>(),
    );
    out.u64s(
        "table.rows",
        0,
        &layer.rows.iter().map(|&r| r as u64).collect::<Vec<_>>(),
    );
    let (mut cells, mut values, mut valid) = (Vec::new(), Vec::new(), Vec::new());
    for r in 0..layer.rows.len() {
        for column in &columns {
            cells.push(column.0[r].as_str());
            values.push(column.1[r]);
            valid.push(column.2[r]);
        }
    }
    out.texts("table.cells", 0, &cells);
    out.f64s("table.values", 0, &values);
    out.u8s("table.valid", 0, &valid);
    encode_decisions(&mut out, &decisions);
    Ok(out.finish())
}

// -- bar charts ----------------------------------------------------------------

fn bar_chart(layer: &Layer<'_>, mut decisions: Vec<Decision>) -> GfResult<Vec<u8>> {
    let category = layer
        .field(Role::Category)
        .expect("category schemas name a category");
    let metric = layer
        .field(Role::Metric)
        .expect("category schemas name a value");
    let labels =
        texts(&layer.table.column(category).unwrap()).map_err(|e| e.in_layer(layer.index))?;
    let values = layer
        .column_f64(metric)
        .map_err(|e| e.in_layer(layer.index))?;
    if layer.rows.len() > MAX_TABLE_CELLS {
        return Err(layer_error(
            "GF_COMPOSE_TOO_LARGE",
            layer.index,
            format!("bar charts hold at most {MAX_TABLE_CELLS} categories; select rows"),
        ));
    }
    let mut nulls = 0u64;
    let mut names = Vec::with_capacity(layer.rows.len());
    let mut bars = Vec::with_capacity(layer.rows.len());
    for &row in &layer.rows {
        nulls += u64::from(labels[row].is_none()) + u64::from(values[row].is_nan());
        names.push(labels[row].unwrap_or(""));
        bars.push(values[row]);
    }
    decide(&mut decisions, "GF_COMPOSE_NULL_VALUES", layer, nulls);
    let mut out = Builder::new(DOCUMENT_MAGIC);
    document_header(&mut out, "bar-chart");
    layer_provenance(&mut out, 0, layer);
    counts(&mut out, layer, layer.rows.len(), 0, 0);
    out.utf8("chart.category_name", 0, category);
    out.utf8("chart.value_name", 0, metric);
    out.texts("chart.category", 0, &names);
    out.f64s("chart.value", 0, &bars);
    out.f64s("chart.domain", 0, &bar_domain(&bars));
    out.u64s(
        "chart.result_row",
        0,
        &layer.rows.iter().map(|&r| r as u64).collect::<Vec<_>>(),
    );
    encode_decisions(&mut out, &decisions);
    Ok(out.finish())
}

/// `[x0, x1, y0, y1]` for bars at x = 0..k-1 (one unit slot each, so category
/// ticks sit on integer positions) over a value range that always includes the
/// zero baseline, with 5% headroom on the sides away from zero.
fn bar_domain(bars: &[f64]) -> [f64; 4] {
    let k = bars.len().max(1) as f64;
    let (mut lo, mut hi) = bars
        .iter()
        .filter(|v| v.is_finite())
        .fold((0.0f64, 0.0f64), |(lo, hi), &v| (lo.min(v), hi.max(v)));
    if hi - lo <= 0.0 {
        hi = lo + 1.0;
    }
    let pad = (hi - lo) * 0.05;
    if hi > 0.0 {
        hi += pad;
    }
    if lo < 0.0 {
        lo -= pad;
    }
    [-0.5, k - 0.5, lo, hi]
}

// -- embeddings ------------------------------------------------------------------

/// Embedding rows joined to the optional base graph: `(result row, node id,
/// base row)` in result order, after the extra policy.
struct EmbeddingRows {
    rows: Vec<(usize, Uuid, u64)>,
    dimensions: usize,
    values: Vec<f64>,
    extra: u64,
}

fn embedding_rows(
    layer: &Layer<'_>,
    base: Option<&BaseGraph>,
    decisions: &mut Vec<Decision>,
) -> GfResult<EmbeddingRows> {
    let node_field = layer.field(Role::Node).unwrap();
    let vector_field = layer.field(Role::Vector).unwrap();
    let ids = uuids(&layer.table.column(node_field).unwrap(), false)
        .map_err(|e| e.in_layer(layer.index))?;
    // Bound the decode before allocating it: every row's vector is decoded,
    // so the table's row count times the declared width must fit.
    let column = layer.table.column(vector_field).unwrap();
    let declared = match column.field.data_type {
        DataType::FixedSizeList(n) => Some(n),
        _ => layer
            .table
            .schema
            .metadata("graphforge.dimensions")
            .and_then(|d| d.parse::<usize>().ok()),
    };
    if declared.is_some_and(|d| layer.table.rows.saturating_mul(d) > MAX_EMBEDDING_VALUES) {
        return Err(layer_error(
            "GF_COMPOSE_TOO_LARGE",
            layer.index,
            format!("embedding views hold at most {MAX_EMBEDDING_VALUES} values"),
        ));
    }
    let vectors = vectors(&column).map_err(|e| e.in_layer(layer.index))?;
    let dimensions = vectors.dimensions;
    if let Some(declared) = layer.table.schema.metadata("graphforge.dimensions") {
        if declared.parse::<usize>().ok() != Some(dimensions) {
            return Err(layer_error(
                "GF_RESULT_SCHEMA_MISMATCH",
                layer.index,
                "graphforge.dimensions disagrees with the embedding vector length".into(),
            )
            .with_field(vector_field));
        }
    }
    if dimensions == 0 {
        return Err(layer_error(
            "GF_RESULT_SCHEMA_MISMATCH",
            layer.index,
            "embedding vectors have no dimensions".into(),
        )
        .with_field(vector_field));
    }
    if layer.rows.len().saturating_mul(dimensions) > MAX_EMBEDDING_VALUES {
        return Err(layer_error(
            "GF_COMPOSE_TOO_LARGE",
            layer.index,
            format!("embedding views hold at most {MAX_EMBEDDING_VALUES} values; select rows"),
        ));
    }
    let mut rows = Vec::with_capacity(layer.rows.len());
    let mut values = Vec::with_capacity(layer.rows.len() * dimensions);
    let mut extra = 0u64;
    let mut seen = uuid_map(layer.rows.len());
    for &row in &layer.rows {
        let id = ids[row].ok_or_else(|| {
            layer_error(
                "GF_RESULT_NULL_IDENTITY",
                layer.index,
                format!("field \"{node_field}\" contains a null UUID"),
            )
            .with_field(node_field)
        })?;
        if seen.insert(UuidKey(id), row).is_some() {
            return Err(layer_error(
                "GF_COMPOSE_DUPLICATE_ID",
                layer.index,
                "embedding results name one node in more than one row".into(),
            ));
        }
        let base_row = match base {
            None => NONE_U64,
            Some(base) => {
                match base.node_index.get(&UuidKey(id)) {
                    Some(&node) => node as u64,
                    None => {
                        if base.edge_index.contains_key(&UuidKey(id)) {
                            return Err(layer_error(
                            "GF_COMPOSE_IDENTITY_KIND",
                            layer.index,
                            format!("node identities in field \"{node_field}\" name base relationships"),
                        ));
                        }
                        extra += 1;
                        continue;
                    }
                }
            }
        };
        rows.push((row, id, base_row));
        values.extend_from_slice(&vectors.values[row * dimensions..(row + 1) * dimensions]);
    }
    if extra > 0 {
        match layer.extra {
            ExtraPolicy::Error => {
                return Err(layer_error(
                    "GF_COMPOSE_EXTRA_IDS",
                    layer.index,
                    format!(
                        "{extra} of {} embedding rows name nodes absent from the base graph; the base graph is stale or incompatible (pass extra: \"drop\" to drop them)",
                        layer.rows.len()
                    ),
                ))
            }
            ExtraPolicy::Drop => decide(decisions, "GF_COMPOSE_EXTRA_DROPPED", layer, extra),
        }
    }
    decide(
        decisions,
        "GF_COMPOSE_NULL_VALUES",
        layer,
        vectors.nulls as u64,
    );
    Ok(EmbeddingRows {
        rows,
        dimensions,
        values,
        extra,
    })
}

fn names(base: Option<&BaseGraph>, rows: &[(usize, Uuid, u64)]) -> Vec<String> {
    rows.iter()
        .map(|&(_, _, base_row)| match base {
            Some(base) if base_row != NONE_U64 => base.node_name[base_row as usize]
                .clone()
                .unwrap_or_default(),
            _ => String::new(),
        })
        .collect()
}

/// An honest dimensional view: every node's full vector over dimension index.
fn parallel_coordinates(
    layer: &Layer<'_>,
    base: Option<&BaseGraph>,
    mut decisions: Vec<Decision>,
) -> GfResult<Vec<u8>> {
    let embedding = embedding_rows(layer, base, &mut decisions)?;
    let mut out = Builder::new(DOCUMENT_MAGIC);
    document_header(&mut out, "parallel-coordinates");
    layer_provenance(&mut out, 0, layer);
    counts(&mut out, layer, embedding.rows.len(), 0, embedding.extra);
    out.u32s("vector.dimensions", 0, &[embedding.dimensions as u32]);
    out.uuids(
        "vector.uuid",
        0,
        &embedding.rows.iter().map(|r| r.1).collect::<Vec<_>>(),
    );
    out.u64s(
        "vector.result_row",
        0,
        &embedding
            .rows
            .iter()
            .map(|r| r.0 as u64)
            .collect::<Vec<_>>(),
    );
    out.u64s(
        "vector.base_row",
        0,
        &embedding.rows.iter().map(|r| r.2).collect::<Vec<_>>(),
    );
    out.texts("vector.name", 0, &names(base, &embedding.rows));
    out.f64s("vector.values", 0, &embedding.values);
    out.f64s(
        "vector.domain",
        0,
        &parallel_domain(embedding.dimensions, &embedding.values),
    );
    encode_decisions(&mut out, &decisions);
    Ok(out.finish())
}

/// Plot domain `[x0, x1, y0, y1]` for parallel coordinates: the dimension
/// index span and the finite value range, each padded by 5% (a constant range
/// pads by 5% of its magnitude, at least 0.05) so every polyline is inside.
fn parallel_domain(dimensions: usize, values: &[f64]) -> [f64; 4] {
    let pad = |lo: f64, hi: f64| {
        let span = hi - lo;
        let p = if span > 0.0 {
            span * 0.05
        } else {
            lo.abs().max(1.0) * 0.05
        };
        (lo - p, hi + p)
    };
    let (x0, x1) = pad(0.0, dimensions.saturating_sub(1) as f64);
    let (mut lo, mut hi) = (f64::INFINITY, f64::NEG_INFINITY);
    for &v in values.iter().filter(|v| v.is_finite()) {
        lo = lo.min(v);
        hi = hi.max(v);
    }
    let (y0, y1) = if lo.is_finite() {
        pad(lo, hi)
    } else {
        (-1.0, 1.0)
    };
    [x0, x1, y0, y1]
}

/// Caller coordinates (`node_uuid`, `x`, `y`) keyed by UUID.
fn caller_coordinates(layer: &Layer<'_>, bytes: &[u8]) -> GfResult<Vec<(Uuid, f64, f64)>> {
    let table = read_table(bytes).map_err(|e| GfError::from(e).in_layer(layer.index))?;
    let schema_error = |message: &str| {
        layer_error(
            "GF_COMPOSE_COORDINATES_INVALID",
            layer.index,
            message.into(),
        )
    };
    let (Some(ids), Some(xs), Some(ys)) = (
        table.column("node_uuid"),
        table.column("x"),
        table.column("y"),
    ) else {
        return Err(schema_error("coordinates need node_uuid, x, and y columns"));
    };
    let numeric = |d: &DataType| matches!(d, DataType::Float { .. } | DataType::Int { .. });
    if !numeric(&xs.field.data_type) || !numeric(&ys.field.data_type) {
        return Err(schema_error("coordinate x and y must be numeric"));
    }
    let ids = uuids(&ids, true).map_err(|e| e.in_layer(layer.index))?;
    let xs = f64s(&xs).map_err(|e| e.in_layer(layer.index))?;
    let ys = f64s(&ys).map_err(|e| e.in_layer(layer.index))?;
    let mut seen = uuid_map(ids.len());
    let mut out = Vec::with_capacity(ids.len());
    for i in 0..ids.len() {
        let (Some(id), Some(x), Some(y)) = (ids[i], xs[i], ys[i]) else {
            return Err(schema_error("coordinates contain nulls"));
        };
        if !x.is_finite() || !y.is_finite() {
            return Err(schema_error("coordinates must be finite"));
        }
        if seen.insert(UuidKey(id), i).is_some() {
            return Err(layer_error(
                "GF_COMPOSE_DUPLICATE_ID",
                layer.index,
                "coordinates name one node twice".into(),
            ));
        }
        out.push((id, x, y));
    }
    Ok(out)
}

/// Embedding nodes placed at caller-provided 2D coordinates. A two-dimensional
/// embedding may place itself; any other dimensionality needs coordinates.
fn coordinates(
    layer: &Layer<'_>,
    base: Option<&BaseGraph>,
    mut decisions: Vec<Decision>,
) -> GfResult<Vec<u8>> {
    let embedding = embedding_rows(layer, base, &mut decisions)?;
    let d = embedding.dimensions;
    let mut placed: Vec<(usize, f64, f64)> = Vec::with_capacity(embedding.rows.len());
    let mut missing = 0u64;
    let mut extra = embedding.extra;
    let source = match layer.request.coordinates {
        Some(bytes) => {
            let coords = caller_coordinates(layer, bytes)?;
            let mut index = uuid_map(coords.len());
            for (i, c) in coords.iter().enumerate() {
                index.insert(UuidKey(c.0), i);
            }
            let mut used = vec![false; coords.len()];
            for (k, row) in embedding.rows.iter().enumerate() {
                match index.get(&UuidKey(row.1)) {
                    Some(&i) => {
                        used[i] = true;
                        placed.push((k, coords[i].1, coords[i].2));
                    }
                    None => missing += 1,
                }
            }
            let unused = used.iter().filter(|&&u| !u).count() as u64;
            if unused > 0 {
                match layer.extra {
                    ExtraPolicy::Error => {
                        return Err(layer_error(
                            "GF_COMPOSE_EXTRA_IDS",
                            layer.index,
                            format!("{unused} coordinate rows name nodes absent from the embedding"),
                        ))
                    }
                    ExtraPolicy::Drop => {
                        extra += unused;
                        decide(&mut decisions, "GF_COMPOSE_EXTRA_DROPPED", layer, unused);
                    }
                }
            }
            "caller"
        }
        None if d == 2 => {
            for (k, _) in embedding.rows.iter().enumerate() {
                let (x, y) = (embedding.values[k * 2], embedding.values[k * 2 + 1]);
                if x.is_finite() && y.is_finite() {
                    placed.push((k, x, y));
                } else {
                    missing += 1;
                }
            }
            decide(&mut decisions, "GF_COMPOSE_EMBEDDING_2D", layer, 1);
            "embedding"
        }
        None => {
            return Err(layer_error(
                "GF_COMPOSE_COORDINATES_REQUIRED",
                layer.index,
                format!(
                    "a {d}-dimensional embedding needs caller-provided 2D coordinates (node_uuid, x, y); dimensions are never plotted as x/y. Request parallel-coordinates for a dimensional view"
                ),
            ))
        }
    };
    if missing > 0 {
        if layer.missing != MissingPolicy::Hide {
            return Err(layer_error(
                "GF_COMPOSE_COORDINATES_MISSING",
                layer.index,
                format!("{missing} embedded nodes have no coordinates (pass missing: \"hide\" to leave them out)"),
            ));
        }
        decide(&mut decisions, "GF_COMPOSE_MISSING_HIDDEN", layer, missing);
    }
    let rows: Vec<(usize, Uuid, u64)> = placed.iter().map(|&(k, _, _)| embedding.rows[k]).collect();
    let mut out = Builder::new(DOCUMENT_MAGIC);
    document_header(&mut out, "scatter");
    layer_provenance(&mut out, 0, layer);
    counts(&mut out, layer, placed.len(), missing, extra);
    out.utf8("point.source", 0, source);
    out.u32s("vector.dimensions", 0, &[d as u32]);
    out.uuids(
        "point.uuid",
        0,
        &rows.iter().map(|r| r.1).collect::<Vec<_>>(),
    );
    out.u64s(
        "point.result_row",
        0,
        &rows.iter().map(|r| r.0 as u64).collect::<Vec<_>>(),
    );
    out.u64s(
        "point.base_row",
        0,
        &rows.iter().map(|r| r.2).collect::<Vec<_>>(),
    );
    out.texts("point.name", 0, &names(base, &rows));
    out.f64s(
        "point.x",
        0,
        &placed.iter().map(|p| p.1).collect::<Vec<_>>(),
    );
    out.f64s(
        "point.y",
        0,
        &placed.iter().map(|p| p.2).collect::<Vec<_>>(),
    );
    encode_decisions(&mut out, &decisions);
    Ok(out.finish())
}
