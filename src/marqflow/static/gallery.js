// @ts-check

/** @type {WorkspaceSummary | null} */
let workspace = null;
/** @type {DesignHitmap | null} */
let hitmap = null;
/** @type {Set<number>} */
let selectedRegionIds = new Set();
let sourceImage = new Image();
/** @type {{x: number, y: number} | null} */
let dragStart = null;
/** @type {{x: number, y: number} | null} */
let dragCurrent = null;

const el = /** @type {Record<string, any>} */ ({
  imageInput: document.getElementById('image-input'),
  targetRegions: document.getElementById('target-regions'),
  compactness: document.getElementById('compactness'),
  gridRows: document.getElementById('grid-rows'),
  gridCols: document.getElementById('grid-cols'),
  minRegions: document.getElementById('min-regions'),
  maxRegions: document.getElementById('max-regions'),
  minCompactness: document.getElementById('min-compactness'),
  maxCompactness: document.getElementById('max-compactness'),
  openImage: document.getElementById('open-image'),
  candidateGrid: document.getElementById('candidate-grid'),
  candidates: document.getElementById('candidates'),
  status: document.getElementById('status'),
  summary: document.getElementById('summary'),
  physicalWidth: document.getElementById('physical-width'),
  physicalHeight: document.getElementById('physical-height'),
  physicalUnit: document.getElementById('physical-unit'),
  updateSize: document.getElementById('update-size'),
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
  applySuggestions: document.getElementById('apply-suggestions'),
  clearSelection: document.getElementById('clear-selection'),
  designCanvas: document.getElementById('design-canvas'),
  selectionStatus: document.getElementById('selection-status'),
  undo: document.getElementById('undo'),
  viewSvg: document.getElementById('view-svg'),
  pack: document.getElementById('pack'),
  packOutput: document.getElementById('pack-output'),
});

function setStatus(text, error = false) {
  el.status.textContent = text;
  el.status.style.color = error ? '#b6332a' : 'var(--muted)';
}

function rgb(color) {
  return `rgb(${color[0]}, ${color[1]}, ${color[2]})`;
}

async function refresh() {
  const response = await fetch('/api/workspace');
  if (!response.ok) {
    workspace = null;
    render();
    return;
  }
  workspace = await response.json();
  await loadHitmap();
  render();
}

async function loadHitmap() {
  if (!workspace?.design) {
    hitmap = null;
    selectedRegionIds.clear();
    return;
  }
  const response = await fetch('/api/design/hitmap');
  if (!response.ok) {
    hitmap = null;
    return;
  }
  hitmap = await response.json();
  sourceImage = new Image();
  sourceImage.onload = () => drawDesign();
  sourceImage.src = '/api/workspace-file/source.png';
}

function render() {
  if (!workspace) {
    el.summary.textContent = 'No workspace.';
    el.candidates.textContent = '';
    el.regions.textContent = '';
    el.mergeSuggestions.textContent = '';
    hitmap = null;
    selectedRegionIds.clear();
    drawDesign();
    return;
  }
  el.summary.textContent = JSON.stringify(
    {
      source: workspace.source,
      candidates: workspace.candidates,
      valid_partition: workspace.validation.valid,
      region_count: workspace.validation.region_count,
    },
    null,
    2,
  );
  if (workspace.design) {
    el.physicalWidth.value = workspace.design.physical_size.width;
    el.physicalHeight.value = workspace.design.physical_size.height;
    el.physicalUnit.value = workspace.design.physical_size.unit;
  }
  renderSelectedVeneerOptions();
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
      .map(
        (veneer) =>
          `<option value="${veneer.veneer_id}" ${
            veneer.veneer_id === region.veneer_id ? 'selected' : ''
          }>${veneer.name}</option>`,
      )
      .join('');
    item.innerHTML = `
      <strong>Region ${region.region_id}</strong>
      <span><span class="swatch" style="background:${rgb(region.color_rgb)}"></span>
      area ${region.area_physical.toFixed(3)}</span>
      <select data-region-id="${region.region_id}">${options}</select>
      <small>${region.warnings.join(', ') || 'ok'}</small>
    `;
    item.querySelector('select')?.addEventListener('change', async (event) => {
      const select = /** @type {HTMLSelectElement} */ (event.currentTarget);
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

function updateSelectionStatus() {
  const ids = [...selectedRegionIds].sort((a, b) => a - b);
  el.selectionStatus.textContent = ids.length
    ? `Selected ${ids.length} region(s): ${ids.join(', ')}`
    : 'No selected regions.';
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

function labelAt(point) {
  if (!hitmap) return 0;
  const x = Math.max(0, Math.min(hitmap.width - 1, point.x));
  const y = Math.max(0, Math.min(hitmap.height - 1, point.y));
  return Number(hitmap.labels[y]?.[x] || 0);
}

function selectRect(start, end, additive) {
  if (!hitmap) return;
  const minX = Math.max(0, Math.min(start.x, end.x));
  const maxX = Math.min(hitmap.width - 1, Math.max(start.x, end.x));
  const minY = Math.max(0, Math.min(start.y, end.y));
  const maxY = Math.min(hitmap.height - 1, Math.max(start.y, end.y));
  if (!additive) selectedRegionIds.clear();
  for (let y = minY; y <= maxY; y += 1) {
    for (let x = minX; x <= maxX; x += 1) {
      const regionId = Number(hitmap.labels[y]?.[x] || 0);
      if (regionId > 0) selectedRegionIds.add(regionId);
    }
  }
  updateSelectionStatus();
  drawDesign();
}

function drawDesign() {
  const canvas = /** @type {HTMLCanvasElement} */ (el.designCanvas);
  const ctx = canvas.getContext('2d');
  if (!ctx) return;
  const width = hitmap?.width || 1;
  const height = hitmap?.height || 1;
  canvas.width = width;
  canvas.height = height;
  ctx.clearRect(0, 0, width, height);
  if (!workspace || !hitmap) return;
  if (sourceImage.complete && sourceImage.naturalWidth) {
    ctx.drawImage(sourceImage, 0, 0, width, height);
  }

  const imageData = ctx.getImageData(0, 0, width, height);
  for (let y = 0; y < height; y += 1) {
    for (let x = 0; x < width; x += 1) {
      const regionId = Number(hitmap.labels[y]?.[x] || 0);
      if (!selectedRegionIds.has(regionId)) continue;
      const offset = (y * width + x) * 4;
      const color = regionColor(regionId);
      imageData.data[offset] = Math.round(imageData.data[offset] * 0.45 + color[0] * 0.55);
      imageData.data[offset + 1] = Math.round(imageData.data[offset + 1] * 0.45 + color[1] * 0.55);
      imageData.data[offset + 2] = Math.round(imageData.data[offset + 2] * 0.45 + color[2] * 0.55);
      imageData.data[offset + 3] = 255;
    }
  }
  ctx.putImageData(imageData, 0, 0);

  if (dragStart && dragCurrent) {
    ctx.strokeStyle = '#f4f0dc';
    ctx.lineWidth = Math.max(1, width / 300);
    ctx.setLineDash([6, 4]);
    ctx.strokeRect(
      dragStart.x,
      dragStart.y,
      dragCurrent.x - dragStart.x,
      dragCurrent.y - dragStart.y,
    );
    ctx.setLineDash([]);
  }
}

async function updateSize() {
  if (!workspace?.design) {
    setStatus('Create a design before changing size.', true);
    return;
  }
  const response = await fetch('/api/design/size', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
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
  form.append('target_regions', el.targetRegions.value || '80');
  form.append('compactness', el.compactness.value || '18');
  setStatus('Building first partition...');
  const response = await fetch('/api/workspace/open-image', {method: 'POST', body: form});
  if (!response.ok) {
    setStatus(await response.text(), true);
    return;
  }
  workspace = await response.json();
  selectedRegionIds.clear();
  await loadHitmap();
  setStatus('Workspace ready.');
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
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({
      rows: Number(el.gridRows.value || 4),
      cols: Number(el.gridCols.value || 4),
      min_regions: Number(el.minRegions.value || 20),
      max_regions: Number(el.maxRegions.value || 140),
      min_compactness: Number(el.minCompactness.value || 4),
      max_compactness: Number(el.maxCompactness.value || 28),
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
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({candidate_id: candidateId, width: 8, height: 10, unit: 'in'}),
  });
  if (!response.ok) {
    setStatus(await response.text(), true);
    return;
  }
  workspace = await response.json();
  selectedRegionIds.clear();
  await loadHitmap();
  setStatus(`Design seeded from ${candidateId}.`);
  render();
}

async function assignVeneer(regionId, veneerId) {
  const response = await fetch('/api/design/veneer', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({region_id: regionId, veneer_id: veneerId}),
  });
  if (!response.ok) {
    setStatus(await response.text(), true);
    return;
  }
  workspace = await response.json();
  await loadHitmap();
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
    headers: {'Content-Type': 'application/json'},
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
  setStatus(`Assigned ${selectedRegionIds.size} selected region(s).`);
  render();
}

async function mergeRegions(regionIds) {
  const response = await fetch('/api/design/merge', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({region_ids: regionIds}),
  });
  if (!response.ok) {
    setStatus(await response.text(), true);
    return;
  }
  workspace = await response.json();
  selectedRegionIds.clear();
  await loadHitmap();
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
    headers: {'Content-Type': 'application/json'},
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
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({region_ids: [...selectedRegionIds], locked}),
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

async function applySuggestions() {
  const response = await fetch('/api/design/apply-merge-suggestions', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({max_merges: 10}),
  });
  if (!response.ok) {
    setStatus(await response.text(), true);
    return;
  }
  workspace = await response.json();
  selectedRegionIds.clear();
  await loadHitmap();
  setStatus(`Applied ${workspace.applied_merge_count || 0} merge suggestion(s).`);
  render();
}

async function undo() {
  const response = await fetch('/api/design/undo', {method: 'POST'});
  if (!response.ok) {
    setStatus(await response.text(), true);
    return;
  }
  workspace = await response.json();
  selectedRegionIds.clear();
  await loadHitmap();
  setStatus('Undid last edit.');
  render();
}

async function pack() {
  const response = await fetch('/api/pack', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({output_dir: './exported'}),
  });
  if (!response.ok) {
    setStatus(await response.text(), true);
    return;
  }
  el.packOutput.textContent = JSON.stringify(await response.json(), null, 2);
  setStatus('Pack manifest written.');
}

el.openImage.addEventListener('click', openImage);
el.candidateGrid.addEventListener('click', generateCandidateGrid);
el.updateSize.addEventListener('click', updateSize);
el.assignSelected.addEventListener('click', assignSelected);
el.mergeSelected.addEventListener('click', mergeSelected);
el.splitSelected.addEventListener('click', splitSelected);
el.lockSelected.addEventListener('click', () => lockSelected(true));
el.unlockSelected.addEventListener('click', () => lockSelected(false));
el.applySuggestions.addEventListener('click', applySuggestions);
el.clearSelection.addEventListener('click', () => {
  selectedRegionIds.clear();
  updateSelectionStatus();
  drawDesign();
});
el.designCanvas.addEventListener('pointerdown', (event) => {
  dragStart = canvasPoint(event);
  dragCurrent = dragStart;
  el.designCanvas.setPointerCapture(event.pointerId);
});
el.designCanvas.addEventListener('pointermove', (event) => {
  if (!dragStart) return;
  dragCurrent = canvasPoint(event);
  drawDesign();
});
el.designCanvas.addEventListener('pointerup', (event) => {
  if (!dragStart) return;
  const end = canvasPoint(event);
  const distance = Math.hypot(end.x - dragStart.x, end.y - dragStart.y);
  if (distance < 4) {
    const regionId = labelAt(end);
    if (!event.shiftKey) selectedRegionIds.clear();
    if (regionId > 0) {
      if (selectedRegionIds.has(regionId) && event.shiftKey) {
        selectedRegionIds.delete(regionId);
      } else {
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
el.undo.addEventListener('click', undo);
el.viewSvg.addEventListener('click', () => window.open('/api/design.svg', '_blank'));
el.pack.addEventListener('click', pack);

refresh().catch(() => render());
