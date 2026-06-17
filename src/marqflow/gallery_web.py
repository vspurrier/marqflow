# ruff: noqa: E501
"""Browser UI for grid-search marquetry workspaces."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response
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


def _load_workspace(workspace_dir: Path) -> GridWorkspace:
    try:
        return GridWorkspace.load(workspace_dir)
    except FileNotFoundError as exc:  # pragma: no cover - defensive guard
        raise HTTPException(status_code=404, detail='workspace not found') from exc


def _workspace_summary(workspace: GridWorkspace) -> dict[str, object]:
    summary = workspace.summary()
    candidates: list[dict[str, object]] = []
    for candidate in summary['candidates']:
        candidate = dict(candidate)
        candidate_id = str(candidate['candidate_id'])
        candidate['preview_url'] = f'/api/workspace/candidates/{candidate_id}/preview'
        candidate['svg_url'] = f'/api/workspace/candidates/{candidate_id}/svg'
        candidates.append(candidate)
    summary['candidates'] = candidates
    active = summary.get('active_candidate')
    if isinstance(active, dict):
        candidate_id = str(active['candidate_id'])
        active['preview_url'] = f'/api/workspace/candidates/{candidate_id}/preview'
        active['svg_url'] = f'/api/workspace/candidates/{candidate_id}/svg'
    return summary


def _candidate_summary(workspace: GridWorkspace, candidate_id: str) -> dict[str, object]:
    summary = workspace.candidate_summary(candidate_id)
    if summary is None:
        raise HTTPException(status_code=404, detail='candidate not found')
    summary = dict(summary)
    summary['preview_url'] = f'/api/workspace/candidates/{candidate_id}/preview'
    summary['svg_url'] = f'/api/workspace/candidates/{candidate_id}/svg'
    return summary


def _html_page() -> str:
    return """
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Marqflow Gallery</title>
  <style>
    :root {
      color-scheme: dark;
      --bg: #121212;
      --panel: #1a1816;
      --panel-2: #231f1b;
      --line: #3a332d;
      --line-strong: #5d5248;
      --text: #f7f1e8;
      --muted: #b9b1a7;
      --accent: #dfb26a;
      --accent-2: #7fc4af;
      --danger: #de7f6f;
      --shadow: 0 18px 48px rgba(0, 0, 0, 0.38);
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      background:
        radial-gradient(circle at top left, rgba(223,178,106,0.13), transparent 24%),
        radial-gradient(circle at top right, rgba(127,196,175,0.11), transparent 28%),
        linear-gradient(180deg, #141312, #0c0b0a 68%);
      color: var(--text);
      font-family: ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      overflow: hidden;
    }
    button, input {
      font: inherit;
    }
    .shell {
      display: grid;
      grid-template-columns: 374px 1fr;
      height: 100vh;
      min-height: 0;
    }
    .sidebar {
      border-right: 1px solid var(--line);
      background: rgba(17, 16, 14, 0.96);
      overflow: auto;
      padding: 18px;
      min-height: 0;
    }
    .content {
      display: grid;
      grid-template-rows: auto 1fr;
      min-width: 0;
      min-height: 0;
    }
    .toolbar {
      display: flex;
      justify-content: space-between;
      align-items: center;
      gap: 12px;
      padding: 14px 18px;
      border-bottom: 1px solid var(--line);
      background: rgba(18, 16, 14, 0.92);
      backdrop-filter: blur(10px);
    }
    .toolbar .pill {
      padding: 7px 12px;
      border-radius: 999px;
      border: 1px solid var(--line);
      background: rgba(255,255,255,0.03);
      color: var(--muted);
      font-size: 13px;
    }
    .toolbar .pill strong {
      color: var(--text);
    }
    .toolbar-actions {
      display: flex;
      align-items: center;
      gap: 8px;
      flex-wrap: wrap;
    }
    .toolbar-actions button, .tiny {
      border: 1px solid var(--line);
      background: var(--panel-2);
      color: var(--text);
      border-radius: 12px;
      padding: 9px 11px;
      cursor: pointer;
    }
    .toolbar-actions button.primary, .primary {
      background: linear-gradient(180deg, rgba(223,178,106,0.24), rgba(223,178,106,0.12));
      border-color: rgba(223,178,106,0.56);
    }
    .toolbar-actions button:disabled, .tiny:disabled, button:disabled {
      opacity: 0.55;
      cursor: not-allowed;
    }
    .toolbar-actions input[type="range"] {
      width: 170px;
      accent-color: var(--accent);
    }
    .stage-wrap {
      position: relative;
      overflow: auto;
      min-width: 0;
      min-height: 0;
      padding: 18px;
    }
    .stage {
      position: relative;
      display: inline-block;
      border-radius: 18px;
      border: 1px solid var(--line);
      background:
        radial-gradient(circle at center, rgba(255,255,255,0.03), transparent 58%),
        #0f0d0c;
      box-shadow: var(--shadow);
      user-select: none;
      touch-action: none;
    }
    .stage-inner {
      position: relative;
      transform-origin: top left;
    }
    #preview {
      display: block;
      width: 100%;
      height: auto;
      -webkit-user-drag: none;
      user-select: none;
      image-rendering: auto;
    }
    #svg-layer {
      position: absolute;
      inset: 0;
      width: 100%;
      height: 100%;
    }
    #svg-layer svg {
      width: 100%;
      height: 100%;
      display: block;
      pointer-events: auto;
    }
    #svg-layer path {
      opacity: 0.88;
      stroke: rgba(255,255,255,0.18);
      stroke-width: 1;
      vector-effect: non-scaling-stroke;
      cursor: pointer;
      transition: stroke 120ms ease, stroke-width 120ms ease, opacity 120ms ease, filter 120ms ease;
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
      filter: drop-shadow(0 0 2px rgba(223, 178, 106, 0.38));
    }
    .selection-box {
      position: absolute;
      border: 1px solid rgba(223,178,106,0.95);
      background: rgba(223,178,106,0.14);
      border-radius: 8px;
      pointer-events: none;
      display: none;
      z-index: 3;
    }
    .title {
      margin: 0 0 4px;
      font-size: 24px;
      letter-spacing: -0.02em;
    }
    .subtitle {
      margin: 0 0 16px;
      color: var(--muted);
      font-size: 13px;
      line-height: 1.45;
    }
    .card {
      border: 1px solid var(--line);
      background:
        linear-gradient(180deg, rgba(255,255,255,0.03), transparent),
        var(--panel);
      border-radius: 16px;
      padding: 14px;
      margin-bottom: 14px;
      box-shadow: 0 10px 26px rgba(0,0,0,0.18);
    }
    .section-title {
      display: flex;
      justify-content: space-between;
      align-items: center;
      gap: 8px;
      margin-bottom: 10px;
      text-transform: uppercase;
      letter-spacing: 0.08em;
      font-size: 12px;
      color: var(--text);
    }
    .badge {
      display: inline-flex;
      align-items: center;
      justify-content: center;
      min-width: 28px;
      padding: 2px 8px;
      border-radius: 999px;
      border: 1px solid var(--line);
      background: rgba(255,255,255,0.03);
      color: var(--muted);
      font-size: 12px;
      text-transform: none;
      letter-spacing: 0;
    }
    .stats {
      display: grid;
      gap: 8px;
      color: var(--muted);
      font-size: 14px;
    }
    .row {
      display: flex;
      gap: 8px;
      flex-wrap: wrap;
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
      letter-spacing: 0.05em;
    }
    input[type="text"] {
      border: 1px solid var(--line);
      background: var(--panel-2);
      color: var(--text);
      border-radius: 12px;
      padding: 10px 12px;
      width: 100%;
    }
    .grid-grid {
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(108px, 1fr));
      gap: 10px;
    }
    .candidate {
      border: 1px solid var(--line);
      border-radius: 14px;
      overflow: hidden;
      background: rgba(255,255,255,0.02);
      cursor: pointer;
      transition: transform 120ms ease, border-color 120ms ease, background 120ms ease;
    }
    .candidate:hover {
      transform: translateY(-1px);
      border-color: var(--line-strong);
    }
    .candidate.active {
      border-color: rgba(223,178,106,0.8);
      background: rgba(223,178,106,0.08);
    }
    .candidate.kept {
      border-color: rgba(127,196,175,0.72);
    }
    .candidate img {
      display: block;
      width: 100%;
      aspect-ratio: 1 / 1;
      object-fit: cover;
      background: #090807;
    }
    .candidate .meta {
      padding: 8px 9px 9px;
      display: grid;
      gap: 4px;
    }
    .candidate .name {
      font-size: 12px;
      font-weight: 650;
      line-height: 1.2;
    }
    .candidate .sub {
      color: var(--muted);
      font-size: 11px;
      line-height: 1.35;
    }
    .candidate .actions {
      display: flex;
      gap: 6px;
      flex-wrap: wrap;
    }
    .candidate .actions button {
      padding: 5px 7px;
      border-radius: 999px;
      font-size: 11px;
      border: 1px solid var(--line);
      background: var(--panel-2);
      color: var(--text);
      cursor: pointer;
    }
    .candidate .actions button.primary {
      border-color: rgba(223,178,106,0.55);
    }
    .candidate .actions button.keep-on {
      border-color: rgba(127,196,175,0.55);
      color: #dbfff4;
    }
    .muted {
      color: var(--muted);
    }
    .small {
      font-size: 12px;
      line-height: 1.45;
      color: var(--muted);
    }
    .selected-list {
      display: flex;
      flex-wrap: wrap;
      gap: 6px;
      margin-top: 8px;
    }
    .selected-chip {
      border: 1px solid var(--line);
      border-radius: 999px;
      padding: 5px 9px;
      font-size: 11px;
      background: rgba(255,255,255,0.03);
      color: var(--muted);
    }
    .selected-chip strong {
      color: var(--text);
    }
    @media (max-width: 1080px) {
      body { overflow: auto; }
      .shell {
        grid-template-columns: 1fr;
        height: auto;
      }
      .sidebar {
        border-right: none;
        border-bottom: 1px solid var(--line);
      }
      .content {
        min-height: 70vh;
      }
    }
  </style>
</head>
<body>
  <div class="shell">
    <aside class="sidebar">
      <h1 class="title">Marqflow Gallery</h1>
      <p class="subtitle">
        Grid search first. Rows move toward more regions, columns move toward smoother regions.
        Keep candidates you like, then select regions across them for a combined marquetry image.
      </p>

      <div class="card stats">
        <div><strong>Workspace</strong> <span id="workspace-dir"></span></div>
        <div><strong>Source</strong> <span id="source-path"></span></div>
        <div><strong>Active</strong> <span id="active-id"></span></div>
        <div><strong>Candidates</strong> <span id="candidate-count"></span></div>
        <div><strong>Kept</strong> <span id="kept-count"></span></div>
        <div><strong>Selection</strong> <span id="selection-count">0</span></div>
      </div>

      <div class="card">
        <div class="section-title">
          <span>Workflow</span>
          <span class="badge">grid</span>
        </div>
        <div class="row">
          <button id="refine-btn" class="primary" type="button">Refine active</button>
          <button id="keep-btn" type="button">Keep active</button>
          <button id="clear-btn" type="button">Clear selection</button>
          <button id="export-btn" class="primary" type="button">Export composite</button>
        </div>
        <div class="field">
          <label for="export-dir">Export dir</label>
          <input id="export-dir" type="text" value="./exported" />
        </div>
        <div class="small" id="action-status"></div>
      </div>

      <div class="card">
        <div class="section-title">
          <span>Candidate Grid</span>
          <span class="badge">9+</span>
        </div>
        <div class="small">
          Click a tile to open it. The active tile is the one in the main viewer.
          Keep the tiles that feel promising, then box-select regions in those tiles for the final composite.
        </div>
        <div id="grid" class="grid-grid" style="margin-top: 12px;"></div>
      </div>

      <div class="card">
        <div class="section-title">
          <span>Selected Regions</span>
          <span class="badge" id="selected-badge">0</span>
        </div>
        <div class="small" id="selection-summary">No regions selected.</div>
        <div id="selected-list" class="selected-list"></div>
      </div>
    </aside>

    <main class="content">
      <div class="toolbar">
        <div class="pill" id="status">Loading workspace…</div>
        <div class="toolbar-actions">
          <button id="zoom-out" type="button">-</button>
          <button id="fit-btn" type="button">Fit</button>
          <button id="one-btn" type="button">1:1</button>
          <button id="zoom-in" type="button">+</button>
          <input id="zoom-range" type="range" min="0.15" max="8" step="0.05" value="1" />
          <div class="pill" id="zoom-status">100%</div>
        </div>
      </div>
      <div class="stage-wrap" id="stage-wrap">
        <div id="stage" class="stage">
          <div id="stage-inner" class="stage-inner">
            <img id="preview" alt="candidate preview" />
            <div id="svg-layer"></div>
            <div id="selection-box" class="selection-box"></div>
          </div>
        </div>
      </div>
    </main>
  </div>

  <script>
    const state = {
      workspace: null,
      active: null,
      activeDetail: null,
      regionById: new Map(),
      selected: new Set(),
      zoom: 1,
      fitZoom: 1,
      drag: null,
    };

    const el = {
      status: document.getElementById('status'),
      actionStatus: document.getElementById('action-status'),
      workspaceDir: document.getElementById('workspace-dir'),
      sourcePath: document.getElementById('source-path'),
      activeId: document.getElementById('active-id'),
      candidateCount: document.getElementById('candidate-count'),
      keptCount: document.getElementById('kept-count'),
      selectionCount: document.getElementById('selection-count'),
      selectionBadge: document.getElementById('selected-badge'),
      selectionSummary: document.getElementById('selection-summary'),
      selectedList: document.getElementById('selected-list'),
      grid: document.getElementById('grid'),
      preview: document.getElementById('preview'),
      svgLayer: document.getElementById('svg-layer'),
      stage: document.getElementById('stage'),
      stageInner: document.getElementById('stage-inner'),
      selectionBox: document.getElementById('selection-box'),
      zoomRange: document.getElementById('zoom-range'),
      zoomStatus: document.getElementById('zoom-status'),
      zoomOut: document.getElementById('zoom-out'),
      zoomIn: document.getElementById('zoom-in'),
      fitBtn: document.getElementById('fit-btn'),
      oneBtn: document.getElementById('one-btn'),
      keepBtn: document.getElementById('keep-btn'),
      refineBtn: document.getElementById('refine-btn'),
      clearBtn: document.getElementById('clear-btn'),
      exportBtn: document.getElementById('export-btn'),
      exportDir: document.getElementById('export-dir'),
    };

    function setStatus(text, error = false) {
      el.status.textContent = text;
      el.status.style.color = error ? 'var(--danger)' : 'var(--muted)';
    }

    function setActionStatus(text, error = false) {
      el.actionStatus.textContent = text;
      el.actionStatus.style.color = error ? 'var(--danger)' : 'var(--muted)';
    }

    function fmt(value) {
      return Number.isFinite(value) ? Math.round(value).toString() : '0';
    }

    function updateWorkspaceSummary(workspace) {
      el.workspaceDir.textContent = workspace.workspace_dir;
      el.sourcePath.textContent = workspace.source_image_path;
      el.activeId.textContent = workspace.active_candidate_id || 'none';
      el.candidateCount.textContent = workspace.candidate_count;
      el.keptCount.textContent = workspace.kept_count;
    }

    function candidateLabel(candidate) {
      return candidate.label || candidate.candidate_id.slice(0, 8);
    }

    function renderGrid(workspace) {
      el.grid.innerHTML = '';
      for (const candidate of workspace.candidates) {
        const card = document.createElement('div');
        card.className = 'candidate' + (candidate.candidate_id === workspace.active_candidate_id ? ' active' : '') + (candidate.kept ? ' kept' : '');

        const img = document.createElement('img');
        img.src = `${candidate.preview_url}?t=${Date.now()}`;
        img.alt = candidateLabel(candidate);

        const meta = document.createElement('div');
        meta.className = 'meta';

        const name = document.createElement('div');
        name.className = 'name';
        name.textContent = candidateLabel(candidate);

        const sub = document.createElement('div');
        sub.className = 'sub';
        sub.textContent = `${candidate.region_count} regions · gen ${candidate.generation}`;

        const preset = candidate.preset || {};
        const details = document.createElement('div');
        details.className = 'sub';
        details.textContent = `segments ${preset.target_segments} · compactness ${Number(preset.compactness).toFixed(1)}`;

        const actions = document.createElement('div');
        actions.className = 'actions';

        const openButton = document.createElement('button');
        openButton.textContent = 'Open';
        openButton.className = 'primary';
        openButton.addEventListener('click', (event) => {
          event.stopPropagation();
          setActive(candidate.candidate_id);
        });

        const keepButton = document.createElement('button');
        keepButton.textContent = candidate.kept ? 'Unkeep' : 'Keep';
        keepButton.className = candidate.kept ? 'keep-on' : '';
        keepButton.addEventListener('click', async (event) => {
          event.stopPropagation();
          await toggleKeep(candidate.candidate_id);
        });

        actions.append(openButton, keepButton);
        meta.append(name, sub, details, actions);
        card.append(img, meta);
        card.addEventListener('click', () => setActive(candidate.candidate_id));
        el.grid.appendChild(card);
      }
    }

    function renderSelection() {
      el.selectionCount.textContent = state.selected.size;
      el.selectionBadge.textContent = state.selected.size;
      if (!state.selected.size) {
        el.selectionSummary.textContent = 'No regions selected.';
        el.selectedList.innerHTML = '';
        return;
      }
      const regions = [...state.selected].map((id) => state.regionById.get(id)).filter(Boolean);
      const totalArea = regions.reduce((sum, region) => sum + region.area, 0);
      el.selectionSummary.textContent = `${regions.length} region${regions.length === 1 ? '' : 's'} selected, ${totalArea} total pixels.`;
      el.selectedList.innerHTML = '';
      for (const region of regions.slice(0, 18)) {
        const chip = document.createElement('div');
        chip.className = 'selected-chip';
        chip.innerHTML = `<strong>#${region.region_id}</strong> · ${region.area}`;
        el.selectedList.appendChild(chip);
      }
    }

    function regionFromPath(path) {
      const id = Number(path.dataset.regionId);
      return state.regionById.get(id) || null;
    }

    function applySelectionToSvg() {
      el.svgLayer.querySelectorAll('path').forEach((path) => {
        const id = Number(path.dataset.regionId);
        path.classList.toggle('selected', state.selected.has(id));
      });
    }

    function coordsFromEvent(event) {
      const rect = el.stage.getBoundingClientRect();
      const x = (event.clientX - rect.left) / state.zoom;
      const y = (event.clientY - rect.top) / state.zoom;
      return { x, y };
    }

    function updateSelectionBox(start, end) {
      const left = Math.min(start.x, end.x);
      const top = Math.min(start.y, end.y);
      const width = Math.abs(end.x - start.x);
      const height = Math.abs(end.y - start.y);
      el.selectionBox.style.left = `${left}px`;
      el.selectionBox.style.top = `${top}px`;
      el.selectionBox.style.width = `${width}px`;
      el.selectionBox.style.height = `${height}px`;
      el.selectionBox.style.display = 'block';
    }

    function hideSelectionBox() {
      el.selectionBox.style.display = 'none';
    }

    function applyBoxSelection(start, end, additive) {
      const left = Math.min(start.x, end.x);
      const right = Math.max(start.x, end.x);
      const top = Math.min(start.y, end.y);
      const bottom = Math.max(start.y, end.y);
      const next = additive ? new Set(state.selected) : new Set();
      for (const [id, region] of state.regionById.entries()) {
        const [x0, y0, x1, y1] = region.bbox;
        const intersects = x1 >= left && x0 <= right && y1 >= top && y0 <= bottom;
        if (intersects) {
          next.add(id);
        }
      }
      state.selected = next;
      applySelectionToSvg();
      renderSelection();
    }

    async function fetchWorkspace() {
      const response = await fetch('/api/workspace');
      if (!response.ok) {
        throw new Error(await response.text());
      }
      const workspace = await response.json();
      state.workspace = workspace;
      updateWorkspaceSummary(workspace);
      renderGrid(workspace);
      if (!state.active || !workspace.candidates.find((item) => item.candidate_id === state.active)) {
        state.active = workspace.active_candidate_id || (workspace.candidates[0] && workspace.candidates[0].candidate_id) || null;
      }
      if (state.active) {
        await setActive(state.active, { preserveSelection: true });
      }
    }

    async function fetchCandidate(candidateId) {
      const response = await fetch(`/api/workspace/candidates/${candidateId}`);
      if (!response.ok) {
        throw new Error(await response.text());
      }
      return response.json();
    }

    async function loadCandidateSvg(candidate) {
      const response = await fetch(candidate.svg_url);
      if (!response.ok) {
        throw new Error(await response.text());
      }
      el.svgLayer.innerHTML = await response.text();
      const svg = el.svgLayer.querySelector('svg');
      if (svg) {
        svg.setAttribute('preserveAspectRatio', 'none');
        svg.setAttribute('width', '100%');
        svg.setAttribute('height', '100%');
        svg.querySelectorAll('path').forEach((path) => {
          path.addEventListener('mouseenter', () => path.classList.add('hovered'));
          path.addEventListener('mouseleave', () => path.classList.remove('hovered'));
          path.addEventListener('click', async (event) => {
            event.stopPropagation();
            const id = Number(path.dataset.regionId);
            const next = new Set(state.selected);
            if (event.shiftKey || event.metaKey || event.ctrlKey) {
              if (next.has(id)) {
                next.delete(id);
              } else {
                next.add(id);
              }
            } else {
              next.clear();
              next.add(id);
            }
            state.selected = next;
            await saveSelection(false);
          });
        });
      }
    }

    async function setActive(candidateId, options = {}) {
      state.active = candidateId;
      setStatus(`Loading ${candidateId}…`);
      const detail = await fetchCandidate(candidateId);
      state.activeDetail = detail;
      state.regionById = new Map(detail.regions.map((region) => [region.region_id, region]));
      if (!options.preserveSelection) {
        state.selected = new Set(detail.selected_region_ids || []);
      }
      el.preview.src = `${detail.preview_url}?t=${Date.now()}`;
      el.preview.width = detail.size.width;
      el.preview.height = detail.size.height;
      el.stage.style.width = `${detail.size.width * state.zoom}px`;
      el.stage.style.height = `${detail.size.height * state.zoom}px`;
      el.stageInner.style.width = `${detail.size.width}px`;
      el.stageInner.style.height = `${detail.size.height}px`;
      await loadCandidateSvg(detail);
      applySelectionToSvg();
      renderSelection();
      renderGrid(state.workspace);
      updateWorkspaceSummary(state.workspace);
      el.activeId.textContent = detail.candidate_id;
      setStatus(`Active ${candidateLabel(detail)} · ${detail.region_count} regions`);
    }

    async function saveSelection(additive) {
      if (!state.active) {
        return;
      }
      const response = await fetch('/api/workspace/selection', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({
          candidate_id: state.active,
          region_ids: [...state.selected],
          additive,
        }),
      });
      if (!response.ok) {
        throw new Error(await response.text());
      }
      const workspace = await response.json();
      state.workspace = workspace;
      renderGrid(workspace);
      updateWorkspaceSummary(workspace);
      setActionStatus(`Saved ${state.selected.size} selected region${state.selected.size === 1 ? '' : 's'}.`);
    }

    async function toggleKeep(candidateId) {
      const response = await fetch('/api/workspace/keep', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({candidate_id: candidateId}),
      });
      if (!response.ok) {
        throw new Error(await response.text());
      }
      const workspace = await response.json();
      state.workspace = workspace;
      renderGrid(workspace);
      updateWorkspaceSummary(workspace);
      setActionStatus(`Updated keep state for ${candidateId}.`);
    }

    async function refineActive() {
      if (!state.active) {
        return;
      }
      setActionStatus('Refining active candidate…');
      const response = await fetch('/api/workspace/refine', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({candidate_id: state.active}),
      });
      if (!response.ok) {
        throw new Error(await response.text());
      }
      const workspace = await response.json();
      state.workspace = workspace;
      renderGrid(workspace);
      updateWorkspaceSummary(workspace);
      const active = workspace.active_candidate_id;
      if (active) {
        await setActive(active);
      }
      setActionStatus('Generated a tighter 3x3 search around the active candidate.');
    }

    async function clearSelection() {
      if (!state.active) {
        return;
      }
      const response = await fetch('/api/workspace/selection/clear', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({candidate_id: state.active}),
      });
      if (!response.ok) {
        throw new Error(await response.text());
      }
      state.selected = new Set();
      applySelectionToSvg();
      renderSelection();
      const workspace = await response.json();
      state.workspace = workspace;
      renderGrid(workspace);
      updateWorkspaceSummary(workspace);
      setActionStatus('Selection cleared.');
    }

    async function exportComposite() {
      const response = await fetch('/api/workspace/export', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({output_dir: el.exportDir.value}),
      });
      if (!response.ok) {
        throw new Error(await response.text());
      }
      const payload = await response.json();
      setActionStatus(`Exported ${payload.composite_png} and ${payload.composite_svg}.`);
    }

    function applyZoom(zoom, mode = 'manual') {
      state.zoom = zoom;
      state.stageZoomMode = mode;
      el.stageInner.style.transform = `scale(${zoom})`;
      if (state.activeDetail) {
        el.stage.style.width = `${state.activeDetail.size.width * zoom}px`;
        el.stage.style.height = `${state.activeDetail.size.height * zoom}px`;
      }
      el.zoomRange.value = String(zoom);
      el.zoomStatus.textContent = `${Math.round(zoom * 100)}%`;
    }

    function fitZoom() {
      if (!state.activeDetail) {
        return;
      }
      const padding = 36;
      const wrap = document.getElementById('stage-wrap');
      const maxWidth = wrap.clientWidth - padding;
      const maxHeight = wrap.clientHeight - padding;
      const zoom = Math.max(0.15, Math.min(maxWidth / state.activeDetail.size.width, maxHeight / state.activeDetail.size.height));
      state.fitZoom = zoom;
      applyZoom(zoom, 'fit');
    }

    el.stage.addEventListener('pointerdown', (event) => {
      if (event.target.closest('path')) {
        return;
      }
      if (!state.activeDetail) {
        return;
      }
      event.preventDefault();
      const start = coordsFromEvent(event);
      state.drag = {
        start,
        additive: event.shiftKey || event.metaKey || event.ctrlKey,
      };
      updateSelectionBox(start, start);
      el.stage.setPointerCapture(event.pointerId);
    });

    el.stage.addEventListener('pointermove', (event) => {
      if (!state.drag) {
        return;
      }
      const current = coordsFromEvent(event);
      updateSelectionBox(state.drag.start, current);
    });

    el.stage.addEventListener('pointerup', async (event) => {
      if (!state.drag) {
        return;
      }
      const end = coordsFromEvent(event);
      const drag = state.drag;
      state.drag = null;
      hideSelectionBox();
      if (Math.abs(end.x - drag.start.x) < 6 && Math.abs(end.y - drag.start.y) < 6) {
        return;
      }
      applyBoxSelection(drag.start, end, drag.additive);
      await saveSelection(drag.additive);
    });

    el.stage.addEventListener('pointercancel', () => {
      state.drag = null;
      hideSelectionBox();
    });

    el.zoomRange.addEventListener('input', () => applyZoom(Number(el.zoomRange.value), 'manual'));
    el.zoomOut.addEventListener('click', () => applyZoom(Math.max(0.15, state.zoom / 1.18), 'manual'));
    el.zoomIn.addEventListener('click', () => applyZoom(Math.min(8, state.zoom * 1.18), 'manual'));
    el.oneBtn.addEventListener('click', () => applyZoom(1, 'manual'));
    el.fitBtn.addEventListener('click', fitZoom);
    el.keepBtn.addEventListener('click', async () => {
      if (state.active) {
        await toggleKeep(state.active);
      }
    });
    el.refineBtn.addEventListener('click', refineActive);
    el.clearBtn.addEventListener('click', clearSelection);
    el.exportBtn.addEventListener('click', exportComposite);
    window.addEventListener('resize', () => {
      if (state.active && state.activeDetail) {
        fitZoom();
      }
    });

    async function boot() {
      try {
        await fetchWorkspace();
        if (state.activeDetail) {
          fitZoom();
        }
      } catch (error) {
        setStatus(String(error), true);
        setActionStatus(String(error), true);
      }
    }

    boot();
  </script>
</body>
</html>
"""


def create_app(workspace_dir: str | Path) -> FastAPI:
    workspace_path = Path(workspace_dir)
    app = FastAPI(title='Marqflow Gallery')
    app.state.workspace_dir = workspace_path

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
        return FileResponse(candidate.preview_path)

    @app.get('/api/workspace/candidates/{candidate_id}/svg')
    def candidate_svg(candidate_id: str) -> Response:
        workspace = _load_workspace(workspace_path)
        candidate = workspace.candidate_by_id(candidate_id)
        if candidate is None:
            raise HTTPException(status_code=404, detail='candidate not found')
        return FileResponse(candidate.svg_path, media_type='image/svg+xml')

    @app.post('/api/workspace/selection')
    def set_selection(request: CandidateSelectionRequest) -> JSONResponse:
        workspace = _load_workspace(workspace_path)
        workspace.set_candidate_selection(
            request.candidate_id,
            request.region_ids,
            additive=request.additive,
        )
        return JSONResponse(_workspace_summary(workspace))

    @app.post('/api/workspace/selection/clear')
    def clear_selection(request: CandidateRequest) -> JSONResponse:
        workspace = _load_workspace(workspace_path)
        if not workspace.clear_candidate_selection(request.candidate_id):
            raise HTTPException(status_code=404, detail='candidate not found')
        return JSONResponse(_workspace_summary(workspace))

    @app.post('/api/workspace/active')
    def set_active(request: CandidateRequest) -> JSONResponse:
        workspace = _load_workspace(workspace_path)
        workspace.set_active_candidate(request.candidate_id)
        return JSONResponse(_workspace_summary(workspace))

    @app.post('/api/workspace/keep')
    def toggle_keep(request: CandidateRequest) -> JSONResponse:
        workspace = _load_workspace(workspace_path)
        if workspace.candidate_by_id(request.candidate_id) is None:
            raise HTTPException(status_code=404, detail='candidate not found')
        workspace.toggle_keep_candidate(request.candidate_id)
        return JSONResponse(_workspace_summary(workspace))

    @app.post('/api/workspace/refine')
    def refine(request: CandidateRequest) -> JSONResponse:
        workspace = _load_workspace(workspace_path)
        if not workspace.refine_candidate(request.candidate_id):
            raise HTTPException(status_code=404, detail='candidate not found')
        return JSONResponse(_workspace_summary(workspace))

    @app.post('/api/workspace/export')
    def export(request: ExportRequest) -> JSONResponse:
        workspace = _load_workspace(workspace_path)
        composite_png, composite_svg = workspace.export_composite(request.output_dir)
        return JSONResponse(
            {
                'composite_png': str(composite_png),
                'composite_svg': str(composite_svg),
            }
        )

    return app
