# Marqflow Rewrite Review

Status date: 2026-06-26

`main` is the active marquetry-first prototype. Older exploratory branches have
been retired; previous designs remain recoverable from Git history.

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
- Browser code is maintained as TypeScript source and compiled to static
  JavaScript for FastAPI to serve.

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
- Boundary-notch cleanup that removes tiny jagged protrusions with validation
  and undo support.
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
- Topology graph endpoint derived from raster boundaries with unique vertices,
  exterior edges, shared edges, and region-edge references.
- Shapely coverage validation for exported physical region polygons.
- Browser selected-boundary summary with internal/external edge lengths.
- Veneer-grouped SVG export in physical units with adjustable contour
  simplification.
- Shapely coverage-safe SVG export that simplifies shared edges together.
- Coverage-safe SVG exports persist artifact metadata on the design, including
  tolerance, coverage validity, topology counts, and path.
- Topology graphs can be persisted as versioned vector artifacts.
- Shared-boundary topology graphs can be simplified into undoable vector graph
  artifacts without modifying the raster partition.
- Persisted graph artifacts can be reconstructed into filled SVG regions from
  graph linework.
- A persisted vector graph can be promoted as the active output geometry.
- Promoted vector geometry drives SVG export and pack-manifest physical
  contours/bounds.
- Topology-safe vector edit operations exist for selected-boundary
  simplification and single-vertex movement, with graph validation before save.
- Browser vector-handle mode draws topology edges/vertices on the canvas and
  supports dragging vertices through the topology-safe move endpoint, with
  grid snapping, image-bound clamping, no-op rejection, and hover labels.
- Vector vertex moves can be previewed/validated before saving; invalid moves
  return concise coverage-failure reasons in the browser.
- Browser vector drags now create a graphical before/after preview overlay with
  explicit accept/cancel controls before committing the topology edit.
- Individual shared boundaries can be simplified directly from the selected
  boundary summary without selecting all touching regions.
- Vector simplification can be previewed before saving, reporting validation
  status and vertex reduction.
- Browser vector mode supports selecting explicit graph edges and smoothing
  selected edges or one selected boundary through topology-validated edits.
- Browser controls expose vector simplification, selected-boundary vector
  cleanup, graph promotion, graph SVG preview, direct vertex dragging, and
  fallback vertex movement by ID.
- Marquetry-mode candidate generation compresses source images into value bands
  before SLIC and merges tiny source-stage regions unless focus-zone detail is
  being preserved.
- Cuttability cleanup combines sliver repair, raster smoothing, and vector
  simplification for warning regions as one browser/API action.
- Browser endpoints and CLI commands exist for topology persistence,
  simplification, graph loading, graph promotion, graph-SVG export, and vertex
  movement.
- Shapely polygon-aware rotation-capable shelf pack manifest grouped by veneer.
- Pack manifest includes each piece's physical contour, SVG path, placement,
  transformed placed contour, and transformed placed SVG path.
- Browser pack summary with placed/unplaced counts and stock warnings.
- Pack manifest includes recommended sheet counts, stock shortfall, area totals,
  and bounding-box material utilization by veneer.
- Browser pack output is constrained to the configured workspace root.
- Browser canvas raster overlays are cached so vector dragging and linework
  redraws avoid recomputing every image pixel on each pointer move.
- Browser TypeScript source lives in `src/marqflow/static/gallery.ts` and is
  compiled to the served `gallery.js` with `npm run build`.
- User-facing workflow and packing/export documentation lives under `docs/`.
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
- `pack` writes both `design.svg` and Shapely coverage-safe `design-coverage.svg`.
- Thin browser UI over the new API.

## Still Outstanding

1. Advanced vector shared-boundary geometry.

   Shared-boundary polylines now exist for adjacent regions in pixel and
   physical units, with simplified-path analysis and vertex reduction
   estimates. A topology graph now exposes unique vertices, exterior/shared
   edges, and region-edge references, and Shapely coverage validation checks the
   exported physical polygons. Coverage-safe exports persist vector artifact
   metadata. Topology graphs can now be persisted, simplified as undoable vector
   artifacts, reconstructed into filled SVG regions, edited with validated
   single-vertex moves, dragged directly with browser canvas handles, and
   promoted as active output geometry. Dragging now includes grid snapping,
   clamping, hover labels, no-op rejection, and preview validation before save.
   Browser vertex dragging now previews the proposed linework graphically and
   requires accept/cancel before save. Individual shared-boundary simplification
   is available from boundary cards. Vector mode can select graph edges and
   smooth selected edges or one boundary through topology validation. The
   remaining gap is richer handle tooling: true curve/spline editing,
   multi-vertex transforms, and graphical before/after previews for every batch
   mutation, not just vertex movement.

2. Real cleanup tools beyond merge.

   Merge, targeted split, lock/unlock, physical-area sliver repair, raster
   smoothing, selected-region smoothing, boundary-notch removal,
   selected-boundary inspection, bounded auto-merge, vector-graph
   simplification, selected-boundary vector simplification, graph SVG
   reconstruction, graph promotion, edge smoothing, vertex dragging, combined
   cuttability cleanup, and undo now exist. Remaining cleanup depth: true
   curve/spline smoothing, constrained snapping, stronger tiny-piece decision
   tooling, and more usable visual editing affordances.

3. Subject/detail logic.

   Detail zones can drive local splits after a design exists and can optionally
   refine new candidates with denser local source-stage segmentation. A
   first-class pixel-level subject/background mask exists and can guide
   candidate generation. The browser can show the mask overlay and paint
   subject/background mask pixels with a brush.

4. Browser selection tooling.

   Canvas click/drag selection, lasso selection, selected-boundary summaries,
   zoom, scroll-panning, vector cleanup buttons, and direct vector vertex
   handles exist. Invalid vertex drags preview coverage failures before saving.
   Valid drags now render a before/after overlay and require explicit accept or
   cancel. It remains visually basic and needs richer edge/curve handles plus
   preview UI for batch edits beyond normal undo.

5. Material planning.

   Veneer inventory fields, replacement, browser editing, stock-fit summary,
   purchasing quantity estimates, material utilization, grain notes, and texture
   URL previews exist. Deeper grain review and managed texture upload/library
   workflows are not implemented.

6. Real packing/nesting.

   Packing now uses a Shapely-backed polygon shelf adapter. It places true
   physical contours, collision-checks placed polygons, tries rotated
   orientations when grain settings allow, and emits transformed tracing
   contours. This is a real contour-aware baseline, but it is not yet an
   optimized irregular nester: it does not exploit concavities, optimize across
   row/sheet choices deeply, or minimize waste beyond simple shelf placement.

7. TypeScript migration.

   The browser source is now TypeScript and compiles to the served JavaScript.
   A deeper module split remains open; the UI is still concentrated in one
   large file.

8. Browser tests.

   A Playwright smoke test covers image upload, workspace creation,
   candidate-grid generation, design seeding, direct vector-handle dragging,
   vector simplification preview, vector edge selection/smoothing, canvas
   selection, selected veneer assignment, undo, notch cleanup, pack summary
   generation, zoom, lasso selection, box selection, merge/undo, and SVG
   preview. Broader visual regression and multi-browser coverage are still
   future hardening work, but the current vertical slice now has a browser smoke
   test.

## Engineering Direction

Do not reintroduce the prototype's mirrored state model. `MarquetryDesign`
should remain the durable object. Candidates are inputs. Export and packing
must consume only the final design.
