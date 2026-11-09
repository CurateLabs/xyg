use crate::raster;
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub(crate) enum PngError {
    Size,
    Raster,
}
fn rasterize_png_policy<const RETAINED: bool>(
    cmds: &[u8],
    width: usize,
    height: usize,
) -> Result<Vec<u8>, PngError> {
    if RETAINED && !raster::retained_commands_valid(cmds) {
        return Err(PngError::Raster);
    }
    let raw = width
        .checked_mul(height)
        .and_then(|count| count.checked_mul(4))
        .ok_or(PngError::Size)?;
    let cap = raw
        .checked_add(raw / 8)
        .and_then(|n| n.checked_add(65_536))
        .ok_or(PngError::Size)?;
    let mut out = vec![0u8; cap.max(1)];
    let written = if RETAINED {
        raster::rasterize_retained_png_into(cmds, width, height, &mut out)
    } else {
        raster::rasterize_png_into(cmds, width, height, &mut out)
    }
    .ok_or(PngError::Raster)?;
    if written > out.len() {
        return Err(PngError::Raster);
    }
    out.truncate(written);
    Ok(out)
}

pub(crate) fn rasterize_png(cmds: &[u8], w: usize, h: usize) -> Result<Vec<u8>, PngError> {
    rasterize_png_policy::<true>(cmds, w, h)
}
#[cfg(feature = "raster")]
pub(crate) fn rasterize_png_full(cmds: &[u8], w: usize, h: usize) -> Result<Vec<u8>, PngError> {
    rasterize_png_policy::<false>(cmds, w, h)
}

#[cfg(all(test, feature = "raster"))]
mod tests {
    use super::*;
    use crate::scene::SceneDocument;
    const BUDGET: usize = 384 * 1024 * 1024;
    fn document() -> SceneDocument {
        let raw = include_bytes!("../../../spec/performance/temporal-native-render-2026-11-07/artifacts/retained-later.xyfg");
        let scene = crate::temporal_graph_export::canonical_scene(raw, [77, 110, 159, 191], BUDGET)
            .unwrap();
        SceneDocument::decode(&scene).unwrap()
    }
    #[test]
    fn retained_specialization_preserves_full_renderer_png_bytes() {
        let document = document();
        for scale in [1.0, 2.0] {
            let ordinary = document.to_raster_commands(scale).unwrap();
            let retained = document.to_raster_commands_retained(scale).unwrap();
            let (w, h) = (
                document.viewport_size().0 as usize * scale as usize,
                document.viewport_size().1 as usize * scale as usize,
            );
            assert_eq!(
                rasterize_png(&retained, w, h).unwrap(),
                rasterize_png_full(&ordinary, w, h).unwrap()
            );
        }
    }
    #[test]
    fn unsupported_truncated_or_huge_commands_refuse_before_buffer_allocation() {
        for commands in [&[6u8][..], &[19, 255, 255, 255, 255][..], &[255][..]] {
            assert_eq!(
                rasterize_png(commands, usize::MAX, usize::MAX),
                Err(PngError::Raster)
            );
        }
        let commands = document().to_raster_commands_retained(1.0).unwrap();
        let mut out = [0xa5; 1];
        assert!(raster::rasterize_retained_png_into(&commands, 240, 180, &mut out).is_none());
        let mut full = vec![0; 240 * 180 * 4 + 65536];
        assert!(raster::rasterize_retained_png_into(&commands, 240, 180, &mut full).is_some());
        assert_eq!(
            rasterize_png(&[], usize::MAX, usize::MAX),
            Err(PngError::Size)
        );
    }
}
