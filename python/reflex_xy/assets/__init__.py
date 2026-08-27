"""Frontend assets for the Reflex component.

One wrapper file ships in the ``xyg`` distribution:

- ``XYChart.jsx`` — the React wrapper (multiplexes the `/_xy` namespace onto
  the app's existing websocket and drives ChartView).

The render client itself (``xy_client.js``) is deliberately NOT packaged
here: `register()` links it out of the **installed ``xyg`` distribution**
(``xyg/static/index.js``, the same ESM bundle notebooks load), landing it
beside the wrapper so the wrapper's relative ``./xy_client.js`` import
resolves. Sourcing from the install makes client/kernel drift structurally
impossible — the JS that renders a payload is always the build that shipped
with the Python that produced it.

`register()` is deliberately lazy (called from the component factory, not at
import): ``rx.asset(shared=True)`` symlinks into ``Path.cwd()/assets``, which
only makes sense while compiling an actual Reflex app.
"""

from __future__ import annotations

from pathlib import Path

WRAPPER_TAG = "XYChart"

#: Destination directory under the app's assets/ tree — must match where
#: rx.asset(shared=True) puts this module's files, because the wrapper
#: imports the client by relative path.
_EXTERNAL_SUBDIR = Path("external") / "reflex_xy" / "assets"
_CLIENT_NAME = "xy_client.js"
_WASM_TICK_ASSETS = ("wasm-worker.js", "xyg-wasm.wasm")


def _static_source(name: str) -> Path:
    """A generated static file inside the installed xyg package."""
    import xyg

    source = Path(xyg.__file__).resolve().parent / "static" / name
    if not source.exists():
        msg = (
            f"{source} missing — the xyg install has no bundled {name}. "
            "Dev checkout: run `node js/build.mjs` and `node js/package-wasm.mjs`; "
            "otherwise reinstall xyg."
        )
        raise FileNotFoundError(msg)
    return source


def _client_source() -> Path:
    """The canonical render client inside the installed xyg package."""
    return _static_source("index.js")


def _link_static(asset_root: Path, source: Path, dest_name: str) -> None:
    """Symlink one installed static file beside the wrapper (repairing stale links)."""
    dst_dir = asset_root / _EXTERNAL_SUBDIR
    dst_dir.mkdir(parents=True, exist_ok=True)
    dst = dst_dir / dest_name
    if dst.is_symlink() or dst.exists():
        try:
            if dst.resolve() == source:
                return
        except OSError:
            pass
        dst.unlink()
    dst.symlink_to(source)


def _wasm_tick_sources() -> dict[str, Path] | None:
    """Packaged Worker + WASM paths, or None if either file is absent.

    Fail-closed: never return a partial pair and never invent a path or CDN.
    """
    import xyg

    static_dir = Path(xyg.__file__).resolve().parent / "static"
    sources = {name: static_dir / name for name in _WASM_TICK_ASSETS}
    if all(path.is_file() for path in sources.values()):
        return sources
    return None


def reflex_wasm_tick_urls() -> dict[str, str] | None:
    """Explicit sibling URLs for XYChart auto-attach.

    When both packaged files exist, returns the same mapping
    ``resolve_wasm_tick_assets`` uses for hosted ``to_html()``:
    ``{"workerUrl": "./wasm-worker.js", "wasm": "./xyg-wasm.wasm"}``.
    Missing assets return None — never a guessed, Blob, or CDN URL.
    """
    from xyg.export import WASM_TICK_WASM, WASM_TICK_WORKER, resolve_wasm_tick_assets

    if _wasm_tick_sources() is None:
        return None
    return resolve_wasm_tick_assets(
        {
            "worker_url": f"./{WASM_TICK_WORKER}",
            "wasm": f"./{WASM_TICK_WASM}",
        }
    )


def _link_client(asset_root: Path) -> None:
    """Symlink the installed client and packaged WASM tick assets.

    Unlike rx.asset's shared files (which live at a fixed path next to their
    module), the client's location moves whenever the ``xyg`` install
    does — so an existing link pointing at the wrong target is replaced, not
    trusted. Tick assets are linked as a pair when packaged so XYChart can
    attach ``attachHostWasmTicks`` with explicit same-origin
    ``./wasm-worker.js`` and ``./xyg-wasm.wasm`` URLs. A missing file leaves
    both unlinked rather than guessing a path.
    """
    _link_static(asset_root, _client_source(), _CLIENT_NAME)
    sources = _wasm_tick_sources()
    if sources is None:
        return
    for name, source in sources.items():
        _link_static(asset_root, source, name)


def register() -> str:
    """Wire both frontend files into the compiling app; return the wrapper's
    importable module path (``$/public/external/reflex_xy/assets/...``)."""
    import reflex as rx
    from reflex.assets import EnvironmentVariables

    wrapper = rx.asset("XYChart.jsx", shared=True)
    if not EnvironmentVariables.REFLEX_BACKEND_ONLY.get():
        _link_client(Path.cwd() / "assets")
    return wrapper.importable_path
