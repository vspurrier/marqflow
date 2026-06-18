    const state = {
      workspace: null,
      active: null,
      composeFitZoom: 1,
      mergeThreshold: 24,
      composeSize: null,
      mode: 'search',
      composeDetails: {},
      candidateDetailCache: {},
      candidateSvgCache: {},
      previewRequestId: 0,
      previewAbortController: null,
      mergeRenderTimer: null,
    };

    const el = {
      workspacePill: document.getElementById('workspace-pill'),
      statusPill: document.getElementById('status-pill'),
      candidateSelect: document.getElementById('candidate-select'),
      keepBtn: document.getElementById('keep-btn'),
      refineBtn: document.getElementById('refine-btn'),
      exportBtn: document.getElementById('export-btn'),
      exportDir: document.getElementById('export-dir'),
      searchTabBtn: document.getElementById('search-tab-btn'),
      composeTabBtn: document.getElementById('compose-tab-btn'),
      mergeTabBtn: document.getElementById('merge-tab-btn'),
      searchPanel: document.getElementById('search-panel'),
      composePanel: document.getElementById('compose-panel'),
      mergePanel: document.getElementById('merge-panel'),
      keptStrip: document.getElementById('kept-strip'),
      composeStage: document.getElementById('compose-stage'),
      composeCanvas: document.getElementById('compose-canvas'),
      mergeStage: document.getElementById('merge-stage'),
      mergeCanvas: document.getElementById('merge-canvas'),
      composePaletteList: document.getElementById('compose-palette-list'),
      composeKeptCount: document.getElementById('compose-kept-count'),
      mergeThreshold: document.getElementById('merge-threshold'),
      mergeThresholdValue: document.getElementById('merge-threshold-value'),
      exportFinalBtn: document.getElementById('export-final-btn'),
      composeSummary: document.getElementById('compose-summary'),
      mergeSummary: document.getElementById('merge-summary'),
      grid: document.getElementById('grid'),
      candidateCount: document.getElementById('candidate-count'),
    };

    function setBusy(isBusy) {
      document.body.classList.toggle('busy', isBusy);
    }

    function setStatus(text, error = false) {
      el.statusPill.textContent = text;
      el.statusPill.style.color = error ? 'var(--danger)' : 'var(--muted)';
    }

    function candidateLabel(candidate) {
      return candidate.label || candidate.candidate_id.slice(0, 8);
    }

    function updateComposeActiveCandidate(candidateId) {
      document.querySelectorAll('.compose-candidate').forEach((card) => {
        card.classList.toggle('active', card.dataset.candidateId === candidateId);
      });
    }

    function setWorkspaceSummary(workspace) {
      el.workspacePill.textContent = `${workspace.candidate_count} candidates · ${workspace.kept_count} kept`;
      el.candidateCount.textContent = workspace.candidate_count;
    }

    function setMode(mode) {
      state.mode = mode;
      el.searchPanel.classList.toggle('active', mode === 'search');
      el.composePanel.classList.toggle('active', mode === 'compose');
      el.mergePanel.classList.toggle('active', mode === 'merge');
      el.searchTabBtn.classList.toggle('active', mode === 'search');
      el.composeTabBtn.classList.toggle('active', mode === 'compose');
      el.mergeTabBtn.classList.toggle('active', mode === 'merge');
      if (mode === 'compose' && state.workspace) {
        renderComposeWorkspace(state.workspace).catch((error) => setStatus(String(error), true));
      } else if (mode === 'merge' && state.workspace) {
        renderMergeWorkspace(state.workspace).catch((error) => setStatus(String(error), true));
      }
    }

    function renderSelect(workspace) {
      el.candidateSelect.innerHTML = '';
      for (const candidate of workspace.candidates) {
        const option = document.createElement('option');
        option.value = candidate.candidate_id;
        option.textContent = `${candidateLabel(candidate)} · ${candidate.region_count} regions`;
        if (candidate.candidate_id === workspace.active_candidate_id) {
          option.selected = true;
        }
        el.candidateSelect.appendChild(option);
      }
    }

    function renderGrid(workspace) {
      el.grid.innerHTML = '';
      for (const candidate of workspace.candidates) {
        const card = document.createElement('div');
        card.className = 'candidate' + (candidate.candidate_id === workspace.active_candidate_id ? ' active' : '') + (candidate.kept ? ' kept' : '');

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
        sub.textContent = `${candidate.region_count} regions · gen ${candidate.generation}`;

        const preset = candidate.preset || {};
        const details = document.createElement('div');
        details.className = 'sub';
        details.textContent = `segments ${preset.target_segments} · compactness ${Number(preset.compactness).toFixed(1)}`;

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

    function applyComposeZoom(zoom) {
      state.composeFitZoom = zoom;
      if (!state.composeSize) {
        return;
      }
      const width = Math.max(1, Math.round(state.composeSize.width * zoom));
      const height = Math.max(1, Math.round(state.composeSize.height * zoom));
      el.composeStage.style.width = `${width}px`;
      el.composeStage.style.height = `${height}px`;
      el.composeCanvas.style.width = '100%';
      el.composeCanvas.style.height = '100%';
    }

    async function fetchWorkspace() {
      setBusy(true);
      try {
        const response = await fetch('/api/workspace');
        if (!response.ok) {
          throw new Error(await response.text());
        }
        const workspace = await response.json();
        state.workspace = workspace;
        setWorkspaceSummary(workspace);
        renderSelect(workspace);
        renderGrid(workspace);
        renderKeptStrip(workspace);
        const active = workspace.active_candidate_id || (workspace.candidates[0] && workspace.candidates[0].candidate_id);
        if (active) {
          await openCandidate(active);
        }
        if (state.mode === 'compose' || state.mode === 'merge') {
          if (state.mode === 'compose') {
            await renderComposeWorkspace(workspace);
          } else {
            await renderMergeWorkspace(workspace);
          }
        }
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
        setStatus(`Loading ${candidateId}…`);
        const detail = await fetchCandidate(candidateId);
        state.active = candidateId;
        el.candidateSelect.value = candidateId;
        await syncActiveCandidate(candidateId);
        setStatus(`Active ${candidateLabel(detail)} · ${detail.region_count} regions`);
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
      renderSelect(workspace);
      renderGrid(workspace);
      renderKeptStrip(workspace);
      return workspace;
    }

    async function renderComposeWorkspace(workspace) {
      const kept = workspace.candidates.filter((candidate) => candidate.kept);
      el.composeKeptCount.textContent = kept.length;
      el.composePaletteList.innerHTML = '';
      state.composeDetails = {};
      if (!kept.length) {
        el.composeSummary.textContent = 'Keep at least one candidate to start painting the composite.';
        el.composeStage.style.width = 'auto';
        el.composeStage.style.height = 'auto';
        el.composeCanvas.width = 0;
        el.composeCanvas.height = 0;
        el.composeCanvas.getContext('2d').clearRect(0, 0, 0, 0);
        return;
      }

      state.composeSize =
        state.composeSize || {
          width: Math.max(1, Math.round(el.composeCanvas.clientWidth || 960)),
          height: Math.max(1, Math.round(el.composeCanvas.clientHeight || 720)),
        };
      void renderCompositeCanvas(el.composeCanvas, el.composeSummary, 0).catch((error) =>
        setStatus(String(error), true),
      );
      applyComposeZoom(composeFitZoom());

      await Promise.all(
        kept.map((candidate) =>
          renderComposeCandidate(candidate).catch((error) => setStatus(String(error), true)),
        ),
      );
    }

    async function renderMergeWorkspace(workspace) {
      if (!workspace.kept_count) {
        el.mergeSummary.textContent = 'Keep at least one candidate to preview the merge.';
        el.mergeCanvas.width = 0;
        el.mergeCanvas.height = 0;
        el.mergeStage.style.width = 'auto';
        el.mergeStage.style.height = 'auto';
        return;
      }
      void renderCompositeCanvas(el.mergeCanvas, el.mergeSummary, state.mergeThreshold).catch(
        (error) => setStatus(String(error), true),
      );
      applyMergeZoom();
    }

    function scheduleMergeRender() {
      if (state.mergeRenderTimer) {
        window.clearTimeout(state.mergeRenderTimer);
      }
      state.mergeRenderTimer = window.setTimeout(() => {
        state.mergeRenderTimer = null;
        if (state.workspace && state.mode === 'merge') {
          renderMergeWorkspace(state.workspace).catch((error) => setStatus(String(error), true));
        }
      }, 180);
    }

    async function renderComposeCandidate(candidate) {
      let detail = state.composeDetails[candidate.candidate_id];
      if (!detail) {
        detail = {
          candidate_id: candidate.candidate_id,
          label: candidate.label,
          selected_region_ids: candidate.selected_region_ids || [],
          regions: [],
          svg_url: candidate.svg_url,
        };
        state.composeDetails[candidate.candidate_id] = detail;
      }

      const card = document.createElement('article');
      card.className = 'compose-candidate' + (candidate.candidate_id === state.active ? ' active' : '');
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
      sub.textContent = `${candidate.region_count} regions · ${detail.selected_region_ids.length} painted`;
      titleRow.append(name, sub);
      const paintBtn = document.createElement('button');
      paintBtn.className = 'paint-btn';
      paintBtn.textContent = 'Paint all';
      paintBtn.title = 'Paint every region from this candidate onto the composite.';
      paintBtn.addEventListener('click', async (event) => {
        event.stopPropagation();
        await paintAllCandidate(candidate.candidate_id);
      });
      const clearBtn = document.createElement('button');
      clearBtn.className = 'paint-btn secondary';
      clearBtn.textContent = 'Clear';
      clearBtn.title = 'Clear painted regions from this candidate.';
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
      img.addEventListener('load', () => {
        if (img.naturalWidth > 0 && img.naturalHeight > 0) {
          preview.style.setProperty('--preview-aspect', `${img.naturalWidth} / ${img.naturalHeight}`);
        }
      });
      const overlay = document.createElement('div');
      overlay.className = 'compose-candidate-svg';
      preview.append(img, overlay);

      const foot = document.createElement('div');
      foot.className = 'foot';
      const selected = document.createElement('span');
      selected.className = 'selected-stat';
      selected.textContent = `${(detail.selected_region_ids || []).length} selected`;
      const selectAllHint = document.createElement('span');
      selectAllHint.textContent = 'Click regions to paint';
      foot.append(selected, selectAllHint);

      card.append(head, preview, foot);
      el.composePaletteList.appendChild(card);

      const fullDetail =
        state.candidateDetailCache[candidate.candidate_id] ||
        (detail.regions && detail.regions.length ? detail : await fetchCandidate(candidate.candidate_id));
      state.candidateDetailCache[candidate.candidate_id] = fullDetail;
      fullDetail.selected_region_ids = detail.selected_region_ids || fullDetail.selected_region_ids || [];
      state.composeDetails[candidate.candidate_id] = fullDetail;
      selected.textContent = `${fullDetail.selected_region_ids.length} selected`;

      const svgText =
        state.candidateSvgCache[candidate.candidate_id] ||
        (await (async () => {
          const response = await fetch(fullDetail.svg_url);
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
          path.classList.toggle('selected', (fullDetail.selected_region_ids || []).includes(id));
        });
        svg.addEventListener('click', async (event) => {
          const path = event.target.closest('path');
          if (!path || !svg.contains(path)) {
            return;
          }
          event.stopPropagation();
          await togglePaletteRegion(candidate.candidate_id, fullDetail, Number(path.dataset.regionId));
        });
      }
    }

    function composeFitZoom() {
      const size = state.composeSize;
      if (!size) {
        return 1;
      }
      const wrap = el.composeCanvas.closest('.compose-canvas-wrap');
      const availableWidth = Math.max(320, wrap.clientWidth - 36);
      const availableHeight = Math.max(360, window.innerHeight - 320);
      const zoom = Math.max(
        0.15,
        Math.min(availableWidth / size.width, availableHeight / size.height),
      );
      state.composeFitZoom = zoom;
      return zoom;
    }

    function mergeFitZoom() {
      const size = state.composeSize;
      if (!size) {
        return 1;
      }
      const wrap = el.mergeCanvas.closest('.compose-canvas-wrap');
      const availableWidth = Math.max(320, wrap.clientWidth - 36);
      const availableHeight = Math.max(360, window.innerHeight - 320);
      return Math.max(0.15, Math.min(availableWidth / size.width, availableHeight / size.height));
    }

    function applyMergeZoom() {
      if (!state.composeSize) {
        return;
      }
      const zoom = mergeFitZoom();
      const width = Math.max(1, Math.round(state.composeSize.width * zoom));
      const height = Math.max(1, Math.round(state.composeSize.height * zoom));
      el.mergeStage.style.width = `${width}px`;
      el.mergeStage.style.height = `${height}px`;
      el.mergeCanvas.style.width = '100%';
      el.mergeCanvas.style.height = '100%';
    }

    async function renderCompositeCanvas(canvas, summaryEl, mergeThreshold = 0) {
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
        const response = await fetch(
          `/api/workspace/composite/preview?merge_threshold=${mergeThreshold}`,
          {signal: controller.signal},
        );
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
            state.composeSize = {width: image.naturalWidth, height: image.naturalHeight};
            if (canvas === el.composeCanvas) {
              applyComposeZoom(composeFitZoom());
            } else {
              applyMergeZoom();
            }
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

        const summaryResponse = await fetch(
          `/api/workspace/composite/summary?merge_threshold=${mergeThreshold}`,
          {signal: controller.signal},
        );
        if (summaryResponse.ok && !controller.signal.aborted && requestId === state.previewRequestId) {
          const summary = await summaryResponse.json();
          summaryEl.textContent =
            mergeThreshold > 0
              ? `Merge view at threshold ${mergeThreshold}. Final paths: ${summary.path_count}.`
              : `Painted composite preview. Final paths: ${summary.path_count}.`;
        }
      } catch (error) {
        if (controller.signal.aborted || requestId !== state.previewRequestId) {
          return;
        }
        throw error;
      }
    }

    async function refreshWorkspace(workspace) {
      state.workspace = workspace;
      setWorkspaceSummary(workspace);
      renderSelect(workspace);
      renderGrid(workspace);
      renderKeptStrip(workspace);
      if (state.mode === 'compose') {
        await renderComposeWorkspace(workspace);
      } else if (state.mode === 'merge') {
        await renderMergeWorkspace(workspace);
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
        state.active = workspace.active_candidate_id;
        el.candidateSelect.value = workspace.active_candidate_id;
        updateComposeActiveCandidate(workspace.active_candidate_id);
      } finally {
        setBusy(false);
      }
    }

    async function refineActive() {
      if (!state.active) {
        return;
      }
      setBusy(true);
      try {
        setStatus('Refining active candidate…');
        const response = await fetch('/api/workspace/refine', {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({candidate_id: state.active}),
        });
        if (!response.ok) {
          throw new Error(await response.text());
        }
        const workspace = await response.json();
        await refreshWorkspace(workspace);
        const active = workspace.active_candidate_id;
        if (active) {
          await openCandidate(active);
        }
      } finally {
        setBusy(false);
      }
    }

    async function exportComposite() {
      setBusy(true);
      try {
        const threshold = state.mode === 'merge' ? state.mergeThreshold : 0;
        const response = await fetch('/api/workspace/composite/export', {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({output_dir: el.exportDir.value, merge_threshold: threshold}),
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

    el.candidateSelect.addEventListener('change', () => {
      if (el.candidateSelect.value) {
        openCandidate(el.candidateSelect.value);
      }
    });
    el.keepBtn.addEventListener('click', () => {
      if (state.active) {
        toggleKeep(state.active);
      }
    });
    el.refineBtn.addEventListener('click', refineActive);
    el.exportBtn.addEventListener('click', exportComposite);
    el.exportFinalBtn.addEventListener('click', exportComposite);
    el.mergeThreshold.addEventListener('input', () => {
      state.mergeThreshold = Number(el.mergeThreshold.value);
      el.mergeThresholdValue.textContent = String(state.mergeThreshold);
      scheduleMergeRender();
    });
    el.searchTabBtn.addEventListener('click', () => setMode('search'));
    el.composeTabBtn.addEventListener('click', () => setMode('compose'));
    el.mergeTabBtn.addEventListener('click', () => setMode('merge'));
    window.addEventListener('resize', () => {
      if (state.mode === 'compose' && state.workspace) {
        applyComposeZoom(composeFitZoom());
      } else if (state.mode === 'merge' && state.workspace) {
        applyMergeZoom();
      }
    });

    fetchWorkspace().catch((error) => {
      setStatus(String(error), true);
    });
  
