//! Bounded, dependency-free Arrow IPC reader for GraphForge result ingress
//! (spec/design/graphforge-compositions.md §2).
//!
//! GraphForge returns results as Arrow IPC bytes. Hosts pass those bytes to
//! Rust unchanged, so schema metadata, field types, and columns are validated
//! once, here, for every host (native C ABI and direct-browser WASM alike).
//!
//! Scope: little-endian IPC streams and files, metadata V4/V5, uncompressed
//! bodies, no dictionary encoding. Every flatbuffer offset, buffer range,
//! offsets array, validity bitmap, and child length is checked before a value
//! can be read; nothing here panics on hostile input. Arrays borrow the input
//! bytes; values are decoded on access with explicit little-endian reads.
//!
//! Types a result may carry but a composition never reads (unions, views,
//! run-end encoding, ...) are walked for buffer accounting and kept as
//! [`ArrayData::Opaque`]; reading one reports its type instead of a value.

use std::fmt;

/// Total fields (including nested children) in one schema.
pub const MAX_IPC_FIELDS: usize = 4096;
/// Maximum nesting depth of one field tree.
pub const MAX_IPC_DEPTH: usize = 16;
/// Schema-level custom metadata entries.
pub const MAX_IPC_METADATA_ENTRIES: usize = 64;
/// Bytes per metadata key.
pub const MAX_IPC_METADATA_KEY_BYTES: usize = 256;
/// Bytes per metadata value (matches the GraphForge extension's decode bound).
pub const MAX_IPC_METADATA_VALUE_BYTES: usize = 1024;
/// Record batches in one table.
pub const MAX_IPC_BATCHES: usize = 1 << 20;
/// Rows in one table (all batches).
pub const MAX_IPC_ROWS: usize = 1 << 31;
/// Bytes of one field name.
pub const MAX_IPC_NAME_BYTES: usize = 1024;

const CONTINUATION: u32 = 0xFFFF_FFFF;
const FILE_MAGIC: &[u8; 6] = b"ARROW1";
const METADATA_V4: i16 = 3;
const METADATA_V5: i16 = 4;
const HEADER_SCHEMA: u8 = 1;
const HEADER_DICTIONARY: u8 = 2;
const HEADER_RECORD_BATCH: u8 = 3;

/// Stable failure classes; the host-facing code is `GF_ARROW_<class>`.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum IpcErrorKind {
    /// Bytes are not a well-formed Arrow IPC stream or file.
    Malformed,
    /// Well-formed Arrow that this reader deliberately does not accept.
    Unsupported,
    /// A declared bound was exceeded.
    Limit,
}

/// A reader failure: a class plus a static reason (never a data value).
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct IpcError {
    pub kind: IpcErrorKind,
    pub reason: &'static str,
}

impl IpcError {
    fn malformed(reason: &'static str) -> Self {
        Self {
            kind: IpcErrorKind::Malformed,
            reason,
        }
    }
    fn unsupported(reason: &'static str) -> Self {
        Self {
            kind: IpcErrorKind::Unsupported,
            reason,
        }
    }
    fn limit(reason: &'static str) -> Self {
        Self {
            kind: IpcErrorKind::Limit,
            reason,
        }
    }

    /// Stable host-facing code.
    pub fn code(&self) -> &'static str {
        match self.kind {
            IpcErrorKind::Malformed => "GF_ARROW_MALFORMED",
            IpcErrorKind::Unsupported => "GF_ARROW_UNSUPPORTED",
            IpcErrorKind::Limit => "GF_ARROW_LIMIT",
        }
    }
}

impl fmt::Display for IpcError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "{}: {}", self.code(), self.reason)
    }
}

type Result<T> = std::result::Result<T, IpcError>;

// ---------------------------------------------------------------------------
// Flatbuffer access (read-only, bounds-checked)
// ---------------------------------------------------------------------------

#[derive(Clone, Copy)]
struct FbTable<'a> {
    buf: &'a [u8],
    pos: usize,
    vtable: usize,
    vtable_len: usize,
    table_len: usize,
}

fn read_u16(buf: &[u8], at: usize) -> Result<u16> {
    let bytes = buf
        .get(
            at..at
                .checked_add(2)
                .ok_or(IpcError::malformed("offset overflow"))?,
        )
        .ok_or(IpcError::malformed("flatbuffer read out of range"))?;
    Ok(u16::from_le_bytes([bytes[0], bytes[1]]))
}

fn read_u32(buf: &[u8], at: usize) -> Result<u32> {
    let bytes = buf
        .get(
            at..at
                .checked_add(4)
                .ok_or(IpcError::malformed("offset overflow"))?,
        )
        .ok_or(IpcError::malformed("flatbuffer read out of range"))?;
    Ok(u32::from_le_bytes(bytes.try_into().unwrap()))
}

fn read_i64(buf: &[u8], at: usize) -> Result<i64> {
    let bytes = buf
        .get(
            at..at
                .checked_add(8)
                .ok_or(IpcError::malformed("offset overflow"))?,
        )
        .ok_or(IpcError::malformed("flatbuffer read out of range"))?;
    Ok(i64::from_le_bytes(bytes.try_into().unwrap()))
}

impl<'a> FbTable<'a> {
    fn root(buf: &'a [u8]) -> Result<Self> {
        let offset = read_u32(buf, 0)? as usize;
        Self::at(buf, offset)
    }

    fn at(buf: &'a [u8], pos: usize) -> Result<Self> {
        let soffset = read_u32(buf, pos)? as i32 as i64;
        let vtable = (pos as i64)
            .checked_sub(soffset)
            .filter(|&v| v >= 0)
            .ok_or(IpcError::malformed("flatbuffer vtable out of range"))?
            as usize;
        let vtable_len = read_u16(buf, vtable)? as usize;
        let table_len = read_u16(buf, vtable + 2)? as usize;
        if vtable_len < 4
            || vtable_len % 2 != 0
            || vtable
                .checked_add(vtable_len)
                .is_none_or(|end| end > buf.len())
            || table_len < 4
            || pos.checked_add(table_len).is_none_or(|end| end > buf.len())
        {
            return Err(IpcError::malformed("flatbuffer table out of range"));
        }
        Ok(Self {
            buf,
            pos,
            vtable,
            vtable_len,
            table_len,
        })
    }

    /// Absolute position of field `index`, or None when absent/defaulted.
    fn field(&self, index: usize) -> Result<Option<usize>> {
        let slot = 4 + 2 * index;
        if slot + 2 > self.vtable_len {
            return Ok(None);
        }
        let offset = read_u16(self.buf, self.vtable + slot)? as usize;
        if offset == 0 {
            return Ok(None);
        }
        if offset >= self.table_len {
            return Err(IpcError::malformed("flatbuffer field outside its table"));
        }
        Ok(Some(self.pos + offset))
    }

    fn u8_or(&self, index: usize, default: u8) -> Result<u8> {
        match self.field(index)? {
            Some(at) => self
                .buf
                .get(at)
                .copied()
                .ok_or(IpcError::malformed("flatbuffer read out of range")),
            None => Ok(default),
        }
    }

    fn bool_or(&self, index: usize, default: bool) -> Result<bool> {
        Ok(self.u8_or(index, u8::from(default))? != 0)
    }

    fn i16_or(&self, index: usize, default: i16) -> Result<i16> {
        match self.field(index)? {
            Some(at) => Ok(read_u16(self.buf, at)? as i16),
            None => Ok(default),
        }
    }

    fn i32_or(&self, index: usize, default: i32) -> Result<i32> {
        match self.field(index)? {
            Some(at) => Ok(read_u32(self.buf, at)? as i32),
            None => Ok(default),
        }
    }

    fn i64_or(&self, index: usize, default: i64) -> Result<i64> {
        match self.field(index)? {
            Some(at) => read_i64(self.buf, at),
            None => Ok(default),
        }
    }

    /// Follow a uoffset field to its target position.
    fn indirect(&self, index: usize) -> Result<Option<usize>> {
        let Some(at) = self.field(index)? else {
            return Ok(None);
        };
        let target = at
            .checked_add(read_u32(self.buf, at)? as usize)
            .filter(|&t| t < self.buf.len())
            .ok_or(IpcError::malformed("flatbuffer offset out of range"))?;
        Ok(Some(target))
    }

    fn table(&self, index: usize) -> Result<Option<FbTable<'a>>> {
        match self.indirect(index)? {
            Some(at) => Ok(Some(FbTable::at(self.buf, at)?)),
            None => Ok(None),
        }
    }

    /// `(start, len)` of a vector whose elements are `elem` bytes wide.
    fn vector(&self, index: usize, elem: usize) -> Result<Option<(usize, usize)>> {
        let Some(at) = self.indirect(index)? else {
            return Ok(None);
        };
        let len = read_u32(self.buf, at)? as usize;
        let start = at + 4;
        let end = len
            .checked_mul(elem)
            .and_then(|bytes| start.checked_add(bytes))
            .ok_or(IpcError::malformed("flatbuffer vector overflow"))?;
        if end > self.buf.len() {
            return Err(IpcError::malformed("flatbuffer vector out of range"));
        }
        Ok(Some((start, len)))
    }

    fn string(&self, index: usize, max: usize) -> Result<Option<&'a str>> {
        let Some((start, len)) = self.vector(index, 1)? else {
            return Ok(None);
        };
        if len > max {
            return Err(IpcError::limit("flatbuffer string exceeds its bound"));
        }
        std::str::from_utf8(&self.buf[start..start + len])
            .map(Some)
            .map_err(|_| IpcError::malformed("flatbuffer string is not UTF-8"))
    }

    fn table_vector(&self, index: usize) -> Result<Vec<FbTable<'a>>> {
        let Some((start, len)) = self.vector(index, 4)? else {
            return Ok(Vec::new());
        };
        let mut out = Vec::with_capacity(len.min(MAX_IPC_FIELDS));
        for i in 0..len {
            let slot = start + 4 * i;
            let target = slot
                .checked_add(read_u32(self.buf, slot)? as usize)
                .ok_or(IpcError::malformed("flatbuffer offset out of range"))?;
            out.push(FbTable::at(self.buf, target)?);
        }
        Ok(out)
    }
}

// ---------------------------------------------------------------------------
// Schema model
// ---------------------------------------------------------------------------

/// Logical Arrow type, restricted to what composition reads plus opaque
/// placeholders that still account for their buffers.
#[derive(Clone, Debug, PartialEq, Eq)]
pub enum DataType {
    Null,
    Bool,
    Int {
        bits: u8,
        signed: bool,
    },
    Float {
        bits: u8,
    },
    Utf8 {
        large: bool,
    },
    Binary {
        large: bool,
    },
    FixedSizeBinary(usize),
    List {
        large: bool,
    },
    FixedSizeList(usize),
    Struct,
    /// Any other fixed-width type (decimal, date, time, timestamp, interval,
    /// duration). The width is its byte size per value.
    OtherFixed {
        name: &'static str,
        width: usize,
    },
    /// A layout composition never reads; buffers are walked, values are not.
    Opaque {
        name: &'static str,
        layout: OpaqueLayout,
    },
}

/// Buffer layout of an opaque type (for body accounting only).
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum OpaqueLayout {
    Map,
    SparseUnion,
    DenseUnion,
    RunEndEncoded,
    View,
    ListView,
}

impl DataType {
    /// Short stable type name for diagnostics (never includes values).
    pub fn name(&self) -> String {
        match self {
            DataType::Null => "Null".into(),
            DataType::Bool => "Bool".into(),
            DataType::Int { bits, signed } => {
                format!("{}Int{bits}", if *signed { "" } else { "U" })
            }
            DataType::Float { bits } => format!("Float{bits}"),
            DataType::Utf8 { large } => if *large { "LargeUtf8" } else { "Utf8" }.into(),
            DataType::Binary { large } => if *large { "LargeBinary" } else { "Binary" }.into(),
            DataType::FixedSizeBinary(w) => format!("FixedSizeBinary({w})"),
            DataType::List { large } => if *large { "LargeList" } else { "List" }.into(),
            DataType::FixedSizeList(n) => format!("FixedSizeList({n})"),
            DataType::Struct => "Struct".into(),
            DataType::OtherFixed { name, .. } => (*name).into(),
            DataType::Opaque { name, .. } => (*name).into(),
        }
    }
}

#[derive(Clone, Debug)]
pub struct Field {
    pub name: String,
    pub nullable: bool,
    pub data_type: DataType,
    pub children: Vec<Field>,
}

impl Field {
    /// Child field by name (struct members, list item).
    pub fn child(&self, name: &str) -> Option<(usize, &Field)> {
        self.children
            .iter()
            .enumerate()
            .find(|(_, f)| f.name == name)
    }

    /// Nested type description for diagnostics, e.g. `List<FixedSizeBinary(16)>`.
    pub fn type_name(&self) -> String {
        match &self.data_type {
            DataType::List { .. } | DataType::FixedSizeList(_) => {
                let item = self
                    .children
                    .first()
                    .map(|c| c.type_name())
                    .unwrap_or_else(|| "?".into());
                format!("{}<{item}>", self.data_type.name())
            }
            other => other.name(),
        }
    }
}

#[derive(Clone, Debug, Default)]
pub struct Schema {
    pub fields: Vec<Field>,
    pub metadata: Vec<(String, String)>,
}

impl Schema {
    pub fn metadata(&self, key: &str) -> Option<&str> {
        self.metadata
            .iter()
            .find(|(k, _)| k == key)
            .map(|(_, v)| v.as_str())
    }

    pub fn field_index(&self, name: &str) -> Option<usize> {
        self.fields.iter().position(|f| f.name == name)
    }
}

fn parse_type(field: &FbTable<'_>) -> Result<DataType> {
    let type_code = field.u8_or(2, 0)?;
    let table = field.table(3)?;
    let t = |name: &'static str| table.ok_or(IpcError::malformed(name));
    Ok(match type_code {
        1 => DataType::Null,
        2 => {
            let t = t("Int type table missing")?;
            let bits = t.i32_or(0, 0)?;
            if !matches!(bits, 8 | 16 | 32 | 64) {
                return Err(IpcError::malformed("Int bit width must be 8/16/32/64"));
            }
            DataType::Int {
                bits: bits as u8,
                signed: t.bool_or(1, false)?,
            }
        }
        3 => {
            let precision = t("FloatingPoint type table missing")?.i16_or(0, 0)?;
            let bits = match precision {
                0 => 16,
                1 => 32,
                2 => 64,
                _ => return Err(IpcError::malformed("unknown float precision")),
            };
            DataType::Float { bits }
        }
        4 => DataType::Binary { large: false },
        5 => DataType::Utf8 { large: false },
        6 => DataType::Bool,
        7 => {
            let bits = t("Decimal type table missing")?.i32_or(2, 128)?;
            if !matches!(bits, 32 | 64 | 128 | 256) {
                return Err(IpcError::malformed("Decimal bit width is invalid"));
            }
            DataType::OtherFixed {
                name: "Decimal",
                width: bits as usize / 8,
            }
        }
        8 => {
            let unit = t("Date type table missing")?.i16_or(0, 1)?;
            DataType::OtherFixed {
                name: "Date",
                width: if unit == 0 { 4 } else { 8 },
            }
        }
        9 => {
            let bits = t("Time type table missing")?.i32_or(1, 32)?;
            if !matches!(bits, 32 | 64) {
                return Err(IpcError::malformed("Time bit width is invalid"));
            }
            DataType::OtherFixed {
                name: "Time",
                width: bits as usize / 8,
            }
        }
        10 => DataType::OtherFixed {
            name: "Timestamp",
            width: 8,
        },
        11 => {
            let unit = t("Interval type table missing")?.i16_or(0, 0)?;
            DataType::OtherFixed {
                name: "Interval",
                width: match unit {
                    0 => 4,
                    1 => 8,
                    2 => 16,
                    _ => return Err(IpcError::malformed("unknown interval unit")),
                },
            }
        }
        12 => DataType::List { large: false },
        13 => DataType::Struct,
        14 => {
            let mode = t("Union type table missing")?.i16_or(0, 0)?;
            DataType::Opaque {
                name: "Union",
                layout: if mode == 1 {
                    OpaqueLayout::DenseUnion
                } else {
                    OpaqueLayout::SparseUnion
                },
            }
        }
        15 => {
            let width = t("FixedSizeBinary type table missing")?.i32_or(0, 0)?;
            if width < 0 {
                return Err(IpcError::malformed("negative FixedSizeBinary width"));
            }
            DataType::FixedSizeBinary(width as usize)
        }
        16 => {
            let size = t("FixedSizeList type table missing")?.i32_or(0, 0)?;
            if size < 0 {
                return Err(IpcError::malformed("negative FixedSizeList size"));
            }
            DataType::FixedSizeList(size as usize)
        }
        17 => DataType::Opaque {
            name: "Map",
            layout: OpaqueLayout::Map,
        },
        18 => DataType::OtherFixed {
            name: "Duration",
            width: 8,
        },
        19 => DataType::Binary { large: true },
        20 => DataType::Utf8 { large: true },
        21 => DataType::List { large: true },
        22 => DataType::Opaque {
            name: "RunEndEncoded",
            layout: OpaqueLayout::RunEndEncoded,
        },
        23 => DataType::Opaque {
            name: "BinaryView",
            layout: OpaqueLayout::View,
        },
        24 => DataType::Opaque {
            name: "Utf8View",
            layout: OpaqueLayout::View,
        },
        25 => DataType::Opaque {
            name: "ListView",
            layout: OpaqueLayout::ListView,
        },
        26 => DataType::Opaque {
            name: "LargeListView",
            layout: OpaqueLayout::ListView,
        },
        _ => return Err(IpcError::unsupported("unknown Arrow type")),
    })
}

fn parse_field(fb: &FbTable<'_>, depth: usize, budget: &mut usize) -> Result<Field> {
    if depth > MAX_IPC_DEPTH {
        return Err(IpcError::limit("field nesting exceeds the depth bound"));
    }
    *budget = budget
        .checked_sub(1)
        .ok_or(IpcError::limit("schema exceeds the field bound"))?;
    if fb.field(4)?.is_some() {
        return Err(IpcError::unsupported("dictionary-encoded fields"));
    }
    let name = fb.string(0, MAX_IPC_NAME_BYTES)?.unwrap_or("").to_owned();
    let data_type = parse_type(fb)?;
    let mut children = Vec::new();
    for child in fb.table_vector(5)? {
        children.push(parse_field(&child, depth + 1, budget)?);
    }
    let arity_ok = match &data_type {
        DataType::List { .. } | DataType::FixedSizeList(_) => children.len() == 1,
        DataType::Struct => true,
        DataType::Opaque { layout, .. } => match layout {
            OpaqueLayout::Map | OpaqueLayout::ListView => children.len() == 1,
            OpaqueLayout::RunEndEncoded => children.len() == 2,
            _ => true,
        },
        _ => children.is_empty(),
    };
    if !arity_ok {
        return Err(IpcError::malformed(
            "field has the wrong number of children",
        ));
    }
    Ok(Field {
        name,
        nullable: fb.bool_or(1, false)?,
        data_type,
        children,
    })
}

fn parse_schema(fb: &FbTable<'_>) -> Result<Schema> {
    if fb.i16_or(0, 0)? != 0 {
        return Err(IpcError::unsupported("big-endian Arrow data"));
    }
    let mut budget = MAX_IPC_FIELDS;
    let mut fields = Vec::new();
    for field in fb.table_vector(1)? {
        fields.push(parse_field(&field, 0, &mut budget)?);
    }
    let entries = fb.table_vector(2)?;
    if entries.len() > MAX_IPC_METADATA_ENTRIES {
        return Err(IpcError::limit("schema metadata exceeds the entry bound"));
    }
    let mut metadata = Vec::with_capacity(entries.len());
    for kv in entries {
        let key = kv
            .string(0, MAX_IPC_METADATA_KEY_BYTES)?
            .unwrap_or("")
            .to_owned();
        let value = kv
            .string(1, MAX_IPC_METADATA_VALUE_BYTES)?
            .unwrap_or("")
            .to_owned();
        metadata.push((key, value));
    }
    Ok(Schema { fields, metadata })
}

// ---------------------------------------------------------------------------
// Arrays
// ---------------------------------------------------------------------------

/// One validated array (a column chunk or a nested child).
#[derive(Clone, Debug)]
pub struct Array<'a> {
    pub len: usize,
    pub null_count: usize,
    validity: Option<&'a [u8]>,
    pub data: ArrayData<'a>,
}

#[derive(Clone, Debug)]
pub enum ArrayData<'a> {
    Null,
    Bool(&'a [u8]),
    /// `width` little-endian bytes per value.
    Fixed {
        width: usize,
        values: &'a [u8],
    },
    /// Variable-width UTF-8 or binary values.
    Var {
        offsets: Offsets<'a>,
        values: &'a [u8],
    },
    List {
        offsets: Offsets<'a>,
        child: Box<Array<'a>>,
    },
    FixedList {
        size: usize,
        child: Box<Array<'a>>,
    },
    Struct(Vec<Array<'a>>),
    Opaque,
}

/// Validated monotone offsets (`len + 1` entries).
#[derive(Clone, Copy, Debug)]
pub struct Offsets<'a> {
    raw: &'a [u8],
    large: bool,
}

impl<'a> Offsets<'a> {
    fn get(&self, i: usize) -> usize {
        if self.large {
            i64::from_le_bytes(self.raw[i * 8..i * 8 + 8].try_into().unwrap()) as usize
        } else {
            i32::from_le_bytes(self.raw[i * 4..i * 4 + 4].try_into().unwrap()) as usize
        }
    }

    /// `(start, end)` of element `i`.
    pub fn range(&self, i: usize) -> (usize, usize) {
        (self.get(i), self.get(i + 1))
    }
}

impl<'a> Array<'a> {
    pub fn is_valid(&self, i: usize) -> bool {
        match self.validity {
            None => !matches!(self.data, ArrayData::Null),
            Some(bits) => bits[i / 8] & (1 << (i % 8)) != 0,
        }
    }

    /// Raw little-endian bytes of fixed-width element `i`.
    pub fn fixed(&self, i: usize) -> Option<&'a [u8]> {
        match &self.data {
            ArrayData::Fixed { width, values } => Some(&values[i * width..(i + 1) * width]),
            _ => None,
        }
    }

    pub fn bool_value(&self, i: usize) -> Option<bool> {
        match &self.data {
            ArrayData::Bool(bits) => Some(bits[i / 8] & (1 << (i % 8)) != 0),
            _ => None,
        }
    }

    /// Bytes of variable-width element `i`.
    pub fn var(&self, i: usize) -> Option<&'a [u8]> {
        match &self.data {
            ArrayData::Var { offsets, values } => {
                let (start, end) = offsets.range(i);
                Some(&values[start..end])
            }
            _ => None,
        }
    }

    /// Child range of list element `i`.
    pub fn list_range(&self, i: usize) -> Option<(usize, usize)> {
        match &self.data {
            ArrayData::List { offsets, .. } => Some(offsets.range(i)),
            ArrayData::FixedList { size, .. } => Some((i * size, (i + 1) * size)),
            _ => None,
        }
    }

    pub fn list_child(&self) -> Option<&Array<'a>> {
        match &self.data {
            ArrayData::List { child, .. } | ArrayData::FixedList { child, .. } => Some(child),
            _ => None,
        }
    }

    pub fn struct_child(&self, index: usize) -> Option<&Array<'a>> {
        match &self.data {
            ArrayData::Struct(children) => children.get(index),
            _ => None,
        }
    }
}

struct BodyReader<'a, 'b> {
    body: &'a [u8],
    nodes: &'b [(i64, i64)],
    buffers: &'b [(i64, i64)],
    variadic: &'b [i64],
    next_node: usize,
    next_buffer: usize,
    next_variadic: usize,
}

impl<'a, 'b> BodyReader<'a, 'b> {
    fn node(&mut self) -> Result<(usize, usize)> {
        let &(len, nulls) = self
            .nodes
            .get(self.next_node)
            .ok_or(IpcError::malformed("record batch has too few field nodes"))?;
        self.next_node += 1;
        if len < 0 || nulls < 0 || nulls > len || len as u64 > MAX_IPC_ROWS as u64 {
            return Err(IpcError::malformed("field node length is invalid"));
        }
        Ok((len as usize, nulls as usize))
    }

    fn buffer(&mut self) -> Result<&'a [u8]> {
        let &(offset, length) = self
            .buffers
            .get(self.next_buffer)
            .ok_or(IpcError::malformed("record batch has too few buffers"))?;
        self.next_buffer += 1;
        if offset < 0 || length < 0 {
            return Err(IpcError::malformed("negative buffer range"));
        }
        let start = offset as usize;
        let end = start
            .checked_add(length as usize)
            .filter(|&end| end <= self.body.len())
            .ok_or(IpcError::malformed("buffer lies outside the message body"))?;
        Ok(&self.body[start..end])
    }

    fn validity(&mut self, len: usize, nulls: usize) -> Result<Option<&'a [u8]>> {
        let bits = self.buffer()?;
        if nulls == 0 {
            return Ok(None);
        }
        if bits.len() < len.div_ceil(8) {
            return Err(IpcError::malformed(
                "validity bitmap is shorter than its array",
            ));
        }
        Ok(Some(bits))
    }

    fn offsets(&mut self, len: usize, large: bool, limit: usize) -> Result<Offsets<'a>> {
        let raw = self.buffer()?;
        let width = if large { 8 } else { 4 };
        let need = (len + 1)
            .checked_mul(width)
            .ok_or(IpcError::limit("offsets overflow"))?;
        if len == 0 && raw.is_empty() {
            // An empty array may omit its single zero offset.
            static ZERO: [u8; 8] = [0; 8];
            return Ok(Offsets { raw: &ZERO, large });
        }
        if raw.len() < need {
            return Err(IpcError::malformed(
                "offsets buffer is shorter than its array",
            ));
        }
        let offsets = Offsets {
            raw: &raw[..need],
            large,
        };
        let mut previous = if large {
            i64::from_le_bytes(raw[0..8].try_into().unwrap())
        } else {
            i32::from_le_bytes(raw[0..4].try_into().unwrap()) as i64
        };
        if previous < 0 {
            return Err(IpcError::malformed("negative offset"));
        }
        for i in 1..=len {
            let value = if large {
                i64::from_le_bytes(raw[i * 8..i * 8 + 8].try_into().unwrap())
            } else {
                i32::from_le_bytes(raw[i * 4..i * 4 + 4].try_into().unwrap()) as i64
            };
            if value < previous {
                return Err(IpcError::malformed("offsets are not monotone"));
            }
            previous = value;
        }
        if previous as u64 > limit as u64 {
            return Err(IpcError::malformed("offsets exceed their values"));
        }
        Ok(offsets)
    }

    fn array(&mut self, field: &Field) -> Result<Array<'a>> {
        let (len, null_count) = self.node()?;
        let fixed = |values: &'a [u8], width: usize| -> Result<ArrayData<'a>> {
            let need = len
                .checked_mul(width)
                .ok_or(IpcError::limit("fixed-width buffer overflow"))?;
            if values.len() < need {
                return Err(IpcError::malformed(
                    "value buffer is shorter than its array",
                ));
            }
            Ok(ArrayData::Fixed {
                width,
                values: &values[..need],
            })
        };
        let (validity, data) = match &field.data_type {
            DataType::Null => (None, ArrayData::Null),
            DataType::Bool => {
                let validity = self.validity(len, null_count)?;
                let values = self.buffer()?;
                if values.len() < len.div_ceil(8) {
                    return Err(IpcError::malformed(
                        "boolean buffer is shorter than its array",
                    ));
                }
                (validity, ArrayData::Bool(values))
            }
            DataType::Int { bits, .. } | DataType::Float { bits } => {
                let validity = self.validity(len, null_count)?;
                let values = self.buffer()?;
                (validity, fixed(values, *bits as usize / 8)?)
            }
            DataType::FixedSizeBinary(width) => {
                let validity = self.validity(len, null_count)?;
                let values = self.buffer()?;
                (validity, fixed(values, *width)?)
            }
            DataType::OtherFixed { width, .. } => {
                let validity = self.validity(len, null_count)?;
                let values = self.buffer()?;
                (validity, fixed(values, *width)?)
            }
            DataType::Utf8 { large } | DataType::Binary { large } => {
                let validity = self.validity(len, null_count)?;
                // Offsets precede the values buffer; peek the values length.
                let values_index = self.next_buffer + 1;
                let &(_, values_len) = self
                    .buffers
                    .get(values_index)
                    .ok_or(IpcError::malformed("record batch has too few buffers"))?;
                let offsets = self.offsets(len, *large, values_len.max(0) as usize)?;
                let values = self.buffer()?;
                if matches!(field.data_type, DataType::Utf8 { .. }) {
                    for i in 0..len {
                        let (start, end) = offsets.range(i);
                        if std::str::from_utf8(&values[start..end]).is_err() {
                            return Err(IpcError::malformed("Utf8 value is not valid UTF-8"));
                        }
                    }
                }
                (validity, ArrayData::Var { offsets, values })
            }
            DataType::List { large } => {
                let validity = self.validity(len, null_count)?;
                let offsets = self.offsets(len, *large, usize::MAX)?;
                let child = self.array(&field.children[0])?;
                if len > 0 && offsets.range(len - 1).1 > child.len {
                    return Err(IpcError::malformed("list offsets exceed the child length"));
                }
                (
                    validity,
                    ArrayData::List {
                        offsets,
                        child: Box::new(child),
                    },
                )
            }
            DataType::FixedSizeList(size) => {
                let validity = self.validity(len, null_count)?;
                let child = self.array(&field.children[0])?;
                let need = len
                    .checked_mul(*size)
                    .ok_or(IpcError::limit("fixed-size list overflow"))?;
                if child.len < need {
                    return Err(IpcError::malformed("fixed-size list child is too short"));
                }
                (
                    validity,
                    ArrayData::FixedList {
                        size: *size,
                        child: Box::new(child),
                    },
                )
            }
            DataType::Struct => {
                let validity = self.validity(len, null_count)?;
                let mut children = Vec::with_capacity(field.children.len());
                for child_field in &field.children {
                    let child = self.array(child_field)?;
                    if child.len < len {
                        return Err(IpcError::malformed(
                            "struct child is shorter than its parent",
                        ));
                    }
                    children.push(child);
                }
                (validity, ArrayData::Struct(children))
            }
            DataType::Opaque { layout, .. } => {
                let buffers = match layout {
                    OpaqueLayout::Map => 2,
                    OpaqueLayout::SparseUnion => 1,
                    OpaqueLayout::DenseUnion => 2,
                    OpaqueLayout::RunEndEncoded => 0,
                    OpaqueLayout::ListView => 3,
                    OpaqueLayout::View => {
                        let extra = *self
                            .variadic
                            .get(self.next_variadic)
                            .ok_or(IpcError::malformed("missing variadic buffer count"))?;
                        self.next_variadic += 1;
                        if extra < 0 || extra > 1 << 20 {
                            return Err(IpcError::malformed("variadic buffer count is invalid"));
                        }
                        2 + extra as usize
                    }
                };
                for _ in 0..buffers {
                    self.buffer()?;
                }
                for child in &field.children {
                    self.array(child)?;
                }
                (None, ArrayData::Opaque)
            }
        };
        Ok(Array {
            len,
            null_count,
            validity,
            data,
        })
    }
}

/// One record batch: one array per top-level field.
#[derive(Clone, Debug)]
pub struct Batch<'a> {
    pub rows: usize,
    pub columns: Vec<Array<'a>>,
}

/// A decoded IPC table: the schema plus validated record batches.
#[derive(Clone, Debug)]
pub struct Table<'a> {
    pub schema: Schema,
    pub batches: Vec<Batch<'a>>,
    pub rows: usize,
}

fn read_struct_vector(fb: &FbTable<'_>, index: usize) -> Result<Vec<(i64, i64)>> {
    let Some((start, len)) = fb.vector(index, 16)? else {
        return Ok(Vec::new());
    };
    let mut out = Vec::with_capacity(len.min(1 << 16));
    for i in 0..len {
        let at = start + 16 * i;
        out.push((read_i64(fb.buf, at)?, read_i64(fb.buf, at + 8)?));
    }
    Ok(out)
}

fn parse_batch<'a>(fb: &FbTable<'_>, body: &'a [u8], schema: &Schema) -> Result<Batch<'a>> {
    if fb.field(3)?.is_some() {
        return Err(IpcError::unsupported("compressed record batch bodies"));
    }
    let rows = fb.i64_or(0, 0)?;
    if rows < 0 || rows as u64 > MAX_IPC_ROWS as u64 {
        return Err(IpcError::malformed("record batch length is invalid"));
    }
    let nodes = read_struct_vector(fb, 1)?;
    let buffers = read_struct_vector(fb, 2)?;
    let variadic = match fb.vector(4, 8)? {
        Some((start, len)) => (0..len)
            .map(|i| read_i64(fb.buf, start + 8 * i))
            .collect::<Result<Vec<_>>>()?,
        None => Vec::new(),
    };
    let mut reader = BodyReader {
        body,
        nodes: &nodes,
        buffers: &buffers,
        variadic: &variadic,
        next_node: 0,
        next_buffer: 0,
        next_variadic: 0,
    };
    let mut columns = Vec::with_capacity(schema.fields.len());
    for field in &schema.fields {
        let column = reader.array(field)?;
        if column.len != rows as usize {
            return Err(IpcError::malformed("column length differs from its batch"));
        }
        columns.push(column);
    }
    if reader.next_node != nodes.len() || reader.next_buffer != buffers.len() {
        return Err(IpcError::malformed(
            "record batch buffers do not match its schema",
        ));
    }
    Ok(Batch {
        rows: rows as usize,
        columns,
    })
}

/// One encapsulated message: `(header type, header table, body)`.
struct Message<'a> {
    header_type: u8,
    header: FbTable<'a>,
    body: &'a [u8],
}

/// Parse one encapsulated message at `pos`; returns it and the next position,
/// or `None` at an end-of-stream marker.
fn read_message(bytes: &[u8], pos: usize) -> Result<Option<(Message<'_>, usize)>> {
    if pos == bytes.len() {
        return Ok(None);
    }
    let mut at = pos;
    let mut size = read_u32(bytes, at)?;
    at += 4;
    if size == CONTINUATION {
        size = read_u32(bytes, at)?;
        at += 4;
    }
    if size == 0 {
        return Ok(None);
    }
    let size = size as i32;
    if size < 0 {
        return Err(IpcError::malformed("negative message length"));
    }
    let meta_end = at
        .checked_add(size as usize)
        .filter(|&end| end <= bytes.len())
        .ok_or(IpcError::malformed("message metadata exceeds the input"))?;
    let meta = &bytes[at..meta_end];
    let message = FbTable::root(meta)?;
    let version = message.i16_or(0, 0)?;
    if version != METADATA_V4 && version != METADATA_V5 {
        return Err(IpcError::unsupported("Arrow metadata version before V4"));
    }
    let header_type = message.u8_or(1, 0)?;
    let header = message
        .table(2)?
        .ok_or(IpcError::malformed("message header missing"))?;
    let body_len = message.i64_or(3, 0)?;
    if body_len < 0 {
        return Err(IpcError::malformed("negative body length"));
    }
    let body_end = meta_end
        .checked_add(body_len as usize)
        .filter(|&end| end <= bytes.len())
        .ok_or(IpcError::malformed("message body exceeds the input"))?;
    Ok(Some((
        Message {
            header_type,
            header,
            body: &bytes[meta_end..body_end],
        },
        body_end,
    )))
}

fn push_batch<'a>(table: &mut Table<'a>, message: &Message<'a>) -> Result<()> {
    if table.batches.len() >= MAX_IPC_BATCHES {
        return Err(IpcError::limit("table exceeds the record batch bound"));
    }
    let batch = parse_batch(&message.header, message.body, &table.schema)?;
    table.rows = table
        .rows
        .checked_add(batch.rows)
        .filter(|&rows| rows <= MAX_IPC_ROWS)
        .ok_or(IpcError::limit("table exceeds the row bound"))?;
    table.batches.push(batch);
    Ok(())
}

fn read_stream(bytes: &[u8], start: usize) -> Result<Table<'_>> {
    let (first, mut pos) = read_message(bytes, start)?
        .ok_or(IpcError::malformed("Arrow stream has no schema message"))?;
    if first.header_type != HEADER_SCHEMA {
        return Err(IpcError::malformed("Arrow stream must start with a schema"));
    }
    let mut table = Table {
        schema: parse_schema(&first.header)?,
        batches: Vec::new(),
        rows: 0,
    };
    while let Some((message, next)) = read_message(bytes, pos)? {
        pos = next;
        match message.header_type {
            HEADER_RECORD_BATCH => push_batch(&mut table, &message)?,
            HEADER_DICTIONARY => return Err(IpcError::unsupported("dictionary batches")),
            HEADER_SCHEMA => return Err(IpcError::malformed("repeated schema message")),
            _ => return Err(IpcError::unsupported("tensor messages")),
        }
    }
    Ok(table)
}

fn read_file(bytes: &[u8]) -> Result<Table<'_>> {
    let len = bytes.len();
    if len < 16 || &bytes[len - 6..] != FILE_MAGIC {
        return Err(IpcError::malformed("Arrow file trailer is missing"));
    }
    let footer_len = read_u32(bytes, len - 10)? as usize;
    let footer_start = (len - 10)
        .checked_sub(footer_len)
        .filter(|&start| start >= 8)
        .ok_or(IpcError::malformed("Arrow file footer is out of range"))?;
    let footer = FbTable::root(&bytes[footer_start..len - 10])?;
    let schema = footer
        .table(1)?
        .ok_or(IpcError::malformed("Arrow file footer has no schema"))?;
    let mut table = Table {
        schema: parse_schema(&schema)?,
        batches: Vec::new(),
        rows: 0,
    };
    if footer.vector(2, 24)?.is_some_and(|(_, n)| n > 0) {
        return Err(IpcError::unsupported("dictionary batches"));
    }
    if let Some((start, count)) = footer.vector(3, 24)? {
        for i in 0..count {
            let at = start + 24 * i;
            let offset = read_i64(footer.buf, at)?;
            if offset < 8 || offset as u64 >= footer_start as u64 {
                return Err(IpcError::malformed("record batch block is out of range"));
            }
            let meta_len = read_u32(footer.buf, at + 8)? as i32 as i64;
            let body_len = read_i64(footer.buf, at + 16)?;
            let (message, _) = read_message(&bytes[..footer_start], offset as usize)?
                .ok_or(IpcError::malformed("record batch block is empty"))?;
            // The block must describe exactly the message it points at:
            // prefix + metadata, then the body.
            let body_start = message.body.as_ptr() as usize - bytes.as_ptr() as usize;
            if body_start as i64 - offset != meta_len || message.body.len() as i64 != body_len {
                return Err(IpcError::malformed(
                    "record batch block disagrees with its message",
                ));
            }
            if message.header_type != HEADER_RECORD_BATCH {
                return Err(IpcError::malformed("file block is not a record batch"));
            }
            push_batch(&mut table, &message)?;
        }
    }
    Ok(table)
}

/// Decode an Arrow IPC stream or file. `bytes` must hold exactly one table.
pub fn read_table(bytes: &[u8]) -> Result<Table<'_>> {
    if bytes.len() >= 8 && &bytes[..6] == FILE_MAGIC {
        read_file(bytes)
    } else {
        read_stream(bytes, 0)
    }
}

// ---------------------------------------------------------------------------
// Column access across batches
// ---------------------------------------------------------------------------

/// A logical column: one array per batch plus the physical rows to visit.
/// Top-level columns visit every row in order; navigating into a struct child
/// or flattening a list keeps only rows whose ancestors are valid, so nested
/// columns are for entity collection, not row alignment.
#[derive(Clone, Debug)]
pub struct Column<'t, 'a> {
    pub field: &'t Field,
    parts: Vec<(&'t Array<'a>, Rows)>,
}

#[derive(Clone, Debug)]
enum Rows {
    All(usize),
    Some(Vec<usize>),
}

impl Rows {
    fn len(&self) -> usize {
        match self {
            Rows::All(n) => *n,
            Rows::Some(rows) => rows.len(),
        }
    }
    fn get(&self, i: usize) -> usize {
        match self {
            Rows::All(_) => i,
            Rows::Some(rows) => rows[i],
        }
    }
}

impl<'a> Table<'a> {
    /// Top-level column by name.
    pub fn column(&self, name: &str) -> Option<Column<'_, 'a>> {
        let index = self.schema.field_index(name)?;
        Some(self.column_at(index))
    }

    pub fn column_at(&self, index: usize) -> Column<'_, 'a> {
        Column {
            field: &self.schema.fields[index],
            parts: self
                .batches
                .iter()
                .map(|b| (&b.columns[index], Rows::All(b.rows)))
                .collect(),
        }
    }
}

impl<'t, 'a> Column<'t, 'a> {
    pub fn len(&self) -> usize {
        self.parts.iter().map(|(_, r)| r.len()).sum()
    }

    pub fn is_empty(&self) -> bool {
        self.len() == 0
    }

    /// Visit `(array, physical row)` for every logical row in order.
    pub fn for_each<E>(
        &self,
        mut f: impl FnMut(&'t Array<'a>, usize) -> std::result::Result<(), E>,
    ) -> std::result::Result<(), E> {
        for (array, rows) in &self.parts {
            for i in 0..rows.len() {
                f(array, rows.get(i))?;
            }
        }
        Ok(())
    }

    /// Struct member by name; rows whose struct is null are dropped.
    pub fn child(&self, name: &str) -> Option<Column<'t, 'a>> {
        if self.field.data_type != DataType::Struct {
            return None;
        }
        let (index, field) = self.field.child(name)?;
        let parts = self
            .parts
            .iter()
            .map(|(array, rows)| {
                let child = array.struct_child(index).expect("validated struct arity");
                let kept = (0..rows.len())
                    .map(|i| rows.get(i))
                    .filter(|&r| array.is_valid(r))
                    .collect();
                (child, Rows::Some(kept))
            })
            .collect();
        Some(Column { field, parts })
    }

    /// Items of every valid list row, flattened in order.
    pub fn flatten(&self) -> Option<Column<'t, 'a>> {
        if !matches!(
            self.field.data_type,
            DataType::List { .. } | DataType::FixedSizeList(_)
        ) {
            return None;
        }
        let field = &self.field.children[0];
        let parts = self
            .parts
            .iter()
            .map(|(array, rows)| {
                let child = array.list_child().expect("validated list child");
                let mut kept = Vec::new();
                for i in 0..rows.len() {
                    let r = rows.get(i);
                    if array.is_valid(r) {
                        let (start, end) = array.list_range(r).unwrap();
                        kept.extend(start..end);
                    }
                }
                (child, Rows::Some(kept))
            })
            .collect();
        Some(Column { field, parts })
    }
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use super::*;

    fn fixture(name: &str) -> Vec<u8> {
        let path = format!(
            "{}/../../tests/fixtures/graphforge/results/{name}.arrow",
            env!("CARGO_MANIFEST_DIR")
        );
        std::fs::read(&path).unwrap_or_else(|e| panic!("{path}: {e}"))
    }

    #[test]
    fn reads_every_graphforge_fixture() {
        let dir = format!(
            "{}/../../tests/fixtures/graphforge/results",
            env!("CARGO_MANIFEST_DIR")
        );
        let mut count = 0;
        for entry in std::fs::read_dir(dir).unwrap() {
            let path = entry.unwrap().path();
            if path.extension().is_some_and(|e| e == "arrow") {
                let bytes = std::fs::read(&path).unwrap();
                let table =
                    read_table(&bytes).unwrap_or_else(|e| panic!("{}: {e}", path.display()));
                assert_eq!(
                    table.rows,
                    table.batches.iter().map(|b| b.rows).sum::<usize>()
                );
                count += 1;
            }
        }
        assert!(count >= 100, "expected the GraphForge fixture corpus");
    }

    #[test]
    fn pagerank_schema_metadata_and_values() {
        let bytes = fixture("pagerank");
        let table = read_table(&bytes).unwrap();
        assert_eq!(
            table.schema.metadata("graphforge.algorithm"),
            Some("pagerank")
        );
        assert_eq!(table.schema.metadata("graphforge.verb"), Some("rank"));
        assert_eq!(
            table.schema.metadata("graphforge.algorithm_schema_version"),
            Some("1")
        );
        let uuid = table.column("node_uuid").unwrap();
        assert_eq!(uuid.field.data_type, DataType::FixedSizeBinary(16));
        let score = table.column("score").unwrap();
        assert_eq!(score.field.data_type, DataType::Float { bits: 64 });
        let mut total = 0.0;
        score
            .for_each::<()>(|array, row| {
                total += f64::from_le_bytes(array.fixed(row).unwrap().try_into().unwrap());
                Ok(())
            })
            .unwrap();
        assert!((total - 1.0).abs() < 1e-6, "pagerank scores sum to one");
    }

    #[test]
    fn uuid_lists_and_vectors_decode() {
        let bytes = fixture("euler_circuit");
        let table = read_table(&bytes).unwrap();
        let path = table.column("edge_path").unwrap();
        assert_eq!(path.field.type_name(), "List<FixedSizeBinary(16)>");
        let items = path.flatten().unwrap();
        assert_eq!(items.len(), 4);

        let bytes = fixture("node2vec");
        let table = read_table(&bytes).unwrap();
        assert_eq!(table.schema.metadata("graphforge.dimensions"), Some("4"));
        let embedding = table.column("embedding").unwrap();
        assert_eq!(embedding.field.type_name(), "FixedSizeList(4)<Float32>");
        assert_eq!(embedding.flatten().unwrap().len(), 4 * table.rows);
    }

    #[test]
    fn cypher_entity_structs_navigate() {
        let bytes = fixture("cypher-paths");
        let table = read_table(&bytes).unwrap();
        let path = table.column("p").unwrap();
        let nodes = path.child("nodes").unwrap().flatten().unwrap();
        let ids = nodes.child("node_uuid").unwrap();
        assert_eq!(ids.len(), 3 * table.rows);
        let rels = path.child("relationships").unwrap().flatten().unwrap();
        assert_eq!(rels.child("src_uuid").unwrap().len(), 2 * table.rows);
    }

    #[test]
    fn truncation_never_panics_and_fails_closed() {
        for name in ["pagerank", "cypher-paths", "node2vec", "euler_circuit"] {
            let bytes = fixture(name);
            for cut in 0..bytes.len() {
                // Every strict prefix is either rejected or (when the cut
                // lands on a message boundary) a shorter valid table.
                if let Ok(table) = read_table(&bytes[..cut]) {
                    assert!(table.rows <= read_table(&bytes).unwrap().rows);
                }
            }
        }
    }

    #[test]
    fn byte_flips_never_panic() {
        let bytes = fixture("cypher-edges");
        let mut state = 0x9E37_79B9_7F4A_7C15_u64;
        for _ in 0..20_000 {
            state ^= state << 13;
            state ^= state >> 7;
            state ^= state << 17;
            let mut copy = bytes.clone();
            let at = (state as usize) % copy.len();
            copy[at] ^= (state >> 32) as u8 | 1;
            let _ = read_table(&copy);
        }
    }

    #[test]
    fn empty_and_garbage_inputs_are_malformed() {
        assert_eq!(read_table(&[]).unwrap_err().kind, IpcErrorKind::Malformed);
        assert_eq!(
            read_table(&[0xFF, 0xFF, 0xFF, 0xFF, 0, 0, 0, 0])
                .unwrap_err()
                .kind,
            IpcErrorKind::Malformed
        );
        assert_eq!(
            read_table(b"ARROW1\0\0garbage").unwrap_err().kind,
            IpcErrorKind::Malformed
        );
    }

    #[test]
    fn arrow_file_blocks_must_match_their_messages() {
        let path = format!(
            "{}/../../tests/fixtures/graphforge/airports_nodes.arrow",
            env!("CARGO_MANIFEST_DIR")
        );
        let bytes = std::fs::read(path).unwrap();
        let len = bytes.len();
        let footer_len = u32::from_le_bytes(bytes[len - 10..len - 6].try_into().unwrap()) as usize;
        let footer_start = len - 10 - footer_len;
        let footer = FbTable::root(&bytes[footer_start..len - 10]).unwrap();
        let (start, count) = footer.vector(3, 24).unwrap().unwrap();
        assert_eq!(count, 1);
        let at = footer_start + start;
        for (field, delta) in [(8usize, 8i64), (16, 8)] {
            let mut damaged = bytes.clone();
            let width = if field == 8 { 4 } else { 8 };
            let mut raw = [0u8; 8];
            raw[..width].copy_from_slice(&damaged[at + field..at + field + width]);
            let value = i64::from_le_bytes(raw) + delta;
            damaged[at + field..at + field + width].copy_from_slice(&value.to_le_bytes()[..width]);
            assert_eq!(
                read_table(&damaged).unwrap_err().kind,
                IpcErrorKind::Malformed
            );
        }
    }

    #[test]
    fn arrow_file_format_reads_like_a_stream() {
        let path = format!(
            "{}/../../tests/fixtures/graphforge/airports_nodes.arrow",
            env!("CARGO_MANIFEST_DIR")
        );
        let bytes = std::fs::read(path).unwrap();
        let table = read_table(&bytes).unwrap();
        assert_eq!(table.rows, 3);
        assert_eq!(
            table.column("node_uuid").unwrap().field.data_type,
            DataType::Utf8 { large: false }
        );
    }
}
