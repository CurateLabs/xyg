"""Annotation builders for `Figure` (vline/hline/band/callout/text/marker/
arrow + reference-line and zone helpers) and the annotation spec compiler.

Split out of `_figure.py` as a mixin: `Figure` inherits `AnnotationsMixin`, so
`fig.vline(...)` etc. are unchanged and every `self.*` (validators, the column
store, `self.annotations`, rollback) resolves through the concrete `Figure` via
the MRO. Only numpy + the columns/channels helpers are needed at module level."""

from __future__ import annotations

from typing import Any

from ._annotations_marks import AnnotationsMarksMixin
from ._annotations_rules import AnnotationsRulesMixin
from ._annotations_spec import AnnotationsSpecMixin


class AnnotationsMixin(AnnotationsRulesMixin, AnnotationsMarksMixin, AnnotationsSpecMixin):
    """Combined annotation API bound onto `Figure`."""


# Bound by `_figure` after `Figure` is defined (breaks the import cycle).
Figure: Any = None
