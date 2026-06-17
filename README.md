# Marqflow

Marqflow is an early-stage Python pipeline for turning a source image into a
small, editable region graph for marquetry planning.

The current pipeline does three things:

1. Downscales the source image to a working resolution.
2. Builds a superpixel region map with `scikit-image`.
3. Exports a flat-color preview and an SVG containing the region contours.

This is the foundation for manual region refinement:

- split a selected region into smaller regions
- merge a selected set of regions
- preserve a stable graph of region adjacency for later editing

## Install

```bash
uv sync
```

## Run

Prepare outputs for an image:

```bash
uv run marqflow prepare ~/code/bennett_16x.jpg ./out
```

Inspect the summary without writing files:

```bash
uv run marqflow summary ~/code/bennett_16x.jpg
```

## Output

The `prepare` command writes:

- `preview.png`
- `regions.svg`

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

## Project Workflow

Create an editable project:

```bash
uv run marqflow init ~/code/bennett_16x.jpg ./demo-project
```

List the current regions:

```bash
uv run marqflow regions ./demo-project
```

Refine selected regions:

```bash
uv run marqflow split ./demo-project 1 2 --segments 4
```

Merge selected regions:

```bash
uv run marqflow merge ./demo-project 3 4
```

Export the current SVG and preview:

```bash
uv run marqflow export ./demo-project ./exported
```
