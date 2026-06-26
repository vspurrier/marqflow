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
2. Generate one SLIC candidate partition or a candidate search grid.
3. Seed a durable `MarquetryDesign` from that candidate.
4. Set final physical dimensions.
5. Auto-assign veneers from a default palette.
6. Manually override veneers for one or many selected regions.
7. Click or drag-select final regions from a canvas hitmap.
8. Merge connected selected regions.
9. Split one selected region for local detail.
10. Lock/unlock selected regions before cleanup passes.
11. Create focus zones from selected regions.
12. Mark selected regions as subject or background.
13. Apply focus zones as local split passes.
14. Validate the partition invariant.
15. Export a veneer-grouped SVG in physical units.
16. Write a `rectpack` bounding-box packing manifest.

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

- name, list, open, and delete workspaces
- choose an image
- generate and choose candidate partitions
- inspect the generated design invariant and physical dimensions
- edit veneer colors, sheet sizes, sheet counts, grain, and notes
- click or drag-select final regions
- lasso-select regions with a freehand stroke
- zoom and scroll-pan the design canvas
- inspect selected internal/external boundary lengths
- assign veneers to selected final regions
- merge selected connected regions
- split one selected region
- lock/unlock selected regions
- mark selected regions as subject/background for later candidate generation
- create and apply focus zones for local detail
- auto-merge small/thin suggested regions
- repair regions below a physical area threshold
- smooth raster boundary noise while preserving a valid partition
- export SVG with adjustable contour simplification
- write the bounding-box pack manifest
- review placed/unplaced piece counts and stock warnings

The UI should stay thin until the core design model is strong.

When `marqflow serve` is launched without a workspace argument, browser-created
workspaces are stored under `~/.marqflow`. When launched with a workspace path,
new browser workspaces are created alongside that path.

## Verification

```bash
npm run typecheck
uv run ruff check src tests
uv run pytest -q
```

The browser smoke test uses Playwright. If Chromium is not installed locally,
the test skips instead of failing the suite.
