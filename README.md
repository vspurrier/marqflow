# Marqflow

Marqflow is a Python tool for planning marquetry from raster images.

The workflow is deliberately gallery-first:

1. Start with a source image.
2. Generate a grid of segmentation candidates.
3. Keep the candidates that are worth carrying forward.
4. Paint regions from the kept candidates into a composite.
5. Merge visually similar regions into final wood-piece groups.
6. Export PNG and SVG outputs for packing and stencil work.

The core pipeline still does the same underlying work:

- downscale the source image to a working resolution
- build a superpixel region map with `scikit-image`
- export a flat-color preview and SVG contours for each candidate

## Install

```bash
uv sync
```

## Browser Workflow

The browser UI has three top-level tabs:

- `Search`: browse the candidate grid, open candidates, and keep the ones worth using.
- `Compose`: paint regions from kept candidates into a composite canvas.
- `Merge`: preview how similar colors will be merged before the final export.

Typical flow:

1. Create a workspace from an image.
2. Use `Search` to find a good starting set of candidates.
3. Use `Compose` to paint regions from kept candidates into the working canvas.
4. Use `Merge` to preview the final shape grouping and merge threshold.
5. Export the final composite once the piece breakdown looks right.

Create a workspace from an image:

```bash
uv run marqflow grid-init ~/code/bennett.jpg ./bennett-workspace
```

Launch the browser UI:

```bash
uv run marqflow grid-serve ./bennett-workspace
```

Export the combined composite after selecting regions:

```bash
uv run marqflow grid-export ./bennett-workspace ./exported
```

### Search Tab

The search grid is a parameter sweep over segmentation settings:

- rows move toward more regions
- columns move toward smoother, more regular regions
- click a tile to open it in the viewer
- keep tiles you want to carry forward into compose

### Compose Tab

Compose is a two-column workspace:

- the left side is the kept-candidate palette
- the right side is the composite canvas
- click regions in the palette to paint them onto the canvas
- use `Paint all` when a kept candidate should be copied wholesale

### Merge Tab

Merge is a final review stage:

- it previews the composite before final export
- the threshold slider controls how aggressively similar colors are grouped
- use it to reduce the number of wood pieces before packing

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
