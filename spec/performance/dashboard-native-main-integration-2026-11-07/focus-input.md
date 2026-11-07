# Preserve the shared chart input target during GPU suspension

This follow-up to `e5077aa5e231cca51ead261231aefac2bcaa9e2d` keeps the
Canvas2D presentation surface visible below its pointer-transparent saved-picture
stand-in. Unlike
a native lost WebGL canvas, this surface does not show a broken-context tile;
the stand-in covers unpublished clears even with opaque custom canvas CSS. Keeping it visible
also preserves the original keyboard-focus target during GPU suspension.

The 32-chart regression requires the same retained picture, a connected
stand-in, a visible original input canvas, and actual `document.activeElement`
identity after focusing that canvas. The previous exact client fails the new
visibility assertion. This is additional accessibility preservation, not full
keyboard/assistive-technology or whole-issue acceptance.

`focus-checks.json` binds the final runtime artifacts, source, logs, original
pre-fix bundles and fresh checks. The preparation API inventory is unchanged:
this is a private body-only edit, with the old generation-time source hash
retained under that inventory's declared policy. The official semantic checker
must pass. Previous receipts and their raw/archive identities remain unchanged.
