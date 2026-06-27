let workspace = null;
let hitmap = null;
let topologyEditLayer = null;
let selectedRegionIds = new Set();
let sourceImage = new Image();
let dragStart = null;
let dragCurrent = null;
let lassoPoints = [];
let activeVertexDrag = null;
let hoveredVertex = null;
let pendingVertexMove = null;
let selectedEdgeIds = new Set();
let cachedBaseCanvas = null;
let cachedBaseKey = '';
let canvasZoom = 100;
const el = {
    workspaceName: document.getElementById('workspace-name'),
    refreshWorkspaces: document.getElementById('refresh-workspaces'),
    workspaceList: document.getElementById('workspace-list'),
    openWorkspace: document.getElementById('open-workspace'),
    deleteWorkspace: document.getElementById('delete-workspace'),
    imageInput: document.getElementById('image-input'),
    maxEdge: document.getElementById('max-edge'),
    targetRegions: document.getElementById('target-regions'),
    compactness: document.getElementById('compactness'),
    marquetryMode: document.getElementById('marquetry-mode'),
    gridRows: document.getElementById('grid-rows'),
    gridCols: document.getElementById('grid-cols'),
    minRegions: document.getElementById('min-regions'),
    maxRegions: document.getElementById('max-regions'),
    minCompactness: document.getElementById('min-compactness'),
    maxCompactness: document.getElementById('max-compactness'),
    useDetailZones: document.getElementById('use-detail-zones'),
    useSubjectMask: document.getElementById('use-subject-mask'),
    gridMarquetryMode: document.getElementById('grid-marquetry-mode'),
    openImage: document.getElementById('open-image'),
    candidateGrid: document.getElementById('candidate-grid'),
    candidates: document.getElementById('candidates'),
    status: document.getElementById('status'),
    summary: document.getElementById('summary'),
    physicalWidth: document.getElementById('physical-width'),
    physicalHeight: document.getElementById('physical-height'),
    physicalUnit: document.getElementById('physical-unit'),
    updateSize: document.getElementById('update-size'),
    veneerEditor: document.getElementById('veneer-editor'),
    addVeneer: document.getElementById('add-veneer'),
    saveVeneers: document.getElementById('save-veneers'),
    mergeSuggestions: document.getElementById('merge-suggestions'),
    regions: document.getElementById('regions'),
    selectedVeneer: document.getElementById('selected-veneer'),
    assignSelected: document.getElementById('assign-selected'),
    mergeSelected: document.getElementById('merge-selected'),
    splitParts: document.getElementById('split-parts'),
    splitCompactness: document.getElementById('split-compactness'),
    splitSelected: document.getElementById('split-selected'),
    lockSelected: document.getElementById('lock-selected'),
    unlockSelected: document.getElementById('unlock-selected'),
    markSubject: document.getElementById('mark-subject'),
    markBackground: document.getElementById('mark-background'),
    focusMultiplier: document.getElementById('focus-multiplier'),
    focusSelected: document.getElementById('focus-selected'),
    applyFocus: document.getElementById('apply-focus'),
    repairArea: document.getElementById('repair-area'),
    repairSmall: document.getElementById('repair-small'),
    cuttabilityCleanup: document.getElementById('cuttability-cleanup'),
    smoothPasses: document.getElementById('smooth-passes'),
    smoothBoundaries: document.getElementById('smooth-boundaries'),
    removeNotches: document.getElementById('remove-notches'),
    applySuggestions: document.getElementById('apply-suggestions'),
    vectorTolerance: document.getElementById('vector-tolerance'),
    vectorSmoothStrength: document.getElementById('vector-smooth-strength'),
    vectorSimplifyAll: document.getElementById('vector-simplify-all'),
    previewVectorSimplify: document.getElementById('preview-vector-simplify'),
    vectorSimplifySelected: document.getElementById('vector-simplify-selected'),
    smoothVectorSelected: document.getElementById('smooth-vector-selected'),
    vectorKind: document.getElementById('vector-kind'),
    vectorPromote: document.getElementById('vector-promote'),
    viewGraphSvg: document.getElementById('view-graph-svg'),
    snapVertices: document.getElementById('snap-vertices'),
    vertexId: document.getElementById('vertex-id'),
    vertexX: document.getElementById('vertex-x'),
    vertexY: document.getElementById('vertex-y'),
    previewVertexMove: document.getElementById('preview-vertex-move'),
    acceptVertexPreview: document.getElementById('accept-vertex-preview'),
    cancelVertexPreview: document.getElementById('cancel-vertex-preview'),
    moveVertex: document.getElementById('move-vertex'),
    clearSelection: document.getElementById('clear-selection'),
    designCanvas: document.getElementById('design-canvas'),
    canvasZoom: document.getElementById('canvas-zoom'),
    selectionMode: document.getElementById('selection-mode'),
    brushRadius: document.getElementById('brush-radius'),
    zoomLabel: document.getElementById('zoom-label'),
    zoomIn: document.getElementById('zoom-in'),
    zoomOut: document.getElementById('zoom-out'),
    zoomFit: document.getElementById('zoom-fit'),
    showMask: document.getElementById('show-mask'),
    selectionStatus: document.getElementById('selection-status'),
    boundarySummary: document.getElementById('boundary-summary'),
    undo: document.getElementById('undo'),
    svgSimplify: document.getElementById('svg-simplify'),
    viewSvg: document.getElementById('view-svg'),
    viewCoverageSvg: document.getElementById('view-coverage-svg'),
    cleanupReport: document.getElementById('cleanup-report'),
    pack: document.getElementById('pack'),
    packSummary: document.getElementById('pack-summary'),
    packOutput: document.getElementById('pack-output'),
};
function setStatus(text, error = false) {
    el.status.textContent = text;
    el.status.style.color = error ? '#b6332a' : 'var(--muted)';
}
function invalidateDesignBase() {
    cachedBaseCanvas = null;
    cachedBaseKey = '';
}
function designBaseKey(width, height) {
    return JSON.stringify({
        width,
        height,
        showMask: Boolean(el.showMask.checked),
        selected: [...selectedRegionIds].sort((a, b) => a - b),
        sourceReady: Boolean(sourceImage.complete && sourceImage.naturalWidth),
    });
}
function rgb(color) {
    return `rgb(${color[0]}, ${color[1]}, ${color[2]})`;
}
async function refresh() {
    await loadWorkspaces();
    const response = await fetch('/api/workspace');
    if (!response.ok) {
        workspace = null;
        render();
        return;
    }
    workspace = await response.json();
    await loadHitmap();
    await loadTopologyEditLayer();
    render();
}
async function loadWorkspaces() {
    const response = await fetch('/api/workspaces');
    if (!response.ok)
        return;
    const payload = await response.json();
    el.workspaceList.innerHTML = '';
    for (const item of payload.workspaces || []) {
        const option = document.createElement('option');
        option.value = item.name;
        option.textContent = `${item.active ? '* ' : ''}${item.name}`;
        option.selected = Boolean(item.active);
        el.workspaceList.appendChild(option);
    }
}
async function loadHitmap() {
    if (!workspace?.design) {
        hitmap = null;
        topologyEditLayer = null;
        selectedRegionIds.clear();
        selectedEdgeIds.clear();
        invalidateDesignBase();
        return;
    }
    const response = await fetch('/api/design/hitmap');
    if (!response.ok) {
        hitmap = null;
        invalidateDesignBase();
        return;
    }
    hitmap = await response.json();
    invalidateDesignBase();
    sourceImage = new Image();
    sourceImage.onload = () => {
        invalidateDesignBase();
        drawDesign();
    };
    sourceImage.src = '/api/workspace-file/source.png';
}
async function loadTopologyEditLayer() {
    if (!workspace?.design) {
        topologyEditLayer = null;
        return;
    }
    const kind = workspace.design.active_vector_graph_kind || 'raster_topology';
    const response = await fetch(`/api/design/topology/edit-layer?kind=${encodeURIComponent(kind)}`);
    if (!response.ok) {
        topologyEditLayer = null;
        return;
    }
    topologyEditLayer = await response.json();
}
function render() {
    if (!workspace) {
        el.summary.textContent = 'No workspace.';
        el.candidates.textContent = '';
        el.regions.textContent = '';
        el.mergeSuggestions.textContent = '';
        hitmap = null;
        topologyEditLayer = null;
        selectedRegionIds.clear();
        drawDesign();
        return;
    }
    el.summary.textContent = JSON.stringify({
        source: workspace.source,
        candidates: workspace.candidates,
        subject_mask: workspace.subject_mask,
        valid_partition: workspace.validation.valid,
        region_count: workspace.validation.region_count,
        active_vector_graph: workspace.design?.active_vector_graph_kind || null,
        vector_vertices: topologyEditLayer?.vertices?.length || 0,
        vector_graphs: workspace.design?.vector_graphs || [],
    }, null, 2);
    if (workspace.design) {
        el.physicalWidth.value = workspace.design.physical_size.width;
        el.physicalHeight.value = workspace.design.physical_size.height;
        el.physicalUnit.value = workspace.design.physical_size.unit;
    }
    renderSelectedVeneerOptions();
    renderVeneerEditor();
    renderCandidates();
    renderMergeSuggestions();
    drawDesign();
    updateSelectionStatus();
    el.regions.innerHTML = '';
    for (const region of workspace.regions) {
        const item = document.createElement('article');
        item.className = 'region';
        const veneers = workspace.design?.veneers || [];
        const options = veneers
            .map((veneer) => `<option value="${veneer.veneer_id}" ${veneer.veneer_id === region.veneer_id ? 'selected' : ''}>${veneer.name}</option>`)
            .join('');
        item.innerHTML = `
      <strong>Region ${region.region_id}</strong>
      <span><span class="swatch" style="background:${rgb(region.color_rgb)}"></span>
      area ${region.area_physical.toFixed(3)}</span>
      <select data-region-id="${region.region_id}">${options}</select>
      <small>${region.warnings.join(', ') || 'ok'}</small>
    `;
        item.querySelector('select')?.addEventListener('change', async (event) => {
            const select = event.currentTarget;
            await assignVeneer(Number(select.dataset.regionId), select.value);
        });
        el.regions.appendChild(item);
    }
}
function renderSelectedVeneerOptions() {
    const veneers = workspace?.design?.veneers || [];
    el.selectedVeneer.innerHTML = veneers
        .map((veneer) => `<option value="${veneer.veneer_id}">${veneer.name}</option>`)
        .join('');
}
function toHex(color) {
    return `#${color.map((value) => value.toString(16).padStart(2, '0')).join('')}`;
}
function fromHex(hex) {
    const normalized = hex.replace('#', '').padEnd(6, '0').slice(0, 6);
    return [
        parseInt(normalized.slice(0, 2), 16) || 0,
        parseInt(normalized.slice(2, 4), 16) || 0,
        parseInt(normalized.slice(4, 6), 16) || 0,
    ];
}
function renderVeneerEditor() {
    const veneers = workspace?.design?.veneers || [];
    el.veneerEditor.innerHTML = '';
    if (!veneers.length) {
        el.veneerEditor.textContent = 'No veneers yet.';
        return;
    }
    for (const veneer of veneers) {
        const row = document.createElement('article');
        row.className = 'veneer-row';
        row.innerHTML = `
      <label>ID <input data-field="veneer_id" value="${veneer.veneer_id}" /></label>
      <label>Name <input data-field="name" value="${veneer.name}" /></label>
      <label>Color <input data-field="color_rgb" type="color" value="${toHex(veneer.color_rgb)}" /></label>
      <label>Sheet width <input data-field="sheet_width" type="number" min="0" step="0.1" value="${veneer.sheet_width || 0}" /></label>
      <label>Sheet height <input data-field="sheet_height" type="number" min="0" step="0.1" value="${veneer.sheet_height || 0}" /></label>
      <label>Sheet count <input data-field="sheet_count" type="number" min="0" step="1" value="${veneer.sheet_count || 0}" /></label>
      <label>Grain <input data-field="grain_direction" value="${veneer.grain_direction || ''}" /></label>
      <label class="wide">Texture URL <input data-field="texture_url" value="${veneer.texture_url || ''}" placeholder="https://..." /></label>
      <label class="wide">Notes <input data-field="notes" value="${veneer.notes || ''}" /></label>
      ${veneer.texture_url ? `<img class="texture-preview" alt="${veneer.name} texture" src="${veneer.texture_url}" />` : ''}
      <button data-remove="true" type="button">Remove</button>
    `;
        row.querySelector('[data-remove="true"]')?.addEventListener('click', () => row.remove());
        el.veneerEditor.appendChild(row);
    }
}
function collectVeneers() {
    return [...el.veneerEditor.querySelectorAll('.veneer-row')].map((row) => {
        const value = (field) => row.querySelector(`[data-field="${field}"]`)?.value || '';
        return {
            veneer_id: value('veneer_id').trim(),
            name: value('name').trim() || value('veneer_id').trim(),
            color_rgb: fromHex(value('color_rgb')),
            sheet_width: Number(value('sheet_width') || 0),
            sheet_height: Number(value('sheet_height') || 0),
            sheet_count: Number(value('sheet_count') || 0),
            grain_direction: value('grain_direction'),
            texture_url: value('texture_url'),
            notes: value('notes'),
        };
    });
}
function addVeneerRow() {
    const veneers = collectVeneers();
    const next = veneers.length + 1;
    const current = workspace?.design?.veneers || [];
    if (workspace?.design) {
        workspace.design.veneers = [
            ...current,
            {
                veneer_id: `veneer-${next}`,
                name: `Veneer ${next}`,
                color_rgb: [180, 130, 80],
                sheet_width: 0,
                sheet_height: 0,
                sheet_count: 0,
                grain_direction: '',
                texture_url: '',
                notes: '',
            },
        ];
    }
    renderVeneerEditor();
}
async function saveVeneers() {
    const veneers = collectVeneers();
    if (!veneers.length || veneers.some((veneer) => !veneer.veneer_id)) {
        setStatus('Each veneer needs an ID.', true);
        return;
    }
    const response = await fetch('/api/design/veneers', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(veneers),
    });
    if (!response.ok) {
        setStatus(await response.text(), true);
        return;
    }
    workspace = await response.json();
    await loadHitmap();
    setStatus('Saved veneer palette.');
    render();
}
function updateSelectionStatus() {
    invalidateDesignBase();
    const ids = [...selectedRegionIds].sort((a, b) => a - b);
    el.selectionStatus.textContent = ids.length
        ? `Selected ${ids.length} region(s): ${ids.join(', ')}`
        : 'No selected regions.';
    renderBoundarySummary(ids);
}
function renderBoundarySummary(ids) {
    el.boundarySummary.innerHTML = '';
    if (!ids.length || !workspace?.boundaries?.boundaries?.length) {
        el.boundarySummary.textContent = ids.length ? 'No selected boundaries.' : '';
        return;
    }
    const selected = new Set(ids);
    const touching = workspace.boundaries.boundaries.filter((boundary) => selected.has(boundary.region_a) || selected.has(boundary.region_b));
    const internal = touching.filter((boundary) => selected.has(boundary.region_a) && selected.has(boundary.region_b));
    const external = touching.filter((boundary) => !(selected.has(boundary.region_a) && selected.has(boundary.region_b)));
    const internalLength = internal.reduce((total, boundary) => total + boundary.edge_length_physical, 0);
    const externalLength = external.reduce((total, boundary) => total + boundary.edge_length_physical, 0);
    const simplifiable = touching.reduce((total, boundary) => total + (boundary.simplified_vertex_reduction || 0), 0);
    const summary = document.createElement('article');
    summary.className = 'boundary-card';
    summary.innerHTML = `
    <strong>Selected boundaries</strong>
    <span>${internal.length} internal, ${external.length} external</span>
    <small>${internalLength.toFixed(2)} internal + ${externalLength.toFixed(2)} external length</small>
    <small>${simplifiable} potential vertex reduction(s)</small>
  `;
    el.boundarySummary.appendChild(summary);
    for (const boundary of touching
        .slice()
        .sort((a, b) => {
        const reductionDelta = (b.simplified_vertex_reduction || 0) - (a.simplified_vertex_reduction || 0);
        return reductionDelta || b.edge_length_physical - a.edge_length_physical;
    })
        .slice(0, 5)) {
        const card = document.createElement('article');
        card.className = 'boundary-card';
        card.innerHTML = `
      <strong>${boundary.region_a} - ${boundary.region_b}</strong>
      <span>${boundary.edge_length_physical.toFixed(3)} physical units</span>
      <small>
        ${boundary.edge_px} boundary px, ${boundary.path_count || 0} shared path(s),
        ${boundary.vertex_count || 0} -> ${boundary.simplified_vertex_count || 0} vertices
      </small>
      <button type="button">Simplify this boundary</button>
      <button data-smooth="true" type="button">Smooth this boundary</button>
    `;
        card.querySelector('button')?.addEventListener('click', () => {
            void simplifyVectorBoundary(boundary.region_a, boundary.region_b);
        });
        card.querySelector('[data-smooth="true"]')?.addEventListener('click', () => {
            void smoothVectorBoundary(boundary.region_a, boundary.region_b);
        });
        el.boundarySummary.appendChild(card);
    }
}
function regionColor(regionId) {
    const region = workspace?.regions.find((item) => item.region_id === regionId);
    return region?.color_rgb || [180, 180, 180];
}
function canvasPoint(event) {
    const canvas = /** @type {HTMLCanvasElement} */ (el.designCanvas);
    const rect = canvas.getBoundingClientRect();
    return {
        x: Math.floor(((event.clientX - rect.left) / rect.width) * canvas.width),
        y: Math.floor(((event.clientY - rect.top) / rect.height) * canvas.height),
    };
}
function clampCanvasPoint(point) {
    const width = hitmap?.width || 1;
    const height = hitmap?.height || 1;
    return {
        x: Math.max(0, Math.min(width, point.x)),
        y: Math.max(0, Math.min(height, point.y)),
    };
}
function snappedCanvasPoint(point) {
    const clamped = clampCanvasPoint(point);
    if (!el.snapVertices.checked)
        return clamped;
    return {
        x: Math.round(clamped.x),
        y: Math.round(clamped.y),
    };
}
function labelAt(point) {
    if (!hitmap)
        return 0;
    const x = Math.max(0, Math.min(hitmap.width - 1, point.x));
    const y = Math.max(0, Math.min(hitmap.height - 1, point.y));
    return Number(hitmap.labels[y]?.[x] || 0);
}
function selectRect(start, end, additive) {
    if (!hitmap)
        return;
    const minX = Math.max(0, Math.min(start.x, end.x));
    const maxX = Math.min(hitmap.width - 1, Math.max(start.x, end.x));
    const minY = Math.max(0, Math.min(start.y, end.y));
    const maxY = Math.min(hitmap.height - 1, Math.max(start.y, end.y));
    if (!additive)
        selectedRegionIds.clear();
    for (let y = minY; y <= maxY; y += 1) {
        for (let x = minX; x <= maxX; x += 1) {
            const regionId = Number(hitmap.labels[y]?.[x] || 0);
            if (regionId > 0)
                selectedRegionIds.add(regionId);
        }
    }
    updateSelectionStatus();
    drawDesign();
}
function selectLasso(points, additive) {
    if (!hitmap || points.length < 2)
        return;
    if (!additive)
        selectedRegionIds.clear();
    for (let index = 1; index < points.length; index += 1) {
        const start = points[index - 1];
        const end = points[index];
        const steps = Math.max(Math.abs(end.x - start.x), Math.abs(end.y - start.y), 1);
        for (let step = 0; step <= steps; step += 1) {
            const point = {
                x: Math.round(start.x + ((end.x - start.x) * step) / steps),
                y: Math.round(start.y + ((end.y - start.y) * step) / steps),
            };
            const regionId = labelAt(point);
            if (regionId > 0)
                selectedRegionIds.add(regionId);
        }
    }
    updateSelectionStatus();
    drawDesign();
}
function selectionMode() {
    return el.selectionMode.value || 'box';
}
function maskBrushRole() {
    const mode = selectionMode();
    if (mode === 'mask-subject')
        return 'subject';
    if (mode === 'mask-background')
        return 'background';
    return '';
}
function vectorEditMode() {
    return selectionMode() === 'vector-edit';
}
function nearestVertex(point) {
    if (!topologyEditLayer?.vertices?.length)
        return null;
    const radius = Math.max(3, (hitmap?.width || 1) / 120);
    let best = null;
    let bestDistance = Infinity;
    for (const vertex of topologyEditLayer.vertices) {
        const [x, y] = vertex.point;
        const distance = Math.hypot(point.x - x, point.y - y);
        if (distance < bestDistance && distance <= radius) {
            best = vertex;
            bestDistance = distance;
        }
    }
    return best;
}
function pointSegmentDistance(point, start, end) {
    const dx = end[0] - start[0];
    const dy = end[1] - start[1];
    const lengthSquared = dx * dx + dy * dy || 1;
    const t = Math.max(0, Math.min(1, ((point.x - start[0]) * dx + (point.y - start[1]) * dy) / lengthSquared));
    const x = start[0] + t * dx;
    const y = start[1] + t * dy;
    return Math.hypot(point.x - x, point.y - y);
}
function nearestEdge(point) {
    if (!topologyEditLayer?.edges?.length)
        return null;
    const radius = Math.max(3, (hitmap?.width || 1) / 140);
    let best = null;
    let bestDistance = Infinity;
    for (const edge of topologyEditLayer.edges) {
        const path = edge.path || [];
        for (let index = 1; index < path.length; index += 1) {
            const distance = pointSegmentDistance(point, path[index - 1], path[index]);
            if (distance < bestDistance && distance <= radius) {
                best = edge;
                bestDistance = distance;
            }
        }
    }
    return best;
}
function drawDesign() {
    const canvas = /** @type {HTMLCanvasElement} */ (el.designCanvas);
    const ctx = canvas.getContext('2d');
    if (!ctx)
        return;
    const width = hitmap?.width || 1;
    const height = hitmap?.height || 1;
    canvas.width = width;
    canvas.height = height;
    applyCanvasZoom();
    ctx.clearRect(0, 0, width, height);
    if (!workspace || !hitmap)
        return;
    const baseKey = designBaseKey(width, height);
    if (!cachedBaseCanvas || cachedBaseKey !== baseKey) {
        const base = document.createElement('canvas');
        base.width = width;
        base.height = height;
        const baseCtx = base.getContext('2d');
        if (!baseCtx)
            return;
        baseCtx.clearRect(0, 0, width, height);
        if (sourceImage.complete && sourceImage.naturalWidth) {
            baseCtx.drawImage(sourceImage, 0, 0, width, height);
        }
        const imageData = baseCtx.getImageData(0, 0, width, height);
        for (let y = 0; y < height; y += 1) {
            for (let x = 0; x < width; x += 1) {
                const maskValue = Number(hitmap.subject_mask[y]?.[x] || 0);
                const regionId = Number(hitmap.labels[y]?.[x] || 0);
                const offset = (y * width + x) * 4;
                if (el.showMask.checked && maskValue > 0) {
                    const maskColor = maskValue === 1 ? [225, 126, 72] : [70, 130, 190];
                    imageData.data[offset] = Math.round(imageData.data[offset] * 0.55 + maskColor[0] * 0.45);
                    imageData.data[offset + 1] = Math.round(imageData.data[offset + 1] * 0.55 + maskColor[1] * 0.45);
                    imageData.data[offset + 2] = Math.round(imageData.data[offset + 2] * 0.55 + maskColor[2] * 0.45);
                    imageData.data[offset + 3] = 255;
                }
                if (!selectedRegionIds.has(regionId))
                    continue;
                const color = regionColor(regionId);
                imageData.data[offset] = Math.round(imageData.data[offset] * 0.45 + color[0] * 0.55);
                imageData.data[offset + 1] = Math.round(imageData.data[offset + 1] * 0.45 + color[1] * 0.55);
                imageData.data[offset + 2] = Math.round(imageData.data[offset + 2] * 0.45 + color[2] * 0.55);
                imageData.data[offset + 3] = 255;
            }
        }
        baseCtx.putImageData(imageData, 0, 0);
        cachedBaseCanvas = base;
        cachedBaseKey = baseKey;
    }
    ctx.drawImage(cachedBaseCanvas, 0, 0);
    if (dragStart && dragCurrent) {
        ctx.strokeStyle = '#f4f0dc';
        ctx.lineWidth = Math.max(1, width / 300);
        ctx.setLineDash([6, 4]);
        ctx.strokeRect(dragStart.x, dragStart.y, dragCurrent.x - dragStart.x, dragCurrent.y - dragStart.y);
        ctx.setLineDash([]);
    }
    if (lassoPoints.length > 1) {
        const role = maskBrushRole();
        ctx.strokeStyle = role === 'subject' ? '#e17e48' : role === 'background' ? '#4682be' : '#f4f0dc';
        ctx.lineWidth = role ? Number(el.brushRadius.value || 5) * 2 : Math.max(1, width / 220);
        ctx.beginPath();
        ctx.moveTo(lassoPoints[0].x, lassoPoints[0].y);
        for (const point of lassoPoints.slice(1)) {
            ctx.lineTo(point.x, point.y);
        }
        ctx.stroke();
    }
    if (vectorEditMode() && topologyEditLayer?.vertices?.length) {
        ctx.save();
        ctx.lineWidth = Math.max(1, width / 260);
        ctx.strokeStyle = 'rgba(12, 31, 38, 0.72)';
        for (const edge of topologyEditLayer.edges || []) {
            if (!edge.path?.length)
                continue;
            const selectedEdge = selectedEdgeIds.has(edge.edge_id);
            ctx.strokeStyle = selectedEdge ? 'rgba(70, 130, 190, 0.96)' : 'rgba(12, 31, 38, 0.72)';
            ctx.lineWidth = Math.max(selectedEdge ? 2 : 1, width / (selectedEdge ? 150 : 260));
            ctx.beginPath();
            ctx.moveTo(edge.path[0][0], edge.path[0][1]);
            for (const point of edge.path.slice(1)) {
                ctx.lineTo(point[0], point[1]);
            }
            ctx.stroke();
        }
        if (pendingVertexMove) {
            const vertexById = new Map(topologyEditLayer.vertices.map((vertex) => [
                vertex.vertex_id,
                { x: vertex.point[0], y: vertex.point[1] },
            ]));
            vertexById.set(pendingVertexMove.vertexId, pendingVertexMove.point);
            ctx.strokeStyle = 'rgba(225, 126, 72, 0.95)';
            ctx.lineWidth = Math.max(1.5, width / 160);
            ctx.setLineDash([5, 3]);
            for (const edge of topologyEditLayer.edges || []) {
                if (!(edge.vertex_ids || []).includes(pendingVertexMove.vertexId))
                    continue;
                const points = (edge.vertex_ids || [])
                    .map((vertexId) => vertexById.get(vertexId))
                    .filter(Boolean);
                if (points.length < 2)
                    continue;
                ctx.beginPath();
                ctx.moveTo(points[0].x, points[0].y);
                for (const point of points.slice(1)) {
                    ctx.lineTo(point.x, point.y);
                }
                ctx.stroke();
            }
            ctx.setLineDash([]);
            ctx.strokeStyle = '#e17e48';
            ctx.fillStyle = '#f7c873';
            ctx.beginPath();
            ctx.moveTo(pendingVertexMove.sourcePoint.x, pendingVertexMove.sourcePoint.y);
            ctx.lineTo(pendingVertexMove.point.x, pendingVertexMove.point.y);
            ctx.stroke();
            ctx.beginPath();
            ctx.arc(pendingVertexMove.point.x, pendingVertexMove.point.y, Math.max(4, width / 140), 0, Math.PI * 2);
            ctx.fill();
            ctx.stroke();
        }
        for (const vertex of topologyEditLayer.vertices) {
            const [x, y] = vertex.point;
            const isActive = activeVertexDrag?.vertexId === vertex.vertex_id;
            const isHovered = hoveredVertex?.vertex_id === vertex.vertex_id;
            const drawPoint = isActive ? activeVertexDrag.current : { x, y };
            ctx.fillStyle = isActive ? '#e17e48' : isHovered ? '#f7c873' : '#f4f0dc';
            ctx.strokeStyle = '#10232a';
            ctx.beginPath();
            ctx.arc(drawPoint.x, drawPoint.y, Math.max(isHovered || isActive ? 3 : 2, width / 180), 0, Math.PI * 2);
            ctx.fill();
            ctx.stroke();
            if (isHovered || isActive) {
                ctx.font = `${Math.max(8, width / 55)}px sans-serif`;
                ctx.fillStyle = '#10232a';
                ctx.fillText(`v${vertex.vertex_id} ${Math.round(drawPoint.x)},${Math.round(drawPoint.y)}`, drawPoint.x + 5, drawPoint.y - 5);
            }
        }
        ctx.restore();
    }
}
function applyCanvasZoom() {
    el.designCanvas.style.width = `${canvasZoom}%`;
    el.zoomLabel.textContent = `${canvasZoom}%`;
    el.canvasZoom.value = String(canvasZoom);
}
function setCanvasZoom(nextZoom) {
    canvasZoom = Math.max(25, Math.min(400, Number(nextZoom) || 100));
    applyCanvasZoom();
}
async function updateSize() {
    if (!workspace?.design) {
        setStatus('Create a design before changing size.', true);
        return;
    }
    const response = await fetch('/api/design/size', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            width: Number(el.physicalWidth.value || 8),
            height: Number(el.physicalHeight.value || 10),
            unit: String(el.physicalUnit.value || 'in'),
        }),
    });
    if (!response.ok) {
        setStatus(await response.text(), true);
        return;
    }
    workspace = await response.json();
    setStatus('Updated physical size.');
    render();
}
function renderCandidates() {
    el.candidates.innerHTML = '';
    if (!workspace?.candidates.length) {
        el.candidates.textContent = 'No candidate partitions yet.';
        return;
    }
    for (const candidate of workspace.candidates) {
        const item = document.createElement('article');
        item.className = 'candidate';
        item.innerHTML = `
      <img alt="${candidate.candidate_id} preview" src="/api/workspace-file/${candidate.preview_path}" />
      <strong>${candidate.candidate_id}</strong>
      <small>${candidate.region_count} regions, compactness ${candidate.compactness}</small>
      <button type="button">Use for design</button>
    `;
        item.querySelector('button')?.addEventListener('click', async () => {
            await createDesign(candidate.candidate_id);
        });
        el.candidates.appendChild(item);
    }
}
function renderMergeSuggestions() {
    el.mergeSuggestions.innerHTML = '';
    const suggestions = workspace?.merge_suggestions || [];
    if (!suggestions.length) {
        el.mergeSuggestions.textContent = 'No small/thin merge suggestions.';
        return;
    }
    for (const suggestion of suggestions.slice(0, 8)) {
        const item = document.createElement('div');
        item.className = 'suggestion';
        item.innerHTML = `
      <span>
        Merge ${suggestion.region_id} into ${suggestion.target_region_id}
        <small>${suggestion.reason}${suggestion.same_veneer ? ', same veneer' : ''}</small>
      </span>
      <button type="button">Merge</button>
    `;
        item.querySelector('button')?.addEventListener('click', async () => {
            await mergeRegions([suggestion.region_id, suggestion.target_region_id]);
        });
        el.mergeSuggestions.appendChild(item);
    }
}
async function openImage() {
    if (!el.imageInput.files?.length) {
        setStatus('Choose an image first.', true);
        return;
    }
    const form = new FormData();
    form.append('image', el.imageInput.files[0]);
    form.append('max_edge', el.maxEdge.value || '768');
    form.append('target_regions', el.targetRegions.value || '80');
    form.append('compactness', el.compactness.value || '18');
    form.append('marquetry_mode', el.marquetryMode.checked ? 'true' : 'false');
    if (el.workspaceName.value)
        form.append('workspace_name', el.workspaceName.value);
    setStatus('Building first partition...');
    const response = await fetch('/api/workspace/open-image', { method: 'POST', body: form });
    if (!response.ok) {
        setStatus(await response.text(), true);
        return;
    }
    workspace = await response.json();
    selectedRegionIds.clear();
    await loadHitmap();
    await loadTopologyEditLayer();
    await loadWorkspaces();
    setStatus('Workspace ready.');
    render();
}
async function openSelectedWorkspace() {
    if (!el.workspaceList.value) {
        setStatus('Choose a workspace to open.', true);
        return;
    }
    const response = await fetch('/api/workspace/open', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name: el.workspaceList.value }),
    });
    if (!response.ok) {
        setStatus(await response.text(), true);
        return;
    }
    workspace = await response.json();
    selectedRegionIds.clear();
    await loadHitmap();
    await loadTopologyEditLayer();
    await loadWorkspaces();
    setStatus(`Opened workspace ${el.workspaceList.value}.`);
    render();
}
async function deleteSelectedWorkspace() {
    if (!el.workspaceList.value) {
        setStatus('Choose a workspace to delete.', true);
        return;
    }
    const name = el.workspaceList.value;
    const response = await fetch(`/api/workspace/${encodeURIComponent(name)}`, {
        method: 'DELETE',
    });
    if (!response.ok) {
        setStatus(await response.text(), true);
        return;
    }
    if (workspace?.workspace_dir?.endsWith(`/${name}`)) {
        workspace = null;
        hitmap = null;
        selectedRegionIds.clear();
    }
    await loadWorkspaces();
    setStatus(`Deleted workspace ${name}.`);
    render();
}
async function generateCandidateGrid() {
    if (!workspace) {
        setStatus('Open an image before generating a grid.', true);
        return;
    }
    setStatus('Generating candidate grid...');
    const response = await fetch('/api/candidate-grid', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            rows: Number(el.gridRows.value || 4),
            cols: Number(el.gridCols.value || 4),
            min_regions: Number(el.minRegions.value || 20),
            max_regions: Number(el.maxRegions.value || 140),
            min_compactness: Number(el.minCompactness.value || 4),
            max_compactness: Number(el.maxCompactness.value || 28),
            use_detail_zones: Boolean(el.useDetailZones.checked),
            use_subject_mask: Boolean(el.useSubjectMask.checked),
            marquetry_mode: Boolean(el.gridMarquetryMode.checked),
        }),
    });
    if (!response.ok) {
        setStatus(await response.text(), true);
        return;
    }
    workspace = await response.json();
    setStatus('Candidate grid ready.');
    render();
}
async function createDesign(candidateId) {
    const response = await fetch('/api/design', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ candidate_id: candidateId, width: 8, height: 10, unit: 'in' }),
    });
    if (!response.ok) {
        setStatus(await response.text(), true);
        return;
    }
    workspace = await response.json();
    selectedRegionIds.clear();
    await loadHitmap();
    await loadTopologyEditLayer();
    setStatus(`Design seeded from ${candidateId}.`);
    render();
}
async function assignVeneer(regionId, veneerId) {
    const response = await fetch('/api/design/veneer', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ region_id: regionId, veneer_id: veneerId }),
    });
    if (!response.ok) {
        setStatus(await response.text(), true);
        return;
    }
    workspace = await response.json();
    await loadHitmap();
    await loadTopologyEditLayer();
    setStatus(`Assigned region ${regionId}.`);
    render();
}
async function assignSelected() {
    if (!selectedRegionIds.size) {
        setStatus('Select at least one region first.', true);
        return;
    }
    const response = await fetch('/api/design/veneer-bulk', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            region_ids: [...selectedRegionIds],
            veneer_id: el.selectedVeneer.value,
        }),
    });
    if (!response.ok) {
        setStatus(await response.text(), true);
        return;
    }
    workspace = await response.json();
    await loadHitmap();
    await loadTopologyEditLayer();
    setStatus(`Assigned ${selectedRegionIds.size} selected region(s).`);
    render();
}
async function mergeRegions(regionIds) {
    const response = await fetch('/api/design/merge', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ region_ids: regionIds }),
    });
    if (!response.ok) {
        setStatus(await response.text(), true);
        return;
    }
    workspace = await response.json();
    selectedRegionIds.clear();
    await loadHitmap();
    await loadTopologyEditLayer();
    setStatus(`Merged ${regionIds.join(', ')}.`);
    render();
}
async function mergeSelected() {
    if (selectedRegionIds.size < 2) {
        setStatus('Select at least two connected regions to merge.', true);
        return;
    }
    await mergeRegions([...selectedRegionIds]);
}
async function splitSelected() {
    if (selectedRegionIds.size !== 1) {
        setStatus('Select exactly one region to split.', true);
        return;
    }
    const [regionId] = [...selectedRegionIds];
    const response = await fetch('/api/design/split', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            region_id: regionId,
            target_parts: Number(el.splitParts.value || 3),
            compactness: Number(el.splitCompactness.value || 12),
        }),
    });
    if (!response.ok) {
        setStatus(await response.text(), true);
        return;
    }
    workspace = await response.json();
    selectedRegionIds.clear();
    await loadHitmap();
    await loadTopologyEditLayer();
    setStatus(`Split region ${regionId}.`);
    render();
}
async function lockSelected(locked) {
    if (!selectedRegionIds.size) {
        setStatus('Select at least one region first.', true);
        return;
    }
    const response = await fetch('/api/design/lock', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ region_ids: [...selectedRegionIds], locked }),
    });
    if (!response.ok) {
        setStatus(await response.text(), true);
        return;
    }
    workspace = await response.json();
    await loadHitmap();
    setStatus(`${locked ? 'Locked' : 'Unlocked'} ${selectedRegionIds.size} region(s).`);
    render();
}
async function focusSelected() {
    if (!selectedRegionIds.size) {
        setStatus('Select at least one region for a focus zone.', true);
        return;
    }
    const response = await fetch('/api/design/detail-zone-for-regions', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            region_ids: [...selectedRegionIds],
            name: 'Selected focus',
            detail_multiplier: Number(el.focusMultiplier.value || 3),
        }),
    });
    if (!response.ok) {
        setStatus(await response.text(), true);
        return;
    }
    workspace = await response.json();
    await loadHitmap();
    setStatus('Created focus zone from selected regions.');
    render();
}
async function markSubjectMask(role) {
    if (!selectedRegionIds.size) {
        setStatus('Select at least one region first.', true);
        return;
    }
    const response = await fetch('/api/design/subject-mask-for-regions', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            region_ids: [...selectedRegionIds],
            role,
        }),
    });
    if (!response.ok) {
        setStatus(await response.text(), true);
        return;
    }
    workspace = await response.json();
    await loadHitmap();
    setStatus(`Marked ${selectedRegionIds.size} region(s) as ${role}.`);
    render();
}
async function paintSubjectMaskStroke(points, role) {
    if (!points.length)
        return;
    const response = await fetch('/api/design/subject-mask-stroke', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            points: points.map((point) => [point.x, point.y]),
            role,
            brush_radius: Number(el.brushRadius.value || 5),
        }),
    });
    if (!response.ok) {
        setStatus(await response.text(), true);
        return;
    }
    workspace = await response.json();
    await loadHitmap();
    setStatus(`Painted ${role} mask.`);
    render();
}
async function applyFocus() {
    const response = await fetch('/api/design/apply-detail-zones', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            max_splits: 10,
            compactness: Number(el.splitCompactness.value || 10),
        }),
    });
    if (!response.ok) {
        setStatus(await response.text(), true);
        return;
    }
    workspace = await response.json();
    selectedRegionIds.clear();
    await loadHitmap();
    setStatus(`Applied ${workspace.applied_detail_split_count || 0} focus split(s).`);
    render();
}
async function repairSmall() {
    const response = await fetch('/api/design/repair-small-regions', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            max_area: Number(el.repairArea.value || 0.05),
            max_repairs: 25,
        }),
    });
    if (!response.ok) {
        setStatus(await response.text(), true);
        return;
    }
    workspace = await response.json();
    selectedRegionIds.clear();
    await loadHitmap();
    await loadTopologyEditLayer();
    setStatus(`Repaired ${workspace.repaired_region_count || 0} small region(s).`);
    render();
}
async function cuttabilityCleanup() {
    const response = await fetch('/api/design/cuttability-cleanup', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            max_repairs: 25,
            min_area: Number(el.repairArea.value || 0.05),
            smooth_iterations: Number(el.smoothPasses.value || 1),
            vector_tolerance: Number(el.vectorTolerance.value || 1.25),
        }),
    });
    if (!response.ok) {
        setStatus(await response.text(), true);
        return;
    }
    workspace = await response.json();
    selectedRegionIds.clear();
    await loadHitmap();
    await loadTopologyEditLayer();
    const result = workspace.cuttability_cleanup || {
        repaired_region_count: 0,
        smoothed_pixel_count: 0,
        vector_simplified: false,
        remaining_warning_region_ids: [],
    };
    setStatus(`Cleanup: repaired ${result.repaired_region_count || 0}, smoothed ${result.smoothed_pixel_count || 0}, vector ${result.vector_simplified ? 'simplified' : 'unchanged'}.`);
    render();
}
async function smoothBoundaries() {
    const regionIds = [...selectedRegionIds];
    const response = await fetch('/api/design/smooth-boundaries', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            iterations: Number(el.smoothPasses.value || 1),
            region_ids: regionIds,
        }),
    });
    if (!response.ok) {
        setStatus(await response.text(), true);
        return;
    }
    workspace = await response.json();
    await loadHitmap();
    await loadTopologyEditLayer();
    const currentIds = new Set(workspace.regions.map((region) => region.region_id));
    selectedRegionIds = new Set(regionIds.filter((regionId) => currentIds.has(regionId)));
    setStatus(`Smoothed ${workspace.smoothed_pixel_count || 0} boundary pixel(s)${regionIds.length ? ' in selected regions' : ''}.`);
    render();
}
async function removeNotches() {
    const regionIds = [...selectedRegionIds];
    const response = await fetch('/api/design/remove-notches', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            iterations: Number(el.smoothPasses.value || 1),
            region_ids: regionIds,
            min_neighbor_votes: 5,
        }),
    });
    if (!response.ok) {
        setStatus(await response.text(), true);
        return;
    }
    workspace = await response.json();
    await loadHitmap();
    await loadTopologyEditLayer();
    const currentIds = new Set(workspace.regions.map((region) => region.region_id));
    selectedRegionIds = new Set(regionIds.filter((regionId) => currentIds.has(regionId)));
    setStatus(`Removed ${workspace.notch_removed_pixel_count || 0} notch pixel(s)${regionIds.length ? ' in selected regions' : ''}.`);
    render();
}
async function simplifyVectorGraphAll() {
    const tolerance = Number(el.vectorTolerance.value || 1.25);
    const response = await fetch('/api/design/topology/simplify', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            tolerance,
            source_kind: workspace?.design?.active_vector_graph_kind || 'raster_topology',
            target_kind: 'simplified_topology',
        }),
    });
    if (!response.ok) {
        setStatus(await response.text(), true);
        return;
    }
    const promoteResponse = await fetch('/api/design/topology/promote', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ kind: 'simplified_topology' }),
    });
    if (!promoteResponse.ok) {
        setStatus(await promoteResponse.text(), true);
        return;
    }
    await refresh();
    setStatus(`Simplified and promoted graph at tolerance ${tolerance}.`);
}
async function previewVectorSimplify() {
    const tolerance = Number(el.vectorTolerance.value || 1.25);
    const response = await fetch('/api/design/topology/preview-simplify', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            tolerance,
            region_ids: [...selectedRegionIds],
            source_kind: workspace?.design?.active_vector_graph_kind || null,
        }),
    });
    if (!response.ok) {
        setStatus(await response.text(), true);
        return;
    }
    const preview = await response.json();
    el.packOutput.textContent = JSON.stringify(preview, null, 2);
    setStatus(preview.valid
        ? `Preview valid: ${preview.vertex_reduction} vector vertex reduction(s) on ${preview.target}.`
        : 'Preview invalid: simplification would break puzzle coverage.', !preview.valid);
}
async function simplifyVectorGraphSelected() {
    if (!selectedRegionIds.size) {
        setStatus('Select at least one region before simplifying selected boundaries.', true);
        return;
    }
    const tolerance = Number(el.vectorTolerance.value || 1.25);
    const response = await fetch('/api/design/topology/simplify-selected', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            region_ids: [...selectedRegionIds],
            tolerance,
            source_kind: workspace?.design?.active_vector_graph_kind || null,
            target_kind: 'edited_topology',
        }),
    });
    if (!response.ok) {
        setStatus(await response.text(), true);
        return;
    }
    workspace = await response.json();
    await loadHitmap();
    await loadTopologyEditLayer();
    setStatus(`Simplified selected vector boundaries at tolerance ${tolerance}.`);
    render();
}
async function smoothVectorSelected() {
    if (!selectedEdgeIds.size) {
        setStatus('Select one or more vector edges in vector-handle mode first.', true);
        return;
    }
    const response = await fetch('/api/design/topology/smooth-edges', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            edge_ids: [...selectedEdgeIds],
            strength: Number(el.vectorSmoothStrength.value || 0.35),
            iterations: Number(el.smoothPasses.value || 2),
            source_kind: workspace?.design?.active_vector_graph_kind || null,
            target_kind: 'edited_topology',
        }),
    });
    if (!response.ok) {
        setStatus(await response.text(), true);
        return;
    }
    workspace = await response.json();
    selectedEdgeIds.clear();
    await loadHitmap();
    await loadTopologyEditLayer();
    setStatus('Smoothed selected vector edge(s).');
    render();
}
async function smoothVectorBoundary(regionA, regionB) {
    const response = await fetch('/api/design/topology/smooth-edges', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            region_a: regionA,
            region_b: regionB,
            strength: Number(el.vectorSmoothStrength.value || 0.35),
            iterations: Number(el.smoothPasses.value || 2),
            source_kind: workspace?.design?.active_vector_graph_kind || null,
            target_kind: 'edited_topology',
        }),
    });
    if (!response.ok) {
        setStatus(await response.text(), true);
        return;
    }
    workspace = await response.json();
    selectedEdgeIds.clear();
    await loadHitmap();
    await loadTopologyEditLayer();
    setStatus(`Smoothed boundary ${regionA}-${regionB}.`);
    render();
}
async function simplifyVectorBoundary(regionA, regionB) {
    const tolerance = Number(el.vectorTolerance.value || 1.25);
    const response = await fetch('/api/design/topology/simplify-boundary', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            region_a: regionA,
            region_b: regionB,
            tolerance,
            source_kind: workspace?.design?.active_vector_graph_kind || null,
            target_kind: 'edited_topology',
        }),
    });
    if (!response.ok) {
        setStatus(await response.text(), true);
        return;
    }
    workspace = await response.json();
    pendingVertexMove = null;
    await loadHitmap();
    await loadTopologyEditLayer();
    setStatus(`Simplified boundary ${regionA}-${regionB} at tolerance ${tolerance}.`);
    render();
}
async function promoteVectorGraph() {
    const kind = String(el.vectorKind.value || 'edited_topology').trim();
    const response = await fetch('/api/design/topology/promote', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ kind }),
    });
    if (!response.ok) {
        setStatus(await response.text(), true);
        return;
    }
    workspace = await response.json();
    await loadHitmap();
    await loadTopologyEditLayer();
    setStatus(`Promoted ${kind} as output geometry.`);
    render();
}
async function moveVectorVertex() {
    const vertexId = pendingVertexMove?.vertexId || Number(el.vertexId.value || 0);
    if (!vertexId) {
        setStatus('Enter a vector vertex ID to move.', true);
        return;
    }
    const point = pendingVertexMove?.point || snappedCanvasPoint({
        x: Number(el.vertexX.value || 0),
        y: Number(el.vertexY.value || 0),
    });
    if (!pendingVertexMove) {
        const preview = await previewVectorVertexMove(false);
        if (!preview?.valid)
            return;
    }
    const response = await fetch('/api/design/topology/move-vertex', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            vertex_id: vertexId,
            point: [point.x, point.y],
            source_kind: pendingVertexMove?.sourceKind || workspace?.design?.active_vector_graph_kind || null,
            target_kind: 'edited_topology',
        }),
    });
    if (!response.ok) {
        setStatus(await response.text(), true);
        return;
    }
    workspace = await response.json();
    pendingVertexMove = null;
    await loadHitmap();
    await loadTopologyEditLayer();
    setStatus(`Moved vector vertex ${vertexId} to ${point.x}, ${point.y}.`);
    render();
}
function vectorMoveInvalidReason(preview) {
    if (!preview)
        return 'unknown validation failure';
    const validation = preview.graph_validation;
    if (!validation)
        return preview.reason || 'invalid move';
    const parts = [];
    if (validation.missing_region_ids?.length) {
        parts.push(`missing region(s) ${validation.missing_region_ids.join(', ')}`);
    }
    if (validation.duplicate_region_ids?.length) {
        parts.push(`duplicate region(s) ${validation.duplicate_region_ids.join(', ')}`);
    }
    if (validation.extra_region_ids?.length) {
        parts.push(`extra region(s) ${validation.extra_region_ids.join(', ')}`);
    }
    if (validation.area_delta > 0.01) {
        parts.push(`area delta ${validation.area_delta.toFixed(3)}`);
    }
    return parts.join('; ') || preview.reason || 'move would break puzzle coverage';
}
async function previewVectorVertexMove(showValidStatus = true) {
    const vertexId = Number(el.vertexId.value || 0);
    if (!vertexId) {
        setStatus('Enter a vector vertex ID to preview.', true);
        return null;
    }
    const point = snappedCanvasPoint({
        x: Number(el.vertexX.value || 0),
        y: Number(el.vertexY.value || 0),
    });
    const response = await fetch('/api/design/topology/preview-move-vertex', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            vertex_id: vertexId,
            point: [point.x, point.y],
            source_kind: workspace?.design?.active_vector_graph_kind || null,
            target_kind: 'edited_topology',
        }),
    });
    if (!response.ok) {
        setStatus(await response.text(), true);
        return null;
    }
    const preview = /** @type {VertexMovePreview} */ (await response.json());
    el.packOutput.textContent = JSON.stringify(preview, null, 2);
    if (!preview.valid) {
        pendingVertexMove = null;
        drawDesign();
        setStatus(`Invalid vector move: ${vectorMoveInvalidReason(preview)}.`, true);
        return preview;
    }
    const vertex = topologyEditLayer?.vertices?.find((item) => item.vertex_id === vertexId);
    pendingVertexMove = {
        vertexId,
        sourcePoint: vertex
            ? { x: Number(vertex.point[0]), y: Number(vertex.point[1]) }
            : { x: point.x, y: point.y },
        point,
        sourceKind: preview.source_kind || workspace?.design?.active_vector_graph_kind || null,
    };
    drawDesign();
    if (showValidStatus) {
        setStatus(`Preview valid for vertex ${vertexId} at ${point.x}, ${point.y}. Accept preview to save.`);
    }
    return preview;
}
function cancelVertexPreview() {
    pendingVertexMove = null;
    setStatus('Canceled vector move preview.');
    drawDesign();
}
async function applySuggestions() {
    const response = await fetch('/api/design/apply-merge-suggestions', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ max_merges: 10 }),
    });
    if (!response.ok) {
        setStatus(await response.text(), true);
        return;
    }
    workspace = await response.json();
    selectedRegionIds.clear();
    await loadHitmap();
    await loadTopologyEditLayer();
    setStatus(`Applied ${workspace.applied_merge_count || 0} merge suggestion(s).`);
    render();
}
async function undo() {
    const response = await fetch('/api/design/undo', { method: 'POST' });
    if (!response.ok) {
        setStatus(await response.text(), true);
        return;
    }
    workspace = await response.json();
    selectedRegionIds.clear();
    await loadHitmap();
    await loadTopologyEditLayer();
    setStatus('Undid last edit.');
    render();
}
async function pack() {
    const response = await fetch('/api/pack', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ output_dir: './exported' }),
    });
    if (!response.ok) {
        setStatus(await response.text(), true);
        return;
    }
    const manifest = await response.json();
    renderPackSummary(manifest);
    el.packOutput.textContent = JSON.stringify(manifest, null, 2);
    const warnings = manifest.sheets.filter((sheet) => sheet.over_stock_capacity).length;
    setStatus(warnings ? `Pack manifest written with ${warnings} stock warning(s).` : 'Pack manifest written.', warnings > 0);
}
async function cleanupReport() {
    const response = await fetch('/api/cleanup-report');
    if (!response.ok) {
        setStatus(await response.text(), true);
        return;
    }
    const report = /** @type {CleanupReport} */ (await response.json());
    el.packOutput.textContent = JSON.stringify(report, null, 2);
    setStatus(`Cleanup report: ${report.readiness} (${report.readiness_score}/100), ${report.region_count} regions, coverage ${report.coverage.valid ? 'valid' : 'invalid'}, ${report.merge_suggestion_count} merge suggestion(s), ${report.jagged_boundary_count} jagged boundary group(s).`);
}
/** @param {PackManifest} manifest */
function renderPackSummary(manifest) {
    el.packSummary.innerHTML = '';
    if (!manifest.sheets?.length) {
        el.packSummary.textContent = 'No pieces to pack.';
        return;
    }
    for (const sheet of manifest.sheets) {
        const unplaced = sheet.piece_count - sheet.placed_piece_count;
        const shortfall = sheet.stock_shortfall_count || 0;
        const card = document.createElement('article');
        card.className = `pack-card${sheet.over_stock_capacity || shortfall ? ' warning' : ''}`;
        card.innerHTML = `
      <strong>${sheet.veneer_id}</strong>
      <span>${sheet.placed_piece_count}/${sheet.piece_count} pieces placed</span>
      <span>${sheet.sheet_count_used} sheet(s) used${sheet.available_sheet_count ? ` of ${sheet.available_sheet_count}` : ''}</span>
      <span>${sheet.recommended_sheet_count} sheet(s) recommended${shortfall ? `, buy ${shortfall}` : ''}</span>
      <span>Sheet: ${sheet.sheet_width} x ${sheet.sheet_height}</span>
      <span>${(sheet.material_utilization * 100).toFixed(1)}% bbox utilization</span>
      <span>${sheet.total_piece_area.toFixed(2)} actual area, ${sheet.total_bounding_box_area.toFixed(2)} packed bbox area</span>
      <small>${unplaced ? `${unplaced} piece(s) did not fit` : 'All pieces fit bounding boxes'}</small>
    `;
        el.packSummary.appendChild(card);
    }
}
el.openImage.addEventListener('click', openImage);
el.refreshWorkspaces.addEventListener('click', loadWorkspaces);
el.openWorkspace.addEventListener('click', openSelectedWorkspace);
el.deleteWorkspace.addEventListener('click', deleteSelectedWorkspace);
el.candidateGrid.addEventListener('click', generateCandidateGrid);
el.updateSize.addEventListener('click', updateSize);
el.addVeneer.addEventListener('click', addVeneerRow);
el.saveVeneers.addEventListener('click', saveVeneers);
el.assignSelected.addEventListener('click', assignSelected);
el.mergeSelected.addEventListener('click', mergeSelected);
el.splitSelected.addEventListener('click', splitSelected);
el.lockSelected.addEventListener('click', () => lockSelected(true));
el.unlockSelected.addEventListener('click', () => lockSelected(false));
el.markSubject.addEventListener('click', () => markSubjectMask('subject'));
el.markBackground.addEventListener('click', () => markSubjectMask('background'));
el.focusSelected.addEventListener('click', focusSelected);
el.applyFocus.addEventListener('click', applyFocus);
el.repairSmall.addEventListener('click', repairSmall);
el.cuttabilityCleanup.addEventListener('click', cuttabilityCleanup);
el.smoothBoundaries.addEventListener('click', smoothBoundaries);
el.removeNotches.addEventListener('click', removeNotches);
el.applySuggestions.addEventListener('click', applySuggestions);
el.vectorSimplifyAll.addEventListener('click', simplifyVectorGraphAll);
el.previewVectorSimplify.addEventListener('click', previewVectorSimplify);
el.vectorSimplifySelected.addEventListener('click', simplifyVectorGraphSelected);
el.smoothVectorSelected.addEventListener('click', smoothVectorSelected);
el.vectorPromote.addEventListener('click', promoteVectorGraph);
el.previewVertexMove.addEventListener('click', () => {
    void previewVectorVertexMove(true);
});
el.acceptVertexPreview.addEventListener('click', moveVectorVertex);
el.cancelVertexPreview.addEventListener('click', cancelVertexPreview);
el.moveVertex.addEventListener('click', moveVectorVertex);
el.canvasZoom.addEventListener('input', () => setCanvasZoom(el.canvasZoom.value));
el.zoomIn.addEventListener('click', () => setCanvasZoom(canvasZoom + 25));
el.zoomOut.addEventListener('click', () => setCanvasZoom(canvasZoom - 25));
el.zoomFit.addEventListener('click', () => setCanvasZoom(100));
el.showMask.addEventListener('change', () => {
    invalidateDesignBase();
    drawDesign();
});
el.snapVertices.addEventListener('change', drawDesign);
el.clearSelection.addEventListener('click', () => {
    selectedRegionIds.clear();
    selectedEdgeIds.clear();
    updateSelectionStatus();
    drawDesign();
});
el.designCanvas.addEventListener('pointerdown', (event) => {
    dragStart = canvasPoint(event);
    dragCurrent = dragStart;
    if (vectorEditMode()) {
        if (event.shiftKey) {
            const edge = nearestEdge(dragStart);
            if (edge) {
                if (selectedEdgeIds.has(edge.edge_id)) {
                    selectedEdgeIds.delete(edge.edge_id);
                }
                else {
                    selectedEdgeIds.add(edge.edge_id);
                }
                setStatus(`Selected ${selectedEdgeIds.size} vector edge(s).`);
                dragStart = null;
                dragCurrent = null;
                drawDesign();
                return;
            }
        }
        const vertex = nearestVertex(dragStart);
        if (vertex) {
            activeVertexDrag = {
                vertexId: vertex.vertex_id,
                start: { x: vertex.point[0], y: vertex.point[1] },
                current: { x: vertex.point[0], y: vertex.point[1] },
            };
            hoveredVertex = vertex;
            el.vertexId.value = String(vertex.vertex_id);
            el.vertexX.value = String(vertex.point[0]);
            el.vertexY.value = String(vertex.point[1]);
            setStatus(`Dragging vertex ${vertex.vertex_id}.`);
            el.designCanvas.setPointerCapture(event.pointerId);
            drawDesign();
            return;
        }
        const edge = nearestEdge(dragStart);
        if (edge) {
            if (!event.shiftKey)
                selectedEdgeIds.clear();
            if (selectedEdgeIds.has(edge.edge_id) && event.shiftKey) {
                selectedEdgeIds.delete(edge.edge_id);
            }
            else {
                selectedEdgeIds.add(edge.edge_id);
            }
            setStatus(`Selected ${selectedEdgeIds.size} vector edge(s).`);
            dragStart = null;
            dragCurrent = null;
            drawDesign();
            return;
        }
    }
    lassoPoints = (selectionMode() === 'lasso' || maskBrushRole()) && dragStart ? [dragStart] : [];
    el.designCanvas.setPointerCapture(event.pointerId);
});
el.designCanvas.addEventListener('pointermove', (event) => {
    if (!dragStart)
        return;
    dragCurrent = canvasPoint(event);
    if (activeVertexDrag && dragCurrent) {
        activeVertexDrag.current = snappedCanvasPoint(dragCurrent);
        el.vertexX.value = String(activeVertexDrag.current.x);
        el.vertexY.value = String(activeVertexDrag.current.y);
        drawDesign();
        return;
    }
    if ((selectionMode() === 'lasso' || maskBrushRole()) && dragCurrent) {
        lassoPoints.push(dragCurrent);
    }
    drawDesign();
});
el.designCanvas.addEventListener('pointerup', (event) => {
    if (!dragStart)
        return;
    const end = canvasPoint(event);
    if (activeVertexDrag) {
        const vertexId = activeVertexDrag.vertexId;
        const snapped = snappedCanvasPoint(end);
        const didMove = Math.hypot(snapped.x - activeVertexDrag.start.x, snapped.y - activeVertexDrag.start.y) >= 0.5;
        el.vertexId.value = String(vertexId);
        el.vertexX.value = String(snapped.x);
        el.vertexY.value = String(snapped.y);
        activeVertexDrag = null;
        dragStart = null;
        dragCurrent = null;
        if (didMove) {
            void previewVectorVertexMove(true);
        }
        else {
            setStatus(`Selected vertex ${vertexId}.`);
            drawDesign();
        }
        return;
    }
    const role = maskBrushRole();
    if (role) {
        lassoPoints.push(end);
        void paintSubjectMaskStroke(lassoPoints, role);
        dragStart = null;
        dragCurrent = null;
        lassoPoints = [];
        return;
    }
    if (selectionMode() === 'lasso') {
        lassoPoints.push(end);
        selectLasso(lassoPoints, event.shiftKey);
        dragStart = null;
        dragCurrent = null;
        lassoPoints = [];
        drawDesign();
        return;
    }
    const distance = Math.hypot(end.x - dragStart.x, end.y - dragStart.y);
    if (distance < 4) {
        const regionId = labelAt(end);
        if (!event.shiftKey)
            selectedRegionIds.clear();
        if (regionId > 0) {
            if (selectedRegionIds.has(regionId) && event.shiftKey) {
                selectedRegionIds.delete(regionId);
            }
            else {
                selectedRegionIds.add(regionId);
            }
        }
        updateSelectionStatus();
        dragStart = null;
        dragCurrent = null;
        drawDesign();
        return;
    }
    selectRect(dragStart, end, event.shiftKey);
    dragStart = null;
    dragCurrent = null;
});
el.designCanvas.addEventListener('pointermove', (event) => {
    if (dragStart || !vectorEditMode())
        return;
    hoveredVertex = nearestVertex(canvasPoint(event));
    drawDesign();
});
el.designCanvas.addEventListener('pointerleave', () => {
    if (!dragStart) {
        hoveredVertex = null;
        drawDesign();
    }
});
el.undo.addEventListener('click', undo);
el.viewSvg.addEventListener('click', () => {
    const tolerance = encodeURIComponent(String(el.svgSimplify.value || 1));
    window.open(`/api/design.svg?simplify_tolerance=${tolerance}`, '_blank');
});
el.viewCoverageSvg.addEventListener('click', () => {
    const tolerance = encodeURIComponent(String(el.svgSimplify.value || 1));
    window.open(`/api/design-coverage.svg?tolerance=${tolerance}`, '_blank');
});
el.viewGraphSvg.addEventListener('click', () => {
    const kind = encodeURIComponent(String(el.vectorKind.value || 'edited_topology'));
    window.open(`/api/design-graph.svg?kind=${kind}`, '_blank');
});
el.cleanupReport.addEventListener('click', cleanupReport);
el.pack.addEventListener('click', pack);
refresh().catch(() => render());
