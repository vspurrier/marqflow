// @ts-check

/** @type {WorkspaceSummary | null} */
let workspace = null;

const el = /** @type {Record<string, any>} */ ({
  imageInput: document.getElementById('image-input'),
  targetRegions: document.getElementById('target-regions'),
  compactness: document.getElementById('compactness'),
  openImage: document.getElementById('open-image'),
  status: document.getElementById('status'),
  summary: document.getElementById('summary'),
  regions: document.getElementById('regions'),
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
    el.regions.textContent = '';
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
el.viewSvg.addEventListener('click', () => window.open('/api/design.svg', '_blank'));
el.pack.addEventListener('click', pack);

refresh().catch(() => render());
