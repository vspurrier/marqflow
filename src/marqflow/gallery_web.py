"""Small FastAPI UI for the marquetry-first rewrite."""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Annotated

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .models import PhysicalSize, Veneer
from .workspace import MarquetryWorkspace

STATIC_DIR = Path(__file__).with_name('static')


class CandidateRequest(BaseModel):
    target_regions: int = 80
    compactness: float = 18.0


class DesignRequest(BaseModel):
    candidate_id: str
    width: float = Field(default=8.0, gt=0)
    height: float = Field(default=10.0, gt=0)
    unit: str = 'in'


class VeneerRequest(BaseModel):
    region_id: int
    veneer_id: str


class PackRequest(BaseModel):
    output_dir: str = './exported'


def _html_page() -> str:
    return (STATIC_DIR / 'gallery.html').read_text(encoding='utf-8')


def _load_workspace(path: Path | None) -> MarquetryWorkspace:
    if path is None:
        raise HTTPException(status_code=404, detail='workspace not loaded')
    try:
        return MarquetryWorkspace.load(path)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail='workspace not found') from exc


def create_app(workspace_dir: str | Path | None = None) -> FastAPI:
    workspace_path = Path(workspace_dir) if workspace_dir is not None else None
    workspace_root = workspace_path.parent if workspace_path else None
    app = FastAPI(title='Marqflow')
    app.mount('/static', StaticFiles(directory=STATIC_DIR), name='static')

    @app.get('/', response_class=HTMLResponse)
    def index() -> str:
        return _html_page()

    @app.get('/api/workspace')
    def workspace() -> JSONResponse:
        return JSONResponse(_load_workspace(workspace_path).summary())

    @app.post('/api/workspace/open-image')
    async def open_image(
        image: Annotated[UploadFile, File()],
        target_regions: Annotated[int, Form()] = 80,
        compactness: Annotated[float, Form()] = 18.0,
    ) -> JSONResponse:
        nonlocal workspace_path
        nonlocal workspace_root
        if workspace_root is None:
            workspace_root = Path(tempfile.mkdtemp(prefix='marqflow-'))
        workspace_root.mkdir(parents=True, exist_ok=True)
        suffix = Path(image.filename or 'source.png').suffix or '.png'
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix, dir=workspace_root) as tmp:
            tmp.write(await image.read())
            upload_path = Path(tmp.name)
        try:
            workspace_path = workspace_root / f'workspace-{upload_path.stem}'
            ws = MarquetryWorkspace.create(upload_path, workspace_path)
            candidate = ws.generate_candidate(
                target_regions=target_regions,
                compactness=compactness,
            )
            ws.create_design(candidate.candidate_id, PhysicalSize(width=8, height=10, unit='in'))
            return JSONResponse(ws.summary())
        finally:
            upload_path.unlink(missing_ok=True)

    @app.post('/api/candidate')
    def generate_candidate(request: CandidateRequest) -> JSONResponse:
        ws = _load_workspace(workspace_path)
        ws.generate_candidate(
            target_regions=request.target_regions,
            compactness=request.compactness,
        )
        return JSONResponse(ws.summary())

    @app.post('/api/design')
    def create_design(request: DesignRequest) -> JSONResponse:
        ws = _load_workspace(workspace_path)
        ws.create_design(
            request.candidate_id,
            PhysicalSize(width=request.width, height=request.height, unit=request.unit),
        )
        return JSONResponse(ws.summary())

    @app.post('/api/design/veneer')
    def assign_veneer(request: VeneerRequest) -> JSONResponse:
        ws = _load_workspace(workspace_path)
        try:
            ws.assign_veneer(request.region_id, request.veneer_id)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return JSONResponse(ws.summary())

    @app.post('/api/design/veneers')
    def replace_veneers(veneers: list[Veneer]) -> JSONResponse:
        ws = _load_workspace(workspace_path)
        if ws.design is None:
            raise HTTPException(status_code=400, detail='create a design first')
        ws.design.veneers = veneers
        ws.save()
        return JSONResponse(ws.summary())

    @app.get('/api/design.svg')
    def design_svg() -> Response:
        ws = _load_workspace(workspace_path)
        if ws.design is None:
            raise HTTPException(status_code=400, detail='create a design first')
        svg_path = ws.export_svg(ws.workspace_dir / 'design.svg')
        return Response(svg_path.read_text(encoding='utf-8'), media_type='image/svg+xml')

    @app.post('/api/pack')
    def pack(request: PackRequest) -> JSONResponse:
        ws = _load_workspace(workspace_path)
        return JSONResponse(ws.pack(request.output_dir))

    return app
