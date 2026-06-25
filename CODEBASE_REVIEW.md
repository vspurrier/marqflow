# Marqflow Rewrite Review

Status date: 2026-06-25

This branch, `marquetry-rewrite`, intentionally starts over. The prior gallery
prototype remains recoverable from `grid-gallery`.

## What Changed

- Removed the prototype candidate-gallery workspace model from the active product surface.
- Added a small marquetry-first domain model:
  - `SourceImage`
  - `Candidate`
  - `MarquetryDesign`
  - `Region`
  - `Veneer`
  - `DetailZone`
  - `EditOperation`
- Added `MarquetryWorkspace` as the persistence boundary.
- Final design export and pack operate on `MarquetryDesign`, not on candidate selections.
- Browser UI is reduced to the first vertical slice instead of carrying over prototype tabs.
- TypeScript checking is retained for static browser JavaScript through `npm run typecheck`.

## Current Verification

Run:

```bash
npm run typecheck
uv run ruff check src tests
uv run pytest -q
```

## Implemented

- Image normalization with EXIF orientation and bounded working size.
- One SLIC-based candidate generator.
- Candidate-grid generation that stays separate from final design state.
- Durable design seeded from a candidate label partition.
- Editable physical dimensions for final output.
- Partition validation for unassigned pixels and disconnected regions.
- Region metrics with physical area, bbox, contour, neighbors, and warnings.
- Default veneer palette and nearest-color veneer assignment.
- Manual veneer override as a persisted edit operation.
- Bulk veneer override as one persisted edit operation.
- Veneer inventory replacement with sheet dimensions/count fields.
- Connected-region merge as a persisted edit operation.
- Targeted single-region split as a persisted edit operation.
- Region lock/unlock as a persisted edit operation.
- Undo for veneer assignment, bulk assignment, merge, size, veneer inventory,
  detail-zone, lock, and split operations.
- Merge suggestions for small/thin regions, preferring same-veneer neighbors.
- Bounded auto-merge cleanup using merge suggestions.
- Physical-area sliver repair that respects locks.
- Raster boundary smoothing that validates the puzzle invariant before saving.
- Final label hitmap API and canvas click/drag selection.
- Persisted rectangular detail zones.
- Detail zones can be created from selected regions.
- Detail zones can drive bounded local split passes.
- Raster shared-boundary metrics with physical edge lengths.
- Veneer-grouped SVG export in physical units with adjustable contour
  simplification.
- `rectpack` bounding-box pack manifest grouped by veneer.
- Thin browser UI over the new API.

## Still Outstanding

1. True vector shared-boundary geometry.

   Raster boundary metrics now exist, but contours are still independently
   extracted from raster labels. The core invariant is enforced at the raster
   level, but vector smoothing/editing still needs a planar graph or
   shared-boundary model before advanced cleanup.

2. Real cleanup tools beyond merge.

   Merge, targeted split, lock/unlock, physical-area sliver repair, raster
   smoothing, bounded auto-merge, and undo now exist. Vector simplify, selected
   boundary smoothing, point editing, and shared-boundary-safe cleanup are still
   open.

3. Subject/detail logic.

   Detail zones can drive local splits after a design exists. Candidate
   generation does not yet use focus zones to allocate more regions before
   seeding the final design.

4. Browser selection tooling.

   Canvas click/drag selection exists. It remains visually basic and lacks
   browser regression tests, zoom/pan, lasso selection, and selected-boundary
   editing.

5. Material planning.

   Veneer inventory fields and replacement exist, but purchasing quantities,
   grain review, stock-fit checks, texture previews, and a polished swatch UI
   are not implemented.

6. Real packing/nesting.

   Packing now uses `rectpack` on physical bounding boxes. This is useful for
   rough stock planning but is not irregular nesting of true cut paths.

7. TypeScript migration.

   The browser has `checkJs` and domain declarations. A full TS module split
   remains open.

8. Browser tests.

   Current tests are API/core level. Add browser tests after the new UI
   stabilizes.

9. File/workspace lifecycle.

   Uploaded images create temporary workspaces when no directory is provided.
   The rewrite still needs explicit workspace naming, reload/delete behavior,
   and a clear default storage location for real projects.

## Engineering Direction

Do not reintroduce the prototype's mirrored state model. `MarquetryDesign`
should remain the durable object. Candidates are inputs. Export and packing
must consume only the final design.
