"""Command-line interface for marqflow."""

from __future__ import annotations

import threading
import time
import webbrowser
from pathlib import Path
from typing import Annotated

import typer
import uvicorn

from .config import SegmentationConfig, SuperpixelConfig
from .gallery_web import create_app as create_gallery_app
from .pipeline import build_region_map, build_superpixel_preview, write_pipeline_outputs
from .project import MarqflowProject
from .svg import region_map_to_svg
from .workspace import GridWorkspace

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
        1, help='Integer resize factor applied before segmentation.'
    ),
    target_segments: int = typer.Option(96, help='Approximate number of coarse regions.'),
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
        1, help='Integer resize factor applied before segmentation.'
    ),
    target_segments: int = typer.Option(96, help='Approximate number of coarse regions.'),
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
def serve(
    workspace_dir: Annotated[Path | None, typer.Argument()] = None,
    host: str = typer.Option('127.0.0.1', help='Host to bind the browser server to.'),
    port: int = typer.Option(8000, help='Port to bind the browser server to.'),
    open_browser: bool = typer.Option(
        True,
        '--open-browser/--no-open-browser',
        help='Open the browser automatically.',
    ),
) -> None:
    """Serve the browser UI for a grid-search workspace."""

    _serve_workspace_ui(workspace_dir, host=host, port=port, open_browser=open_browser)


@app.command()
def summary(
    input_path: Annotated[Path, typer.Argument(..., exists=True, readable=True)],
    downscale_factor: int = typer.Option(1),
    target_segments: int = typer.Option(96),
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


@app.command('grid-init')
def grid_init(
    input_path: Annotated[Path, typer.Argument(..., exists=True, readable=True)],
    workspace_dir: Annotated[Path, typer.Argument(...)],
) -> None:
    """Create a grid-search workspace with a preset gallery."""

    workspace = GridWorkspace.create(input_path, workspace_dir)
    typer.echo(f'workspace: {workspace.workspace_dir}')
    typer.echo(f'source: {workspace.source_image_path}')
    typer.echo(f'candidates: {len(workspace.candidates)}')
    typer.echo(f'active: {workspace.active_candidate_id}')


@app.command('grid-export')
def grid_export(
    workspace_dir: Annotated[Path, typer.Argument(..., exists=True, readable=True)],
    output_dir: Annotated[Path, typer.Argument(...)],
) -> None:
    """Export a composite preview and SVG from the kept gallery selections."""

    workspace = GridWorkspace.load(workspace_dir)
    composite_png, composite_svg = workspace.export_composite(output_dir)
    typer.echo(f'composite_png: {composite_png}')
    typer.echo(f'composite_svg: {composite_svg}')


@app.command('grid-serve')
def grid_serve(
    workspace_dir: Annotated[Path | None, typer.Argument()] = None,
    host: str = typer.Option('127.0.0.1', help='Host to bind the browser server to.'),
    port: int = typer.Option(8000, help='Port to bind the browser server to.'),
    open_browser: bool = typer.Option(
        True,
        '--open-browser/--no-open-browser',
        help='Open the browser automatically.',
    ),
) -> None:
    """Serve the browser UI for a grid-search workspace."""

    _serve_workspace_ui(workspace_dir, host=host, port=port, open_browser=open_browser)


def _serve_workspace_ui(
    workspace_dir: Path | None,
    *,
    host: str,
    port: int,
    open_browser: bool,
) -> None:
    """Serve the browser UI for a workspace."""

    app_obj = create_gallery_app(workspace_dir)
    url = f'http://{host}:{port}'

    if open_browser:

        def _open() -> None:
            time.sleep(0.5)
            webbrowser.open(url)

        threading.Thread(target=_open, daemon=True).start()

    uvicorn.run(app_obj, host=host, port=port, log_level='info')
