"""External-consumer assertions for the lazy ``xy`` root API.

This module is checked by ty but is not a pytest test.  Keep the imports rooted
at ``xy``: importing the implementation modules directly would miss regressions
where a lazy root export silently falls back to ``Any``.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING, assert_type

import xyg


def _build_plugin(context: xyg.MarkContext) -> Sequence[xyg.Mark]:
    del context
    return ()


def check_root_typing_surface() -> None:
    """Type-check the public root without executing or mutating the registry."""
    if TYPE_CHECKING:
        assert_type(xyg.__version__, str)

        assert_type(xyg.Animation(), xyg.Animation)
        assert_type(xyg.ExportConfig(), xyg.ExportConfig)
        assert_type(xyg.Spring(), xyg.Spring)
        assert_type(xyg.MarkContext(columns={}, options={}), xyg.MarkContext)
        assert_type(xyg.MarkPlugin(name="consumer_fixture", build=_build_plugin), xyg.MarkPlugin)

        assert_type(xyg.animation(), xyg.Animation)
        assert_type(xyg.export_config(), xyg.ExportConfig)
        assert_type(xyg.mark("plugin"), xyg.Mark)
        assert_type(xyg.segments(), xyg.Mark)
        assert_type(xyg.segments_chart(), xyg.Chart)
        assert_type(xyg.spring(), xyg.Spring)
        assert_type(xyg.triangle_mesh(), xyg.Mark)
        assert_type(xyg.triangle_mesh_chart(), xyg.Chart)

        plugin = xyg.MarkPlugin(name="consumer_fixture", build=_build_plugin)
        assert_type(xyg.register_mark(plugin), xyg.MarkPlugin)
        assert_type(xyg.registered_marks(), tuple[str, ...])
        assert_type(xyg.unregister_mark("consumer_fixture"), None)
