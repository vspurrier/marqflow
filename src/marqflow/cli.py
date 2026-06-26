"""Command-line interface for the marquetry-first rewrite."""

from __future__ import annotations

import threading
import time
import webbrowser
from pathlib import Path
from typing import Annotated

import typer
import uvicorn

from .gallery_web import create_app
from .models import PhysicalSize
from .workspace import MarquetryWorkspace

app = typer.Typer(add_completion=False, help='Plan marquetry designs from source images.')


@app.command()
def init(
    input_path: Annotated[Path, typer.Argument(..., exists=True, readable=True)],
    workspace_dir: Annotated[Path, typer.Argument(...)],
    target_regions: int = typer.Option(80, help='Approximate starting region count.'),
    compactness: float = typer.Option(18.0, help='Higher values produce more regular shapes.'),
    width: float = typer.Option(8.0, help='Finished physical width.'),
    height: float = typer.Option(10.0, help='Finished physical height.'),
    unit: str = typer.Option('in', help='Physical unit label.'),
) -> None:
    """Create a workspace, one candidate, and a seeded marquetry design."""

    workspace = MarquetryWorkspace.create(input_path, workspace_dir)
    candidate = workspace.generate_candidate(target_regions=target_regions, compactness=compactness)
    workspace.create_design(
        candidate.candidate_id,
        PhysicalSize(width=width, height=height, unit=unit),
    )
    typer.echo(f'workspace: {workspace.workspace_dir}')
    typer.echo(f'candidate: {candidate.candidate_id} ({candidate.region_count} regions)')
    typer.echo(f'valid: {workspace.validation()["valid"]}')


@app.command()
def export(
    workspace_dir: Annotated[Path, typer.Argument(..., exists=True, readable=True)],
    output_svg: Annotated[Path, typer.Argument(...)],
    simplify_tolerance: float = typer.Option(
        1.0,
        help='SVG contour simplification tolerance in working-image pixels.',
    ),
) -> None:
    """Export the current design as veneer-grouped SVG."""

    workspace = MarquetryWorkspace.load(workspace_dir)
    path = workspace.export_svg(output_svg, simplify_tolerance=simplify_tolerance)
    typer.echo(f'svg: {path}')


@app.command()
def pack(
    workspace_dir: Annotated[Path, typer.Argument(..., exists=True, readable=True)],
    output_dir: Annotated[Path, typer.Argument(...)],
) -> None:
    """Write veneer-grouped packing and cleanup manifests."""

    workspace = MarquetryWorkspace.load(workspace_dir)
    manifest = workspace.pack(output_dir)
    typer.echo(f'sheets: {len(manifest["sheets"])}')
    typer.echo(f'pack: {output_dir / "pack.json"}')
    typer.echo(f'report: {output_dir / "cleanup-report.json"}')


@app.command()
def report(
    workspace_dir: Annotated[Path, typer.Argument(..., exists=True, readable=True)],
    output_json: Annotated[Path, typer.Argument(...)],
) -> None:
    """Write the cut-readiness cleanup report without packing."""

    workspace = MarquetryWorkspace.load(workspace_dir)
    path = workspace.export_cleanup_report(output_json)
    typer.echo(f'report: {path}')


@app.command()
def serve(
    workspace_dir: Annotated[Path | None, typer.Argument()] = None,
    host: str = typer.Option('127.0.0.1', help='Host to bind.'),
    port: int = typer.Option(8000, help='Port to bind.'),
    open_browser: bool = typer.Option(True, '--open-browser/--no-open-browser'),
) -> None:
    """Serve the browser UI."""

    config = uvicorn.Config(create_app(workspace_dir), host=host, port=port, log_level='info')
    server = uvicorn.Server(config)
    if open_browser:
        url = f'http://{host}:{port}/'
        threading.Thread(
            target=lambda: (time.sleep(0.8), webbrowser.open(url)),
            daemon=True,
        ).start()
    server.run()


if __name__ == '__main__':
    app()
