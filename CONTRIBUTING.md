# Contributing to XYG

The full contributor guide — PR checklist, local gate commands, and the
chart-type contribution walkthrough — lives at
[`spec/process/contributing.md`](spec/process/contributing.md).

Quick start:

```bash
git clone https://github.com/CurateLabs/xyg.git
cd xyg
make setup        # dev environment + native core (needs Rust)
make check        # fast gate
make check-full   # full production gate (also needs Node 18+ and clippy)
```

## Check the active backend

`import xyg` is intentionally lightweight: it does not import NumPy or load the
native core. Import `xyg.kernels` to initialize the compute backend:

```bash
python -c "import xyg.kernels as k; print(k.BACKEND)"
```

`BACKEND` is always `native`; an unavailable native core raises `ImportError`
with remediation instead of silently degrading.

Design questions are settled by [`spec/design-dossier.md`](spec/design-dossier.md)
— code comments cite its §-numbers. Read the relevant section before changing
behavior, and don't regress the invariants listed in `CLAUDE.md`.

Milestone creation, renaming, closing, deletion, and moving an issue between
milestones require explicit human approval recorded in a GitHub issue or pull
request. Agents and automation may propose the exact operation but must not
perform it before that approval. See the full contributor guide for the
release-surface gate and milestone-governance rules.
