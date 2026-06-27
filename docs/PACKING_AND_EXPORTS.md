# Packing And Exports

Marqflow exports physical geometry from the final `MarquetryDesign`, not from
temporary candidate images.

## SVG Exports

`design.svg` contains one path per final region, grouped by veneer. Dimensions
use the physical size configured in the design.

`design-coverage.svg` uses Shapely coverage simplification so shared edges stay
coherent during simplification.

Use the coverage-safe SVG when you intend to cut adjacent pieces from the same
linework.

## Pack Manifest

`pack.json` groups pieces by veneer and includes:

- original physical contour
- original physical SVG path
- packed sheet placement
- transformed placed contour
- transformed placed SVG path
- stock shortfall and utilization estimates

The current backend is `shapely-polygon-shelf-rotating`.

It is contour-aware:

- Places true piece polygons, not only abstract rectangles.
- Collision-checks placed polygons.
- Tries rotated orientations when grain settings allow.
- Preserves per-veneer grouping.

It is not yet a full irregular nesting optimizer:

- It does not exploit concavities.
- It does not perform deep no-fit-polygon search.
- It does not globally optimize waste across all sheets.

## Grain And Rotation

Veneer grain notes affect rotation:

- Include `fixed`, `locked`, `no-rotate`, or `no rotate` to prevent rotation.
- Include `vertical` or `horizontal` to allow only `0` and `180` degree
  orientations.
- Leave grain unconstrained to allow `0`, `90`, `180`, and `270` degree
  orientations.

## Why Not Let A Library Do All Nesting?

That is the right long-term direction. The current packer is deliberately an
adapter-shaped baseline: it converts Marqflow's validated physical contours,
veneer groupings, grain constraints, and output manifest into data that an
external irregular nesting package can consume.

The remaining work is not inventing nesting theory. It is integrating a
maintained nesting package behind this manifest boundary and preserving
Marqflow-specific constraints.

