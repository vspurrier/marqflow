# Marqflow Product Plan

Review date: 2026-06-24

Role: orchestration and validation plan for implementation by a smaller coding model.

## Current Assessment

The current project is a useful prototype, but it is not yet structured around the object the user actually wants: an editable marquetry design with physical pieces.

The superpixel workflow should remain as a candidate generator, not as the source of truth. A usable marquetry tool needs a persistent design model that knows:

- which final regions exist
- which veneer each region uses
- which source candidate/region produced a region
- which edit operation last painted or changed an area
- which regions are manually merged, split, smoothed, locked, or marked for extra detail
- the real-world size of the finished image
- whether the current final regions form a complete non-overlapping partition
- which pieces are too small, too thin, too jagged, or otherwise impractical to cut

The current implementation stores kept candidates plus selected source-region IDs. That is too implicit for the user-facing workflow. It cannot reliably express last-paint-wins behavior, manual merge decisions, veneer constraints, or targeted geometry cleanup.

The core invariant should be:

```text
At every final-design step, the plan is a puzzle: every point in the design area belongs to exactly one final region, with no overlaps and no gaps.
```

Candidate maps may be rough suggestions. The final marquetry plan must be a measured, planar partition suitable for cutting and packing by veneer.

## Implementation Status

Implemented in the current branch:

- final partition raster derived from candidate layers
- persisted physical size, cleanup thresholds, veneer palette, and provenance metadata
- merge and split operations on the final partition
- veneer-aware packing summary output
- browser size controls and pack action
- seven-tab browser shell: Image, Size, Subject, Shapes, Hues, Cleanup, Pack
- image-first startup, configurable candidate grid dimensions, and reset workflow
- background grid/refine jobs with visible progress
- Cleanup point editing, contour smoothing, hover inspection, drag selection, and merge suggestions
- veneer-grouped SVG sheet export from the pack step
- `packing.py` adapter layer around the current packing backend
- one headless browser smoke test for the main upload/keep/paint/cleanup/pack path
- browser upload caps working images at a 768 px longest edge by default
- final unmerged SVG export uses final design records, user veneer overrides, and edited contours
- cleanup reports high point count, holed, and disconnected final regions
- pack/export validates positive physical dimensions and basic partition invariants before writing files
- pack/export writes `pieces.json` and `pieces.csv` bills of pieces with final region IDs and veneer assignments
- editable veneer inventory with persisted swatch IDs, names, and display colors
- cleanup canvas overlays for small, thin, and complex/problem regions
- bulk cleanup action for applying current small/thin merge suggestions

Implemented but not yet product-complete:

- Image tab uploads and normalizes through the existing project pipeline and now records original versus working dimensions, but does not yet expose crop/orientation decisions clearly.
- Size tab persists physical dimensions, and SVG export now scales into physical units, but the packing geometry is still bounding-box based.
- Subject tab persists notes and protection flags, but those settings do not affect segmentation, local refinement, locking, or cleanup.
- Shapes tab can generate and keep candidates, but generation is still synchronous and the parameter grid is still tied to the current SLIC/Felzenszwalb generator assumptions.
- Hues tab still paints candidate source regions into the final preview, while final regions have veneer override and lock controls in Cleanup. It now has an editable veneer inventory, but it is still not a true material workflow with sheet stock, grain direction, or availability constraints.
- Cleanup tab exposes final region lists, merge/split actions, bulk merge suggestions, veneer overrides, lock controls, a basic canvas hitmap, direct point editing, contour smoothing, hover inspection, drag selection, small/thin/geometry warning overlays, and basic geometry warnings, but still lacks sliver repair and shared-boundary repair.
- Pack tab now writes veneer-grouped SVG sheets, but the packing is still bounding-box based rather than a true nesting solver.

Still open:

- explicit `CompositeDesign` persisted in the workspace manifest, but not yet the sole source of truth for every final-design operation
- ordered paint-event model with guaranteed last-paint-wins behavior for final-region edits
- browser-level interaction tests
- more complete geometry editing and sliver cleanup
- user-editable veneer inventory, veneer assignment overrides, and region locks are now present, but they need to be lifted into a first-class material planning model
- real nesting/packing integration beyond the current bounding-box packer

## Validation Of CODEBASE_REVIEW.md

The existing `CODEBASE_REVIEW.md` is directionally correct, but it is stale in several places.

Validated as implemented:

- Static UI files are split out of `gallery_web.py`.
- Search is grid-first and no longer centered around one large preview.
- Candidate thumbnails are generated and used.
- Workspace paths are stored relative to the workspace directory.
- Workspace reset and image-first startup exist.
- Composite preview, composite SVG, and summary share the runtime `_composite_region_records()` path.
- Project loading is cached by `_load_project_cached()`.
- Merge threshold affects preview, summary, and export.
- API, static asset, and browser smoke tests exist and currently pass: `9 passed`.

Implemented but not sufficient:

- Compose uses Canvas only for the final preview. Palette interaction still injects SVG paths into the DOM, so high region counts remain expensive.
- Composite state is partially explicit. The base candidate contributes all regions, later paint events update final labels, and `CompositeDesign` persists paint events and final-region metadata. Workspace fields still mirror that state.
- Last-paint-wins behavior is modeled by ordered paint events for candidate-region selection, but there is no user-facing paint history and final-region edits are not yet represented as first-class event types.
- The composite can create overlapping conceptual regions because source masks are layered. It is rendered as pixels, but exported paths are still independent shapes rather than one normalized planar partition.
- Candidate SVG paths are serialized as independent contours. This can visually suggest gaps/overlaps even when the raster labels cover the image, and it does not create fabrication-ready shared boundaries.
- Merge supports manual connected-region merge and small-piece suggestions. The threshold preview remains RGB clustering and is not veneer-aware.
- The grid has configurable rows/columns and background job endpoints for generation/refinement.
- The browser has one real interaction smoke test, but not a complete workflow suite.

Outstanding from the review:

- Veneer/material palette semantics are partially implemented through editable swatches, but stock dimensions, grain direction, and availability are still open.
- Explicit persisted composite model.
- Canvas plus hitmap interaction.
- Background jobs and progress for generation/refinement.
- Broader browser-level tests.
- Manual merge/edit workflow.
- Partition validation: no gaps, no overlaps, no unassigned pixels/areas.
- Physical sizing and scale-aware piece metrics.
- Small/thin-piece highlighting and bulk merge suggestions are partially implemented; sliver repair and smarter suggestions are still open.
- Geometry cleanup: smoothing, simplification, sliver removal, hole handling, minimum cut size.
- Packing/nesting integration by veneer once final-piece semantics are stable.
- Dependency cleanup.

Corrections applied to `CODEBASE_REVIEW.md`:

- Update test count from 6 to 7.
- Mark backend project-load caching as done.
- Keep "selection still rerenders Compose" open.
- Keep "Canvas plus hitmap" open.
- Keep "background jobs" open.
- Keep "veneer/material palette" open.

Additional 2026-06-22 validation:

- The seven-tab UI exists, but it should be treated as a shell until each tab mutates an explicit marquetry design model.
- The obsolete `DesignState` class has been removed; `CompositeDesign` is the persisted design aggregate, though some workspace fields still mirror it for compatibility.
- The current final raster is a useful working partition, but it is not enough for physical marquetry unless converted into a shared-boundary vector partition with stronger validation.
- Candidate SVG DOM interaction remains a performance risk in the Hues tab.
- Packing is a placeholder and must not be described as production nesting.
- Subject protection is currently advisory metadata only.
- Veneer assignment has per-region user overrides, but it is not yet a full material inventory workflow.

## Current Gap Against Ideal Design

The ideal design is a measured puzzle of physical pieces. The current implementation is closer to "candidate raster composition plus export preview." The next architecture pass should close these gaps in this order:

1. Make `CompositeDesign` real.

   Store one persisted aggregate for base candidate, ordered paint events, final labels, final region graph, veneer assignments, locks, cleanup operations, physical scale, and validation results. `GridWorkspace` should own workspace lifecycle, but the final design state should live in this aggregate.

2. Replace selected-region composition with paint events.

   A click, brush, Paint all, merge, split, veneer override, or smoothing operation should append or update explicit design operations. Rebuilds should be deterministic and replayable. The latest paint event must win where regions overlap.

3. Separate candidate generation from final editing.

   Candidates are source material. The final design should not depend on current candidate selection sets as mutable hidden state.

4. Add a true veneer assignment layer.

   Every final region needs an editable `veneer_id`. Automatic Lab-distance assignment should only be a suggestion. Merge/export/pack should group by user-approved veneer assignment.

5. Convert the raster partition into fabrication geometry.

   Final labels should produce adjacent shared-boundary polygons or a validated planar graph. Smoothing/simplification must preserve the no-gap/no-overlap invariant.

6. Move interactive viewing and selection to canvas plus hitmap.

   Use canvas for image display and a region-ID hitmap for clicks, hover, brushing, and selection. Use SVG only for export/static inspection.

7. Treat packing as a downstream adapter.

   Packing should receive validated final physical-unit paths grouped by veneer, not raw candidates or bounding boxes.

## User Workflow Model

The UI should be organized around marquetry decisions, not around internal implementation stages. Tabs should map to the sequence of choices a user naturally makes while turning an image into a cut plan.

Recommended top-level tabs:

1. Image

   Pick the source image, apply orientation, crop if needed, and choose the useful image area. This is also where the app should show original dimensions, working dimensions, and any automatic downscaling.

2. Size

   Choose the final physical size of the piece: width, height, units, and optionally target board/veneer sheet constraints. This tab establishes the scale used for all later area, width, and cuttability warnings.

3. Subject

   Separate subject from background and mark priority detail zones. For a pet portrait, eyes, nose, and expression areas can be protected or given higher detail while background fabric or open areas can be simplified aggressively.

4. Shapes

   Convert the image into a non-overlapping puzzle of candidate cut shapes. This tab can expose the candidate grid, but the user-facing decision is "which shape breakdown is closest to a workable marquetry plan?"

5. Hues

   Assign the finite veneer palette. The user chooses available hues/materials and maps regions to those veneers, with automatic suggestions treated as editable defaults.

6. Cleanup

   Perform final marquetry edits: merge small pieces, simplify edges, smooth jagged cuts, edit points, remove slivers, lock detail regions, and review warnings.

7. Pack

   Export and pack final pieces by veneer. Packing receives only validated final regions in physical units.

Each tab should preserve the same underlying invariant: the current design is one measured partition of the image area. Earlier tabs may regenerate or reset parts of the design, but later tabs should never silently create overlaps, gaps, or unscaled SVG fragments.

## Core Redesign

The product should be redesigned around the same decision flow, backed by explicit data models.

1. Image Setup

   The app starts with image selection. The selected image is normalized before any candidate generation:

   - apply EXIF orientation
   - resize to a bounded working edge before candidate generation
   - keep an original-reference copy for display/export metadata
   - ask for intended final dimensions and units, for example 8x10 inches or 200x250 mm
   - expose a "detail budget" rather than raw pixel resolution
   - optionally let the user crop or mark subject focus

   Acceptance criteria:

   - Uploading a 3000+ px image does not create 3000+ px working canvases.
   - The generated workspace records original dimensions and working dimensions.
   - The final design records physical width, physical height, units, and pixels-per-unit mapping.
   - The UI shows the working resolution used.

2. Candidate Search

   This belongs mostly inside the Shapes tab. Keep the grid concept, but make it a suggestion engine:

   - rows: fewer to more regions
   - columns: smoother/coarser to more image-following/detailed
   - candidate generation runs as a background job
   - each candidate stores row, col, generation, parent candidate, and parameters explicitly
   - user can keep candidates as source material for the design

   Acceptance criteria:

   - The UI remains responsive during generation.
   - Progress is visible per candidate or per grid.
   - The browser never has to render full SVG DOM for all candidates.

3. Compose Design

   This is the backing model for Shapes, Hues, and Cleanup. Replace the current kept-candidate selection model with an explicit persisted `CompositeDesign`.

   Suggested model:

   ```text
   CompositeDesign
   - working_size
   - physical_size: width, height, unit
   - scale: pixels_per_unit
   - base_candidate_id
   - paint_events: ordered list of operations
   - final_labels: one label per pixel or cell, covering the whole design exactly once
   - final_regions: current editable planar region graph derived from final_labels
   - region_assignments: final_region_id -> source_candidate_id/source_region_id
   - veneer_assignments: final_region_id -> veneer_id
   - fabrication_metrics: area, perimeter, min_width, point_count, holes, islands
   - locked_region_ids
   ```

   Paint behavior:

   - clicking or brushing a source region creates a paint event
   - paint events are ordered
   - the latest event wins where source regions overlap
   - each paint operation updates `final_labels`, replacing ownership of the affected area
   - the rendered composite and exported geometry are rebuilt from the normalized final partition, not from stacked source paths

   Acceptance criteria:

   - Painting candidate A over an area, then candidate B over the same area, displays B.
   - After any paint operation, every design pixel/cell has exactly one final region owner.
   - Export reports zero overlap and zero gap defects before writing fabrication SVGs.
   - Reloading the browser preserves the same paint result.
   - Export uses the same model as the visible preview.

4. Veneer Palette

   This is the backing model for the Hues tab. Add veneer logic before the final merge becomes important.

   Minimal first version:

   - user can define veneer swatches with name and color
   - app ships with a small default palette such as light, medium, dark, black, red, blue
   - every final region has one veneer assignment
   - automatic assignment suggests nearest veneer in Lab color space
   - user can override assignments manually

   Better later version:

   - veneer swatches support grain direction, available sheet dimensions, and optional texture image
   - regions can be grouped by veneer for export and packing
   - color matching shows confidence and out-of-palette warnings

   Acceptance criteria:

   - Merge/export groups regions by veneer, not by raw RGB.
   - The user can force a region into a specific veneer.
   - Final SVG exports one layer/group per veneer.

5. Manual Edit And Cleanup

   This is the backing model for the Cleanup tab. Add targeted edit tools after the explicit design model exists:

   - manual merge adjacent final regions
   - manual split or "add detail" in selected regions
   - smooth selected boundaries
   - simplify selected boundaries
   - remove tiny islands/slivers below a threshold
   - lock regions such as eyes before global simplification
   - highlight regions below a user-controlled physical area threshold
   - highlight narrow pieces below a user-controlled physical width threshold

   Acceptance criteria:

   - Selecting two adjacent regions and merging them creates one final region.
   - Smoothing a region changes its SVG geometry but preserves veneer assignment.
   - Locked regions are not changed by global merge/smooth operations.
   - The tool reports problem geometry: tiny pieces, holes, high point counts, thin slivers.
   - Moving the small-piece threshold slider highlights affected regions without changing the design.

6. Packing And Veneer Layout

   This is the backing model for the Pack tab. Packing should operate only after the final design has stable non-overlapping pieces and veneer assignments.

   Requirements:

   - group final regions by veneer
   - convert each region into a closed cut path in physical units
   - preserve optional labels/registration marks
   - send each veneer group to a nesting/packing backend
   - export traceable sheets with minimal waste

   Acceptance criteria:

   - Export can produce one SVG per veneer with dimensions in real units.
   - Packing never receives transient candidate regions.
   - Packing input has no overlapping paths within the same veneer sheet unless deliberately duplicated.
   - Each packed piece can be traced back to a final design region ID.

## Technical Architecture Recommendation

Keep Python for image processing and export. Use the browser for interactive editing.

Backend:

- FastAPI routes remain acceptable.
- Add a `jobs.py` module for long-running generation/refinement.
- Add a `composite.py` module for the persisted design model.
- Add a `veneer.py` module for palette and assignments.
- Add a `partition.py` module for final-label ownership, partition validation, and conversion from paint events to final regions.
- Add a `geometry.py` module for smoothing, simplification, adjacency, connectedness, and cuttability metrics.
- Add a `packing.py` adapter module so the project can swap nesting libraries without contaminating the design model.
- Keep `MarqflowProject` as the candidate generator implementation detail.

Frontend:

- Move interactive region editing away from live SVG DOM.
- Use Canvas for display.
- Use a region hitmap for click/hover/paint selection.
- Keep SVG only for export and optional static inspection.
- Use top-level tabs for decisions: Image, Size, Subject, Shapes, Hues, Cleanup, Pack.
- Add tool modes within tabs: select, paint, merge, smooth, assign veneer, lock.

Data format:

- Workspace manifest should include:

  ```text
  source image metadata
  working image metadata
  physical dimensions and unit scale
  candidate registry
  veneer palette
  composite design
  final partition labels or equivalent planar graph
  fabrication metrics
  edit history
  packing jobs and outputs
  export settings
  ```

## Immediate Implementation Tasks

These are ordered so each step gives the next one a stable foundation.

### Phase Status As Of 2026-06-22

- Phase 1 is partial. Browser workflows have bounded working images through the existing project creation path, default to a 768 px working edge, report original versus working dimensions, and start image-first. Crop and orientation controls are still missing.
- Phase 2 is partial but not complete. A final label raster exists, ordered paint events are persisted, and a `CompositeDesign` aggregate plus canvas hitmap are now written and served. Final-region editing now updates that aggregate directly, but the workspace still mirrors the same state for compatibility. This remains the highest-priority model gap.
- Phase 3 is partial. Editable veneer swatches, nearest-color suggestions, manual veneer override controls, veneer-grouped final SVG export, and veneer-grouped pack output exist, but they still need stock dimensions, grain direction, and availability constraints.
- Phase 4 is partial. Manual merge/split endpoints exist, cleanup canvas selection exists, warning overlays exist, per-region and bulk merge suggestions exist, and automatic merge logic is still limited.
- Phase 5 is mostly open. Subject settings exist, but detail locks and local segmentation are not connected to the pipeline.
- Phase 6 is partial. Simplification tolerance affects contour extraction, point editing, smoothing, hover inspection, drag-selection controls, and canvas warning overlays exist, but there is no shared-boundary smoothing, sliver repair, or non-destructive cleanup preview.
- Phase 7 is partial. Packing now emits veneer-grouped SVG sheets in physical units, writes traceable JSON/CSV piece manifests, blocks invalid dimensions/partitions, and has a file-based external SVG nester adapter via `MARQFLOW_NESTER_CMD`. The default backend remains bounding-box based; true irregular nesting depends on configuring an external SVGnest/Deepnest-style runner.
- Phase 8 is partial. There are API/static tests and one browser smoke test that now covers upload, keep, paint-all, cleanup hover, drag selection, point edits, smoothing, and pack, but not a full workflow suite.

Highest-value next slice:

1. Collapse the remaining mirrored final-design fields so `CompositeDesign` is the durable source of truth.
2. Expand the paint-event log so it records final-region edits, not only candidate-region selection.
3. Add stronger geometry validation for holes, slivers, and shared-boundary risks.
4. Expand the browser smoke test into a full workflow suite.

Do not spend more time polishing the current Hues palette SVG DOM workflow before the explicit design model exists.

### Phase 1: Stabilize Performance And Startup

Tasks:

- Enforce a smaller default working edge for browser workflows. Use 512 or 768 as the first target, not 1024.
- Store original and working dimensions in workspace summary.
- Move grid generation to a job with progress.
- Ensure all candidate previews and compose canvases use bounded working images.
- Add an API test for uploaded large image resize behavior.

Acceptance:

- Uploading a high-resolution source does not hang the page.
- `/api/workspace` reports working dimensions under the configured cap.
- The UI has visible generation progress.

### Phase 2: Fix Compose Semantics

Tasks:

- Promote final-region edits into `CompositeDesign` and keep it as the single source of truth.
- Replace selected-region-only composition with last-paint-wins rendering.
- Store final ownership as `final_labels` or an equivalent planar partition.
- Add partition validation: no gaps, no overlaps, no unassigned area.
- Persist paint events in `workspace.json` or a dedicated composite manifest.
- Update preview, SVG, summary, and export to use the same composite model.
- Add an API test where overlapping paint operations prove the second paint wins.

Acceptance:

- Repainting the same area with another candidate changes the visible preview.
- The backend can assert that the final design is a complete partition.
- Refreshing the browser does not lose paint order.
- Export matches the canvas preview.

### Phase 3: Add Veneer Palette

Tasks:

- Add veneer palette models: `veneer_id`, name, display color, optional notes.
- Add automatic Lab-distance assignment from region color to nearest veneer.
- Add manual override endpoint.
- Add UI palette panel with swatches.
- Export SVG groups/layers by veneer.

Acceptance:

- Every final region has a veneer assignment.
- User can manually change a region's veneer.
- Export groups paths by veneer ID/name.

### Phase 4: Manual Merge Step

Tasks:

- Replace threshold-only merge with editable final-region graph operations.
- Add select regions in Merge.
- Add Merge Selected and Unmerge/Revert where practical.
- Restrict automatic merge suggestions to same-veneer adjacent regions.
- Add connectedness checks so disconnected areas do not become one physical piece unless explicitly allowed as a veneer group.
- Add a small-region highlight slider based on physical area.
- Add a narrow-region highlight slider based on physical minimum width or approximated medial width.
- Add merge suggestions for small regions into same-veneer or nearest-compatible neighbors.

Acceptance:

- User can manually merge adjacent same-veneer regions.
- Automatic suggestions can be accepted or ignored.
- Path count and piece count update without regenerating the whole candidate grid.
- Highlighting small pieces is non-destructive and updates interactively.

### Phase 5: Targeted Detail

Tasks:

- Add "protect detail" locks for regions like eyes.
- Add "add detail here" on selected final regions.
- Run local segmentation only inside selected regions or masks.
- Preserve veneer assignments where possible and re-suggest only for new child regions.

Acceptance:

- The user can add detail to eyes without increasing complexity everywhere else.
- Locked regions survive global simplify/merge operations.

### Phase 6: Geometry Cleanup

Tasks:

- Add per-region simplify tolerance.
- Add smoothing controls.
- Add min-area and min-width warnings.
- Add boundary point-count metrics.
- Add cleanup preview before applying destructive geometry changes.
- Preserve shared boundaries when smoothing adjacent regions so cleanup does not create gaps or overlaps.

Acceptance:

- The user can smooth jagged cut lines locally.
- The app can flag impractical marquetry pieces before export.
- Exported SVG paths are noticeably cleaner than raw superpixel contours.
- Smoothing preserves the partition invariant.

### Phase 7: Packing Integration

Tasks:

- Keep `packing.py` as the backend seam.
- Use the built-in `rectpack` backend only as the deterministic fallback.
- Convert final regions to physical-unit paths grouped by veneer.
- Generate SVGnest-compatible input SVGs per veneer.
- Support an external SVG nester command through `MARQFLOW_NESTER_CMD` with `{input}` and `{output}` placeholders.
- Generate packed SVG sheets with labels and optional registration marks.
- Add tests that packing input uses only final regions, not candidates.
- Add an integration test with a real nester runner once the project chooses a specific vendored or installed backend.

Acceptance:

- User can export one traceable packed layout per veneer.
- Each packed shape references the final region ID and veneer ID.
- Pack output records which backend produced each sheet.
- External nester input SVGs are saved beside nested outputs for auditability.
- The packing path can be replaced later without rewriting the design model.

### Phase 8: Browser Test Coverage

Tasks:

- Add Playwright or equivalent browser tests.
- Cover image upload, grid generation, keep candidate, compose paint, repaint same area, veneer assignment, manual merge, export.
- Add one test fixture with a small image and predictable regions.
- Cover small-region highlight slider and final partition validation state.

Acceptance:

- Core UI workflows are validated in a real browser.
- Regression in paint ordering or blank startup is caught automatically.

## Validation Tasks For The Smaller Model

Ask the implementation model to work in small PR-like chunks. Each chunk should include tests and a short note explaining which acceptance criteria it satisfies.

Suggested first assignment:

1. Add a `CompositeDesign` model and persist ordered paint events.
2. Update backend composite preview to render paint events in order.
3. Add final ownership labels or equivalent partition state.
4. Add API tests proving second paint wins and the partition has no gaps or overlaps.
5. Do not change the UI beyond what is necessary to send paint events.

Suggested second assignment:

1. Enforce browser working image cap.
2. Add workspace summary fields for original and working image dimensions.
3. Add workspace fields for physical size and units.
4. Add an upload test using a large image.

Suggested third assignment:

1. Add veneer palette data models.
2. Add default palette.
3. Assign final regions to nearest veneer.
4. Export grouped SVG by veneer.

Suggested fourth assignment:

1. Add physical area metrics per final region.
2. Add a small-region threshold endpoint and summary.
3. Add merge suggestions for regions below the threshold.

Suggested fifth assignment:

1. Add a packing adapter abstraction.
2. Export final regions grouped by veneer in physical units.
3. Wire the first maintained nesting library through the adapter.

## Risks

- Superpixels alone will not produce final marquetry-quality pieces. They are useful for initial candidates but weak for final cut geometry.
- SVG DOM editing will keep failing at high region counts. Canvas plus hitmap is the correct direction for interaction.
- Automatic merge by RGB will fight the physical material workflow. Veneer groups need to become first-class.
- Without an explicit composite design, every additional edit feature will be bolted onto candidate selections and become harder to reason about.
- Without an explicit partition invariant, the app can keep producing shapes that look plausible on screen but are not a valid puzzle for fabrication.
- Without physical dimensions, "small" and "too thin" cannot be judged correctly.
- Browser-only visual inspection is currently manual. Add browser tests before relying on the UI for complex editing.

## Near-Term Recommendation

Do not continue polishing the current Compose/Merge behavior as-is. The next real milestone should be:

1. explicit `CompositeDesign`
2. last-paint-wins rendering
3. explicit final partition with no overlaps and no gaps
4. physical dimensions and scale-aware metrics
5. bounded working resolution
6. veneer palette model
7. manual same-veneer merge
8. small-piece highlighting and merge suggestions

After that, revisit whether SLIC superpixels are still good enough as one candidate generator. If not, add alternative generators such as color quantization plus contour tracing, edge-aware segmentation, or manually drawn masks, but keep them behind the same explicit composite design model.
