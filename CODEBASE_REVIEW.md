# Marqflow Codebase Review

Review date: 2026-06-18

Last status update: 2026-06-24

Scope: current `grid-gallery` branch. The first prototype remains recoverable from history and `main`; this branch is the gallery, compose, and merge redesign.
The browser UI in this branch now presents the literal marquetry decision flow: `Image`, `Size`, `Subject`, `Shapes`, `Hues`, `Cleanup`, and `Pack`.
That is a UI shell, not yet a complete marquetry design model. Several tabs still save metadata or operate on raster labels rather than editing a robust physical partition.

## Current Verification

- Last verified commands before this audit:
  - `uv run ruff check src tests` passed.
  - `uv run pytest -q` passed, with 10 tests.
  - `node --check src/marqflow/static/gallery.js` passed.
- A live server check confirmed that `/`, `/static/gallery.css`, and `/static/gallery.js` are served from the FastAPI app.
- The search page no longer renders the old large candidate preview canvas; it is now grid-first.
- The workspace now persists a final partition raster, physical size, veneer palette, and cleanup metadata.
- The browser exposes size controls and a veneer-aware pack action.
- The browser exposes a separate subject tab and cleanup controls for merge/split workflows.
- One headless browser smoke test now covers upload, keep, paint, cleanup, and pack at a high level.
- A follow-up product plan was added at `MARQUETRY_PRODUCT_PLAN.md`.
- Background grid/refine jobs now report visible progress to the browser.
- Cleanup now includes direct point editing and contour smoothing controls.
- Pack/export now writes veneer-grouped SVG sheet files to disk.
- Packing now goes through a dedicated adapter module so the backend can be swapped later.
- Browser upload now caps working images at a 768 px longest edge by default.
- Unmerged composite SVG export now uses final design region records, including veneer overrides and edited contours.
- Cleanup summary now reports high point count, hole, and disconnected-island warnings per final region.
- Size input rejects non-positive physical dimensions, and pack/export validate basic partition invariants before writing files.
- Pack and preview export now write `pieces.json` and `pieces.csv` bills of pieces with region IDs, veneer IDs, physical metrics, geometry warnings, and source references.
- The Hues tab now includes an editable veneer inventory with persisted swatch IDs, names, and display colors.
- Cleanup small/thin/geometry warnings are now visible as translucent overlays on the final canvas, not only in the region list.

## 2026-06-22 Implementation Audit

The project has moved closer to the intended product shape, but the current code still falls short of a fabrication-ready marquetry planner.

Implemented correctly:

- The app can start without a workspace and requires image selection before showing the main workflow.
- The browser now has top-level decision tabs: Image, Size, Subject, Shapes, Hues, Cleanup, and Pack.
- `GridWorkspace` persists physical dimensions, cleanup settings, subject settings, a default veneer palette, final labels, source provenance, and manual merge/split edits.
- The final preview, summary, SVG export, and packing route all use the final label raster rather than independent frontend-only state.
- The final label raster is a complete pixel partition when generated from a base candidate, so the raster preview itself has no pixel gaps or overlaps.
- Manual merge and split endpoints exist and are wired to the Cleanup tab.
- Candidate grid dimensions are user-configurable and the top-left-to-bottom-right axis is intended to move from coarse to detailed.

Important shortcomings:

- `CompositeDesign` now exists and the main final-design mutation paths update it directly, but the workspace still mirrors final state across `GridWorkspace` fields such as selected candidate regions, `final_labels`, `final_region_sources`, `final_region_veneer_overrides`, `final_region_locked_ids`, and `manual_edits`.
- Hues is still partly candidate-driven, but final regions now support explicit veneer overrides, region locks, and an editable veneer inventory. The workflow still needs a true material-planning model with stock/sheet constraints, not just swatches and override maps.
- A persisted ordered paint-event log now exists, and a `CompositeDesign` aggregate is written to the manifest. Final-design operations now update the aggregate directly, but the workspace still mirrors those fields for compatibility.
- Manual merge/split edits are stored against numeric region IDs. Those IDs can become stale if the base candidate or painted source layers change, because the code replays edits onto a rebuilt label raster.
- Subject settings are metadata only. `detail_budget`, `protect_eyes`, and `protect_nose` do not influence candidate generation, local refinement, cleanup, or locking.
- Cleanup now has a canvas hitmap for direct region selection, hover feedback, drag-select, and canvas overlays for small, thin, high-point-count, holed, and disconnected regions. It still lacks true sliver repair and shared-boundary repair.
- `highlight_small_area` and `highlight_thin_width` now surface in the Cleanup list and on the canvas. Thin-width warnings now compare against physical units rather than raw pixel dimensions.
- Unmerged SVG output now uses physical dimensions and scales final-region contours into those units. Merged-threshold preview SVG is still a visual preview path and should not be treated as fabrication export.
- SVG paths are independent contours, not a shared-boundary planar graph. This is risky for marquetry because smoothing or simplification can create tiny visual gaps/overlaps between adjacent pieces.
- Packing now uses a maintained rectangle packer and emits veneer-grouped SVG sheet files, but it is still bounding-box based rather than a true veneer nesting solver.
- `gallery_web.py` now has an accurate module docstring describing the tabbed marquetry browser UI.
- `gallery.js` still has some UI responsibilities split between state refresh helpers and tab renderers, but the old dead helpers have been removed.
- `python-multipart` is required by FastAPI uploads, and there is no stray `httpx2` dependency entry in `pyproject.toml`.
- Browser-level workflow coverage is now broader. Static asset tests, API tests, and one headless browser smoke test cover upload, keep, paint-all, cleanup hover, drag-select, point edit, smooth, and pack.
- API coverage now includes high-resolution browser upload downscaling and final SVG veneer override export.
- API coverage now checks geometry warning summary keys.

Current bugs or likely user-facing failures:

- Candidate paint order is now persisted, and cleanup now exposes direct final-region point edits, but the UI still does not expose a real paint-event history or full brush editing. The current workflow remains candidate-driven rather than design-driven.
- The Hues palette still injects candidate SVGs into the DOM for region clicks. Large candidates can remain slow even though previews use thumbnails/canvas elsewhere.
- Cleanup selection happens through a text/list of final regions plus a canvas hitmap, hover inspection, and drag interactions, but it still lacks brush painting.
- The merge threshold preview can imply fewer pieces, but the actual manual merge operation only merges selected connected final labels. This distinction is easy to misunderstand in the UI.
- Automatic veneer choice still defaults to nearest palette color, but the UI now lets the user edit the palette, override a final region's veneer, and lock regions. A richer material workflow with sheet inventory and grain direction is still missing.
- `packFinal()` now sends only the output directory, which matches the current packing backend that exports veneer sheets from the final design.
- `composite_summary()` now counts merged contours rather than raw records, but the merged preview/SVG can still differ from the summary when clusters produce multiple disconnected contours.

## Progress Summary

Done:

- Composite PNG preview, SVG export, and summary now derive from the same final partition model.
- The final partition is persisted as a raster plus provenance metadata, with last-painted candidate layers applied in order.
- Physical size, cleanup thresholds, veneer palette, and veneer-aware pack output are now persisted on the workspace.
- The first kept candidate is treated as the base layer for the final partition.
- Merge preview now respects `merge_threshold` for PNG preview, SVG export, and path summary.
- Expected composite export validation errors now return 400 responses.
- Candidate open/sync now updates the server-side active candidate.
- Browser UI assets have been split out of `gallery_web.py` into static HTML, CSS, and JS files.
- The browser has basic caching for candidate detail and SVG text.
- The worst image cache-busting behavior was removed.
- Composite summary no longer requires fetching the full SVG just to count paths.
- Merge/composite preview requests now use request IDs and `AbortController` so stale renders do not repaint newer state.
- Compose region selection uses delegated SVG click handling instead of one click listener per path.
- The Compose UI now exposes Clear selection for a candidate.
- The Search tab has been simplified to a grid-first layout without a large preview canvas.
- The README now documents the gallery, compose, and merge workflow and the default `8000` browser port.
- `serve` and `grid-serve` now share one CLI serving helper instead of duplicating the implementation.
- Candidate thumbnails are generated at workspace build time and Search/kept tiles use them.
- Workspace and project manifests now store paths relative to their owning directory and resolve them on load.
- Workspace writes use atomic file replacement, and mutations are guarded by a workspace lock in the web app.
- The browser now has a reset workspace action that clears generated candidates and rebuilds from the copied source image.
- `Paint all` is backed by a dedicated API route and the backend helper is now used.
- The browser now exposes physical size controls and a packing action.
- `iter_region_ids()` and `labels_to_region_lookup()` were removed.
- `paint_all_candidate()` is now wired through the backend route instead of being dead helper code.
- `CompositeDesign` is now persisted in the manifest alongside paint events, veneer overrides, locks, and validation data.
- Merge threshold changes are debounced in the browser.
- The composite base candidate is stored explicitly in the workspace manifest.
- Composite render paths reuse cached candidate project loads.
- Search grid rows and columns are now user-configurable from the UI and persisted in the workspace manifest.
- The search grid now reads coarse-to-detailed from top-left to bottom-right.
- The browser can start without a workspace and create one after image upload.
- Background jobs now provide visible progress for grid and refine operations.
- Cleanup now exposes direct point edit and smooth controls, plus canvas hover and drag selection.
- Packing now writes SVG sheet files per veneer group.
- Unmerged final SVG export now writes groups by veneer and preserves user veneer overrides.
- Browser upload now enforces the 768 px working-edge default and reports original versus working dimensions.
- Cleanup summaries now include high-complexity, holed, and disconnected-region warning IDs.
- Pack/export now block invalid physical sizes and invalid partitions instead of writing misleading fabrication files.
- Pack/export now write traceable JSON and CSV piece manifests beside the SVG artifacts.
- Veneer swatches can now be edited from the Hues tab and saved through `/api/workspace/veneer-palette`.
- Cleanup warnings now draw directly over the canvas for small, thin, and complex/problem regions.

Partial:

- Frontend testing now includes static asset smoke coverage, API workflow coverage, and a headless browser workflow smoke test.
- The UI is more cache-friendly, but candidate selection still rerenders more of the Hues/Cleanup view than it should.
- The final plan is now a non-overlapping physical partition, but provenance is still coarse when cleanup edits are replayed after shape changes.
- Manual merge and split exist. Point editing, smoothing, hover inspection, drag selection, and basic geometry diagnostics are implemented, but richer geometry repair and shared-boundary editing are still not implemented.

Open:

- Expand browser-level interaction tests beyond the current smoke path.
- Add richer canvas-based cleanup interaction, especially brush selection and sliver overlays.
- Add more nuanced sliver repair, shared-boundary cleanup, and merge suggestions.
- Remove or formalize old single-project commands and helpers.
- Review and remove unused dependencies if they remain unreferenced after the current dependency pass.

## High-Impact Issues

1. Compose preview and SVG export did not share the same truth.

   Status: Done.

   What changed: `GridWorkspace` now rebuilds and persists a final partition raster. `composite_preview()`, `composite_svg()`, `composite_summary()`, and export all read from that partition and its provenance metadata instead of from layered source masks.

   Remaining concern: richer canvas interactions are still missing, so the current cleanup workflow is region-based rather than vertex-based.

2. The merge preview did not actually preview merged geometry.

   Status: Done.

   What changed: `/api/workspace/composite/preview` accepts and passes through `merge_threshold`. The backend clusters composite records and renders a merged PNG preview, merged SVG, and merged path summary from the same threshold.

   Remaining concern: merging is still RGB-threshold clustering. It is not veneer-aware and not based on perceptual color distance.

3. Opening a candidate in the UI did not update workspace active state.

   Status: Done.

   What changed: `openCandidate()` posts to `/api/workspace/active` and refreshes the workspace summary from the server response.

4. Export error paths became server errors instead of user-level validation.

   Status: Done.

   What changed: composite preview, SVG, and export routes catch expected `ValueError`s and return HTTP 400 responses.

5. Composite merging is color-order dependent and not veneer-aware.

   Status: Partial.

   Current behavior: the final partition gets suggested veneers from a default palette, the UI can pack by veneer, and merge previews still support a color threshold for quick grouping.

   Why this matters: veneer grouping should map to a material palette, not just RGB proximity. Two visually similar regions should only merge if they are intended to be the same veneer and the resulting piece is physically reasonable.

   Suggested fix: expose per-region veneer overrides and make final export group strictly by veneer assignments.

6. The final design lacks physical fabrication semantics.

   Status: Partial.

   Current behavior: the workspace now stores physical width, height, units, and cleanup thresholds. Region summaries include physical area and perimeter estimates, and SVG export now scales into physical units. Packing produces veneer-grouped output, but it is still a bounding-box adapter rather than a shared-boundary nesting model.

   Why this matters: marquetry decisions are physical. A region that looks acceptable at screen scale may be impossible to cut at 8x10 inches. Packing also requires real units and one closed piece per final region.

   Suggested fix: add more geometry validation for slivers, holes, shared boundaries, and minimum cut width.

## Medium-Impact Issues

1. The frontend had race-prone async rendering.

   Status: Done.

   What changed: composite preview rendering now uses a monotonically increasing request ID plus `AbortController`. Stale responses are ignored.

   What changed next: merge slider input is now debounced before triggering a rerender.

2. Entering the Merge tab unnecessarily rendered the Compose palette.

   Status: Done.

   What changed: `setMode('merge')` now renders the merge workspace directly. Compose rendering is only triggered for the Compose tab.

3. The browser UI is not covered by browser-level tests.

   Status: Partial.

  What changed: `tests/test_gallery_assets.py` verifies that the static browser assets are served. `tests/test_workspace_gallery.py` covers active candidate, selection, clear selection, merge preview, composite summary, SVG, export API behavior, large-upload downscaling, and final SVG veneer override export. `tests/test_browser_workflow.py` covers a real browser upload/keep/paint/cleanup/pack smoke path.

   Remaining work: broaden Playwright coverage for repaint ordering, veneer assignment, small-piece highlighting, export, and pack output inspection.

4. The gallery grid was visually forced into square thumbnails.

   Status: Done.

   What changed: candidate grid images now use `object-fit: contain`, the large search preview was removed, the grid is pinned to fixed desktop/tablet/mobile column counts, and workspace candidate thumbnails are generated at build time.

5. README port mismatch.

   Status: Done.

   What changed: README now documents the default browser URL as `http://127.0.0.1:8000/`.

6. Workspace manifests are not clearly portable.

   Status: Done.

   What changed: workspace and project manifests now store paths relative to their owning directory and resolve them on load.

7. Workspace writes are not protected from concurrent requests.

   Status: Done.

   What changed: workspace mutations are now protected by a process-local lock in the FastAPI app, and manifests are written atomically.

8. Workspace deletion/restart was implicit.

   Status: Done.

   What changed: the browser now exposes a reset action that clears generated candidates and selections, then rebuilds the gallery from the copied source image. Reloading is still just a normal browser refresh because the app re-reads workspace state from disk on each API request.

## Dead Code and Cleanup Candidates

1. `GridWorkspace.paint_all_candidate()` is not used by the API or UI.

   Status: Done.

   What changed: the UI now calls a dedicated `/api/workspace/selection/paint-all` route backed by `paint_all_candidate()`.

2. `/api/workspace/export` duplicated `/api/workspace/composite/export`.

   Status: Done.

   Current state: the explicit `/api/workspace/composite/export` route remains.

3. `/api/workspace/selection/clear` and `/api/workspace/active` appeared unused.

   Status: Done.

   Current state: the frontend uses `/api/workspace/active` when opening candidates and `/api/workspace/selection/clear` from Compose candidate cards.

4. Stale `.compose-step-tabs` CSS remained from an older Compose design.

   Status: Done.

   Current state: the UI CSS is split into `src/marqflow/static/gallery.css` and the stale selector is gone.

5. `progressBar` was captured in JS but never used directly.

   Status: Done.

  Current state: the unused JS reference was removed. Busy progress is still CSS-driven through `body.busy`.

6. `serve` and `grid-serve` duplicated CLI code.

   Status: Done.

   Current state: both commands call `_serve_workspace_ui()`.

7. `iter_region_ids()` and `labels_to_region_lookup()` appear unused.

   Status: Done.

   What changed: both helpers were removed from `regions.py`.

8. `python-multipart` dependency review.

   Status: Done.

   Current note: `python-multipart` is required for FastAPI uploads, and there is no stray `httpx2` dependency entry in `pyproject.toml`.

## Maintainability Issues

1. `gallery_web.py` was doing too much.

   Status: Done.

   What changed:

   - `src/marqflow/gallery_web.py` now owns FastAPI routes and static mounting.
   - `src/marqflow/static/gallery.html` owns markup.
   - `src/marqflow/static/gallery.css` owns styles.
   - `src/marqflow/static/gallery.js` owns browser behavior.

2. There are two overlapping product models.

   Status: Open.

   Current state: `MarqflowProject` still supports lower-level single-project operations, while `GridWorkspace` is the gallery/compose workflow. CLI still exposes both layers.

   Suggested fix: decide whether the old project commands are user-facing utilities or internal implementation details. If internal, move old commands under an experimental or legacy namespace.

3. Composite state is implicit.

   Status: Partial.

   What changed: preview/export now share one composite record model at runtime, and the workspace persists an explicit base candidate.

   Remaining work: persist a full composite assignment model, for example:

   ```text
   Composite
   - base_candidate_id
   - assignments: final_region_id -> source_candidate_id/source_region_id
   - veneer_group_id per final region
   - merge_threshold or palette mapping metadata
   ```

4. The grid search has no metadata model beyond labels.

  Status: Partial.

   Current behavior: row, column, generation, and parent candidate information are now explicit, but search-space bounds are still only implicit in the UI labels and preset values.

   Suggested fix: store search-space bounds explicitly and render refined searches as separate grids.

5. Long-running work now runs in background jobs.

   Status: Done.

   What changed: grid rebuild and refine operations now return job IDs and the browser polls `/api/jobs/{id}` for progress.

## Performance Issues and Recommendations

1. Avoid hydrating every candidate SVG as live DOM.

  Status: Partial.

   Current state: Compose still injects SVG for kept candidates so regions can be clicked, but the cleanup view now uses a canvas hitmap for region selection. The palette still degrades with many regions.

   Suggested fix: render kept-candidate previews with Canvas too, then use a hitmap or binary region map for selection.

2. Use one delegated event listener instead of one listener per path.

   Status: Done for click selection.

   Current state: each Compose SVG root has one click listener and reads `event.target.closest('path')`. Hover styling is handled by CSS.

3. Cache candidate details, SVG text, and preview images.

   Status: Partial.

   What changed: browser-side detail and SVG text caches exist, and preview URLs no longer get unconditional `Date.now()` cache busting.

   Remaining work: add explicit cache invalidation keyed by candidate ID and generation, and avoid rebuilding cards on every selection change.

4. Do not rerender the full compose palette after every region click.

   Status: Open.

   Current behavior: `saveCandidateSelection()` still refreshes the workspace and rerenders the full visible mode.

   Suggested fix: update the clicked candidate card selection state in place, then refresh only the composite preview and summary.

5. Debounce and cancel merge preview renders.

   Status: Done.

   What changed: cancellation/request versioning is implemented, and merge slider input is debounced.

6. Avoid computing PNG and SVG for every preview update.

   Status: Done.

   What changed: `/api/workspace/composite/summary` returns path counts without serializing full SVG for the UI.

7. Cache loaded projects during a request or app session.

   Status: Done.

   What changed: workspace composite code now uses `_load_project_cached()` with an LRU cache.

   Remaining concern: cache invalidation is path-based and should eventually consider project mtime or candidate generation.

8. Generate thumbnails for gallery browsing.

   Status: Done.

   What changed: the workspace now generates `thumb.png` for each candidate, and the gallery grid/kept strip use those thumbnails.

9. Move heavy candidate generation and refinement to jobs.

   Status: Done.

   Current state: grid and refine operations are background jobs with visible progress.

10. Consider Canvas for interactive editing and SVG only for final export.

   Status: Partial.

   Best direction: use Canvas or WebGL for viewing, hit-testing, hover, and painting. Keep SVG as the export format and possibly as a static preview overlay.

## Performance Priority List

1. Stop rebuilding the whole Compose palette after every selection.
2. Cache candidate project loads on the backend.
3. Move interactive selection to Canvas plus hitmap.
4. Add explicit cache invalidation keyed by candidate generation.

Completed from the original performance list:

- Stop cache-busting every image request.
- Add browser caches for candidate detail and SVG text.
- Replace per-path click listeners with delegated SVG click handling.
- Add cancellation/versioning for composite preview renders.
- Add a lightweight composite summary endpoint.
- Add debouncing for the merge slider.
- Generate thumbnails for the grid and kept strip.

## Suggested Product Direction

For a first useful digital pass from image to marquetry design, build around these stages:

0. Reframe the UI around marquetry decisions.

   The top-level tabs should not be implementation stages like Search/Compose/Merge. They should match the way a user thinks through a marquetry plan: Image, Size, Subject, Shapes, Hues, Cleanup, and Pack. The implementation can still use candidate generation and composite models internally, but the user-facing structure should follow physical decisions.

1. Normalize the source image.

   Auto-orient, crop, downscale to a bounded working size, and optionally let the user mark a region of interest. For portraits and pet photos, preserve eyes and high-saliency areas at higher detail.

2. Generate a broad candidate grid.

   Keep the current grid idea, but make the axes explicit: more/fewer regions on one axis, smoother/more image-following regions on the other. Let the user refine a chosen cell into a smaller local grid.

3. Add a veneer palette step before final merging.

   A marquetry design is not just color quantization. The user should define or select veneer groups like light maple, walnut, dark walnut, cherry, dyed blue, etc. The tool should map image regions to those materials and let the user override assignments.

4. Compose from candidates using an explicit region assignment model.

   The right-side canvas should be a real composite object, not just a preview. Every final region should know which candidate and source region it came from.

5. Merge by material and adjacency.

   Similar colors should not automatically become one piece unless they are intended to be the same veneer and the resulting shape is physically reasonable. Merge should consider material group, connectedness, shape complexity, and minimum cut size.

6. Clean vector geometry for cutting.

   Add simplification and smoothing controls that optimize for cuttability, not just image accuracy. Flag tiny islands, hairline slivers, holes, and high-curvature shapes.

7. Export practical fabrication artifacts.

   Export:

   - final SVG with one layer per veneer group
   - numbered pieces
   - registration/reference image
   - CSV/JSON bill of pieces by veneer group
   - nested SVGs per veneer group for packing

## Suggested Implementation Plan

1. Add an explicit persisted composite model.

   The runtime composite records are an improvement, but the design should persist base candidate, source assignments, veneer groups, and merge metadata.

2. Add browser tests for the core workflow.

   Playwright should verify the interactions that matter: keep candidates, paint from palette, clear, Paint all, move to Merge, see path count change, and export.

3. Introduce veneer groups.

   Start simple: user-editable swatches with names. Map each final region to a swatch. Add automatic suggestions later.

4. Improve interactive performance.

   Stop full palette rerenders on every click, and cache project loads where it still matters.

5. Move selection interaction to Canvas plus hitmap.

   This becomes important once candidates have many hundreds or thousands of regions.

6. Improve final geometry.

   Add minimum area filtering, contour simplification settings, hole handling, and per-region complexity metrics.

7. Add final partition validation.

   Validate that the final design covers the source area exactly once, with no gaps, no overlaps, and no unassigned regions. This should be a blocking export check.

8. Add packing integration only after final-region semantics are stable.

   Nesting should operate on final SVG groups by veneer, not on transient candidate regions. The current code now does this through `packing.py`: the default backend uses deterministic bounding-box placement, and `MARQFLOW_NESTER_CMD` can hand per-veneer SVGnest-compatible input SVGs to an external SVG nester.

## Prioritized Fix List

Done:

- Make the composite model shared by preview, summary, and SVG export.
- Make merge preview reflect merge threshold.
- Fix active candidate state so frontend and workspace agree.
- Split `gallery_web.py` into route/static files.
- Remove duplicate export route and stale UI code.
- Wire active and clear-selection routes into the frontend.
- Add composite summary endpoint.
- Add request cancellation for composite preview renders.

Next:

1. Replace candidate selected-region state with an explicit `CompositeDesign`.

   Required outcome: the workspace persists ordered paint events, final labels, final region records, veneer assignments, locks, cleanup operations, physical scale, and validation state in one aggregate.

2. Make paint ordering deterministic and user-visible.

   Required outcome: painting candidate A, then candidate B over the same area, always shows B after preview, export, and browser reload.

3. Move Hues from "paint candidate regions" to "assign veneers."

   Required outcome: the user can select final regions and assign a named veneer swatch. Automatic Lab matching remains only a suggestion.

4. Replace SVG DOM region interaction with canvas plus hitmap.

   Required outcome: candidate and final-region clicks use a region-ID hitmap instead of injecting hundreds or thousands of SVG paths into the page.

5. Add direct final-canvas cleanup tools.

   Required outcome: users can select visual regions on the final canvas, merge adjacent regions, highlight small/thin pieces, and preview smoothing/simplification before applying it.

6. Add partition validation and physical-unit export.

   Required outcome: export blocks on unassigned pixels, overlap defects, holes/slivers beyond thresholds, or invalid physical dimensions. SVG paths use real units or a documented physical scale.

7. Replace placeholder packing with a packing adapter.

   Status: partially done. Packing receives validated final regions grouped by user-assigned veneer, writes traceable SVG sheets, records backend metadata, saves per-veneer nester input SVGs when an external runner is configured, and writes JSON/CSV piece manifests. The built-in fallback is still bounding-box placement; a bundled true irregular nesting engine remains open.

   Required remaining outcome: choose whether to vendor SVGnest/Deepnest automation or require an installed external command, then add an integration test against that concrete backend.

8. Add browser workflow tests.

   Required outcome: Playwright or equivalent covers image upload, candidate generation, keep candidate, paint/repaint, veneer override, merge, small-piece highlighting, export, and pack. A headless smoke test now covers the basic upload/keep/paint/cleanup/pack path.

9. Clean up implementation debt.

   Required outcome: remove unused JS helpers, fix the stale `gallery_web.py` docstring, and decide whether old `MarqflowProject` CLI commands are public or legacy/internal.
