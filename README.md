# Marqflow

Marqflow is being rewritten as a marquetry-first planner.

The previous gallery prototype is preserved in git history on `grid-gallery`.
This branch starts over around one product object: a measured marquetry design.

## Core Invariant

The final design is a puzzle:

- every design pixel belongs to exactly one region
- every region has a physical scale
- every region has one veneer assignment
- export and packing operate only on the final design, not transient candidates

## Current Vertical Slice

The rewrite currently supports:

1. Load and normalize a source image.
2. Generate one SLIC candidate partition.
3. Seed a durable `MarquetryDesign` from that candidate.
4. Auto-assign veneers from a default palette.
5. Manually override a region veneer.
6. Validate the partition invariant.
7. Export a veneer-grouped SVG in physical units.
8. Write a simple veneer-grouped packing manifest.

This is intentionally smaller than the prototype. The goal is a clean core
that can grow without repeating the previous tech debt.

## Install

```bash
uv sync
npm install
```

## CLI

Create a workspace and seed the first design:

```bash
uv run marqflow init ./source.png ./workspace --target-regions 80 --width 8 --height 10 --unit in
```

Export SVG:

```bash
uv run marqflow export ./workspace ./out/design.svg
```

Write a pack manifest:

```bash
uv run marqflow pack ./workspace ./out
```

Run the browser:

```bash
uv run marqflow serve ./workspace
```

## Browser

The browser UI is deliberately minimal in this rewrite:

- choose an image
- inspect the generated design invariant
- assign veneers to final regions
- export SVG
- write the pack manifest

The UI should stay thin until the core design model is strong.

## Verification

```bash
npm run typecheck
uv run ruff check src tests
uv run pytest -q
```
