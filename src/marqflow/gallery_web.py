"""Small FastAPI UI for the marquetry-first rewrite."""

from __future__ import annotations

import re
import shutil
import tempfile
from pathlib import Path
from typing import Annotated

from fastapi import FastAPI, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .models import PhysicalSize, Veneer
from .workspace import MarquetryWorkspace

STATIC_DIR = Path(__file__).with_name('static')


class CandidateRequest(BaseModel):
    target_regions: int = 80
    compactness: float = 18.0
    use_detail_zones: bool = False


class CandidateGridRequest(BaseModel):
    rows: int = Field(default=4, ge=1, le=8)
    cols: int = Field(default=4, ge=1, le=8)
    min_regions: int = Field(default=20, ge=2)
    max_regions: int = Field(default=140, ge=2)
    min_compactness: float = Field(default=4.0, gt=0)
    max_compactness: float = Field(default=28.0, gt=0)
    use_detail_zones: bool = False


class DesignRequest(BaseModel):
    candidate_id: str
    width: float = Field(default=8.0, gt=0)
    height: float = Field(default=10.0, gt=0)
    unit: str = 'in'


class PhysicalSizeRequest(BaseModel):
    width: float = Field(gt=0)
    height: float = Field(gt=0)
    unit: str = 'in'


class VeneerRequest(BaseModel):
    region_id: int
    veneer_id: str


class BulkVeneerRequest(BaseModel):
    region_ids: list[int] = Field(min_length=1)
    veneer_id: str


class VeneerModel(BaseModel):
    veneer_id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    color_rgb: tuple[int, int, int]
    sheet_width: float = Field(default=0.0, ge=0)
    sheet_height: float = Field(default=0.0, ge=0)
    sheet_count: int = Field(default=0, ge=0)
    grain_direction: str = ''
    notes: str = ''

    def to_domain(self) -> Veneer:
        return Veneer(
            veneer_id=self.veneer_id,
            name=self.name,
            color_rgb=self.color_rgb,
            sheet_width=self.sheet_width,
            sheet_height=self.sheet_height,
            sheet_count=self.sheet_count,
            grain_direction=self.grain_direction,
            notes=self.notes,
        )


class MergeRequest(BaseModel):
    region_ids: list[int] = Field(min_length=2)


class SplitRequest(BaseModel):
    region_id: int
    target_parts: int = Field(default=3, ge=2, le=25)
    compactness: float = Field(default=12.0, gt=0)


class LockRequest(BaseModel):
    region_ids: list[int] = Field(min_length=1)
    locked: bool = True


class ApplyMergeSuggestionsRequest(BaseModel):
    max_merges: int = Field(default=10, ge=1, le=200)


class DetailZoneRequest(BaseModel):
    name: str = 'Focus zone'
    bbox: tuple[int, int, int, int]
    detail_multiplier: float = Field(default=2.0, ge=1.0)


class DetailZoneForRegionsRequest(BaseModel):
    region_ids: list[int] = Field(min_length=1)
    name: str = 'Focus zone'
    detail_multiplier: float = Field(default=2.0, ge=1.0)


class ApplyDetailZonesRequest(BaseModel):
    max_splits: int = Field(default=10, ge=1, le=200)
    compactness: float = Field(default=10.0, gt=0)


class RepairSmallRegionsRequest(BaseModel):
    max_area: float = Field(default=0.05, gt=0)
    max_repairs: int = Field(default=25, ge=1, le=500)


class SmoothBoundariesRequest(BaseModel):
    iterations: int = Field(default=1, ge=1, le=20)
    region_ids: list[int] = Field(default_factory=list)


class PackRequest(BaseModel):
    output_dir: str = './exported'


class WorkspaceOpenRequest(BaseModel):
    name: str = Field(min_length=1)


def _workspace_name(raw_name: str) -> str:
    name = re.sub(r'[^a-zA-Z0-9_.-]+', '-', raw_name).strip('.-')
    return name[:80] or 'workspace'


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
    workspace_root = workspace_path.parent if workspace_path else Path.home() / '.marqflow'
    app = FastAPI(title='Marqflow')
    app.mount('/static', StaticFiles(directory=STATIC_DIR), name='static')

    @app.get('/', response_class=HTMLResponse)
    def index() -> str:
        return _html_page()

    @app.get('/api/workspace')
    def workspace() -> JSONResponse:
        return JSONResponse(_load_workspace(workspace_path).summary())

    @app.get('/api/workspaces')
    def workspaces() -> JSONResponse:
        nonlocal workspace_root
        workspace_root.mkdir(parents=True, exist_ok=True)
        items = []
        for path in sorted(workspace_root.iterdir()):
            if not path.is_dir() or not (path / 'workspace.json').exists():
                continue
            items.append(
                {
                    'name': path.name,
                    'path': str(path),
                    'active': (
                        workspace_path is not None
                        and path.resolve() == workspace_path.resolve()
                    ),
                }
            )
        return JSONResponse({'workspace_root': str(workspace_root), 'workspaces': items})

    @app.post('/api/workspace/open')
    def open_workspace(request: WorkspaceOpenRequest) -> JSONResponse:
        nonlocal workspace_path
        target = workspace_root / _workspace_name(request.name)
        if not (target / 'workspace.json').exists():
            raise HTTPException(status_code=404, detail='workspace not found')
        workspace_path = target
        return JSONResponse(MarquetryWorkspace.load(workspace_path).summary())

    @app.delete('/api/workspace/{name}')
    def delete_workspace(name: str) -> JSONResponse:
        nonlocal workspace_path
        target = (workspace_root / _workspace_name(name)).resolve()
        root = workspace_root.resolve()
        if root not in target.parents:
            raise HTTPException(status_code=400, detail='path escapes workspace root')
        if not (target / 'workspace.json').exists():
            raise HTTPException(status_code=404, detail='workspace not found')
        shutil.rmtree(target)
        if workspace_path is not None and target == workspace_path.resolve():
            workspace_path = None
        return JSONResponse({'deleted': name})

    @app.get('/api/workspace-file/{relative_path:path}')
    def workspace_file(relative_path: str) -> FileResponse:
        ws = _load_workspace(workspace_path)
        root = ws.workspace_dir.resolve()
        path = (root / relative_path).resolve()
        if root not in path.parents and path != root:
            raise HTTPException(status_code=400, detail='path escapes workspace')
        if not path.is_file():
            raise HTTPException(status_code=404, detail='file not found')
        return FileResponse(path)

    @app.post('/api/workspace/open-image')
    async def open_image(
        image: Annotated[UploadFile, File()],
        target_regions: Annotated[int, Form()] = 80,
        compactness: Annotated[float, Form()] = 18.0,
        workspace_name: Annotated[str | None, Form()] = None,
    ) -> JSONResponse:
        nonlocal workspace_path
        nonlocal workspace_root
        workspace_root.mkdir(parents=True, exist_ok=True)
        suffix = Path(image.filename or 'source.png').suffix or '.png'
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix, dir=workspace_root) as tmp:
            tmp.write(await image.read())
            upload_path = Path(tmp.name)
        try:
            name = _workspace_name(
                workspace_name or Path(image.filename or upload_path.stem).stem
            )
            workspace_path = workspace_root / name
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
            use_detail_zones=request.use_detail_zones,
        )
        return JSONResponse(ws.summary())

    @app.post('/api/candidate-grid')
    def generate_candidate_grid(request: CandidateGridRequest) -> JSONResponse:
        if request.max_regions < request.min_regions:
            raise HTTPException(status_code=400, detail='max_regions must be >= min_regions')
        if request.max_compactness < request.min_compactness:
            raise HTTPException(
                status_code=400,
                detail='max_compactness must be >= min_compactness',
            )
        ws = _load_workspace(workspace_path)
        ws.generate_candidate_grid(
            rows=request.rows,
            cols=request.cols,
            min_regions=request.min_regions,
            max_regions=request.max_regions,
            min_compactness=request.min_compactness,
            max_compactness=request.max_compactness,
            use_detail_zones=request.use_detail_zones,
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

    @app.post('/api/design/size')
    def update_physical_size(request: PhysicalSizeRequest) -> JSONResponse:
        ws = _load_workspace(workspace_path)
        try:
            ws.update_physical_size(
                PhysicalSize(width=request.width, height=request.height, unit=request.unit)
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return JSONResponse(ws.summary())

    @app.post('/api/design/veneer')
    def assign_veneer(request: VeneerRequest) -> JSONResponse:
        ws = _load_workspace(workspace_path)
        try:
            ws.assign_veneer(request.region_id, request.veneer_id)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return JSONResponse(ws.summary())

    @app.post('/api/design/veneer-bulk')
    def assign_veneer_many(request: BulkVeneerRequest) -> JSONResponse:
        ws = _load_workspace(workspace_path)
        try:
            ws.assign_veneer_many(request.region_ids, request.veneer_id)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return JSONResponse(ws.summary())

    @app.post('/api/design/merge')
    def merge_regions(request: MergeRequest) -> JSONResponse:
        ws = _load_workspace(workspace_path)
        try:
            ws.merge_regions(request.region_ids)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return JSONResponse(ws.summary())

    @app.post('/api/design/split')
    def split_region(request: SplitRequest) -> JSONResponse:
        ws = _load_workspace(workspace_path)
        try:
            ws.split_region(
                request.region_id,
                target_parts=request.target_parts,
                compactness=request.compactness,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return JSONResponse(ws.summary())

    @app.post('/api/design/lock')
    def lock_regions(request: LockRequest) -> JSONResponse:
        ws = _load_workspace(workspace_path)
        try:
            ws.lock_regions(request.region_ids, locked=request.locked)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return JSONResponse(ws.summary())

    @app.post('/api/design/apply-merge-suggestions')
    def apply_merge_suggestions(request: ApplyMergeSuggestionsRequest) -> JSONResponse:
        ws = _load_workspace(workspace_path)
        applied = ws.apply_merge_suggestions(max_merges=request.max_merges)
        payload = ws.summary()
        payload['applied_merge_count'] = applied
        return JSONResponse(payload)

    @app.post('/api/design/undo')
    def undo() -> JSONResponse:
        ws = _load_workspace(workspace_path)
        try:
            ws.undo()
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return JSONResponse(ws.summary())

    @app.get('/api/design/hitmap')
    def design_hitmap() -> JSONResponse:
        ws = _load_workspace(workspace_path)
        labels = ws.design_labels()
        return JSONResponse(
            {
                'width': int(labels.shape[1]),
                'height': int(labels.shape[0]),
                'labels': labels.astype(int).tolist(),
            }
        )

    @app.post('/api/design/detail-zone')
    def add_detail_zone(request: DetailZoneRequest) -> JSONResponse:
        ws = _load_workspace(workspace_path)
        try:
            ws.add_detail_zone(
                name=request.name,
                bbox=request.bbox,
                detail_multiplier=request.detail_multiplier,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return JSONResponse(ws.summary())

    @app.post('/api/design/detail-zone-for-regions')
    def add_detail_zone_for_regions(request: DetailZoneForRegionsRequest) -> JSONResponse:
        ws = _load_workspace(workspace_path)
        try:
            ws.add_detail_zone_for_regions(
                request.region_ids,
                name=request.name,
                detail_multiplier=request.detail_multiplier,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return JSONResponse(ws.summary())

    @app.post('/api/design/apply-detail-zones')
    def apply_detail_zones(request: ApplyDetailZonesRequest) -> JSONResponse:
        ws = _load_workspace(workspace_path)
        try:
            applied = ws.apply_detail_zones(
                max_splits=request.max_splits,
                compactness=request.compactness,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        payload = ws.summary()
        payload['applied_detail_split_count'] = applied
        return JSONResponse(payload)

    @app.post('/api/design/repair-small-regions')
    def repair_small_regions(request: RepairSmallRegionsRequest) -> JSONResponse:
        ws = _load_workspace(workspace_path)
        try:
            applied = ws.repair_small_regions(
                max_area=request.max_area,
                max_repairs=request.max_repairs,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        payload = ws.summary()
        payload['repaired_region_count'] = applied
        return JSONResponse(payload)

    @app.post('/api/design/smooth-boundaries')
    def smooth_boundaries(request: SmoothBoundariesRequest) -> JSONResponse:
        ws = _load_workspace(workspace_path)
        try:
            changed_px = ws.smooth_boundaries(
                iterations=request.iterations,
                region_ids=request.region_ids or None,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        payload = ws.summary()
        payload['smoothed_pixel_count'] = changed_px
        return JSONResponse(payload)

    @app.get('/api/design/boundaries')
    def design_boundaries() -> JSONResponse:
        ws = _load_workspace(workspace_path)
        return JSONResponse(ws.boundary_summary())

    @app.post('/api/design/veneers')
    def replace_veneers(veneers: list[VeneerModel]) -> JSONResponse:
        ws = _load_workspace(workspace_path)
        try:
            ws.replace_veneers([veneer.to_domain() for veneer in veneers])
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return JSONResponse(ws.summary())

    @app.get('/api/design.svg')
    def design_svg(
        simplify_tolerance: float = Query(default=1.0, ge=0.0, le=20.0),
    ) -> Response:
        ws = _load_workspace(workspace_path)
        if ws.design is None:
            raise HTTPException(status_code=400, detail='create a design first')
        svg_path = ws.export_svg(
            ws.workspace_dir / 'design.svg',
            simplify_tolerance=simplify_tolerance,
        )
        return Response(svg_path.read_text(encoding='utf-8'), media_type='image/svg+xml')

    @app.post('/api/pack')
    def pack(request: PackRequest) -> JSONResponse:
        ws = _load_workspace(workspace_path)
        output_dir = Path(request.output_dir)
        if not output_dir.is_absolute():
            output_dir = ws.workspace_dir / output_dir
        output_dir = output_dir.resolve()
        root = workspace_root.resolve()
        if root not in [output_dir, *output_dir.parents]:
            raise HTTPException(status_code=400, detail='pack output escapes workspace')
        return JSONResponse(ws.pack(output_dir))

    return app
