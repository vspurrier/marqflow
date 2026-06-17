"""Browser UI for marqflow."""

from __future__ import annotations

from io import BytesIO
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse, Response
from PIL import Image
from pydantic import BaseModel, Field

from .project import MarqflowProject
from .svg import region_map_to_svg


class SplitRequest(BaseModel):
    region_ids: list[int] = Field(default_factory=list)
    segments: int = 4
    compactness: float | None = None
    sigma: float | None = None


class MergeRequest(BaseModel):
    region_ids: list[int] = Field(default_factory=list)


class ExportRequest(BaseModel):
    output_dir: str | None = None


def _load_project(project_dir: Path) -> MarqflowProject:
    try:
        return MarqflowProject.load(project_dir)
    except FileNotFoundError as exc:  # pragma: no cover - defensive guard
        raise HTTPException(status_code=404, detail='project not found') from exc


def _project_summary(project: MarqflowProject) -> dict[str, object]:
    region_map = project.region_map
    regions = []
    for region in sorted(region_map.regions, key=lambda item: item.region_id):
        regions.append(
            {
                'region_id': region.region_id,
                'area': region.area,
                'fill': region.fill,
                'bbox': region.bbox,
                'neighbors': list(region.neighbors),
            }
        )

    return {
        'project_dir': str(project.project_dir),
        'source_image_path': str(project.source_image_path),
        'size': {'width': region_map.size[0], 'height': region_map.size[1]},
        'region_count': len(region_map.regions),
        'edit_count': len(project.edits),
        'regions': regions,
    }


def _preview_png_bytes(project: MarqflowProject) -> bytes:
    image = Image.fromarray(project.preview.astype('uint8'), mode='RGB')
    buffer = BytesIO()
    image.save(buffer, format='PNG')
    return buffer.getvalue()


def _html_page() -> str:
    return """
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Marqflow</title>
  <style>
    :root {
      color-scheme: dark;
      --bg: #121212;
      --panel: #1b1b1b;
      --panel-2: #222;
      --text: #f2efe8;
      --muted: #a8a29c;
      --line: #37322c;
      --accent: #e7b96a;
      --accent-2: #6db7a2;
      --danger: #d46a62;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      font-family: ui-sans-serif, system-ui, -apple-system,
        BlinkMacSystemFont, "Segoe UI", sans-serif;
      background:
        radial-gradient(circle at top left, rgba(231,185,106,0.12), transparent 22%),
        radial-gradient(circle at top right, rgba(109,183,162,0.10), transparent 28%),
        var(--bg);
      color: var(--text);
    }
    .shell {
      display: grid;
      grid-template-columns: 320px 1fr;
      min-height: 100vh;
    }
    .sidebar {
      border-right: 1px solid var(--line);
      background: rgba(18,18,18,0.96);
      padding: 18px;
      overflow: auto;
    }
    .title {
      font-size: 22px;
      font-weight: 700;
      margin: 0 0 4px;
    }
    .subtitle {
      margin: 0 0 16px;
      color: var(--muted);
      font-size: 13px;
      line-height: 1.4;
    }
    .card {
      background: linear-gradient(180deg, rgba(255,255,255,0.03), transparent);
      border: 1px solid var(--line);
      border-radius: 14px;
      padding: 14px;
      margin-bottom: 14px;
    }
    .field {
      display: grid;
      gap: 6px;
      margin-bottom: 12px;
    }
    .field label {
      color: var(--muted);
      font-size: 12px;
      text-transform: uppercase;
      letter-spacing: 0.04em;
    }
    input, button {
      font: inherit;
    }
    input[type="number"], input[type="text"] {
      width: 100%;
      border: 1px solid var(--line);
      background: var(--panel-2);
      color: var(--text);
      border-radius: 10px;
      padding: 10px 12px;
    }
    button {
      border: 1px solid var(--line);
      background: var(--panel-2);
      color: var(--text);
      border-radius: 10px;
      padding: 10px 12px;
      cursor: pointer;
    }
    button.primary {
      background: linear-gradient(180deg, rgba(231,185,106,0.22), rgba(231,185,106,0.12));
      border-color: rgba(231,185,106,0.55);
    }
    button.danger {
      background: linear-gradient(180deg, rgba(212,106,98,0.24), rgba(212,106,98,0.12));
      border-color: rgba(212,106,98,0.55);
    }
    button:disabled {
      opacity: 0.5;
      cursor: not-allowed;
    }
    .row {
      display: flex;
      gap: 8px;
      flex-wrap: wrap;
    }
    .stats {
      display: grid;
      gap: 8px;
      font-size: 14px;
      color: var(--muted);
    }
    .regions {
      display: grid;
      gap: 8px;
      max-height: 44vh;
      overflow: auto;
      padding-right: 4px;
    }
    .region-item {
      display: grid;
      gap: 3px;
      border: 1px solid var(--line);
      border-radius: 12px;
      padding: 10px;
      cursor: pointer;
      background: rgba(255,255,255,0.02);
    }
    .region-item.selected {
      border-color: rgba(231,185,106,0.75);
      background: rgba(231,185,106,0.08);
    }
    .region-item .meta {
      color: var(--muted);
      font-size: 12px;
    }
    .content {
      display: grid;
      grid-template-rows: auto 1fr;
      min-width: 0;
    }
    .toolbar {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
      padding: 14px 18px;
      border-bottom: 1px solid var(--line);
      background: rgba(18,18,18,0.9);
      position: sticky;
      top: 0;
      z-index: 2;
    }
    .toolbar .status {
      color: var(--muted);
      font-size: 14px;
    }
    .canvas-wrap {
      position: relative;
      padding: 18px;
      overflow: auto;
    }
    .stage {
      position: relative;
      display: inline-block;
      max-width: 100%;
      border-radius: 16px;
      overflow: hidden;
      border: 1px solid var(--line);
      background: #0d0d0d;
      box-shadow: 0 16px 48px rgba(0,0,0,0.35);
    }
    #preview {
      display: block;
      max-width: min(100%, 1200px);
      height: auto;
      user-select: none;
      -webkit-user-drag: none;
    }
    #svg-layer {
      position: absolute;
      inset: 0;
      width: 100%;
      height: 100%;
      pointer-events: none;
    }
    #svg-layer svg {
      width: 100%;
      height: 100%;
      display: block;
      pointer-events: auto;
    }
    #svg-layer path {
      opacity: 0.88;
      stroke: rgba(255,255,255,0.22);
      stroke-width: 1;
      vector-effect: non-scaling-stroke;
      transition: opacity 120ms ease, stroke 120ms ease, stroke-width 120ms ease;
    }
    #svg-layer path.hovered {
      stroke: var(--accent-2);
      stroke-width: 2;
      opacity: 1;
    }
    #svg-layer path.selected {
      stroke: var(--accent);
      stroke-width: 3;
      opacity: 1;
    }
    .small {
      font-size: 12px;
      color: var(--muted);
    }
  </style>
</head>
<body>
  <div class="shell">
    <aside class="sidebar">
      <h1 class="title">Marqflow</h1>
      <p class="subtitle">
        Region-first marquetry planning. Click regions in the preview or list,
        then split or merge the selection.
      </p>

      <div class="card stats">
        <div><strong>Project</strong> <span id="project-dir"></span></div>
        <div><strong>Source</strong> <span id="source-path"></span></div>
        <div><strong>Size</strong> <span id="image-size"></span></div>
        <div><strong>Regions</strong> <span id="region-count"></span></div>
        <div><strong>Edits</strong> <span id="edit-count"></span></div>
        <div><strong>Selected</strong> <span id="selected-count">0</span></div>
      </div>

      <div class="card">
        <div class="field">
          <label for="segments">Split segments</label>
          <input id="segments" type="number" min="2" value="4" />
        </div>
        <div class="field">
          <label for="compactness">Compactness</label>
          <input id="compactness" type="number" min="0.1" step="0.1" value="20" />
        </div>
        <div class="field">
          <label for="sigma">Sigma</label>
          <input id="sigma" type="number" min="0" step="0.1" value="1" />
        </div>
        <div class="row">
          <button id="split-btn" class="primary">Split selected</button>
          <button id="merge-btn" class="danger">Merge selected</button>
          <button id="clear-btn">Clear</button>
        </div>
      </div>

      <div class="card">
        <div class="field">
          <label for="export-dir">Export dir</label>
          <input id="export-dir" type="text" placeholder="./exported" value="./exported" />
        </div>
        <div class="row">
          <button id="export-btn" class="primary">Export</button>
          <button id="refresh-btn">Refresh</button>
        </div>
        <div class="small" id="export-status"></div>
      </div>

      <div class="card">
        <div class="field">
          <label>Regions</label>
        </div>
        <div id="regions" class="regions"></div>
      </div>
    </aside>

    <main class="content">
      <div class="toolbar">
        <div class="status" id="status">Loading project…</div>
        <div class="status" id="selection-status">No selection</div>
      </div>
      <div class="canvas-wrap">
        <div class="stage">
          <img id="preview" alt="project preview" />
          <div id="svg-layer"></div>
        </div>
      </div>
    </main>
  </div>

  <script>
    const state = {
      project: null,
      selected: new Set(),
      svgLoadedAt: 0,
    };

    const elements = {
      status: document.getElementById('status'),
      selectionStatus: document.getElementById('selection-status'),
      projectDir: document.getElementById('project-dir'),
      sourcePath: document.getElementById('source-path'),
      imageSize: document.getElementById('image-size'),
      regionCount: document.getElementById('region-count'),
      editCount: document.getElementById('edit-count'),
      selectedCount: document.getElementById('selected-count'),
      preview: document.getElementById('preview'),
      svgLayer: document.getElementById('svg-layer'),
      regions: document.getElementById('regions'),
      segments: document.getElementById('segments'),
      compactness: document.getElementById('compactness'),
      sigma: document.getElementById('sigma'),
      exportDir: document.getElementById('export-dir'),
      exportStatus: document.getElementById('export-status'),
      splitBtn: document.getElementById('split-btn'),
      mergeBtn: document.getElementById('merge-btn'),
      clearBtn: document.getElementById('clear-btn'),
      exportBtn: document.getElementById('export-btn'),
      refreshBtn: document.getElementById('refresh-btn'),
    };

    function setStatus(message) {
      elements.status.textContent = message;
    }

    function updateSelectionStatus() {
      const ids = [...state.selected].sort((a, b) => a - b);
      elements.selectedCount.textContent = String(ids.length);
      elements.selectionStatus.textContent = ids.length
        ? `Selected: ${ids.join(', ')}`
        : 'No selection';
      elements.splitBtn.disabled = ids.length === 0;
      elements.mergeBtn.disabled = ids.length === 0;
    }

    function regionElement(region) {
      const item = document.createElement('div');
      item.className = 'region-item';
      item.dataset.regionId = String(region.region_id);
      item.innerHTML = `
        <div><strong>#${region.region_id}</strong> area=${region.area}</div>
        <div class="meta">${region.fill} · neighbors ${region.neighbors.length || 0}</div>
      `;
      item.addEventListener('click', () => toggleRegion(region.region_id));
      return item;
    }

    function renderRegions(regions) {
      elements.regions.innerHTML = '';
      regions.forEach((region) => {
        const item = regionElement(region);
        if (state.selected.has(region.region_id)) {
          item.classList.add('selected');
        }
        elements.regions.appendChild(item);
      });
    }

    function syncPathStyles() {
      const paths = elements.svgLayer.querySelectorAll('path[data-region-id]');
      paths.forEach((path) => {
        const id = Number(path.dataset.regionId);
        path.classList.toggle('selected', state.selected.has(id));
      });
      const items = elements.regions.querySelectorAll('.region-item[data-region-id]');
      items.forEach((item) => {
        const id = Number(item.dataset.regionId);
        item.classList.toggle('selected', state.selected.has(id));
      });
    }

    function toggleRegion(regionId) {
      if (state.selected.has(regionId)) {
        state.selected.delete(regionId);
      } else {
        state.selected.add(regionId);
      }
      syncPathStyles();
      updateSelectionStatus();
    }

    async function loadSvg() {
      const response = await fetch('/api/project/regions.svg');
      const text = await response.text();
      elements.svgLayer.innerHTML = text;
      const svg = elements.svgLayer.querySelector('svg');
      if (!svg) {
        return;
      }
      svg.setAttribute('preserveAspectRatio', 'none');
      svg.querySelectorAll('path[data-region-id]').forEach((path) => {
        path.addEventListener('click', (event) => {
          event.preventDefault();
          event.stopPropagation();
          toggleRegion(Number(path.dataset.regionId));
        });
        path.addEventListener('mouseenter', () => path.classList.add('hovered'));
        path.addEventListener('mouseleave', () => path.classList.remove('hovered'));
      });
      syncPathStyles();
      state.svgLoadedAt = Date.now();
    }

    async function refreshProject() {
      const response = await fetch('/api/project');
      const project = await response.json();
      state.project = project;

      elements.projectDir.textContent = project.project_dir;
      elements.sourcePath.textContent = project.source_image_path;
      elements.imageSize.textContent = `${project.size.width} x ${project.size.height}`;
      elements.regionCount.textContent = String(project.region_count);
      elements.editCount.textContent = String(project.edit_count);

      elements.preview.src = `/api/project/preview.png?ts=${Date.now()}`;
      renderRegions(project.regions);
      await loadSvg();
      updateSelectionStatus();
      setStatus('Project loaded');
    }

    async function mutate(endpoint, payload) {
      const response = await fetch(endpoint, {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(payload),
      });
      if (!response.ok) {
        const error = await response.json().catch(() => ({}));
        throw new Error(error.detail || `Request failed (${response.status})`);
      }
      await refreshProject();
    }

    elements.splitBtn.addEventListener('click', async () => {
      const selected = [...state.selected];
      if (!selected.length) return;
      setStatus('Splitting…');
      await mutate('/api/project/split', {
        region_ids: selected,
        segments: Number(elements.segments.value || 4),
        compactness: Number(elements.compactness.value || 20),
        sigma: Number(elements.sigma.value || 1),
      });
    });

    elements.mergeBtn.addEventListener('click', async () => {
      const selected = [...state.selected];
      if (!selected.length) return;
      setStatus('Merging…');
      await mutate('/api/project/merge', {region_ids: selected});
    });

    elements.clearBtn.addEventListener('click', () => {
      state.selected.clear();
      syncPathStyles();
      updateSelectionStatus();
    });

    elements.refreshBtn.addEventListener('click', async () => {
      setStatus('Refreshing…');
      await refreshProject();
    });

    elements.exportBtn.addEventListener('click', async () => {
      setStatus('Exporting…');
      const response = await fetch('/api/project/export', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({output_dir: elements.exportDir.value}),
      });
      if (!response.ok) {
        const error = await response.json().catch(() => ({}));
        elements.exportStatus.textContent = error.detail || `Export failed (${response.status})`;
        setStatus('Export failed');
        return;
      }
      const data = await response.json();
      elements.exportStatus.textContent = `Exported to ${data.output_dir}`;
      setStatus('Exported');
    });

    refreshProject().catch((error) => {
      console.error(error);
      setStatus(`Failed to load project: ${error.message}`);
    });
  </script>
</body>
</html>
    """.strip()


def create_app(project_dir: str | Path) -> FastAPI:
    """Create a FastAPI app bound to a specific project directory."""

    project_path = Path(project_dir)
    app = FastAPI(title='Marqflow')
    app.state.project_dir = project_path

    @app.get('/', response_class=HTMLResponse)
    def index() -> HTMLResponse:
        return HTMLResponse(_html_page())

    @app.head('/')
    def index_head() -> Response:
        return Response(status_code=200)

    @app.get('/api/project')
    def project_summary_endpoint() -> JSONResponse:
        project = _load_project(app.state.project_dir)
        return JSONResponse(_project_summary(project))

    @app.get('/api/project/preview.png')
    def preview_png() -> Response:
        project = _load_project(app.state.project_dir)
        return Response(_preview_png_bytes(project), media_type='image/png')

    @app.get('/api/project/regions.svg')
    def regions_svg() -> Response:
        project = _load_project(app.state.project_dir)
        return Response(region_map_to_svg(project.region_map), media_type='image/svg+xml')

    @app.post('/api/project/split')
    def split_regions(request: SplitRequest) -> JSONResponse:
        project = _load_project(app.state.project_dir)
        changed = project.split_regions(
            request.region_ids,
            request.segments,
            compactness=request.compactness,
            sigma=request.sigma,
        )
        project.save()
        return JSONResponse({'changed': changed, **_project_summary(project)})

    @app.post('/api/project/merge')
    def merge_regions(request: MergeRequest) -> JSONResponse:
        project = _load_project(app.state.project_dir)
        merged = project.merge_regions(request.region_ids)
        project.save()
        return JSONResponse({'merged': merged, **_project_summary(project)})

    @app.post('/api/project/export')
    def export_project(request: ExportRequest) -> JSONResponse:
        project = _load_project(app.state.project_dir)
        output_dir = (
            Path(request.output_dir)
            if request.output_dir is not None
            else project.project_dir / 'export'
        )
        preview_path, svg_path = project.export(output_dir)
        return JSONResponse(
            {
                'output_dir': str(output_dir),
                'preview': str(preview_path),
                'svg': str(svg_path),
            }
        )

    return app
