//! Bounded native oracle for the same geographic catalog processor shipped in wasm32.
use std::io::{self, Read, Write};
fn main() {
    let budget = std::env::args()
        .nth(1)
        .and_then(|v| v.parse::<usize>().ok())
        .unwrap_or(64 * 1024 * 1024);
    if !(65536..=xyg_engine::geo_layers_protocol::MAX_PROTOCOL_BYTES).contains(&budget) {
        eprintln!("XYG_GEO_RESOURCE_LIMIT");
        std::process::exit(3);
    }
    let mut bytes = Vec::new();
    if io::stdin()
        .take(budget as u64 + 1)
        .read_to_end(&mut bytes)
        .is_err()
    {
        eprintln!("XYG_GEO_INVALID_ARGUMENT");
        std::process::exit(2);
    }
    match xyg_engine::geo_layers_protocol::execute(&bytes, budget) {
        Ok(out) => {
            if io::stdout().write_all(&out).is_err() {
                std::process::exit(2);
            }
        }
        Err(error) => {
            eprintln!("{}", error.code());
            std::process::exit(if error == xyg_engine::geo::GeoError::ResourceLimit {
                3
            } else {
                2
            });
        }
    }
}
