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

Marqflow prefers `libnest2d-djd` when the optional native bindings are
installed. Otherwise it uses `shapely-polygon-shelf-rotating`.

It is contour-aware:

- Places true piece polygons, not only abstract rectangles.
- Collision-checks placed polygons.
- Tries rotated orientations when grain settings allow.
- Preserves per-veneer grouping.

Install the external backend on supported platforms with:

```bash
uv sync --extra nesting
```

`python-libnest2d` currently publishes wheels for Linux and Windows. On macOS,
Marqflow falls back automatically.

The Shapely fallback is not a full irregular nesting optimizer:

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

Marqflow now has a libnest2d adapter. The in-repo Shapely backend remains as a
portable fallback and as a deterministic reference implementation for tests.
