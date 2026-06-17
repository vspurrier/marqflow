# Marqflow

Marqflow is a Python tool for planning marquetry from a raster image.

The current workflow is gallery-first:

1. Load a source image into a workspace.
2. Generate a grid of candidate region maps by varying segmentation parameters.
3. Keep the candidates that look promising.
4. Select regions from kept candidates and export a combined composite.

The core pipeline still does the same underlying work:

- downscale the source image to a working resolution
- build a superpixel region map with `scikit-image`
- export a flat-color preview and an SVG of region contours

## Install

```bash
uv sync
```

## Gallery Workflow

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

The gallery UI is built around a search grid:

- rows move toward more regions
- columns move toward smoother, more regular regions
- click a tile to open it in the viewer
- keep the tiles you want to carry forward
- box-select regions in one or more kept tiles
- export a combined PNG and SVG at the end

## Useful Utility Commands

Preview a single segmentation without creating a workspace:

```bash
uv run marqflow prepare ~/code/bennett.jpg ./out
```

Print a quick summary for a source image:

```bash
uv run marqflow summary ~/code/bennett.jpg
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

Images are auto-oriented with EXIF metadata applied when loaded.
