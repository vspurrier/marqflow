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
- Partition validation for unassigned pixels and disconnected regions.
- Region metrics with physical area, bbox, contour, neighbors, and warnings.
- Default veneer palette and nearest-color veneer assignment.
- Manual veneer override as a persisted edit operation.
- Connected-region merge as a persisted edit operation.
- Undo for veneer assignment and merge operations.
- Merge suggestions for small/thin regions, preferring same-veneer neighbors.
- Final label hitmap API for future canvas/SVG selection.
- Veneer-grouped SVG export in physical units.
- Simple veneer-grouped pack manifest.
- Thin browser UI over the new API.

## Still Outstanding

1. True shared-boundary geometry.

   Current contours are still independently extracted from raster labels. The
   core invariant is enforced at the raster level, but vector smoothing/editing
   still needs a planar graph or shared-boundary model before advanced cleanup.

2. Real cleanup tools beyond merge.

   Merge and undo now exist. Split, smooth, simplify, sliver repair, point
   editing, lock/unlock UI, and shared-boundary-safe cleanup are still open.

3. Subject/detail logic.

   There is no subject mask or local detail budget yet.

4. Browser selection tooling.

   The hitmap API exists, but the UI still lacks click/drag selection over a
   rendered final design. Region operations are currently list/button driven.

5. Material planning.

   Veneers exist, but purchasing quantities, grain review, stock-fit checks,
   and texture previews are not implemented.

6. Real packing/nesting.

   Packing is a traceable grouped manifest, not irregular nesting. A future
   adapter should receive validated physical paths by veneer.

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
