//! Bounded native authoring processor for frozen geographic Scenes.
use std::io::{self, Read, Write};
fn main() {
    let budget = std::env::args()
        .nth(1)
        .and_then(|value| value.parse::<usize>().ok())
        .unwrap_or(64 * 1024 * 1024);
    if budget == 0 || budget > 384 * 1024 * 1024 {
        eprintln!("XYG_GEO_RESOURCE_LIMIT");
        std::process::exit(3);
    }
    let mut request = Vec::new();
    if io::stdin()
        .take(budget as u64 + 1)
        .read_to_end(&mut request)
        .is_err()
    {
        eprintln!("XYG_GEO_INVALID_ARGUMENT");
        std::process::exit(2);
    }
    if request.len() > budget {
        eprintln!("XYG_GEO_RESOURCE_LIMIT");
        std::process::exit(3);
    }
    match xyg_engine::geo_scene::compile_geo_scene(&request, budget) {
        Ok(scene) => {
            if io::stdout().write_all(&scene).is_err() {
                std::process::exit(2);
            }
        }
        Err(error) => {
            eprintln!("{}", error.code());
            std::process::exit(if error.is_resource() { 3 } else { 2 });
        }
    }
}
