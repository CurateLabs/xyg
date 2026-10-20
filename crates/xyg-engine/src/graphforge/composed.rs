//! Typed, validated reader over a composed graph `XYGF` document.
//!
//! The interaction session reads a document it did not necessarily produce, so
//! every missing, mistyped, or version-skewed section is a stable
//! `GF_INTERACTION_INVALID` rather than a panic or a silent default.

use super::compose::COMPOSITION_VERSION;
use super::container::{Container, Section, DOCUMENT_MAGIC};
use super::{GfError, GfResult, Uuid};

pub struct ComposedDocument<'a> {
    container: Container<'a>,
    layers: usize,
}

fn invalid(message: impl Into<String>) -> GfError {
    GfError::new("GF_INTERACTION_INVALID", message)
}

impl<'a> ComposedDocument<'a> {
    /// Decode a successful graph document of the current composition version.
    pub fn decode(bytes: &'a [u8]) -> GfResult<Self> {
        let container = Container::decode(bytes, DOCUMENT_MAGIC)
            .map_err(|_| invalid("not a composed graph document"))?;
        let word = |name: &str| -> Option<u32> {
            container.get(name, 0)?.as_u32(name).ok()?.first().copied()
        };
        if word("status") != Some(0)
            || container
                .get("kind", 0)
                .and_then(|s| s.as_utf8("kind").ok())
                != Some("graph")
        {
            return Err(invalid("not a successful graph composition"));
        }
        if word("composition.version") != Some(COMPOSITION_VERSION) {
            return Err(invalid(
                "the document predates the composition version that carries the hierarchy",
            ));
        }
        let layers = container.indices("layer.schema");
        if layers
            .iter()
            .enumerate()
            .any(|(i, &index)| index as usize != i)
        {
            return Err(invalid("layer indices are not contiguous"));
        }
        Ok(Self {
            layers: layers.len(),
            container,
        })
    }

    fn section(&self, name: &str, index: u32) -> GfResult<Section<'a>> {
        self.container
            .get(name, index)
            .ok_or_else(|| invalid(format!("section \"{name}\" is missing")))
    }

    fn optional(&self, name: &str) -> Option<Section<'a>> {
        self.container.get(name, 0)
    }

    pub fn layer_count(&self) -> usize {
        self.layers
    }

    pub fn uuids(&self, name: &str) -> GfResult<Vec<Uuid>> {
        self.section(name, 0)?.as_uuids(name).map_err(retype)
    }

    pub fn u8s(&self, name: &str) -> GfResult<&'a [u8]> {
        self.section(name, 0)?.as_u8(name).map_err(retype)
    }

    pub fn u32s(&self, name: &str) -> GfResult<Vec<u32>> {
        self.section(name, 0)?.as_u32(name).map_err(retype)
    }

    pub fn i64s(&self, name: &str) -> GfResult<Vec<i64>> {
        self.section(name, 0)?.as_i64(name).map_err(retype)
    }

    pub fn u64s(&self, name: &str) -> GfResult<Vec<u64>> {
        self.section(name, 0)?.as_u64(name).map_err(retype)
    }

    pub fn optional_u32s(&self, name: &str) -> GfResult<Option<Vec<u32>>> {
        self.optional(name)
            .map(|s| s.as_u32(name).map_err(retype))
            .transpose()
    }

    pub fn optional_u8s(&self, name: &str) -> GfResult<Option<&'a [u8]>> {
        self.optional(name)
            .map(|s| s.as_u8(name).map_err(retype))
            .transpose()
    }

    pub fn generation(&self) -> GfResult<Option<Uuid>> {
        match self.optional("base.generation") {
            None => Ok(None),
            Some(s) => Ok(s
                .as_uuids("base.generation")
                .map_err(retype)?
                .first()
                .copied()),
        }
    }

    /// The caller-supplied result id of a layer, when it had one.
    pub fn result_id(&self, layer: usize) -> Option<String> {
        self.container
            .get("layer.result_id", layer as u32)
            .and_then(|s| s.as_utf8("layer.result_id").ok())
            .map(str::to_owned)
    }

    /// Result row of every composed edge in `layer` (`u64::MAX` absent).
    pub fn edge_rows(&self, layer: u32) -> GfResult<Vec<u64>> {
        self.section("layer.edge_rows", layer)?
            .as_u64("layer.edge_rows")
            .map_err(retype)
    }
}

/// Container type errors surface as the interaction code.
fn retype(error: GfError) -> GfError {
    invalid(error.message)
}
