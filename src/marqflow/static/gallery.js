// @ts-check

/** @type {WorkspaceSummary | null} */
let workspace = null;

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
  render();
}

function render() {
  if (!workspace) {
    el.summary.textContent = 'No workspace.';
    el.candidates.textContent = '';
    el.regions.textContent = '';
    el.mergeSuggestions.textContent = '';
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
  renderCandidates();
  renderMergeSuggestions();
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
  setStatus(`Assigned region ${regionId}.`);
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
  setStatus(`Merged ${regionIds.join(', ')}.`);
  render();
}

async function undo() {
  const response = await fetch('/api/design/undo', {method: 'POST'});
  if (!response.ok) {
    setStatus(await response.text(), true);
    return;
  }
  workspace = await response.json();
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
el.undo.addEventListener('click', undo);
el.viewSvg.addEventListener('click', () => window.open('/api/design.svg', '_blank'));
el.pack.addEventListener('click', pack);

refresh().catch(() => render());
