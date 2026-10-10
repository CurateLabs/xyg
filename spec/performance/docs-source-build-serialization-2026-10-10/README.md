# Pinned docs source-build serialization

Both docs dependency installs use `UV_CONCURRENT_BUILDS=1`, preserving the frozen lock, Python floors, quality tests and production builds. This limits source-build concurrency only; it adds no CI job or retry policy.

Two exact-head failures occurred before docs tests: run37987362716/job114012580866 lost the pinned Reflex radix `slider.pyi`, and run38011641686/job114092754861 lost internal `tooltip.pyi`. The first run passed after a retry; the failure recurred on the next unchanged host tree. The raw GitHub logs are stored verbatim as base64 with SHA256 and byte count in this directory.

The pinned commit69ef304d hook `packages/hatch-reflex-pyi/src/hatch_reflex_pyi/plugin.py` deletes all package `.pyi` files before generating them in the shared uv Git checkout (lines64–74), without a checkout lock. The second log starts about18 source builds concurrently before Hatch loses a generated file. These source and log observations support overlapping generation as the diagnosis; they do not identify a particular deleting process. Serial dependency builds avoid overlapping hooks within each install. Separate CI jobs retain independent caches/workspaces.

The official setting is documented at https://docs.astral.sh/uv/reference/settings/#concurrent-builds . Local validation runs the existing workflow verifier and unchanged docs test suite. Exact-head CI remains the production acceptance gate.
