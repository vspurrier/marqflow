# Marqflow User Guide

Marqflow turns a source image into a measured marquetry design: a set of
non-overlapping puzzle pieces, each assigned to a veneer, with SVG and packing
exports.

## 1. Start With A Source Image

Use a cropped image where the subject is already prominent. The browser lets
you cap the working image size with **Max working edge**. For interactive work,
start around `512` to `768` pixels. Use higher values only after the workflow
is behaving well.

Good source images:

- Have clear contrast between major subject areas.
- Are cropped to the final composition.
- Avoid unnecessary background detail.
- Preserve important small features, such as eyes, before downscaling.

## 2. Generate Candidate Regions

Use **Generate candidate grid** to compare several region counts and
compactness settings.

Interpret the grid this way:

- Fewer regions are easier to cut but lose detail.
- More regions preserve more detail but can become impractical.
- Lower compactness follows image texture more closely.
- Higher compactness tends toward simpler, rounder regions.

Choose a candidate that is close enough to edit. It does not need to be final.

## 3. Set Physical Size Early

Set width, height, and unit before evaluating cuttability. Region warnings,
small-piece repair, packing, and SVG export all depend on physical scale.

## 4. Mark Subject, Background, And Detail

Use selection tools to mark important parts of the image:

- **Mark subject** for areas that should remain visually coherent.
- **Mark background** for areas that can be simplified.
- **Make focus zone** for important local detail such as eyes.
- **Apply focus detail** to split selected focus areas.

The subject/background mask can guide later candidate generation.

## 5. Assign Veneers

Every region gets one veneer. The automatic assignment is only a starting
point. Use the veneer palette to define stock, color, grain notes, and optional
texture URLs.

Practical approach:

- Assign broad color families first.
- Merge tiny same-veneer regions where possible.
- Avoid assigning several similar hues unless you really have those veneers.

## 6. Clean Up The Puzzle

The design must remain a full puzzle: no overlaps, no gaps, and every region
assigned.

Useful cleanup actions:

- **Auto-merge small pieces** applies suggested merges.
- **Repair small pieces** merges regions below the selected physical area.
- **Remove notches** targets tiny jagged protrusions.
- **Smooth boundaries** denoises raster boundary pixels.
- **Simplify selected boundaries** reduces vector vertices near selected
  regions.
- **Smooth selected vector edges** smooths explicit graph edges selected in
  vector mode.

Use **Cleanup report** before export to review readiness, warnings, and jagged
boundary candidates.

## 7. Vector Editing

Set selection mode to **Vector handles**.

- Drag a vertex to preview a topology-safe move.
- Use **Accept preview** to save it.
- Click an edge to select it.
- Shift-click an edge when dense vertices make ordinary edge selection
  ambiguous.
- Use **Smooth selected vector edges** for local line cleanup.
- Use **Preview simplify** before applying larger simplification passes.

Vector edits are validated before saving so the exported design remains a
non-overlapping puzzle.

## 8. Export And Pack

Use:

- **Open SVG** for the current physical-unit design.
- **Open coverage-safe SVG** for shared-edge-safe simplification.
- **Pack manifest** for veneer-grouped physical contour placement.

The pack manifest is a planning aid, not a final industrial nesting optimizer.
It emits physical contours and placed contours that can be traced or adapted to
more advanced nesting tools.

## Recommended First Pass

1. Open image with max edge `512` or `768`.
2. Generate a `4 x 4` candidate grid.
3. Pick a candidate with the fewest acceptable pieces.
4. Set final physical dimensions.
5. Assign veneers broadly.
6. Merge or repair pieces that are physically too small.
7. Preserve important detail with focus zones and vector cleanup.
8. Run cleanup report.
9. Export SVG and pack manifest.
