# Marqflow Product Plan

Status date: 2026-06-25

This branch is a fresh rewrite guided by the lessons from the prototype.

## Product Model

The product is not a superpixel editor. The product is a marquetry design:

```text
Source image -> candidate partitions -> measured final design -> veneer assignments -> cleanup -> packing/export
```

The final design must stay a complete, non-overlapping puzzle.

## Workflow

1. Image

   Normalize source image, cap working resolution, keep original metadata.

2. Size

   Set real physical dimensions before evaluating cuttability.

3. Generate Shapes

   Generate candidate partitions. Candidates are suggestions, not final truth.

4. Create Design

   Seed `MarquetryDesign` from one candidate partition.

5. Assign Veneers

   Every final region gets one veneer assignment. Automatic matching is only a
   suggestion.

6. Cleanup

   Merge, split, smooth, simplify, lock, and repair while preserving the puzzle
   invariant.

7. Pack/Export

   Export physical-unit SVG and pack pieces by veneer.

## Current Slice

Implemented now:

- image upload/load
- browser-controlled working image size cap
- explicit workspace naming, listing, opening, and deletion
- one-off candidate generation
- candidate grid generation as a source-stage search tool
- durable design partition
- editable final physical dimensions
- veneer assignments
- editable veneer inventory with stock fields
- browser veneer palette editor
- veneer texture/photo URL previews
- manual connected-region merge
- targeted single-region split for local detail
- region lock/unlock
- bulk veneer assignment
- undo for veneer assignment, bulk veneer assignment, detail zones, size changes,
  veneer inventory changes, lock changes, region split edits, and region merge edits
- same-veneer-preferred merge suggestions for small/thin regions
- bounded auto-merge cleanup for suggested small/thin regions
- physical-area sliver repair pass
- raster boundary smoothing pass
- selected-region raster smoothing
- final label hitmap API and browser click/drag selection tooling
- browser canvas zoom and scroll-pan
- lasso selection by freehand stroke
- persisted rectangular detail zones
- detail zones created from selected regions
- subject/background mask painted from selected regions
- subject/background mask painted with a freehand browser brush
- subject/background mask overlay on the browser canvas
- focus-zone-driven local split pass
- focus-zone-aware candidate generation
- subject/background-mask-aware candidate generation
- raster shared-boundary metrics
- shared-boundary polylines in pixel and physical units
- shared-boundary simplification analysis with vertex reduction estimates
- selected-boundary summary in the browser
- partition validation
- physical-unit SVG export with adjustable contour simplification
- `rectpack` bounding-box pack manifest by veneer
- physical contour and SVG path data in each pack manifest piece
- browser stock-fit summary for pack results
- recommended sheet counts, stock shortfall, area totals, and material
  utilization by veneer
- workspace-root-constrained browser pack output
- browser smoke test for image upload, candidate grid generation, and design
  seeding
- browser smoke test for canvas selection, selected veneer assignment, undo, and
  pack summary generation
- browser smoke test for zoom controls, lasso selection, box selection, and
  merge/undo
- browser smoke test for SVG preview generation
- cleanup report for cut-readiness review
- cleanup report artifact in pack exports plus standalone CLI report command
- minimal browser UI

## Next Milestones

1. Improve subject/background mask editing.

   Rectangular focus zones can be created from selected regions, applied to
   split intersecting final regions, and used during candidate generation for
   denser local segmentation. A pixel-level subject/background mask can now be
   painted from selected regions, visualized on the browser canvas, and used
   during candidate generation. The UI also supports freehand subject/background
   mask brush painting.

2. Build editable shared-boundary vector geometry.

   Shared-boundary polylines now exist for adjacent regions in pixel and
   physical units, including simplified-path analysis. Independently extracted
   SVG contours are still not a robust editable planar graph. Advanced
   smoothing, point editing, and no-gap/no-overlap SVG cleanup should be built
   on shared vector edges.

3. Add cleanup operations on top of shared boundaries.

   Current cleanup supports connected merge, targeted split, lock/unlock,
   physical-area sliver repair, raster boundary smoothing, selected-region
   smoothing, selected-boundary inspection, and bounded auto-merge suggestions.
   Needed operations: apply shared vector simplification/smoothing, edit
   vertices, and write edited shared edges back safely.

4. Deepen veneer inventory logic.

   Veneer replacement, stock fields, browser swatch editing, pack stock
   warnings, purchasing quantity estimates, and utilization metrics now exist.
   Texture/photo URL previews now exist. The workflow still needs richer grain
   direction review and managed texture upload/library support.

5. Replace bounding-box packing with irregular nesting.

   Current packing uses `rectpack` against physical bounding boxes, but the
   manifest now includes actual physical contours and SVG path data per piece.
   The next adapter should pack those validated physical paths by veneer.

6. Convert browser JS to TypeScript modules once the API stabilizes.

   The current browser code uses `checkJs` and declarations. A module split
   becomes worthwhile after the core workflow stops shifting.

7. Add browser-level regression tests.

   API/core tests cover the model. A browser smoke test covers image upload,
   candidate-grid generation, design seeding, canvas selection, selected veneer
   assignment, undo, pack summary generation, zoom, lasso selection, box
   selection, merge/undo, and SVG preview. Broader visual regression and
   multi-browser coverage are future hardening work.

## Non-Goals For This Branch

- Do not port the old tabbed prototype wholesale.
- Do not let candidate selections become the final design state.
- Do not add packing before final geometry is validated.
