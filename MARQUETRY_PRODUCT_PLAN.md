# Marqflow Product Plan

Status date: 2026-06-26

`main` is the active marquetry-first prototype guided by the lessons from the
earlier gallery prototype.

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
- marquetry-mode candidate generation with source value-band compression and
  source-stage tiny-region merging
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
- topology graph endpoint with vertices, exterior/shared edges, and region-edge
  references
- persisted topology graph artifacts
- undoable topology graph simplification artifacts
- active vector graph promotion as output geometry
- topology-safe selected-boundary vector simplification
- topology-safe single-vertex movement
- direct browser canvas handles for dragging topology vertices
- snapping, image-bound clamping, hover labels, and no-op rejection for direct
  vertex dragging
- graphical before/after preview overlays for vector vertex drags with explicit
  accept/cancel controls before saving
- direct selected-boundary simplification actions from the browser boundary
  summary
- SVG reconstruction from persisted graph linework
- API and CLI access for graph persistence, simplification, loading, and
  reconstructed graph SVG export
- browser controls for vector cleanup, graph promotion, graph preview, direct
  vertex dragging, and fallback vertex movement by ID
- combined cuttability cleanup that runs small-piece repair, raster smoothing,
  and warning-region vector simplification
- Shapely coverage validation for exported physical polygons
- selected-boundary summary in the browser
- partition validation
- physical-unit SVG export with adjustable contour simplification
- Shapely coverage-safe SVG export with shared-edge simplification
- persisted coverage-safe vector export metadata
- Shapely polygon-aware shelf pack manifest by veneer
- physical contour, SVG path, placement, transformed placed contour, and
  transformed placed SVG path data in each pack manifest piece
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
- browser smoke test for direct vector-handle dragging
- browser smoke test for SVG preview generation
- cleanup report with a readiness score for cut-readiness review
- cleanup report artifact in pack exports plus standalone CLI report command
- coverage-safe SVG artifact in pack exports
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
   physical units, including simplified-path analysis. A topology graph and
   Shapely coverage validation now provide the foundation for correctness, and
   coverage-safe exports persist artifact metadata. Topology graphs can now be
   persisted, simplified into undoable vector artifacts, reconstructed into
   filled SVG, promoted as active output geometry, edited with validated
   single-vertex moves, and dragged with browser canvas handles. Direct dragging
   now snaps to the image grid, clamps to the design bounds, labels hovered
   vertices, rejects no-op moves, previews topology validity, renders a
   before/after overlay, and requires explicit accept/cancel before saving.
   Individual shared boundaries can also be simplified directly from the browser
   boundary summary. Next improvement: edge-level handles, curve/spline editing,
   and graphical previews for batch simplification.

3. Add cleanup operations on top of shared boundaries.

   Current cleanup supports connected merge, targeted split, lock/unlock,
   physical-area sliver repair, raster boundary smoothing, selected-region
   smoothing, selected-boundary inspection, and bounded auto-merge suggestions.
   Coverage-safe shared-edge simplification exists for SVG export, and shared
   graph simplification now persists as an undoable vector artifact. Selected
   regions can drive vector-edge simplification, individual vertices can be
   moved with topology validation, direct handles can drag vertices, promoted
   graph geometry drives SVG/pack output, and cuttability cleanup combines the
   conservative repair passes. Needed operations: smoother curve cleanup and
   explicit graphical preview/accept UI for larger graph mutations.

4. Deepen veneer inventory logic.

   Veneer replacement, stock fields, browser swatch editing, pack stock
   warnings, purchasing quantity estimates, and utilization metrics now exist.
   Texture/photo URL previews now exist. The workflow still needs richer grain
   direction review and managed texture upload/library support.

5. Improve polygon nesting quality.

   Current packing uses a Shapely-backed polygon shelf adapter. It places actual
   physical contours by veneer, collision-checks polygons, and emits transformed
   tracing contours. The next adapter should improve optimization quality with
   rotation options, grain-aware orientation constraints, concavity-aware
   placement, and lower-waste search heuristics.

6. Convert browser JS to TypeScript modules once the API stabilizes.

   The current browser code uses `checkJs` and declarations. A module split
   becomes worthwhile after the core workflow stops shifting.

7. Add browser-level regression tests.

   API/core tests cover the model. A browser smoke test covers image upload,
   candidate-grid generation, design seeding, direct vector-handle dragging,
   canvas selection, selected veneer assignment, undo, pack summary generation,
   zoom, lasso selection, box selection, merge/undo, and SVG preview. Broader
   visual regression and multi-browser coverage are future hardening work.

## Non-Goals For This Branch

- Do not port the old tabbed prototype wholesale.
- Do not let candidate selections become the final design state.
- Do not add packing before final geometry is validated.
