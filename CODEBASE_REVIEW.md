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
- Browser upload exposes the working-size cap for performance control.
- Workspace naming, listing, opening, and deletion through the browser API.
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
- Browser veneer palette editor for color, stock, grain, and notes.
- Veneer palette supports optional texture/photo URLs with browser previews.
- Connected-region merge as a persisted edit operation.
- Targeted single-region split as a persisted edit operation.
- Region lock/unlock as a persisted edit operation.
- Undo for veneer assignment, bulk assignment, merge, size, veneer inventory,
  detail-zone, lock, and split operations.
- Merge suggestions for small/thin regions, preferring same-veneer neighbors.
- Bounded auto-merge cleanup using merge suggestions.
- Physical-area sliver repair that respects locks.
- Raster boundary smoothing that validates the puzzle invariant before saving.
- Selected-region raster smoothing from the browser canvas selection.
- Final label hitmap API and canvas click/drag selection.
- Canvas zoom controls with scroll-based panning.
- Freehand lasso selection by sampled stroke.
- Persisted rectangular detail zones.
- Detail zones can be created from selected regions.
- Detail zones can drive bounded local split passes.
- Pixel-level subject/background mask can be painted from selected regions and
  undone.
- Freehand brush painting can mark subject/background mask pixels and is
  undoable.
- Browser canvas can show a subject/background mask overlay.
- Candidate generation can optionally use persisted detail zones for denser
  local source-stage segmentation.
- Candidate generation can use the subject/background mask to avoid labels that
  span marked subject/background pixels.
- Raster shared-boundary metrics with physical edge lengths.
- Shared-boundary polylines in pixel and physical units for adjacent regions.
- Shared-boundary simplification analysis with vertex reduction estimates.
- Browser selected-boundary summary with internal/external edge lengths.
- Veneer-grouped SVG export in physical units with adjustable contour
  simplification.
- `rectpack` bounding-box pack manifest grouped by veneer.
- Pack manifest includes each piece's physical contour and SVG path for future
  irregular nesting adapters.
- Browser pack summary with placed/unplaced counts and stock warnings.
- Pack manifest includes recommended sheet counts, stock shortfall, area totals,
  and bounding-box material utilization by veneer.
- Browser pack output is constrained to the configured workspace root.
- Browser smoke test for creating a workspace, generating a candidate grid, and
  seeding the design from a candidate.
- Browser smoke test for canvas selection, selected veneer assignment, undo, and
  pack summary generation.
- Browser smoke test for zoom controls, lasso selection, box selection, and
  merge/undo.
- Browser smoke test for SVG preview generation.
- Cleanup report endpoint/browser action summarizing warnings, merge
  suggestions, jagged boundaries, veneers, mask, partition validity, and a
  simple readiness score.
- `pack` writes `cleanup-report.json`, and the CLI can write the report without
  packing.
- Thin browser UI over the new API.

## Still Outstanding

1. Advanced vector shared-boundary geometry.

   Shared-boundary polylines now exist for adjacent regions in pixel and
   physical units, with simplified-path analysis and vertex reduction
   estimates. Region contours are still independently extracted from raster
   labels for SVG export. Advanced smoothing/editing still needs a fuller
   planar graph with editable vertices and topology-preserving writes.

2. Real cleanup tools beyond merge.

   Merge, targeted split, lock/unlock, physical-area sliver repair, raster
   smoothing, selected-region smoothing, selected-boundary inspection, bounded
   auto-merge, and undo now exist. Vector simplify, selected-boundary vector
   smoothing, point editing, and shared-boundary-safe writes are still open;
   simplification is currently analysis-only.

3. Subject/detail logic.

   Detail zones can drive local splits after a design exists and can optionally
   refine new candidates with denser local source-stage segmentation. A
   first-class pixel-level subject/background mask exists and can guide
   candidate generation. The browser can show the mask overlay and paint
   subject/background mask pixels with a brush.

4. Browser selection tooling.

   Canvas click/drag selection, lasso selection, selected-boundary summaries,
   zoom, and scroll-panning exist. It remains visually basic and lacks
   selected-boundary editing.

5. Material planning.

   Veneer inventory fields, replacement, browser editing, stock-fit summary,
   purchasing quantity estimates, material utilization, grain notes, and texture
   URL previews exist. Deeper grain review and managed texture upload/library
   workflows are not implemented.

6. Real packing/nesting.

   Packing now uses `rectpack` on physical bounding boxes and includes true
   physical contours/SVG paths in the manifest. This is useful for rough stock
   planning and adapter development, but is not irregular nesting of true cut
   paths.

7. TypeScript migration.

   The browser has `checkJs` and domain declarations. A full TS module split
   remains open.

8. Browser tests.

   A Playwright smoke test covers image upload, workspace creation,
   candidate-grid generation, design seeding, canvas selection, selected veneer
   assignment, undo, pack summary generation, zoom, lasso selection, box
   selection, merge/undo, and SVG preview. Broader visual regression and
   multi-browser coverage are still future hardening work, but the current
   vertical slice now has a browser smoke test.

## Engineering Direction

Do not reintroduce the prototype's mirrored state model. `MarquetryDesign`
should remain the durable object. Candidates are inputs. Export and packing
must consume only the final design.
