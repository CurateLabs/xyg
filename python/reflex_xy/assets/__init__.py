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


def _link_client(asset_root: Path) -> None:
    """Symlink the installed client and optional WASM tick assets.

    Unlike rx.asset's shared files (which live at a fixed path next to their
    module), the client's location moves whenever the ``xyg`` install
    does — so an existing link pointing at the wrong target is replaced, not
    trusted. Tick assets are linked when packaged so a Reflex host can pass
    explicit same-origin ``./wasm-worker.js`` and ``./xyg-wasm.wasm`` URLs;
    attaching ``attachWasmTicks`` in XYChart remains a follow-up.
    """
    _link_static(asset_root, _client_source(), _CLIENT_NAME)
    import xyg

    static_dir = Path(xyg.__file__).resolve().parent / "static"
    for name in _WASM_TICK_ASSETS:
        source = static_dir / name
        if source.is_file():
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
