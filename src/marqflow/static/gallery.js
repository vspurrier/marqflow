const state = {
  workspace: null,
  activeCandidateId: null,
  mode: 'image',
  imageFileName: '',
  composeFitZoom: 1,
  cleanupThreshold: 24,
  cleanupRenderTimer: null,
  previewRequestId: 0,
  previewAbortController: null,
  candidateDetailCache: {},
  candidateSvgCache: {},
  selectedFinalRegionIds: new Set(),
  activeFinalRegionId: null,
  finalHitmap: null,
  cleanupDragStart: null,
  cleanupDragSelection: false,
  activeJobId: null,
};

const el = {
  landing: document.getElementById('landing'),
  landingStatus: document.getElementById('landing-status'),
  sourceImageInput: document.getElementById('source-image-input'),
  sourceImageInputPanel: document.getElementById('source-image-input-panel'),
  openImageBtn: document.getElementById('open-image-btn'),
  openImageBtnPanel: document.getElementById('open-image-btn-panel'),
  imageBadge: document.getElementById('image-badge'),
  imageSummary: document.getElementById('image-summary'),
  sourcePreview: document.getElementById('source-preview'),
  workspacePill: document.getElementById('workspace-pill'),
  statusPill: document.getElementById('status-pill'),
  imageTabBtn: document.getElementById('image-tab-btn'),
  sizeTabBtn: document.getElementById('size-tab-btn'),
  subjectTabBtn: document.getElementById('subject-tab-btn'),
  shapesTabBtn: document.getElementById('shapes-tab-btn'),
  huesTabBtn: document.getElementById('hues-tab-btn'),
  cleanupTabBtn: document.getElementById('cleanup-tab-btn'),
  packTabBtn: document.getElementById('pack-tab-btn'),
  imagePanel: document.getElementById('image-panel'),
  sizePanel: document.getElementById('size-panel'),
  subjectPanel: document.getElementById('subject-panel'),
  shapesPanel: document.getElementById('shapes-panel'),
  huesPanel: document.getElementById('hues-panel'),
  cleanupPanel: document.getElementById('cleanup-panel'),
  packPanel: document.getElementById('pack-panel'),
  progressBar: document.getElementById('progress-bar'),
  physicalWidth: document.getElementById('physical-width'),
  physicalHeight: document.getElementById('physical-height'),
  physicalUnit: document.getElementById('physical-unit'),
  applySizeBtn: document.getElementById('apply-size-btn'),
  subjectDetailBudget: document.getElementById('subject-detail-budget'),
  subjectNotes: document.getElementById('subject-notes'),
  subjectProtectEyes: document.getElementById('subject-protect-eyes'),
  subjectProtectNose: document.getElementById('subject-protect-nose'),
  saveSubjectBtn: document.getElementById('save-subject-btn'),
  gridRows: document.getElementById('grid-rows'),
  gridCols: document.getElementById('grid-cols'),
  rebuildGridBtn: document.getElementById('rebuild-grid-btn'),
  resetWorkspaceBtn: document.getElementById('reset-workspace-btn'),
  keptStrip: document.getElementById('kept-strip'),
  grid: document.getElementById('grid'),
  candidateCount: document.getElementById('candidate-count'),
  mergeThreshold: document.getElementById('merge-threshold'),
  mergeThresholdValue: document.getElementById('merge-threshold-value'),
  simplifyTolerance: document.getElementById('simplify-tolerance'),
  simplifyToleranceValue: document.getElementById('simplify-tolerance-value'),
  smallArea: document.getElementById('small-area'),
  smallAreaValue: document.getElementById('small-area-value'),
  thinWidth: document.getElementById('thin-width'),
  thinWidthValue: document.getElementById('thin-width-value'),
  splitTarget: document.getElementById('split-target'),
  saveCleanupBtn: document.getElementById('save-cleanup-btn'),
  mergeSelectedBtn: document.getElementById('merge-selected-btn'),
  mergeSuggestionsBtn: document.getElementById('merge-suggestions-btn'),
  splitSelectedBtn: document.getElementById('split-selected-btn'),
  composeKeptCount: document.getElementById('compose-kept-count'),
  veneerPaletteList: document.getElementById('veneer-palette-list'),
  addVeneerBtn: document.getElementById('add-veneer-btn'),
  saveVeneerPaletteBtn: document.getElementById('save-veneer-palette-btn'),
  composePaletteList: document.getElementById('compose-palette-list'),
  composeCanvas: document.getElementById('compose-canvas'),
  composeStage: document.getElementById('compose-stage'),
  composeSummary: document.getElementById('compose-summary'),
  mergeCanvas: document.getElementById('merge-canvas'),
  mergeStage: document.getElementById('merge-stage'),
  mergeSummary: document.getElementById('merge-summary'),
  cleanupHover: document.getElementById('cleanup-hover'),
  finalRegionList: document.getElementById('final-region-list'),
  finalRegionEditor: document.getElementById('final-region-editor'),
  finalRegionEditorNote: document.getElementById('final-region-editor-note'),
  finalPointIndex: document.getElementById('final-point-index'),
  finalPointX: document.getElementById('final-point-x'),
  finalPointY: document.getElementById('final-point-y'),
  finalPointMoveBtn: document.getElementById('final-point-move-btn'),
  finalSmoothBtn: document.getElementById('final-smooth-btn'),
  packSummary: document.getElementById('pack-summary'),
  exportDir: document.getElementById('export-dir'),
  exportBtn: document.getElementById('export-btn'),
  exportFinalBtn: document.getElementById('export-final-btn'),
};

function setBusy(isBusy) {
  document.body.classList.toggle('busy', isBusy);
}

function setHasWorkspace(hasWorkspace) {
  document.body.classList.toggle('has-workspace', hasWorkspace);
}

function setStatus(text, error = false) {
  el.statusPill.textContent = text;
  el.statusPill.style.color = error ? 'var(--danger)' : 'var(--muted)';
}

function candidateLabel(candidate) {
  return candidate.label || candidate.candidate_id.slice(0, 8);
}

function setEmptyWorkspaceState(message = 'No workspace loaded yet.') {
  state.workspace = null;
  state.activeCandidateId = null;
  state.selectedFinalRegionIds.clear();
  state.activeFinalRegionId = null;
  state.finalHitmap = null;
  document.body.classList.remove('has-workspace');
  el.workspacePill.textContent = 'No workspace loaded';
  el.statusPill.textContent = 'Select an image to begin';
  el.statusPill.style.color = 'var(--muted)';
  el.landingStatus.textContent = message;
  el.imageSummary.textContent = message;
  el.imageBadge.textContent = 'No image selected';
  el.sourcePreview.removeAttribute('src');
  if (el.finalPointMoveBtn) {
    el.finalPointMoveBtn.disabled = true;
  }
  if (el.finalSmoothBtn) {
    el.finalSmoothBtn.disabled = true;
  }
}

function setWorkspaceSummary(workspace) {
  el.workspacePill.textContent = `${workspace.candidate_count} candidates / ${workspace.kept_count} kept`;
  el.candidateCount.textContent = workspace.candidate_count;
  if (workspace.grid_rows) {
    el.gridRows.value = String(workspace.grid_rows);
  }
  if (workspace.grid_cols) {
    el.gridCols.value = String(workspace.grid_cols);
  }
  if (workspace.physical_size) {
    el.physicalWidth.value = String(workspace.physical_size.width ?? 1);
    el.physicalHeight.value = String(workspace.physical_size.height ?? 1);
    el.physicalUnit.value = workspace.physical_size.unit || 'px';
  }
  if (workspace.subject_settings) {
    el.subjectDetailBudget.value = String(Math.round((workspace.subject_settings.detail_budget ?? 0.5) * 100));
    el.subjectNotes.value = workspace.subject_settings.notes || '';
    el.subjectProtectEyes.checked = Boolean(workspace.subject_settings.protect_eyes);
    el.subjectProtectNose.checked = Boolean(workspace.subject_settings.protect_nose);
  }
  if (workspace.cleanup_settings) {
    el.simplifyTolerance.value = String(workspace.cleanup_settings.simplify_tolerance ?? 1.0);
    el.simplifyToleranceValue.textContent = String(workspace.cleanup_settings.simplify_tolerance ?? 1.0);
    el.smallArea.value = String(workspace.cleanup_settings.highlight_small_area ?? 0.0);
    el.smallAreaValue.textContent = String(workspace.cleanup_settings.highlight_small_area ?? 0.0);
    el.thinWidth.value = String(workspace.cleanup_settings.highlight_thin_width ?? 0.0);
    el.thinWidthValue.textContent = String(workspace.cleanup_settings.highlight_thin_width ?? 0.0);
    state.cleanupThreshold = Number(workspace.cleanup_settings.merge_rgb_threshold ?? 24);
    el.mergeThreshold.value = String(state.cleanupThreshold);
    el.mergeThresholdValue.textContent = String(state.cleanupThreshold);
  }
  if (workspace.source_image_path) {
    el.imageBadge.textContent = workspace.source_image_path.split('/').pop();
    const originalSize = workspace.original_image_size || {};
    const sourceSize = workspace.source_image_size || {};
    const validation = workspace.partition_validation || {};
    const originalSizeText =
      originalSize.width && originalSize.height
        ? `Original image ${originalSize.width} x ${originalSize.height}.`
        : '';
    const sourceSizeText =
      sourceSize.width && sourceSize.height
        ? `Working image ${sourceSize.width} x ${sourceSize.height}.`
        : '';
    const partitionText =
      validation.partition_valid === false
        ? 'Partition needs attention.'
        : validation.partition_valid === true
          ? 'Partition is valid.'
          : '';
    el.imageSummary.textContent = [
      `Workspace stored at ${workspace.workspace_dir}.`,
      originalSizeText,
      sourceSizeText,
      partitionText,
    ]
      .filter(Boolean)
      .join(' ');
  }
}

function setMode(mode) {
  state.mode = mode;
  const mapping = [
    [el.imagePanel, el.imageTabBtn, 'image'],
    [el.sizePanel, el.sizeTabBtn, 'size'],
    [el.subjectPanel, el.subjectTabBtn, 'subject'],
    [el.shapesPanel, el.shapesTabBtn, 'shapes'],
    [el.huesPanel, el.huesTabBtn, 'hues'],
    [el.cleanupPanel, el.cleanupTabBtn, 'cleanup'],
    [el.packPanel, el.packTabBtn, 'pack'],
  ];
  for (const [panel, button, name] of mapping) {
    panel.classList.toggle('active', name === mode);
    button.classList.toggle('active', name === mode);
  }
  if (!state.workspace) {
    return;
  }
  if (mode === 'hues') {
    renderHuesTab(state.workspace).catch((error) => setStatus(String(error), true));
  } else if (mode === 'cleanup') {
    renderCleanupTab(state.workspace).catch((error) => setStatus(String(error), true));
  } else if (mode === 'pack') {
    renderPackTab(state.workspace).catch((error) => setStatus(String(error), true));
  } else if (mode === 'image') {
    renderImageTab(state.workspace);
  } else if (mode === 'size') {
    renderSizeTab(state.workspace);
  } else if (mode === 'subject') {
    renderSubjectTab(state.workspace);
  } else if (mode === 'shapes') {
    renderShapesTab(state.workspace);
  }
}

function renderImageTab(workspace) {
  const active = workspace.active_candidate || workspace.candidates[0];
  if (active) {
    el.sourcePreview.src = active.preview_url;
    el.sourcePreview.alt = candidateLabel(active);
  }
  const sourceText = workspace.source_image_path
    ? `Source image: ${workspace.source_image_path}.`
    : 'No source image loaded.';
  const summaryText = el.imageSummary.textContent || '';
  if (!summaryText || summaryText === 'No workspace loaded yet.' || summaryText === 'Choose an image file first.') {
    el.imageSummary.textContent = sourceText;
    return;
  }
  if (!summaryText.includes(sourceText)) {
    el.imageSummary.textContent = `${summaryText} ${sourceText}`.trim();
  }
}

function renderSizeTab(workspace) {
  if (workspace.physical_size) {
    el.imageSummary.textContent = `Final size: ${workspace.physical_size.width} x ${workspace.physical_size.height} ${workspace.physical_size.unit}`;
  }
}

function renderSubjectTab(workspace) {
  if (workspace.subject_settings) {
    el.imageSummary.textContent = `Subject notes are stored. Detail budget: ${Math.round((workspace.subject_settings.detail_budget ?? 0.5) * 100)}%.`;
  }
}

function updateFinalSelectionState() {
  document.querySelectorAll('.final-region-item').forEach((item) => {
    item.classList.toggle('selected', state.selectedFinalRegionIds.has(Number(item.dataset.regionId)));
    item.classList.toggle('active', Number(item.dataset.regionId) === state.activeFinalRegionId);
  });
  if (state.workspace && state.mode === 'cleanup') {
    renderSelectedRegionEditor(state.workspace);
  }
}

function canvasPointFromEvent(canvas, event, hitmap) {
  const rect = canvas.getBoundingClientRect();
  const canvasWidth = canvas.width || rect.width;
  const canvasHeight = canvas.height || rect.height;
  const x = Math.floor(((event.clientX - rect.left) / Math.max(1, rect.width)) * canvasWidth);
  const y = Math.floor(((event.clientY - rect.top) / Math.max(1, rect.height)) * canvasHeight);
  return {
    x,
    y,
    inside:
      x >= 0 && y >= 0 && x < (hitmap?.width || canvasWidth) && y < (hitmap?.height || canvasHeight),
  };
}

function regionIdsInRect(hitmap, x0, y0, x1, y1) {
  if (!hitmap || !Array.isArray(hitmap.labels)) {
    return [];
  }
  const left = Math.max(0, Math.min(x0, x1));
  const right = Math.min(hitmap.width - 1, Math.max(x0, x1));
  const top = Math.max(0, Math.min(y0, y1));
  const bottom = Math.min(hitmap.height - 1, Math.max(y0, y1));
  const ids = new Set();
  for (let y = top; y <= bottom; y += 1) {
    const row = hitmap.labels[y] || [];
    for (let x = left; x <= right; x += 1) {
      const regionId = row[x];
      if (regionId && regionId > 0) {
        ids.add(regionId);
      }
    }
  }
  return [...ids];
}

function selectedFinalRegion(workspace) {
  if (!workspace || !Array.isArray(workspace.final_regions)) {
    return null;
  }
  const activeId = state.activeFinalRegionId;
  if (activeId != null) {
    return workspace.final_regions.find((region) => region.region_id === activeId) || null;
  }
  const firstId = [...state.selectedFinalRegionIds][0];
  if (firstId == null) {
    return null;
  }
  return workspace.final_regions.find((region) => region.region_id === firstId) || null;
}

function renderSelectedRegionEditor(workspace) {
  const region = selectedFinalRegion(workspace);
  if (!region) {
    el.finalRegionEditorNote.textContent =
      'Select one final region to edit points or smooth the edge.';
    el.finalPointIndex.value = '0';
    el.finalPointX.value = '0';
    el.finalPointY.value = '0';
    el.finalPointMoveBtn.disabled = true;
    el.finalSmoothBtn.disabled = true;
    return;
  }
  const contour = region.contour || [];
  el.finalRegionEditorNote.textContent = `Region ${region.region_id} has ${contour.length} points. The final point edit is stored on the region contour override.`;
  el.finalPointIndex.max = String(Math.max(0, contour.length - 1));
  const index = Math.min(
    Math.max(0, Number(el.finalPointIndex.value || 0)),
    Math.max(0, contour.length - 1),
  );
  el.finalPointIndex.value = String(index);
  const point = contour[index] || contour[0] || [0, 0];
  el.finalPointX.value = String(point[0] ?? 0);
  el.finalPointY.value = String(point[1] ?? 0);
  el.finalPointMoveBtn.disabled = contour.length === 0;
  el.finalSmoothBtn.disabled = contour.length === 0;
}

function renderShapesTab(workspace) {
  renderSelect(workspace);
  renderGrid(workspace);
  renderKeptStrip(workspace);
}

function renderImageLikeSummary(workspace) {
  el.workspacePill.textContent = `${workspace.candidate_count} candidates / ${workspace.kept_count} kept`;
}

function renderSelect(workspace) {
  void workspace;
}

function renderGrid(workspace) {
  el.grid.innerHTML = '';
  for (const candidate of workspace.candidates) {
    const card = document.createElement('div');
    card.className =
      'candidate' +
      (candidate.candidate_id === workspace.active_candidate_id ? ' active' : '') +
      (candidate.kept ? ' kept' : '');

    const img = document.createElement('img');
    img.src = candidate.thumb_url || candidate.preview_url;
    img.alt = candidateLabel(candidate);

    const meta = document.createElement('div');
    meta.className = 'meta';

    const name = document.createElement('div');
    name.className = 'name';
    name.textContent = candidateLabel(candidate);

    const sub = document.createElement('div');
    sub.className = 'sub';
    sub.textContent = `${candidate.region_count} regions / gen ${candidate.generation}`;

    const preset = candidate.preset || {};
    const details = document.createElement('div');
    details.className = 'sub';
    details.textContent = `segments ${preset.target_segments} / compactness ${Number(preset.compactness).toFixed(1)}`;

    const actions = document.createElement('div');
    actions.className = 'actions';

    const openButton = document.createElement('button');
    openButton.className = 'primary';
    openButton.textContent = 'Open';
    openButton.addEventListener('click', (event) => {
      event.stopPropagation();
      openCandidate(candidate.candidate_id);
    });

    const keepButton = document.createElement('button');
    keepButton.textContent = candidate.kept ? 'Unkeep' : 'Keep';
    keepButton.addEventListener('click', (event) => {
      event.stopPropagation();
      toggleKeep(candidate.candidate_id);
    });

    actions.append(openButton, keepButton);
    meta.append(name, sub, details, actions);
    card.append(img, meta);
    card.addEventListener('click', () => openCandidate(candidate.candidate_id));
    el.grid.appendChild(card);
  }
}

function renderKeptStrip(workspace) {
  el.keptStrip.innerHTML = '';
  const kept = workspace.candidates.filter((candidate) => candidate.kept);
  el.composeKeptCount.textContent = kept.length;
  if (!kept.length) {
    const empty = document.createElement('div');
    empty.className = 'small';
    empty.style.padding = '0 18px 12px';
    empty.textContent = 'Keep candidates here for quick comparison.';
    el.keptStrip.appendChild(empty);
    return;
  }
  for (const candidate of kept) {
    const card = document.createElement('div');
    card.className = 'kept-card' + (candidate.candidate_id === workspace.active_candidate_id ? ' active' : '');
    const img = document.createElement('img');
    img.src = candidate.thumb_url || candidate.preview_url;
    img.alt = candidateLabel(candidate);
    const meta = document.createElement('div');
    meta.className = 'meta';
    const name = document.createElement('div');
    name.className = 'name';
    name.textContent = candidateLabel(candidate);
    const sub = document.createElement('div');
    sub.className = 'sub';
    sub.textContent = `${candidate.region_count} regions`;
    meta.append(name, sub);
    card.append(img, meta);
    card.addEventListener('click', () => openCandidate(candidate.candidate_id));
    el.keptStrip.appendChild(card);
  }
}

async function fetchWorkspace() {
  setBusy(true);
  try {
    const response = await fetch('/api/workspace');
    if (response.status === 404) {
      setEmptyWorkspaceState();
      return;
    }
    if (!response.ok) {
      throw new Error(await response.text());
    }
    const workspace = await response.json();
    state.workspace = workspace;
    setHasWorkspace(true);
    setWorkspaceSummary(workspace);
    renderImageTab(workspace);
    renderShapesTab(workspace);
    const active = workspace.active_candidate_id || (workspace.candidates[0] && workspace.candidates[0].candidate_id);
    if (active) {
      await openCandidate(active);
    }
    if (state.mode === 'hues') {
      await renderHuesTab(workspace);
    } else if (state.mode === 'cleanup') {
      await renderCleanupTab(workspace);
    } else if (state.mode === 'pack') {
      await renderPackTab(workspace);
    }
  } catch (error) {
    setEmptyWorkspaceState(String(error));
    return;
  } finally {
    setBusy(false);
  }
}

async function openSelectedImage() {
  const file = (el.sourceImageInputPanel.files && el.sourceImageInputPanel.files[0]) || (el.sourceImageInput.files && el.sourceImageInput.files[0]);
  if (!file) {
    setEmptyWorkspaceState('Choose an image file first.');
    return;
  }
  setBusy(true);
  try {
    const form = new FormData();
    form.append('image', file);
    form.append('rows', '4');
    form.append('cols', '4');
    const response = await fetch('/api/workspace/open-image', {
      method: 'POST',
      body: form,
    });
    if (!response.ok) {
      throw new Error(await response.text());
    }
    const workspace = await response.json();
    state.workspace = workspace;
    state.imageFileName = file.name;
    setHasWorkspace(true);
    setWorkspaceSummary(workspace);
    renderImageTab(workspace);
    renderShapesTab(workspace);
    const active = workspace.active_candidate_id || (workspace.candidates[0] && workspace.candidates[0].candidate_id);
    if (active) {
      await openCandidate(active);
    }
    setMode('image');
    setStatus(`Opened ${file.name}`);
    el.landingStatus.textContent = `Loaded ${file.name}.`;
  } catch (error) {
    setEmptyWorkspaceState(String(error));
  } finally {
    setBusy(false);
  }
}

async function fetchCandidate(candidateId) {
  const response = await fetch(`/api/workspace/candidates/${candidateId}`);
  if (!response.ok) {
    throw new Error(await response.text());
  }
  return response.json();
}

async function openCandidate(candidateId) {
  setBusy(true);
  try {
    setStatus(`Loading ${candidateId}...`);
    const detail = await fetchCandidate(candidateId);
    state.activeCandidateId = candidateId;
    await syncActiveCandidate(candidateId);
    setStatus(`Active ${candidateLabel(detail)} / ${detail.region_count} regions`);
    if (state.mode === 'hues') {
      await renderHuesTab(state.workspace);
    }
  } finally {
    setBusy(false);
  }
}

async function syncActiveCandidate(candidateId) {
  const response = await fetch('/api/workspace/active', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({candidate_id: candidateId}),
  });
  if (!response.ok) {
    throw new Error(await response.text());
  }
  const workspace = await response.json();
  state.workspace = workspace;
  setWorkspaceSummary(workspace);
  renderImageTab(workspace);
  renderShapesTab(workspace);
  renderKeptStrip(workspace);
  return workspace;
}

async function renderHuesTab(workspace) {
  renderVeneerInventory(workspace);
  const kept = workspace.candidates.filter((candidate) => candidate.kept);
  el.composeKeptCount.textContent = kept.length;
  el.composePaletteList.innerHTML = '';
  if (!kept.length) {
    el.composeSummary.textContent = 'Keep at least one candidate to start assigning hues.';
    el.composeStage.style.width = 'auto';
    el.composeStage.style.height = 'auto';
    el.composeCanvas.width = 0;
    el.composeCanvas.height = 0;
    el.composeCanvas.getContext('2d').clearRect(0, 0, 0, 0);
    return;
  }

  await renderFinalPreview(el.composeCanvas, el.composeSummary, 0);

  await Promise.all(
    kept.map((candidate) => renderHueCandidate(candidate).catch((error) => setStatus(String(error), true))),
  );
}

function rgbToHex(color) {
  const values = Array.isArray(color) ? color : [0, 0, 0];
  return `#${values
    .slice(0, 3)
    .map((value) => Math.max(0, Math.min(255, Number(value) || 0)).toString(16).padStart(2, '0'))
    .join('')}`;
}

function hexToRgb(hex) {
  const normalized = String(hex || '').replace('#', '').trim();
  if (!/^[0-9a-fA-F]{6}$/.test(normalized)) {
    return [0, 0, 0];
  }
  return [
    parseInt(normalized.slice(0, 2), 16),
    parseInt(normalized.slice(2, 4), 16),
    parseInt(normalized.slice(4, 6), 16),
  ];
}

function renderVeneerInventory(workspace) {
  if (!el.veneerPaletteList) {
    return;
  }
  el.veneerPaletteList.innerHTML = '';
  (workspace.veneer_palette || []).forEach((swatch) => {
    el.veneerPaletteList.appendChild(
      buildVeneerRow(swatch.veneer_id, swatch.name, rgbToHex(swatch.color_rgb)),
    );
  });
}

function buildVeneerRow(veneerId, name, color) {
  const row = document.createElement('div');
  row.className = 'veneer-row';
  const idInput = document.createElement('input');
  idInput.className = 'veneer-id';
  idInput.type = 'text';
  idInput.value = veneerId;
  idInput.title = 'Stable veneer ID used in exports.';
  const nameInput = document.createElement('input');
  nameInput.className = 'veneer-name';
  nameInput.type = 'text';
  nameInput.value = name;
  nameInput.title = 'Human-readable veneer name.';
  const colorInput = document.createElement('input');
  colorInput.className = 'veneer-color';
  colorInput.type = 'color';
  colorInput.value = color;
  colorInput.title = 'Approximate display color.';
  const removeButton = document.createElement('button');
  removeButton.className = 'remove-veneer-btn';
  removeButton.type = 'button';
  removeButton.title = 'Remove this veneer swatch.';
  removeButton.textContent = 'Remove';
  removeButton.addEventListener('click', () => row.remove());
  row.append(idInput, nameInput, colorInput, removeButton);
  return row;
}

function addVeneerRow() {
  const nextIndex = (el.veneerPaletteList?.querySelectorAll('.veneer-row').length || 0) + 1;
  el.veneerPaletteList.appendChild(
    buildVeneerRow(`veneer-${nextIndex}`, `Veneer ${nextIndex}`, '#b08a5c'),
  );
}

function collectVeneerPalette() {
  return [...el.veneerPaletteList.querySelectorAll('.veneer-row')]
    .map((row) => ({
      veneer_id: row.querySelector('.veneer-id').value.trim(),
      name: row.querySelector('.veneer-name').value.trim(),
      color_rgb: hexToRgb(row.querySelector('.veneer-color').value),
    }))
    .filter((swatch) => swatch.veneer_id);
}

async function saveVeneerPalette() {
  setBusy(true);
  try {
    const response = await fetch('/api/workspace/veneer-palette', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({swatches: collectVeneerPalette()}),
    });
    if (!response.ok) {
      throw new Error(await response.text());
    }
    const workspace = await response.json();
    await refreshWorkspace(workspace);
    setStatus('Saved veneer inventory.');
  } finally {
    setBusy(false);
  }
}

async function renderHueCandidate(candidate) {
  const card = document.createElement('article');
  card.className = 'compose-candidate' + (candidate.candidate_id === state.activeCandidateId ? ' active' : '');
  card.dataset.candidateId = candidate.candidate_id;

  const head = document.createElement('div');
  head.className = 'head';
  const titleRow = document.createElement('div');
  titleRow.className = 'title-row';
  const name = document.createElement('div');
  name.className = 'name';
  name.textContent = candidateLabel(candidate);
  const sub = document.createElement('div');
  sub.className = 'sub';
  sub.textContent = `${candidate.region_count} regions`;
  titleRow.append(name, sub);

  const paintBtn = document.createElement('button');
  paintBtn.className = 'paint-btn';
  paintBtn.textContent = 'Paint all';
  paintBtn.addEventListener('click', async (event) => {
    event.stopPropagation();
    await paintAllCandidate(candidate.candidate_id);
  });

  const clearBtn = document.createElement('button');
  clearBtn.className = 'paint-btn secondary';
  clearBtn.textContent = 'Clear';
  clearBtn.addEventListener('click', async (event) => {
    event.stopPropagation();
    await clearCandidateSelection(candidate.candidate_id);
  });

  const actions = document.createElement('div');
  actions.className = 'head-actions';
  actions.append(paintBtn, clearBtn);
  head.append(titleRow, actions);

  const preview = document.createElement('div');
  preview.className = 'preview';
  const img = document.createElement('img');
  img.src = candidate.preview_url;
  img.alt = candidateLabel(candidate);
  const overlay = document.createElement('div');
  overlay.className = 'compose-candidate-svg';
  preview.append(img, overlay);

  const foot = document.createElement('div');
  foot.className = 'foot';
  const selected = document.createElement('span');
  selected.className = 'selected-stat';
  selected.textContent = `${(candidate.selected_region_ids || []).length} selected`;
  const selectAllHint = document.createElement('span');
  selectAllHint.textContent = 'Click regions to paint';
  foot.append(selected, selectAllHint);

  card.append(head, preview, foot);
  el.composePaletteList.appendChild(card);

  const detail = state.candidateDetailCache[candidate.candidate_id] || (await fetchCandidate(candidate.candidate_id));
  state.candidateDetailCache[candidate.candidate_id] = detail;
  detail.selected_region_ids = candidate.selected_region_ids || detail.selected_region_ids || [];
  selected.textContent = `${detail.selected_region_ids.length} selected`;

  const svgText =
    state.candidateSvgCache[candidate.candidate_id] ||
    (await (async () => {
      const response = await fetch(detail.svg_url);
      if (!response.ok) {
        throw new Error(await response.text());
      }
      return response.text();
    })());
  state.candidateSvgCache[candidate.candidate_id] = svgText;
  overlay.innerHTML = svgText;
  const svg = overlay.querySelector('svg');
  if (svg) {
    svg.setAttribute('preserveAspectRatio', 'none');
    svg.setAttribute('width', '100%');
    svg.setAttribute('height', '100%');
    svg.style.pointerEvents = 'auto';
    svg.querySelectorAll('path').forEach((path) => {
      const id = Number(path.dataset.regionId);
      path.classList.toggle('selected', (detail.selected_region_ids || []).includes(id));
    });
    svg.addEventListener('click', async (event) => {
      const path = event.target.closest('path');
      if (!path || !svg.contains(path)) {
        return;
      }
      event.stopPropagation();
      await togglePaletteRegion(candidate.candidate_id, detail, Number(path.dataset.regionId));
    });
  }
}

function fitZoomForCanvas(canvas) {
  const size = {width: canvas.naturalWidth || canvas.width, height: canvas.naturalHeight || canvas.height};
  if (!size.width || !size.height) {
    return 1;
  }
  const wrap = canvas.closest('.compose-canvas-wrap');
  const availableWidth = Math.max(320, wrap.clientWidth - 36);
  const availableHeight = Math.max(360, window.innerHeight - 320);
  return Math.max(0.15, Math.min(availableWidth / size.width, availableHeight / size.height));
}

async function renderFinalPreview(canvas, summaryEl, mergeThreshold = 0) {
  if (!state.workspace) {
    return;
  }
  const requestId = state.previewRequestId + 1;
  state.previewRequestId = requestId;
  if (state.previewAbortController) {
    state.previewAbortController.abort();
  }
  const controller = new AbortController();
  state.previewAbortController = controller;

  try {
    const response = await fetch(`/api/workspace/composite/preview?merge_threshold=${mergeThreshold}`, {
      signal: controller.signal,
    });
    if (!response.ok) {
      throw new Error(await response.text());
    }
    const blob = await response.blob();
    if (controller.signal.aborted || requestId !== state.previewRequestId) {
      return;
    }

    await new Promise((resolve, reject) => {
      const url = URL.createObjectURL(blob);
      const image = new Image();
      image.onload = () => {
        if (controller.signal.aborted || requestId !== state.previewRequestId) {
          URL.revokeObjectURL(url);
          resolve();
          return;
        }
        canvas.width = image.naturalWidth;
        canvas.height = image.naturalHeight;
        const ctx = canvas.getContext('2d');
        ctx.clearRect(0, 0, canvas.width, canvas.height);
        ctx.drawImage(image, 0, 0);
        const zoom = fitZoomForCanvas(canvas);
        canvas.style.width = `${Math.max(1, Math.round(image.naturalWidth * zoom))}px`;
        canvas.style.height = `${Math.max(1, Math.round(image.naturalHeight * zoom))}px`;
        canvas.parentElement.style.minWidth = `${Math.max(1, Math.round(image.naturalWidth * zoom))}px`;
        canvas.parentElement.style.minHeight = `${Math.max(1, Math.round(image.naturalHeight * zoom))}px`;
        URL.revokeObjectURL(url);
        resolve();
      };
      image.onerror = () => {
        URL.revokeObjectURL(url);
        reject(new Error('failed to load composite preview'));
      };
      image.src = url;
    });

    if (controller.signal.aborted || requestId !== state.previewRequestId) {
      return;
    }

    const summaryResponse = await fetch(`/api/workspace/composite/summary?merge_threshold=${mergeThreshold}`, {
      signal: controller.signal,
    });
    if (summaryResponse.ok && !controller.signal.aborted && requestId === state.previewRequestId) {
      const summary = await summaryResponse.json();
      summaryEl.textContent =
        mergeThreshold > 0
          ? `Cleanup view at threshold ${mergeThreshold}. Final paths: ${summary.path_count}.`
          : `Final partition preview. Final paths: ${summary.path_count}.`;
    }
  } catch (error) {
    if (controller.signal.aborted || requestId !== state.previewRequestId) {
      return;
    }
    throw error;
  }
}

async function renderCleanupTab(workspace) {
  if (!workspace.kept_count) {
    el.mergeSummary.textContent = 'Keep at least one candidate to preview cleanup.';
    if (el.cleanupHover) {
      el.cleanupHover.textContent = 'Keep at least one candidate to inspect the final partition.';
    }
    el.mergeCanvas.width = 0;
    el.mergeCanvas.height = 0;
    el.mergeStage.style.width = 'auto';
    el.mergeStage.style.height = 'auto';
    el.finalRegionList.innerHTML = '';
    renderSelectedRegionEditor(null);
    state.finalHitmap = null;
    el.mergeCanvas.onclick = null;
    return;
  }
  await renderFinalPreview(el.mergeCanvas, el.mergeSummary, state.cleanupThreshold);
  const validation = workspace.partition_validation || {};
  const summary = workspace.design_summary || {};
  const suggestionCount = (summary.merge_suggestions || []).length;
  const geometryWarningCount =
    (summary.complex_region_ids || []).length +
    (summary.hole_region_ids || []).length +
    (summary.disconnected_region_ids || []).length;
  const suggestionText =
    suggestionCount > 0 ? `Merge suggestions: ${suggestionCount}.` : 'No merge suggestions.';
  el.mergeSummary.textContent = [
    el.mergeSummary.textContent,
    validation.partition_valid ? 'Partition valid.' : 'Partition needs attention.',
    suggestionText,
    geometryWarningCount > 0 ? `Geometry warnings: ${geometryWarningCount}.` : 'No geometry warnings.',
    `Unassigned pixels: ${validation.unassigned_px ?? 0}.`,
    `Disconnected regions: ${validation.disconnected_regions ?? 0}.`,
  ].join(' ');
  if (el.cleanupHover) {
    el.cleanupHover.textContent =
      'Hover a region to inspect it. Click the canvas or list to select regions for merge or point edits.';
  }
  await renderFinalHitmap();
  await renderFinalRegionList(workspace);
  drawCleanupWarningOverlay(workspace);
}

async function renderFinalHitmap() {
  if (!state.workspace) {
    return;
  }
  const response = await fetch('/api/workspace/composite/hitmap');
  if (!response.ok) {
    throw new Error(await response.text());
  }
  state.finalHitmap = await response.json();
  el.mergeCanvas.onmousedown = (event) => {
    if (!state.finalHitmap || !state.finalHitmap.labels || event.button !== 0) {
      return;
    }
    state.cleanupDragSelection = false;
    const point = canvasPointFromEvent(el.mergeCanvas, event, state.finalHitmap);
    if (!point.inside) {
      return;
    }
    state.cleanupDragStart = point;
  };
  el.mergeCanvas.onclick = (event) => {
    if (!state.finalHitmap || !state.finalHitmap.labels) {
      return;
    }
    if (state.cleanupDragSelection) {
      state.cleanupDragSelection = false;
      return;
    }
    const point = canvasPointFromEvent(el.mergeCanvas, event, state.finalHitmap);
    if (!point.inside) {
      return;
    }
    const regionId = state.finalHitmap.labels[point.y][point.x];
    if (!regionId || regionId <= 0) {
      return;
    }
    if (state.selectedFinalRegionIds.has(regionId)) {
      state.selectedFinalRegionIds.delete(regionId);
    } else {
      state.selectedFinalRegionIds.add(regionId);
    }
    state.activeFinalRegionId = regionId;
    updateFinalSelectionState();
  };
  el.mergeCanvas.onmouseup = (event) => {
    if (!state.finalHitmap || !state.finalHitmap.labels || !state.cleanupDragStart) {
      state.cleanupDragStart = null;
      return;
    }
    const point = canvasPointFromEvent(el.mergeCanvas, event, state.finalHitmap);
    const dx = Math.abs(point.x - state.cleanupDragStart.x);
    const dy = Math.abs(point.y - state.cleanupDragStart.y);
    const dragged = dx > 4 || dy > 4;
    if (dragged && point.inside && state.cleanupDragStart.inside) {
      const ids = regionIdsInRect(
        state.finalHitmap,
        state.cleanupDragStart.x,
        state.cleanupDragStart.y,
        point.x,
        point.y,
      );
      ids.forEach((regionId) => state.selectedFinalRegionIds.add(regionId));
      if (ids.length) {
        state.activeFinalRegionId = ids[0];
      }
      updateFinalSelectionState();
    }
    state.cleanupDragStart = null;
    state.cleanupDragSelection = dragged;
  };
  el.mergeCanvas.onmousemove = (event) => {
    if (!state.finalHitmap || !state.finalHitmap.labels) {
      return;
    }
    const point = canvasPointFromEvent(el.mergeCanvas, event, state.finalHitmap);
    if (!point.inside) {
      if (el.cleanupHover) {
        el.cleanupHover.textContent = 'Hover a region to inspect it.';
      }
      return;
    }
    const regionId = state.finalHitmap.labels[point.y][point.x];
    if (!regionId || regionId <= 0) {
      if (el.cleanupHover) {
        el.cleanupHover.textContent = 'Hover a region to inspect it.';
      }
      return;
    }
    const region = state.workspace?.final_regions?.find((item) => item.region_id === regionId);
    if (el.cleanupHover) {
      const area = region ? Math.round(region.area_physical * 100) / 100 : '?';
      const veneer = region ? region.veneer_id : '?';
      el.cleanupHover.textContent = `Region ${regionId} · veneer ${veneer} · area ${area}`;
    }
  };
  el.mergeCanvas.onmouseleave = () => {
    if (el.cleanupHover) {
      el.cleanupHover.textContent = 'Hover a region to inspect it.';
    }
  };
}

function drawCleanupWarningOverlay(workspace) {
  if (!state.finalHitmap || !state.finalHitmap.labels || !el.mergeCanvas.width || !el.mergeCanvas.height) {
    return;
  }
  const summary = workspace.design_summary || {};
  const smallIds = new Set(summary.small_region_ids || []);
  const thinIds = new Set(summary.thin_region_ids || []);
  const geometryIds = new Set([
    ...(summary.complex_region_ids || []),
    ...(summary.hole_region_ids || []),
    ...(summary.disconnected_region_ids || []),
  ]);
  if (!smallIds.size && !thinIds.size && !geometryIds.size) {
    return;
  }
  const ctx = el.mergeCanvas.getContext('2d');
  const image = ctx.getImageData(0, 0, el.mergeCanvas.width, el.mergeCanvas.height);
  const labels = state.finalHitmap.labels;
  for (let y = 0; y < labels.length; y += 1) {
    const row = labels[y];
    for (let x = 0; x < row.length; x += 1) {
      const regionId = row[x];
      let color = null;
      if (geometryIds.has(regionId)) {
        color = [226, 109, 91, 0.42];
      } else if (thinIds.has(regionId)) {
        color = [255, 94, 70, 0.36];
      } else if (smallIds.has(regionId)) {
        color = [233, 177, 80, 0.34];
      }
      if (!color) {
        continue;
      }
      const offset = (y * image.width + x) * 4;
      const alpha = color[3];
      image.data[offset] = Math.round(image.data[offset] * (1 - alpha) + color[0] * alpha);
      image.data[offset + 1] = Math.round(
        image.data[offset + 1] * (1 - alpha) + color[1] * alpha,
      );
      image.data[offset + 2] = Math.round(
        image.data[offset + 2] * (1 - alpha) + color[2] * alpha,
      );
    }
  }
  ctx.putImageData(image, 0, 0);
}

async function renderFinalRegionList(workspace) {
  const regions = workspace.final_regions || [];
  const summary = workspace.design_summary || {};
  const smallIds = new Set(summary.small_region_ids || []);
  const thinIds = new Set(summary.thin_region_ids || []);
  const complexIds = new Set(summary.complex_region_ids || []);
  const holeIds = new Set(summary.hole_region_ids || []);
  const disconnectedIds = new Set(summary.disconnected_region_ids || []);
  const suggestions = new Map((summary.merge_suggestions || []).map((item) => [item.region_id, item]));
  el.finalRegionList.innerHTML = '';
  if (!regions.length) {
    el.finalRegionList.textContent = 'No final regions yet.';
    return;
  }
  const palette = workspace.veneer_palette || [];
  for (const region of regions) {
    const item = document.createElement('article');
    item.className = 'final-region-item';
    item.dataset.regionId = String(region.region_id);
    if (smallIds.has(region.region_id)) {
      item.classList.add('small-piece');
    }
    if (thinIds.has(region.region_id)) {
      item.classList.add('thin-piece');
    }
    if (
      complexIds.has(region.region_id) ||
      holeIds.has(region.region_id) ||
      disconnectedIds.has(region.region_id)
    ) {
      item.classList.add('geometry-warning');
    }
    const warningLabels = [
      smallIds.has(region.region_id) ? 'Small region' : '',
      thinIds.has(region.region_id) ? 'Thin region' : '',
      complexIds.has(region.region_id) ? 'High point count' : '',
      holeIds.has(region.region_id) ? 'Holes' : '',
      disconnectedIds.has(region.region_id) ? 'Disconnected islands' : '',
    ].filter(Boolean);
    const veneerOptions = palette
      .map(
        (swatch) =>
          `<option value="${swatch.veneer_id}" ${swatch.veneer_id === region.veneer_id ? 'selected' : ''}>${swatch.name}</option>`,
      )
      .join('');
    item.innerHTML = `
      <div class="row">
        <strong>Region ${region.region_id}</strong>
        <span class="muted">${region.veneer_override_id ? 'override' : 'auto'}${region.locked ? ' / locked' : ''}</span>
      </div>
      <div class="muted">Area ${Math.round(region.area_physical * 100) / 100} / refs ${region.source_refs.length}</div>
      <div class="muted">${warningLabels.join(' / ')}</div>
      ${
        suggestions.has(region.region_id)
          ? `<div class="row cleanup-suggestion">
              <span class="muted">Suggest merge with ${suggestions.get(region.region_id).target_region_id}</span>
              <button type="button" class="suggest-merge-btn">Merge suggested</button>
            </div>`
          : ''
      }
      <label class="field final-region-veneer" title="Assign this final region to a veneer swatch.">
        <span>Veneer</span>
        <select data-region-id="${region.region_id}">
          <option value="">Auto</option>
          ${veneerOptions}
        </select>
      </label>
      <label class="check-row final-region-lock" title="Keep this region from merge and split operations.">
        <input type="checkbox" ${region.locked ? 'checked' : ''} />
        <span>Lock region</span>
      </label>
    `;
    item.addEventListener('click', () => {
      const regionId = Number(item.dataset.regionId);
      if (state.selectedFinalRegionIds.has(regionId)) {
        state.selectedFinalRegionIds.delete(regionId);
      } else {
        state.selectedFinalRegionIds.add(regionId);
      }
      state.activeFinalRegionId = regionId;
      updateFinalSelectionState();
    });
    const veneerSelect = item.querySelector('select');
    if (veneerSelect) {
      veneerSelect.value = region.veneer_override_id || '';
      veneerSelect.addEventListener('click', (event) => {
        event.stopPropagation();
      });
      veneerSelect.addEventListener('change', async (event) => {
        event.stopPropagation();
        await saveFinalRegionVeneer(region.region_id, veneerSelect.value || null);
      });
    }
    const lockInput = item.querySelector('.final-region-lock input');
    if (lockInput) {
      lockInput.addEventListener('click', (event) => {
        event.stopPropagation();
      });
      lockInput.addEventListener('change', async (event) => {
        event.stopPropagation();
        await saveFinalRegionLock(region.region_id, lockInput.checked);
      });
    }
    const suggestButton = item.querySelector('.suggest-merge-btn');
    if (suggestButton) {
      suggestButton.addEventListener('click', async (event) => {
        event.stopPropagation();
        const suggestion = suggestions.get(region.region_id);
        if (!suggestion) {
          return;
        }
        await mergeSuggestedRegions([region.region_id, suggestion.target_region_id]);
      });
    }
    el.finalRegionList.appendChild(item);
  }
  updateFinalSelectionState();
  renderSelectedRegionEditor(workspace);
}

async function mergeSuggestedRegions(regionIds) {
  setBusy(true);
  try {
    const response = await fetch('/api/workspace/final/merge', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({region_ids: regionIds}),
    });
    if (!response.ok) {
      throw new Error(await response.text());
    }
    const workspace = await response.json();
    await refreshWorkspace(workspace);
    setStatus(`Merged suggested regions ${regionIds.join(', ')}.`);
  } finally {
    setBusy(false);
  }
}

async function renderPackTab(workspace) {
  const summary = workspace.design_summary || {};
  const physical = workspace.physical_size || {};
  el.packSummary.textContent = [
    `Physical size: ${physical.width ?? 1} x ${physical.height ?? 1} ${physical.unit || 'px'}.`,
    `Regions: ${summary.region_count ?? 0}.`,
    `Veneer groups: ${Object.keys(summary.veneer_counts || {}).length}.`,
    summary.partition_valid === false ? 'Partition requires attention.' : 'Partition is valid.',
  ].join(' ');
}

async function refreshWorkspace(workspace) {
  state.workspace = workspace;
  setWorkspaceSummary(workspace);
  renderImageTab(workspace);
  renderShapesTab(workspace);
  if (state.mode === 'hues') {
    await renderHuesTab(workspace);
  } else if (state.mode === 'cleanup') {
    await renderCleanupTab(workspace);
  } else if (state.mode === 'pack') {
    await renderPackTab(workspace);
  }
}

async function togglePaletteRegion(candidateId, detail, regionId) {
  const next = new Set(detail.selected_region_ids || []);
  if (next.has(regionId)) {
    next.delete(regionId);
  } else {
    next.add(regionId);
  }
  await saveCandidateSelection(candidateId, [...next]);
}

async function paintAllCandidate(candidateId) {
  setBusy(true);
  try {
    const response = await fetch('/api/workspace/selection/paint-all', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({candidate_id: candidateId}),
    });
    if (!response.ok) {
      throw new Error(await response.text());
    }
    const workspace = await response.json();
    await refreshWorkspace(workspace);
    setStatus(`Painted all regions on ${candidateLabel(workspace.active_candidate)}`);
  } finally {
    setBusy(false);
  }
}

async function clearCandidateSelection(candidateId) {
  setBusy(true);
  try {
    const response = await fetch('/api/workspace/selection/clear', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({candidate_id: candidateId}),
    });
    if (!response.ok) {
      throw new Error(await response.text());
    }
    const workspace = await response.json();
    await refreshWorkspace(workspace);
    setStatus(`Cleared painted regions on ${candidateLabel(workspace.active_candidate)}`);
  } finally {
    setBusy(false);
  }
}

async function saveCandidateSelection(candidateId, regionIds) {
  setBusy(true);
  try {
    const response = await fetch('/api/workspace/selection', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({
        candidate_id: candidateId,
        region_ids: regionIds,
        additive: false,
      }),
    });
    if (!response.ok) {
      throw new Error(await response.text());
    }
    const workspace = await response.json();
    await refreshWorkspace(workspace);
    setStatus(`Painted ${regionIds.length} regions on ${candidateLabel(workspace.active_candidate)}`);
  } finally {
    setBusy(false);
  }
}

async function toggleKeep(candidateId) {
  setBusy(true);
  try {
    const response = await fetch('/api/workspace/keep', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({candidate_id: candidateId}),
    });
    if (!response.ok) {
      throw new Error(await response.text());
    }
    const workspace = await response.json();
    await refreshWorkspace(workspace);
    state.activeCandidateId = workspace.active_candidate_id;
  } finally {
    setBusy(false);
  }
}

async function refineActive() {
  if (!state.activeCandidateId) {
    return;
  }
  setBusy(true);
  try {
    setStatus('Refining active candidate...');
    const response = await fetch('/api/workspace/refine-job', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({candidate_id: state.activeCandidateId}),
    });
    if (!response.ok) {
      throw new Error(await response.text());
    }
    const {job_id: jobId} = await response.json();
    state.activeJobId = jobId;
    await waitForJob(jobId);
  } finally {
    setBusy(false);
  }
}

async function rebuildGrid() {
  setBusy(true);
  try {
    const response = await fetch('/api/workspace/grid-job', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({
        rows: Number(el.gridRows.value),
        cols: Number(el.gridCols.value),
      }),
    });
    if (!response.ok) {
      throw new Error(await response.text());
    }
    const {job_id: jobId} = await response.json();
    state.activeJobId = jobId;
    await waitForJob(jobId);
  } finally {
    setBusy(false);
  }
}

async function waitForJob(jobId) {
  if (!jobId) {
    return;
  }
  while (true) {
    const response = await fetch(`/api/jobs/${jobId}`);
    if (!response.ok) {
      throw new Error(await response.text());
    }
    const job = await response.json();
    state.activeJobId = jobId;
    setStatus(`${job.kind}: ${job.message} (${Math.round((job.progress || 0) * 100)}%)`);
    if (job.status === 'complete') {
      if (job.result) {
        await refreshWorkspace(job.result);
        const active =
          job.result.active_candidate_id || (job.result.candidates[0] && job.result.candidates[0].candidate_id);
        if (active) {
          await openCandidate(active);
        }
      }
      state.activeJobId = null;
      return;
    }
    if (job.status === 'failed') {
      state.activeJobId = null;
      throw new Error(job.error || 'job failed');
    }
    await new Promise((resolve) => window.setTimeout(resolve, 250));
  }
}

async function resetWorkspace() {
  const confirmed = window.confirm(
    'Reset the workspace? This deletes generated candidates and selections, then rebuilds from the source image.',
  );
  if (!confirmed) {
    return;
  }
  setBusy(true);
  try {
    const response = await fetch('/api/workspace/reset', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({
        rows: Number(el.gridRows.value),
        cols: Number(el.gridCols.value),
      }),
    });
    if (!response.ok) {
      throw new Error(await response.text());
    }
    const workspace = await response.json();
    await refreshWorkspace(workspace);
    const active = workspace.active_candidate_id || (workspace.candidates[0] && workspace.candidates[0].candidate_id);
    if (active) {
      await openCandidate(active);
    }
    setStatus(`Reset workspace to a clean ${workspace.grid_rows}x${workspace.grid_cols} grid.`);
  } finally {
    setBusy(false);
  }
}

async function applySize() {
  setBusy(true);
  try {
    const response = await fetch('/api/workspace/size', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({
        width: Number(el.physicalWidth.value),
        height: Number(el.physicalHeight.value),
        unit: el.physicalUnit.value || 'px',
      }),
    });
    if (!response.ok) {
      throw new Error(await response.text());
    }
    const workspace = await response.json();
    await refreshWorkspace(workspace);
    setStatus(
      `Set physical size to ${workspace.physical_size.width} x ${workspace.physical_size.height} ${workspace.physical_size.unit}.`,
    );
  } finally {
    setBusy(false);
  }
}

async function saveSubject() {
  setBusy(true);
  try {
    const response = await fetch('/api/workspace/subject', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({
        detail_budget: Number(el.subjectDetailBudget.value) / 100,
        notes: el.subjectNotes.value,
        protect_eyes: el.subjectProtectEyes.checked,
        protect_nose: el.subjectProtectNose.checked,
      }),
    });
    if (!response.ok) {
      throw new Error(await response.text());
    }
    const workspace = await response.json();
    await refreshWorkspace(workspace);
    setStatus('Saved subject settings.');
  } finally {
    setBusy(false);
  }
}

async function exportPreviewSvg() {
  setBusy(true);
  try {
    const response = await fetch('/api/workspace/composite/export', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({output_dir: el.exportDir.value, merge_threshold: 0}),
    });
    if (!response.ok) {
      throw new Error(await response.text());
    }
    const payload = await response.json();
    setStatus(`Exported ${payload.composite_png} and ${payload.composite_svg}.`);
  } finally {
    setBusy(false);
  }
}

async function packFinal() {
  setBusy(true);
  try {
    const response = await fetch('/api/workspace/pack', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({output_dir: el.exportDir.value}),
    });
    if (!response.ok) {
      throw new Error(await response.text());
    }
    const payload = await response.json();
    setStatus(`Packed ${payload.packed_sheets.length} veneer sheets to ${payload.output_dir}.`);
    el.packSummary.textContent = `Packed ${payload.packed_sheets.length} veneer sheets.`;
  } finally {
    setBusy(false);
  }
}

async function mergeSelectedRegions() {
  if (!state.selectedFinalRegionIds.size) {
    setStatus('Select one or more final regions to merge.', true);
    return;
  }
  setBusy(true);
  try {
    const response = await fetch('/api/workspace/final/merge', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({region_ids: [...state.selectedFinalRegionIds]}),
    });
    if (!response.ok) {
      throw new Error(await response.text());
    }
    const workspace = await response.json();
    await refreshWorkspace(workspace);
    state.selectedFinalRegionIds.clear();
    await renderCleanupTab(workspace);
    setStatus('Merged selected final regions.');
  } finally {
    setBusy(false);
  }
}

async function mergeAllSuggestions() {
  setBusy(true);
  try {
    const response = await fetch('/api/workspace/final/merge-suggestions', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({}),
    });
    if (!response.ok) {
      throw new Error(await response.text());
    }
    const workspace = await response.json();
    await refreshWorkspace(workspace);
    state.selectedFinalRegionIds.clear();
    await renderCleanupTab(workspace);
    setStatus('Merged cleanup suggestions.');
  } finally {
    setBusy(false);
  }
}

async function saveFinalRegionVeneer(regionId, veneerId) {
  setBusy(true);
  try {
    const response = await fetch('/api/workspace/final/veneer', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({
        region_id: regionId,
        veneer_id: veneerId,
      }),
    });
    if (!response.ok) {
      throw new Error(await response.text());
    }
    const workspace = await response.json();
    await refreshWorkspace(workspace);
    if (state.mode === 'cleanup') {
      await renderCleanupTab(workspace);
    }
    setStatus(`Updated veneer for region ${regionId}.`);
  } finally {
    setBusy(false);
  }
}

async function saveFinalRegionLock(regionId, locked) {
  setBusy(true);
  try {
    const response = await fetch('/api/workspace/final/lock', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({
        region_id: regionId,
        locked,
      }),
    });
    if (!response.ok) {
      throw new Error(await response.text());
    }
    const workspace = await response.json();
    await refreshWorkspace(workspace);
    if (state.mode === 'cleanup') {
      await renderCleanupTab(workspace);
    }
    setStatus(`${locked ? 'Locked' : 'Unlocked'} region ${regionId}.`);
  } finally {
    setBusy(false);
  }
}

async function saveFinalRegionPoint(regionId, pointIndex, x, y) {
  setBusy(true);
  try {
    const response = await fetch('/api/workspace/final/point', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({
        region_id: regionId,
        point_index: pointIndex,
        x,
        y,
      }),
    });
    if (!response.ok) {
      throw new Error(await response.text());
    }
    const workspace = await response.json();
    await refreshWorkspace(workspace);
    if (state.mode === 'cleanup') {
      await renderCleanupTab(workspace);
    }
    setStatus(`Moved point ${pointIndex} on region ${regionId}.`);
  } finally {
    setBusy(false);
  }
}

async function smoothFinalRegion(regionId, tolerance = 1.5) {
  setBusy(true);
  try {
    const response = await fetch('/api/workspace/final/smooth', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({
        region_id: regionId,
        tolerance,
      }),
    });
    if (!response.ok) {
      throw new Error(await response.text());
    }
    const workspace = await response.json();
    await refreshWorkspace(workspace);
    if (state.mode === 'cleanup') {
      await renderCleanupTab(workspace);
    }
    setStatus(`Smoothed region ${regionId}.`);
  } finally {
    setBusy(false);
  }
}

async function splitSelectedRegion() {
  if (!state.selectedFinalRegionIds.size) {
    setStatus('Select one final region to split.', true);
    return;
  }
  const regionId = [...state.selectedFinalRegionIds][0];
  setBusy(true);
  try {
    const response = await fetch('/api/workspace/final/split', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({
        region_id: regionId,
        target_segments: Number(el.splitTarget.value || 4),
      }),
    });
    if (!response.ok) {
      throw new Error(await response.text());
    }
    const workspace = await response.json();
    await refreshWorkspace(workspace);
    state.selectedFinalRegionIds.clear();
    await renderCleanupTab(workspace);
    setStatus(`Split region ${regionId}.`);
  } finally {
    setBusy(false);
  }
}

function scheduleCleanupRender() {
  if (state.cleanupRenderTimer) {
    window.clearTimeout(state.cleanupRenderTimer);
  }
  state.cleanupRenderTimer = window.setTimeout(() => {
    state.cleanupRenderTimer = null;
    if (state.workspace && state.mode === 'cleanup') {
      renderCleanupTab(state.workspace).catch((error) => setStatus(String(error), true));
    }
  }, 150);
}

async function renderCleanupControls() {
  el.mergeThresholdValue.textContent = String(state.cleanupThreshold);
  if (state.workspace) {
    await renderCleanupTab(state.workspace);
  }
}

async function updateCleanupThresholdFromWorkspace(workspace) {
  const cleanup = workspace.cleanup_settings || {};
  el.simplifyTolerance.value = String(cleanup.simplify_tolerance ?? 1.0);
  el.simplifyToleranceValue.textContent = String(cleanup.simplify_tolerance ?? 1.0);
  el.smallArea.value = String(cleanup.highlight_small_area ?? 0.0);
  el.smallAreaValue.textContent = String(cleanup.highlight_small_area ?? 0.0);
  el.thinWidth.value = String(cleanup.highlight_thin_width ?? 0.0);
  el.thinWidthValue.textContent = String(cleanup.highlight_thin_width ?? 0.0);
  state.cleanupThreshold = Number(cleanup.merge_rgb_threshold ?? 24);
  el.mergeThreshold.value = String(state.cleanupThreshold);
  el.mergeThresholdValue.textContent = String(state.cleanupThreshold);
}

async function saveCleanupSettings() {
  setBusy(true);
  try {
    const response = await fetch('/api/workspace/cleanup', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({
        simplify_tolerance: Number(el.simplifyTolerance.value),
        highlight_small_area: Number(el.smallArea.value),
        highlight_thin_width: Number(el.thinWidth.value),
        merge_rgb_threshold: Number(el.mergeThreshold.value),
      }),
    });
    if (!response.ok) {
      throw new Error(await response.text());
    }
    const workspace = await response.json();
    await refreshWorkspace(workspace);
    await updateCleanupThresholdFromWorkspace(workspace);
    setStatus('Saved cleanup settings.');
  } finally {
    setBusy(false);
  }
}

el.openImageBtn.addEventListener('click', openSelectedImage);
el.openImageBtnPanel.addEventListener('click', openSelectedImage);
el.sourceImageInput.addEventListener('change', () => {
  if (el.sourceImageInput.files && el.sourceImageInput.files[0]) {
    el.landingStatus.textContent = `Selected ${el.sourceImageInput.files[0].name}.`;
    state.imageFileName = el.sourceImageInput.files[0].name;
  }
});
el.sourceImageInputPanel.addEventListener('change', () => {
  if (el.sourceImageInputPanel.files && el.sourceImageInputPanel.files[0]) {
    el.landingStatus.textContent = `Selected ${el.sourceImageInputPanel.files[0].name}.`;
    state.imageFileName = el.sourceImageInputPanel.files[0].name;
  }
});
el.imageTabBtn.addEventListener('click', () => setMode('image'));
el.sizeTabBtn.addEventListener('click', () => setMode('size'));
el.subjectTabBtn.addEventListener('click', () => setMode('subject'));
el.shapesTabBtn.addEventListener('click', () => setMode('shapes'));
el.huesTabBtn.addEventListener('click', () => setMode('hues'));
el.cleanupTabBtn.addEventListener('click', () => setMode('cleanup'));
el.packTabBtn.addEventListener('click', () => setMode('pack'));
el.applySizeBtn.addEventListener('click', applySize);
el.saveSubjectBtn.addEventListener('click', saveSubject);
el.rebuildGridBtn.addEventListener('click', rebuildGrid);
el.resetWorkspaceBtn.addEventListener('click', resetWorkspace);
el.saveCleanupBtn.addEventListener('click', saveCleanupSettings);
el.addVeneerBtn.addEventListener('click', addVeneerRow);
el.saveVeneerPaletteBtn.addEventListener('click', saveVeneerPalette);
el.mergeSelectedBtn.addEventListener('click', mergeSelectedRegions);
el.mergeSuggestionsBtn.addEventListener('click', mergeAllSuggestions);
el.splitSelectedBtn.addEventListener('click', splitSelectedRegion);
el.exportBtn.addEventListener('click', exportPreviewSvg);
el.exportFinalBtn.addEventListener('click', packFinal);
el.finalPointMoveBtn.addEventListener('click', async () => {
  const workspace = state.workspace;
  const region = selectedFinalRegion(workspace);
  if (!region) {
    setStatus('Select a final region first.', true);
    return;
  }
  const pointIndex = Number(el.finalPointIndex.value);
  await saveFinalRegionPoint(
    region.region_id,
    Number.isFinite(pointIndex) ? pointIndex : 0,
    Number(el.finalPointX.value),
    Number(el.finalPointY.value),
  );
});
el.finalSmoothBtn.addEventListener('click', async () => {
  const workspace = state.workspace;
  const region = selectedFinalRegion(workspace);
  if (!region) {
    setStatus('Select a final region first.', true);
    return;
  }
  await smoothFinalRegion(region.region_id, 1.5);
});
el.finalPointIndex.addEventListener('input', () => {
  if (state.workspace && state.mode === 'cleanup') {
    renderSelectedRegionEditor(state.workspace);
  }
});
el.mergeThreshold.addEventListener('input', () => {
  state.cleanupThreshold = Number(el.mergeThreshold.value);
  el.mergeThresholdValue.textContent = String(state.cleanupThreshold);
  scheduleCleanupRender();
});
el.simplifyTolerance.addEventListener('input', () => {
  el.simplifyToleranceValue.textContent = String(Number(el.simplifyTolerance.value).toFixed(1));
  scheduleCleanupRender();
});
el.smallArea.addEventListener('input', () => {
  el.smallAreaValue.textContent = String(Number(el.smallArea.value).toFixed(1));
  scheduleCleanupRender();
});
el.thinWidth.addEventListener('input', () => {
  el.thinWidthValue.textContent = String(Number(el.thinWidth.value).toFixed(1));
  scheduleCleanupRender();
});
window.addEventListener('resize', () => {
  if (state.workspace && state.mode === 'hues') {
    renderHuesTab(state.workspace).catch((error) => setStatus(String(error), true));
  } else if (state.workspace && state.mode === 'cleanup') {
    renderCleanupTab(state.workspace).catch((error) => setStatus(String(error), true));
  }
});

setEmptyWorkspaceState();
fetchWorkspace().catch((error) => {
  setStatus(String(error), true);
});
