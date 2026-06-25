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
- one-off candidate generation
- candidate grid generation as a source-stage search tool
- durable design partition
- editable final physical dimensions
- veneer assignments
- editable veneer inventory with stock fields
- manual connected-region merge
- undo for veneer assignment and region merge edits
- same-veneer-preferred merge suggestions for small/thin regions
- final label hitmap API for browser selection tooling
- partition validation
- physical-unit SVG export
- simple pack manifest
- minimal browser UI

## Next Milestones

1. Add browser hitmap interaction.

   The API exposes the final label map. The UI still needs click/drag region
   selection on the final design instead of list-only controls.

2. Add subject/detail masks for eyes/nose or user-selected focus zones.

   The candidate generator is still global. Marquetry portraits need local
   detail budgets so eyes, nose, mouth, and other focal areas can preserve more
   structure than background or clothing.

3. Add shared-boundary geometry before advanced smoothing.

   The raster partition is valid, but independently extracted vector contours
   are not yet a robust planar graph. Advanced smoothing, point editing, and
   no-gap/no-overlap SVG cleanup should be built on shared edges.

4. Add cleanup operations on top of shared boundaries.

   Needed operations: simplify shared edges, smooth selected boundaries, repair
   slivers, lock regions, split selected regions, and edit vertices.

5. Deepen veneer inventory logic.

   Veneer replacement and stock fields now exist. The workflow still needs a
   polished swatch editor, grain direction review, texture/photo swatches, and
   clearer purchasing/overage warnings.

6. Add a packing adapter for an actual irregular nesting backend.

   Current packing writes a grouped manifest plus SVG. The adapter should take
   validated physical paths by veneer and return sheet placements.

7. Convert browser JS to TypeScript modules once the API stabilizes.

   The current browser code uses `checkJs` and declarations. A module split
   becomes worthwhile after the core workflow stops shifting.

8. Add browser-level regression tests.

   API/core tests cover the model. Browser tests should cover image open,
   candidate-grid selection, veneer assignment, merge, undo, SVG preview, and
   pack export once the UI surface is stable.

## Non-Goals For This Branch

- Do not port the old tabbed prototype wholesale.
- Do not let candidate selections become the final design state.
- Do not add packing before final geometry is validated.
