# ruff: noqa: E501
"""Browser UI for grid-search marquetry workspaces.

The browser organizes the workflow into Image, Size, Subject, Shapes, Hues,
Cleanup, and Pack tabs while keeping the workspace API centered on the
candidate grid, explicit final partition edits, and export.
"""

from __future__ import annotations

import tempfile
import threading
from io import BytesIO
from pathlib import Path
from typing import Annotated

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .jobs import JobManager
from .marquetry import CleanupSettings, SubjectSettings, VeneerSwatch
from .workspace import GridWorkspace


class CandidateSelectionRequest(BaseModel):
    candidate_id: str
    region_ids: list[int] = Field(default_factory=list)
    additive: bool = False


class CandidateRequest(BaseModel):
    candidate_id: str


class GridRequest(BaseModel):
    rows: int = 4
    cols: int = 4


class ResetRequest(BaseModel):
    rows: int = 4
    cols: int = 4


class ExportRequest(BaseModel):
    output_dir: str = './exported'


class SizeRequest(BaseModel):
    width: float = Field(default=1.0, gt=0)
    height: float = Field(default=1.0, gt=0)
    unit: str = 'px'


class CleanupRequest(BaseModel):
    simplify_tolerance: float = 1.0
    highlight_small_area: float = 0.0
    highlight_thin_width: float = 0.0
    merge_rgb_threshold: float = 24.0


class SubjectRequest(BaseModel):
    detail_budget: float = 0.5
    notes: str = ''
    protect_eyes: bool = True
    protect_nose: bool = True


class MergeRequest(BaseModel):
    region_ids: list[int] = Field(default_factory=list)


class SplitRequest(BaseModel):
    region_id: int
    target_segments: int = 4
    compactness: float | None = None
    sigma: float | None = None


class VeneerRequest(BaseModel):
    region_id: int
    veneer_id: str | None = None


class VeneerSwatchRequest(BaseModel):
    veneer_id: str
    name: str
    color_rgb: tuple[int, int, int]


class VeneerPaletteRequest(BaseModel):
    swatches: list[VeneerSwatchRequest] = Field(default_factory=list)


class LockRequest(BaseModel):
    region_id: int
    locked: bool = True


class PointEditRequest(BaseModel):
    region_id: int
    point_index: int
    x: float
    y: float


class SmoothRequest(BaseModel):
    region_id: int
    tolerance: float = 1.5


def _load_workspace(workspace_dir: Path | None) -> GridWorkspace:
    if workspace_dir is None:
        raise HTTPException(status_code=404, detail='workspace not loaded')
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


def _job_payload(job) -> dict[str, object]:
    return job.to_dict() if job is not None else {}


STATIC_DIR = Path(__file__).with_name('static')


def _html_page() -> str:
    """Load the gallery shell from the packaged static files."""

    return (STATIC_DIR / 'gallery.html').read_text(encoding='utf-8')


def create_app(workspace_dir: str | Path | None = None) -> FastAPI:
    """Build the FastAPI app that serves the gallery UI and JSON endpoints."""

    workspace_path = Path(workspace_dir) if workspace_dir is not None else None
    workspace_root = (
        workspace_path.parent
        if workspace_path is not None and (workspace_path / 'workspace.json').exists()
        else workspace_path
    )
    workspace_lock = threading.RLock()
    job_manager = JobManager()
    app = FastAPI(title='Marqflow Gallery')
    app.state.workspace_dir = workspace_path
    app.state.workspace_root = workspace_root
    app.state.job_manager = job_manager
    app.mount('/static', StaticFiles(directory=STATIC_DIR), name='static')

    @app.get('/', response_class=HTMLResponse)
    def root() -> str:
        return _html_page()

    @app.get('/api/workspace')
    def workspace_summary() -> JSONResponse:
        workspace = _load_workspace(workspace_path)
        return JSONResponse(_workspace_summary(workspace))

    @app.post('/api/workspace/open-image')
    async def open_image(
        image: Annotated[UploadFile, File()],
        rows: Annotated[int, Form()] = 4,
        cols: Annotated[int, Form()] = 4,
    ) -> JSONResponse:
        nonlocal workspace_path
        nonlocal workspace_root
        with workspace_lock:
            suffix = Path(image.filename or 'upload.png').suffix or '.png'
            if workspace_root is None:
                workspace_root = Path(tempfile.mkdtemp(prefix='marqflow-workspaces-'))
                app.state.workspace_root = workspace_root
            upload_root = workspace_root
            upload_root.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(
                'wb', delete=False, suffix=suffix, dir=upload_root
            ) as tmp:
                tmp.write(await image.read())
                uploaded_path = Path(tmp.name)
            try:
                generated_workspace_dir = upload_root / f'workspace-{uploaded_path.stem}'
                workspace = GridWorkspace.create(uploaded_path, generated_workspace_dir)
                if rows != 4 or cols != 4:
                    workspace.rebuild_initial_grid(rows=rows, cols=cols)
                workspace_path = workspace.workspace_dir
                app.state.workspace_dir = workspace_path
                return JSONResponse(_workspace_summary(workspace))
            finally:
                if uploaded_path.exists():
                    uploaded_path.unlink()

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

    @app.get('/api/workspace/composite/hitmap')
    def composite_hitmap() -> JSONResponse:
        workspace = _load_workspace(workspace_path)
        return JSONResponse(workspace.composite_hitmap())

    @app.get('/api/jobs')
    def list_jobs() -> JSONResponse:
        return JSONResponse({'jobs': [job.to_dict() for job in job_manager.list()]})

    @app.get('/api/jobs/{job_id}')
    def get_job(job_id: str) -> JSONResponse:
        job = job_manager.get(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail='job not found')
        return JSONResponse(job.to_dict())

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

    @app.post('/api/workspace/refine-job')
    def refine_job(request: CandidateRequest) -> JSONResponse:
        if workspace_path is None:
            raise HTTPException(status_code=404, detail='workspace not loaded')

        def task(report):
            with workspace_lock:
                workspace = _load_workspace(workspace_path)
                report(0.15, f'Refining {request.candidate_id}')
                candidates = workspace.refine_candidate(request.candidate_id, progress_callback=report)
                if not candidates:
                    raise HTTPException(status_code=404, detail='candidate not found')
                report(0.95, 'Refreshing workspace summary')
                return _workspace_summary(workspace)

        job_id = job_manager.submit('refine', task)
        return JSONResponse({'job_id': job_id})

    @app.post('/api/workspace/grid')
    def rebuild_grid(request: GridRequest) -> JSONResponse:
        with workspace_lock:
            workspace = _load_workspace(workspace_path)
            workspace.rebuild_initial_grid(rows=request.rows, cols=request.cols)
            return JSONResponse(_workspace_summary(workspace))

    @app.post('/api/workspace/grid-job')
    def rebuild_grid_job(request: GridRequest) -> JSONResponse:
        if workspace_path is None:
            raise HTTPException(status_code=404, detail='workspace not loaded')

        def task(report):
            with workspace_lock:
                workspace = _load_workspace(workspace_path)
                report(0.1, 'Rebuilding grid')
                workspace.rebuild_initial_grid(
                    rows=request.rows,
                    cols=request.cols,
                    progress_callback=report,
                )
                report(0.95, 'Refreshing workspace summary')
                return _workspace_summary(workspace)

        job_id = job_manager.submit('grid', task)
        return JSONResponse({'job_id': job_id})

    @app.post('/api/workspace/reset')
    def reset_workspace(request: ResetRequest) -> JSONResponse:
        with workspace_lock:
            workspace = _load_workspace(workspace_path)
            workspace.reset_workspace(rows=request.rows, cols=request.cols)
            return JSONResponse(_workspace_summary(workspace))

    @app.post('/api/workspace/composite/export')
    def export_composite(request: ExportRequest) -> JSONResponse:
        workspace = _load_workspace(workspace_path)
        try:
            composite_png, composite_svg = workspace.export_composite(request.output_dir)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return JSONResponse(
            {
                'composite_png': str(composite_png),
                'composite_svg': str(composite_svg),
            }
        )

    @app.post('/api/workspace/size')
    def set_size(request: SizeRequest) -> JSONResponse:
        with workspace_lock:
            workspace = _load_workspace(workspace_path)
            workspace.set_physical_size(request.width, request.height, request.unit)
            return JSONResponse(_workspace_summary(workspace))

    @app.post('/api/workspace/cleanup')
    def set_cleanup(request: CleanupRequest) -> JSONResponse:
        with workspace_lock:
            workspace = _load_workspace(workspace_path)
            workspace.set_cleanup_settings(
                CleanupSettings(
                    simplify_tolerance=request.simplify_tolerance,
                    highlight_small_area=request.highlight_small_area,
                    highlight_thin_width=request.highlight_thin_width,
                    merge_rgb_threshold=request.merge_rgb_threshold,
                )
            )
            return JSONResponse(_workspace_summary(workspace))

    @app.post('/api/workspace/subject')
    def set_subject(request: SubjectRequest) -> JSONResponse:
        with workspace_lock:
            workspace = _load_workspace(workspace_path)
            workspace.set_subject_settings(
                SubjectSettings(
                    detail_budget=request.detail_budget,
                    notes=request.notes,
                    protect_eyes=request.protect_eyes,
                    protect_nose=request.protect_nose,
                )
            )
            return JSONResponse(_workspace_summary(workspace))

    @app.post('/api/workspace/final/merge')
    def merge_final(request: MergeRequest) -> JSONResponse:
        with workspace_lock:
            workspace = _load_workspace(workspace_path)
            merged = workspace.merge_final_regions(request.region_ids)
            if merged <= 0:
                raise HTTPException(status_code=404, detail='no regions merged')
            return JSONResponse(_workspace_summary(workspace))

    @app.post('/api/workspace/final/split')
    def split_final(request: SplitRequest) -> JSONResponse:
        with workspace_lock:
            workspace = _load_workspace(workspace_path)
            changed = workspace.split_final_region(
                request.region_id,
                request.target_segments,
                compactness=request.compactness,
                sigma=request.sigma,
            )
            if changed <= 0:
                raise HTTPException(status_code=404, detail='region not found')
            return JSONResponse(_workspace_summary(workspace))

    @app.post('/api/workspace/final/veneer')
    def set_final_veneer(request: VeneerRequest) -> JSONResponse:
        with workspace_lock:
            workspace = _load_workspace(workspace_path)
            if not workspace.set_final_region_veneer(request.region_id, request.veneer_id):
                raise HTTPException(status_code=404, detail='region not found')
            return JSONResponse(_workspace_summary(workspace))

    @app.post('/api/workspace/veneer-palette')
    def set_veneer_palette(request: VeneerPaletteRequest) -> JSONResponse:
        with workspace_lock:
            workspace = _load_workspace(workspace_path)
            try:
                workspace.set_veneer_palette(
                    [
                        VeneerSwatch(
                            veneer_id=swatch.veneer_id,
                            name=swatch.name,
                            color_rgb=swatch.color_rgb,
                        )
                        for swatch in request.swatches
                    ]
                )
            except ValueError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc
            return JSONResponse(_workspace_summary(workspace))

    @app.post('/api/workspace/final/lock')
    def set_final_lock(request: LockRequest) -> JSONResponse:
        with workspace_lock:
            workspace = _load_workspace(workspace_path)
            if not workspace.set_final_region_locked(request.region_id, request.locked):
                raise HTTPException(status_code=404, detail='region not found')
            return JSONResponse(_workspace_summary(workspace))

    @app.post('/api/workspace/final/point')
    def set_final_point(request: PointEditRequest) -> JSONResponse:
        with workspace_lock:
            workspace = _load_workspace(workspace_path)
            if not workspace.set_final_region_point(
                request.region_id,
                request.point_index,
                request.x,
                request.y,
            ):
                raise HTTPException(status_code=404, detail='region not found')
            return JSONResponse(_workspace_summary(workspace))

    @app.post('/api/workspace/final/smooth')
    def smooth_final(request: SmoothRequest) -> JSONResponse:
        with workspace_lock:
            workspace = _load_workspace(workspace_path)
            if not workspace.smooth_final_region(request.region_id, request.tolerance):
                raise HTTPException(status_code=404, detail='region not found')
            return JSONResponse(_workspace_summary(workspace))

    @app.post('/api/workspace/pack')
    def pack_final(request: ExportRequest) -> JSONResponse:
        with workspace_lock:
            workspace = _load_workspace(workspace_path)
            payload = workspace.pack_by_veneer(request.output_dir)
            return JSONResponse({'output_dir': request.output_dir, 'packed_sheets': payload})

    return app
