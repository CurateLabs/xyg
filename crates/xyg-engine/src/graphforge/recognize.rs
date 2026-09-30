//! Recognize a GraphForge result from its Arrow schema metadata (§3).
//!
//! Algorithm results name themselves with `graphforge.verb`,
//! `graphforge.algorithm`, and `graphforge.algorithm_schema_version`; `find`
//! results with `graphforge.verb=find` and `graphforge.search_schema_version`.
//! Nothing is inferred from column names or values for those results. Cypher
//! results are recognized by entity struct columns (base-graph material).
//! Codes match the GraphForge extension's ledger (`GF_RESULT_*`).

use super::ledger::{self, Kind, SchemaEntry, ALGORITHM_VERBS};
use super::{GfError, GfResult};
use crate::arrow_ipc::{DataType, Field, Schema};

#[derive(Clone, Copy, Debug)]
pub struct Recognized {
    pub entry: &'static SchemaEntry,
    pub verb: &'static str,
    /// Algorithm name as registered in the ledger (empty for `find`).
    pub algorithm: &'static str,
}

fn kind_matches(kind: Kind, field: &Field) -> bool {
    let item = || field.children.first().map(|c| &c.data_type);
    match kind {
        Kind::Uuid => field.data_type == DataType::FixedSizeBinary(16),
        Kind::UuidList => {
            matches!(field.data_type, DataType::List { .. })
                && item() == Some(&DataType::FixedSizeBinary(16))
        }
        Kind::Float => matches!(field.data_type, DataType::Float { .. }),
        Kind::Int => matches!(field.data_type, DataType::Int { .. }),
        Kind::Bool => field.data_type == DataType::Bool,
        Kind::Utf8 => matches!(field.data_type, DataType::Utf8 { .. }),
        Kind::FloatVector => {
            matches!(
                field.data_type,
                DataType::List { .. } | DataType::FixedSizeList(_)
            ) && matches!(item(), Some(DataType::Float { .. }))
        }
    }
}

/// Verify every canonical field is present with its declared Arrow kind.
pub fn check_fields(entry: &SchemaEntry, schema: &Schema) -> GfResult<()> {
    for spec in entry.fields {
        let Some(index) = schema.field_index(spec.name) else {
            return Err(GfError::new(
                "GF_RESULT_SCHEMA_MISMATCH",
                format!(
                    "result is missing the canonical \"{}\" field for the {} schema",
                    spec.name, entry.id
                ),
            )
            .with_field(spec.name));
        };
        let field = &schema.fields[index];
        if !kind_matches(spec.kind, field) {
            return Err(GfError::new(
                "GF_RESULT_SCHEMA_MISMATCH",
                format!(
                    "field \"{}\" is {}; the {} schema expects {}",
                    spec.name,
                    field.type_name(),
                    entry.id,
                    spec.kind.name()
                ),
            )
            .with_field(spec.name));
        }
    }
    Ok(())
}

fn version(schema: &Schema, key: &str) -> Option<u32> {
    schema.metadata(key)?.parse().ok()
}

/// Recognize an algorithm or search result. Tables without GraphForge result
/// metadata fail with `GF_RESULT_NOT_ALGORITHM` (Cypher/tabular results are
/// base-graph input, not result layers).
pub fn recognize(schema: &Schema) -> GfResult<Recognized> {
    let verb = schema.metadata("graphforge.verb");
    if let Some(verb) = verb.and_then(|v| ALGORITHM_VERBS.iter().find(|&&known| known == v)) {
        let algorithm = schema.metadata("graphforge.algorithm").unwrap_or("");
        let Some(entry) = ledger::schema_for_algorithm(algorithm) else {
            return Err(GfError::new(
                "GF_RESULT_SCHEMA_UNREGISTERED",
                format!(
                    "no composition is registered for the \"{}\" {verb} result",
                    bounded(algorithm)
                ),
            ));
        };
        let registered = entry
            .algorithms
            .iter()
            .find(|&&a| a == algorithm)
            .expect("ledger lookup matched");
        let got = version(schema, "graphforge.algorithm_schema_version");
        if got != Some(entry.version) || entry.version != ledger::ALGORITHM_SCHEMA_VERSION {
            return Err(GfError::new(
                "GF_RESULT_SCHEMA_VERSION",
                format!(
                    "algorithm result schema version {} is not supported (expected {})",
                    got.map_or("(missing)".into(), |v| v.to_string()),
                    entry.version
                ),
            ));
        }
        check_fields(entry, schema)?;
        return Ok(Recognized {
            entry,
            verb,
            algorithm: registered,
        });
    }
    if verb == Some("find") {
        let got = version(schema, "graphforge.search_schema_version");
        if got != Some(ledger::SEARCH_SCHEMA_VERSION) {
            return Err(GfError::new(
                "GF_RESULT_SCHEMA_VERSION",
                format!(
                    "search result schema version {} is not supported (expected {})",
                    got.map_or("(missing)".into(), |v| v.to_string()),
                    ledger::SEARCH_SCHEMA_VERSION
                ),
            ));
        }
        check_fields(&ledger::SEARCH_SCHEMA, schema)?;
        return Ok(Recognized {
            entry: &ledger::SEARCH_SCHEMA,
            verb: "find",
            algorithm: "",
        });
    }
    Err(GfError::new(
        "GF_RESULT_NOT_ALGORITHM",
        "result carries no GraphForge algorithm or search metadata; pass Cypher entity tables as the base graph",
    ))
}

/// Metadata text is echoed in diagnostics only as a bounded identifier.
fn bounded(text: &str) -> String {
    let clean: String = text
        .chars()
        .filter(|c| c.is_ascii_alphanumeric() || *c == '_' || *c == '-')
        .take(64)
        .collect();
    if clean.is_empty() {
        "unknown".into()
    } else {
        clean
    }
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
    fn every_algorithm_fixture_is_recognized_with_its_schema() {
        let manifest = std::fs::read_to_string(format!(
            "{}/../../tests/fixtures/graphforge/results/manifest.json",
            env!("CARGO_MANIFEST_DIR")
        ))
        .unwrap();
        let contracts = &manifest[..manifest.find("\"fixtures\"").unwrap()];
        for part in contracts.split("\"algorithm\": \"").skip(1) {
            let name = &part[..part.find('"').unwrap()];
            let bytes = load(name);
            let table = read_table(&bytes).unwrap();
            let recognized = recognize(&table.schema).unwrap_or_else(|e| panic!("{name}: {e:?}"));
            assert_eq!(recognized.algorithm, name);
            assert!(recognized.entry.algorithms.contains(&name));
        }
        let find = load("find");
        let table = read_table(&find).unwrap();
        assert_eq!(recognize(&table.schema).unwrap().entry.id, "search");
    }

    #[test]
    fn cypher_and_schema_results_are_not_layers() {
        for name in ["cypher-nodes", "cypher-edges", "cypher-scalars", "schema"] {
            let bytes = load(name);
            let table = read_table(&bytes).unwrap();
            assert_eq!(
                recognize(&table.schema).unwrap_err().code,
                "GF_RESULT_NOT_ALGORITHM"
            );
        }
    }

    fn with_metadata(name: &str, key: &str, value: Option<&str>) -> Schema {
        let bytes = load(name);
        let mut schema = read_table(&bytes).unwrap().schema;
        schema.metadata.retain(|(k, _)| k != key);
        if let Some(value) = value {
            schema.metadata.push((key.into(), value.into()));
        }
        schema
    }

    #[test]
    fn unknown_algorithms_and_versions_fail_with_stable_codes() {
        let schema = with_metadata("pagerank", "graphforge.algorithm", Some("quantum_rank"));
        let error = recognize(&schema).unwrap_err();
        assert_eq!(error.code, "GF_RESULT_SCHEMA_UNREGISTERED");
        assert!(error.message.contains("quantum_rank"));

        let schema = with_metadata("pagerank", "graphforge.algorithm_schema_version", Some("2"));
        assert_eq!(
            recognize(&schema).unwrap_err().code,
            "GF_RESULT_SCHEMA_VERSION"
        );
        let schema = with_metadata("pagerank", "graphforge.algorithm_schema_version", None);
        assert_eq!(
            recognize(&schema).unwrap_err().code,
            "GF_RESULT_SCHEMA_VERSION"
        );
        let schema = with_metadata("find", "graphforge.search_schema_version", Some("9"));
        assert_eq!(
            recognize(&schema).unwrap_err().code,
            "GF_RESULT_SCHEMA_VERSION"
        );
    }

    #[test]
    fn field_type_mismatches_name_the_field() {
        let bytes = load("pagerank");
        let mut schema = read_table(&bytes).unwrap().schema;
        let score = schema.field_index("score").unwrap();
        schema.fields[score].data_type = DataType::Utf8 { large: false };
        let error = recognize(&schema).unwrap_err();
        assert_eq!(error.code, "GF_RESULT_SCHEMA_MISMATCH");
        assert_eq!(error.field.as_deref(), Some("score"));
        assert!(error.message.contains("Utf8"));

        schema.fields.remove(score);
        let error = recognize(&schema).unwrap_err();
        assert_eq!(error.code, "GF_RESULT_SCHEMA_MISMATCH");
        assert!(error.message.contains("missing"));
    }

    #[test]
    fn metadata_echo_is_bounded_to_an_identifier() {
        assert_eq!(bounded("<script>alert(1)</script>"), "scriptalert1script");
        assert_eq!(bounded(""), "unknown");
        assert_eq!(bounded(&"a".repeat(500)).len(), 64);
    }
}
