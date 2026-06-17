"""Command-line interface for marqflow."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from .config import SegmentationConfig, SuperpixelConfig
from .pipeline import build_region_map, build_superpixel_preview, write_pipeline_outputs
from .project import MarqflowProject
from .svg import region_map_to_svg

app = typer.Typer(add_completion=False, help='Prepare and edit marquetry-friendly region maps.')


def _build_config(
    downscale_factor: int,
    target_segments: int,
    compactness: float,
    sigma: float,
) -> SegmentationConfig:
    return SegmentationConfig(
        downscale_factor=downscale_factor,
        superpixels=SuperpixelConfig(
            target_segments=target_segments,
            compactness=compactness,
            sigma=sigma,
        ),
    )


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
    """Write a one-shot preview and SVG from an image."""

    config = _build_config(downscale_factor, target_segments, compactness, sigma)
    region_map = write_pipeline_outputs(input_path, output_dir, config)

    typer.echo(f'input: {input_path}')
    typer.echo(f'output: {output_dir}')
    typer.echo(f'size: {region_map.size[0]}x{region_map.size[1]}')
    typer.echo(f'regions: {len(region_map.regions)}')
    typer.echo(f'svg: {output_dir / "regions.svg"}')
    typer.echo(f'preview: {output_dir / "preview.png"}')


@app.command()
def init(
    input_path: Annotated[Path, typer.Argument(..., exists=True, readable=True)],
    project_dir: Annotated[Path, typer.Argument(...)],
    downscale_factor: int = typer.Option(
        4, help='Integer resize factor applied before segmentation.'
    ),
    target_segments: int = typer.Option(20, help='Approximate number of coarse regions.'),
    compactness: float = typer.Option(20.0, help='Higher values prefer more even superpixels.'),
    sigma: float = typer.Option(1.0, help='Pre-smoothing before superpixel segmentation.'),
) -> None:
    """Create an editable project directory."""

    config = _build_config(downscale_factor, target_segments, compactness, sigma)
    project = MarqflowProject.create(input_path, project_dir, config)
    preview_path, svg_path = project.export(project_dir)

    typer.echo(f'project: {project.project_dir}')
    typer.echo(f'size: {project.region_map.size[0]}x{project.region_map.size[1]}')
    typer.echo(f'regions: {len(project.region_map.regions)}')
    typer.echo(f'preview: {preview_path}')
    typer.echo(f'svg: {svg_path}')


@app.command()
def export(
    project_dir: Annotated[Path, typer.Argument(..., exists=True, readable=True)],
    output_dir: Annotated[Path, typer.Argument(...)],
) -> None:
    """Export preview and SVG artifacts from a saved project."""

    project = MarqflowProject.load(project_dir)
    preview_path, svg_path = project.export(output_dir)
    typer.echo(f'preview: {preview_path}')
    typer.echo(f'svg: {svg_path}')


@app.command()
def split(
    project_dir: Annotated[Path, typer.Argument(..., exists=True, readable=True)],
    region_ids: Annotated[list[int], typer.Argument(...)],
    segments: int = typer.Option(
        4, help='Target number of subregions inside each selected region.'
    ),
    compactness: float | None = typer.Option(
        None, help='Override the local superpixel compactness.'
    ),
    sigma: float | None = typer.Option(None, help='Override the local superpixel blur.'),
) -> None:
    """Refine one or more regions in a project."""

    project = MarqflowProject.load(project_dir)
    changed = project.split_regions(region_ids, segments, compactness=compactness, sigma=sigma)
    typer.echo(f'split_groups: {changed}')
    typer.echo(f'regions: {len(project.region_map.regions)}')


@app.command()
def merge(
    project_dir: Annotated[Path, typer.Argument(..., exists=True, readable=True)],
    region_ids: Annotated[list[int], typer.Argument(...)],
) -> None:
    """Merge connected selected regions in a project."""

    project = MarqflowProject.load(project_dir)
    merged = project.merge_regions(region_ids)
    typer.echo(f'merged_groups: {merged}')
    typer.echo(f'regions: {len(project.region_map.regions)}')


@app.command()
def regions(
    project_dir: Annotated[Path, typer.Argument(..., exists=True, readable=True)],
) -> None:
    """Print a compact list of region metadata."""

    project = MarqflowProject.load(project_dir)
    for region in sorted(project.region_map.regions, key=lambda item: item.region_id):
        neighbors = ','.join(str(value) for value in region.neighbors) or '-'
        typer.echo(
            f'{region.region_id:>4}  area={region.area:>6}  fill={region.fill}  '
            f'neighbors={neighbors}'
        )


@app.command()
def summary(
    input_path: Annotated[Path, typer.Argument(..., exists=True, readable=True)],
    downscale_factor: int = typer.Option(4),
    target_segments: int = typer.Option(20),
    compactness: float = typer.Option(20.0),
    sigma: float = typer.Option(1.0),
) -> None:
    """Print a small summary for a candidate region map."""

    config = _build_config(downscale_factor, target_segments, compactness, sigma)
    region_map = build_region_map(input_path, config)
    preview = build_superpixel_preview(region_map)
    svg = region_map_to_svg(region_map)

    typer.echo(f'size: {region_map.size[0]}x{region_map.size[1]}')
    typer.echo(f'regions: {len(region_map.regions)}')
    typer.echo(f'preview_shape: {preview.shape[1]}x{preview.shape[0]}')
    typer.echo(f'svg_paths: {svg.count("<path")}')
