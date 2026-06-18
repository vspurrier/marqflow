# ruff: noqa: E501
"""Browser UI for grid-search marquetry workspaces.

The UI is intentionally compact: `Search` finds candidates, `Compose` paints
regions from kept candidates into a composite, and `Merge` previews the final
color grouping before export.
"""

from __future__ import annotations

import threading
from io import BytesIO
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .workspace import GridWorkspace


class CandidateSelectionRequest(BaseModel):
    candidate_id: str
    region_ids: list[int] = Field(default_factory=list)
    additive: bool = False


class CandidateRequest(BaseModel):
    candidate_id: str


class ExportRequest(BaseModel):
    output_dir: str = './exported'
    merge_threshold: float = 0.0


def _load_workspace(workspace_dir: Path) -> GridWorkspace:
    try:
        return GridWorkspace.load(workspace_dir)
    except FileNotFoundError as exc:  # pragma: no cover - defensive guard
        raise HTTPException(status_code=404, detail='workspace not found') from exc


def _workspace_summary(workspace: GridWorkspace) -> dict[str, object]:
    summary = workspace.summary()
    candidates: list[dict[str, object]] = []
    for candidate in summary['candidates']:
        candidates.append(_candidate_payload(candidate))
    summary['candidates'] = candidates
    active = summary.get('active_candidate')
    if isinstance(active, dict):
        summary['active_candidate'] = _candidate_payload(active)
    return summary


def _candidate_summary(workspace: GridWorkspace, candidate_id: str) -> dict[str, object]:
    summary = workspace.candidate_summary(candidate_id)
    if summary is None:
        raise HTTPException(status_code=404, detail='candidate not found')
    return _candidate_payload(summary)


def _candidate_payload(candidate: dict[str, object]) -> dict[str, object]:
    candidate = dict(candidate)
    candidate_id = str(candidate['candidate_id'])
    candidate['preview_url'] = f'/api/workspace/candidates/{candidate_id}/preview'
    candidate['thumb_url'] = f'/api/workspace/candidates/{candidate_id}/thumb'
    candidate['svg_url'] = f'/api/workspace/candidates/{candidate_id}/svg'
    return candidate


def _png_response(image_array) -> Response:
    from PIL import Image

    buffer = BytesIO()
    Image.fromarray(image_array.astype('uint8'), mode='RGB').save(buffer, format='PNG')
    return Response(content=buffer.getvalue(), media_type='image/png')


STATIC_DIR = Path(__file__).with_name('static')


def _html_page() -> str:
    """Load the gallery shell from the packaged static files."""

    return (STATIC_DIR / 'gallery.html').read_text(encoding='utf-8')


def create_app(workspace_dir: str | Path) -> FastAPI:
    """Build the FastAPI app that serves the gallery UI and JSON endpoints."""

    workspace_path = Path(workspace_dir)
    workspace_lock = threading.RLock()
    app = FastAPI(title='Marqflow Gallery')
    app.state.workspace_dir = workspace_path
    app.mount('/static', StaticFiles(directory=STATIC_DIR), name='static')

    @app.get('/', response_class=HTMLResponse)
    def root() -> str:
        return _html_page()

    @app.get('/api/workspace')
    def workspace_summary() -> JSONResponse:
        workspace = _load_workspace(workspace_path)
        return JSONResponse(_workspace_summary(workspace))

    @app.get('/api/workspace/candidates/{candidate_id}')
    def candidate_details(candidate_id: str) -> JSONResponse:
        workspace = _load_workspace(workspace_path)
        return JSONResponse(_candidate_summary(workspace, candidate_id))

    @app.get('/api/workspace/candidates/{candidate_id}/preview')
    def candidate_preview(candidate_id: str) -> Response:
        workspace = _load_workspace(workspace_path)
        candidate = workspace.candidate_by_id(candidate_id)
        if candidate is None:
            raise HTTPException(status_code=404, detail='candidate not found')
        path = candidate.preview_path
        return FileResponse(path)

    @app.get('/api/workspace/candidates/{candidate_id}/thumb')
    def candidate_thumb(candidate_id: str) -> Response:
        workspace = _load_workspace(workspace_path)
        candidate = workspace.candidate_by_id(candidate_id)
        if candidate is None:
            raise HTTPException(status_code=404, detail='candidate not found')
        path = candidate.thumb_path if candidate.thumb_path.exists() else candidate.preview_path
        return FileResponse(path)

    @app.get('/api/workspace/candidates/{candidate_id}/svg')
    def candidate_svg(candidate_id: str) -> Response:
        workspace = _load_workspace(workspace_path)
        candidate = workspace.candidate_by_id(candidate_id)
        if candidate is None:
            raise HTTPException(status_code=404, detail='candidate not found')
        return FileResponse(candidate.svg_path, media_type='image/svg+xml')

    @app.get('/api/workspace/composite/preview')
    def composite_preview(merge_threshold: float = 0.0) -> Response:
        workspace = _load_workspace(workspace_path)
        try:
            return _png_response(workspace.composite_preview(merge_threshold=merge_threshold))
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get('/api/workspace/composite/summary')
    def composite_summary(merge_threshold: float = 0.0) -> JSONResponse:
        workspace = _load_workspace(workspace_path)
        return JSONResponse(workspace.composite_summary(merge_threshold=merge_threshold))

    @app.get('/api/workspace/composite/svg')
    def composite_svg(merge_threshold: float = 0.0) -> Response:
        workspace = _load_workspace(workspace_path)
        try:
            return Response(
                content=workspace.composite_svg(merge_threshold=merge_threshold),
                media_type='image/svg+xml',
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post('/api/workspace/selection')
    def set_selection(request: CandidateSelectionRequest) -> JSONResponse:
        with workspace_lock:
            workspace = _load_workspace(workspace_path)
            workspace.set_candidate_selection(
                request.candidate_id,
                request.region_ids,
                additive=request.additive,
            )
            return JSONResponse(_workspace_summary(workspace))

    @app.post('/api/workspace/selection/clear')
    def clear_selection(request: CandidateRequest) -> JSONResponse:
        with workspace_lock:
            workspace = _load_workspace(workspace_path)
            if not workspace.clear_candidate_selection(request.candidate_id):
                raise HTTPException(status_code=404, detail='candidate not found')
            return JSONResponse(_workspace_summary(workspace))

    @app.post('/api/workspace/selection/paint-all')
    def paint_all_selection(request: CandidateRequest) -> JSONResponse:
        with workspace_lock:
            workspace = _load_workspace(workspace_path)
            if workspace.paint_all_candidate(request.candidate_id) <= 0:
                raise HTTPException(status_code=404, detail='candidate not found')
            return JSONResponse(_workspace_summary(workspace))

    @app.post('/api/workspace/active')
    def set_active(request: CandidateRequest) -> JSONResponse:
        with workspace_lock:
            workspace = _load_workspace(workspace_path)
            workspace.set_active_candidate(request.candidate_id)
            return JSONResponse(_workspace_summary(workspace))

    @app.post('/api/workspace/keep')
    def toggle_keep(request: CandidateRequest) -> JSONResponse:
        with workspace_lock:
            workspace = _load_workspace(workspace_path)
            if workspace.candidate_by_id(request.candidate_id) is None:
                raise HTTPException(status_code=404, detail='candidate not found')
            workspace.toggle_keep_candidate(request.candidate_id)
            return JSONResponse(_workspace_summary(workspace))

    @app.post('/api/workspace/refine')
    def refine(request: CandidateRequest) -> JSONResponse:
        with workspace_lock:
            workspace = _load_workspace(workspace_path)
            if not workspace.refine_candidate(request.candidate_id):
                raise HTTPException(status_code=404, detail='candidate not found')
            return JSONResponse(_workspace_summary(workspace))

    @app.post('/api/workspace/composite/export')
    def export_composite(request: ExportRequest) -> JSONResponse:
        workspace = _load_workspace(workspace_path)
        try:
            composite_png, composite_svg = workspace.export_composite(
                request.output_dir,
                merge_threshold=request.merge_threshold,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return JSONResponse(
            {
                'composite_png': str(composite_png),
                'composite_svg': str(composite_svg),
            }
        )

    return app
