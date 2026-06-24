# Marqflow

Marqflow is a Python tool for planning marquetry from raster images.

The workflow is deliberately gallery-first:

1. Start with a source image.
2. Set the final size and subject priorities.
3. Generate a grid of segmentation candidates.
4. Keep the candidates that are worth carrying forward.
5. Assign hues and final regions from the kept candidates.
6. Clean up the partition and review small-piece warnings.
7. Pack the final pieces by veneer.

The core pipeline still does the same underlying work:

- downscale the source image to a working resolution
- build a superpixel region map with `scikit-image`
- export a flat-color preview and SVG contours for each candidate

## Install

```bash
uv sync
```

## Browser Workflow

The browser UI is organized around marquetry decisions:

- `Image`: choose or replace the source image.
- `Size`: set the final physical dimensions.
- `Subject`: mark the detail budget and priority areas.
- `Shapes`: browse the candidate grid, open candidates, and keep the ones worth using.
- `Hues`: paint regions from kept candidates into a working canvas.
- `Cleanup`: preview the final partition, merge selected regions, and split selected regions.
- `Pack`: export a veneer-aware packing plan.

Typical flow:

1. Create a workspace from an image.
2. Set the final physical size and subject priorities.
3. Use `Shapes` to find a good starting set of candidates.
4. Use `Hues` to paint regions from kept candidates into the working canvas.
5. Use `Cleanup` to preview the final partition, merge selected regions, or split a region.
6. Use `Pack` to write a veneer-aware packing plan once the piece breakdown looks right.

Create a workspace from an image:

```bash
uv run marqflow grid-init ~/code/bennett.jpg ./bennett-workspace
```

Launch the browser UI:

```bash
uv run marqflow grid-serve
```

Export the combined composite after selecting regions:

```bash
uv run marqflow grid-export ./bennett-workspace ./exported
```

Workspace lifecycle:

- The browser opens to a blank landing screen until you choose an image.
- Use `Open image` in the browser to create a workspace from the selected file.
- The browser API reloads workspace state from disk on each request, so a page refresh is enough to pick up saved changes.
- Use `Reset workspace` in the browser to delete generated candidates and selections, then rebuild a clean starting grid from the copied source image.
- Use `grid-init` only when you want a brand new workspace directory from the command line.

### Shapes Tab

The shapes grid is a parameter sweep over segmentation settings:

- rows move toward more regions
- columns move from coarser, smoother candidates on the left to more detailed ones on the right
- click a tile to open it in the viewer
- keep tiles you want to carry forward into compose

### Hues Tab

Hues is a two-column workspace:

- edit the veneer inventory before assigning materials, including approximate color, stock size, grain direction, and notes
- the left side is the kept-candidate palette
- the right side is the composite canvas
- click regions in the palette to paint them onto the canvas
- use `Paint all` when a kept candidate should be copied wholesale

### Cleanup Tab

Cleanup is a final review stage:

- it previews the composite before final export
- the threshold slider controls how aggressively similar colors are grouped
- small/thin/geometry warnings are highlighted on the canvas and in the region list
- use Merge selected and Split selected to adjust the final partition
- use Merge suggestions to apply the current small/thin-piece cleanup suggestions in one pass
- the final `Pack final` action writes a veneer-aware packing plan next to the export directory

### Pack Tab

Pack is the final export stage:

- it writes a veneer-aware packing plan
- it uses the current physical size and final partition state
- it uses per-veneer stock dimensions when those are set in the Hues inventory
- the export directory is shown in the top-level controls

By default, packing uses `rectpack` to place each final piece's bounding box
while preserving the actual contour path in the output SVG. This is reliable
and traceable, but it is not true irregular nesting.

For SVGnest/Deepnest-style irregular nesting, configure an external runner:

```bash
export MARQFLOW_NESTER_CMD='/path/to/nester --input {input} --output {output}'
uv run marqflow grid-serve
```

Marqflow writes one SVGnest-compatible input SVG per veneer, calls the command,
and stores both the nested sheet SVG and the input SVG in the pack output. The
runner must write the nested SVG to `{output}`.

## Useful Utility Commands

Preview a single segmentation without creating a workspace:

```bash
uv run marqflow prepare ~/code/bennett.jpg ./out
```

Print a quick summary for a source image:

```bash
uv run marqflow summary ~/code/bennett.jpg
```

Inspect regions in an existing project:

```bash
uv run marqflow regions ./project-dir
```

## Development

Run tests:

```bash
uv run pytest
```

Format and lint:

```bash
uv run ruff format .
uv run ruff check .
```

## Notes

- Images are auto-oriented with EXIF metadata applied when loaded.
- The browser UI currently serves from `http://127.0.0.1:8000/` when started with the default command shown above.
- The default grid is intentionally broad; use `grid-init` only when you want a fresh workspace.
