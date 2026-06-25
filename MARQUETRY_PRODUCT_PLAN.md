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
- one candidate generator
- durable design partition
- veneer assignments
- partition validation
- physical-unit SVG export
- simple pack manifest
- minimal browser UI

## Next Milestones

1. Add region merge and undo in `MarquetryDesign`.
2. Add candidate grid generation as a source stage, not as design state.
3. Add final-region hitmap selection to the new browser UI.
4. Add same-veneer merge suggestions for small/thin regions.
5. Add subject/detail masks for eyes/nose or user-selected focus zones.
6. Add shared-boundary geometry before advanced smoothing.
7. Add a packing adapter for an actual irregular nesting backend.
8. Convert browser JS to TypeScript modules once the API stabilizes.

## Non-Goals For This Branch

- Do not port the old tabbed prototype wholesale.
- Do not let candidate selections become the final design state.
- Do not add packing before final geometry is validated.
