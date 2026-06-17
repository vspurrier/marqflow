"""Command-line interface for marqflow."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from .config import SegmentationConfig, SuperpixelConfig
from .pipeline import build_region_map, build_superpixel_preview, write_pipeline_outputs
from .svg import region_map_to_svg

app = typer.Typer(add_completion=False, help='Prepare marquetry-friendly region maps.')


@app.command()
def prepare(
    input_path: Annotated[Path, typer.Argument(..., exists=True, readable=True)],
    output_dir: Annotated[Path, typer.Argument(...)],
    downscale_factor: int = typer.Option(
        4, help='Integer resize factor applied before segmentation.'
    ),
    target_segments: int = typer.Option(20, help='Approximate number of coarse regions.'),
    compactness: float = typer.Option(20.0, help='Higher values prefer more even superpixels.'),
    sigma: float = typer.Option(1.0, help='Pre-smoothing before superpixel segmentation.'),
) -> None:
    """Create a downscaled preview, SVG outline, and region graph."""

    config = SegmentationConfig(
        downscale_factor=downscale_factor,
        superpixels=SuperpixelConfig(
            target_segments=target_segments,
            compactness=compactness,
            sigma=sigma,
        ),
    )
    region_map = write_pipeline_outputs(input_path, output_dir, config)

    typer.echo(f'input: {input_path}')
    typer.echo(f'output: {output_dir}')
    typer.echo(f'size: {region_map.size[0]}x{region_map.size[1]}')
    typer.echo(f'regions: {len(region_map.regions)}')
    typer.echo(f'svg: {output_dir / "regions.svg"}')
    typer.echo(f'preview: {output_dir / "preview.png"}')


@app.command()
def summary(
    input_path: Annotated[Path, typer.Argument(..., exists=True, readable=True)],
    downscale_factor: int = typer.Option(4),
    target_segments: int = typer.Option(20),
    compactness: float = typer.Option(20.0),
    sigma: float = typer.Option(1.0),
) -> None:
    """Print a small summary for a candidate region map."""

    config = SegmentationConfig(
        downscale_factor=downscale_factor,
        superpixels=SuperpixelConfig(
            target_segments=target_segments,
            compactness=compactness,
            sigma=sigma,
        ),
    )
    region_map = build_region_map(input_path, config)
    preview = build_superpixel_preview(region_map)
    svg = region_map_to_svg(region_map)

    typer.echo(f'size: {region_map.size[0]}x{region_map.size[1]}')
    typer.echo(f'regions: {len(region_map.regions)}')
    typer.echo(f'preview_shape: {preview.shape[1]}x{preview.shape[0]}')
    typer.echo(f'svg_paths: {svg.count("<path")}')


if __name__ == '__main__':
    app()
