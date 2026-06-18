# Marqflow Codebase Review

Review date: 2026-06-18

Last status update: 2026-06-18

Scope: current `grid-gallery` branch. The first prototype remains recoverable from history and `main`; this branch is the gallery, compose, and merge redesign.

## Current Verification

- `uv run ruff check .` passes.
- `uv run pytest -q` passes, with 6 tests.
- `node --check src/marqflow/static/gallery.js` passes.
- A live server check confirmed that `/`, `/static/gallery.css`, and `/static/gallery.js` are served from the FastAPI app.
- The search page no longer renders the old large candidate preview canvas; it is now grid-first.

## Progress Summary

Done:

- Composite PNG preview, SVG export, and summary now derive from the same composite record model.
- The first kept candidate is treated as the base layer for compose/export.
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
- `Paint all` is backed by a dedicated API route and the backend helper is now used.
- `iter_region_ids()` and `labels_to_region_lookup()` were removed.
- `paint_all_candidate()` is now wired through the backend route instead of being dead helper code.
- Merge threshold changes are debounced in the browser.
- The composite base candidate is stored explicitly in the workspace manifest.

Partial:

- Frontend testing now includes static asset smoke coverage, but not full browser interaction coverage.
- The UI is more cache-friendly, but selection still rerenders more of the Compose view than it should.
- Composite state is more explicit now, but region-to-source assignments are still modeled through kept candidates plus selected source regions rather than a dedicated composite assignment table.

Open:

- Add veneer/material palette semantics.
- Remove or formalize old single-project commands and helpers.
- Move heavy generation/refinement work to background jobs with progress.
- Replace interactive SVG editing with Canvas plus hitmap if region counts keep stressing the browser.
- Review and remove unused dependencies if they remain unreferenced after the current dependency pass.

## High-Impact Issues

1. Compose preview and SVG export did not share the same truth.

   Status: Done.

   What changed: `GridWorkspace` now builds composite records through `_composite_region_records()`. The first kept candidate contributes all of its regions as the base, and additional kept candidates contribute selected regions. `composite_preview()`, `composite_svg()`, and `composite_summary()` all use this model.

   Remaining concern: this is still an implicit composite. A real marquetry workflow should persist an explicit composite object with base candidate, assignments, material groups, and merge metadata.

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

   Status: Open.

   Current behavior: `_cluster_records()` greedily assigns regions to the first RGB cluster within threshold and updates the cluster average as it goes.

   Why this matters: veneer grouping should map to a material palette, not just RGB proximity. Two visually similar regions should only merge if they are intended to be the same veneer and the resulting piece is physically reasonable.

   Suggested fix: introduce explicit veneer/material groups. Use Lab color distance or user-defined swatches for suggestions, then let the user override region-to-veneer assignments. Merge by material group and connectedness.

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

  What changed: `tests/test_gallery_assets.py` verifies that the static browser assets are served. `tests/test_workspace_gallery.py` covers active candidate, selection, clear selection, merge preview, composite summary, SVG, and export API behavior.

   Remaining work: add Playwright coverage for the actual user workflow: keep candidates, switch tabs, paint regions, Paint all, Clear, change merge threshold, and export.

4. The gallery grid was visually forced into square thumbnails.

   Status: Done.

   What changed: candidate grid images now use `object-fit: contain`, the large search preview was removed, the grid is pinned to 3 desktop columns, 2 tablet columns, and 1 mobile column, and workspace candidate thumbnails are generated at build time.

5. README port mismatch.

   Status: Done.

   What changed: README now documents the default browser URL as `http://127.0.0.1:8000/`.

6. Workspace manifests are not clearly portable.

   Status: Done.

   What changed: workspace and project manifests now store paths relative to their owning directory and resolve them on load.

7. Workspace writes are not protected from concurrent requests.

   Status: Done.

   What changed: workspace mutations are now protected by a process-local lock in the FastAPI app, and manifests are written atomically.

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

8. `python-multipart` and `httpx2` dependencies should be reviewed.

   Status: Open.

   Current note: no direct imports were found. `httpx2` is especially surprising. Remove both if they are not required by indirect FastAPI/test behavior.

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

  Status: Open.

   Current behavior: row/column/parameter information is encoded mostly in labels, and refined candidates are appended to the same flat list.

   Suggested fix: store `row`, `col`, `generation`, `parent_candidate_id`, and search-space bounds explicitly. Then the UI can render refined searches as separate grids.

5. Long-running work is synchronous.

   Status: Open.

   Current behavior: grid init and refine block while candidates are generated.

   Suggested fix: add jobs:

   - `POST /api/workspace/refine` returns a job ID.
   - `GET /api/jobs/{id}` returns progress.
   - UI shows determinate progress when possible.

## Performance Issues and Recommendations

1. Avoid hydrating every candidate SVG as live DOM.

  Status: Open.

   Current state: Compose still injects SVG for kept candidates so regions can be clicked. This is workable for modest region counts but will degrade with many regions.

   Suggested fix: render previews with Canvas and use a hitmap for selection. Serve labels as a compressed PNG or binary array where each pixel maps to a region ID.

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

   Status: Partial.

   What changed: cancellation/request versioning is implemented.

   Remaining work: debounce slider input.

6. Avoid computing PNG and SVG for every preview update.

   Status: Done.

   What changed: `/api/workspace/composite/summary` returns path counts without serializing full SVG for the UI.

7. Cache loaded projects during a request or app session.

   Status: Open.

   Current behavior: composite rendering still loads candidate projects from disk repeatedly.

   Suggested fix: load each candidate project once per composite render and pass that cache through preview, summary, and SVG generation. Consider an app-session LRU cache keyed by candidate ID and project mtime.

8. Generate thumbnails for gallery browsing.

   Status: Done.

   What changed: the workspace now generates `thumb.png` for each candidate, and the gallery grid/kept strip use those thumbnails.

9. Move heavy candidate generation and refinement to jobs.

   Status: Open.

   Current behavior: refine is a blocking POST that generates nine candidates before returning.

10. Consider Canvas for interactive editing and SVG only for final export.

   Status: Open.

   Best direction: use Canvas or WebGL for viewing, hit-testing, hover, and painting. Keep SVG as the export format and possibly as a static preview overlay.

## Performance Priority List

1. Stop rebuilding the whole Compose palette after every selection.
2. Cache candidate project loads on the backend.
3. Move interactive selection to Canvas plus hitmap.
4. Move candidate generation/refinement into background jobs.
5. Add explicit cache invalidation keyed by candidate generation.

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

7. Add packing integration only after final-region semantics are stable.

   Nesting should operate on final SVG groups by veneer, not on transient candidate regions.

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

1. Stop full Compose rerenders after each region click.
2. Add Playwright coverage for Compose and Merge.
3. Review dependencies and remove `httpx2`/`python-multipart` if not intentional.
4. Cache loaded candidate projects during composite rendering.
5. Add explicit persisted composite assignment state.
6. Add veneer palette groups and final fabrication exports.
7. Move candidate generation/refinement into background jobs with progress.
