"""Grid-search workspace for candidate marquetry region maps.

The workspace is the gallery layer on top of the single-project pipeline.
It owns a grid of segmentation presets, tracks which candidates are kept,
and stores the region selections that feed the compose/merge stages.
"""

from __future__ import annotations

import csv
import json
import os
import re
import shutil
import tempfile
from collections.abc import Iterable
from dataclasses import asdict, dataclass, field
from functools import lru_cache
from pathlib import Path
from time import time_ns
from typing import Any

import numpy as np
from PIL import Image
from skimage.measure import approximate_polygon, find_contours
from skimage.measure import label as connected_components

from .config import SegmentationConfig, SuperpixelConfig
from .marquetry import (
    CleanupSettings,
    CompositeDesign,
    DesignRegion,
    PaintEvent,
    PhysicalSize,
    SubjectSettings,
    VeneerSwatch,
    build_design_regions,
    default_veneer_palette,
    design_regions_to_svg,
    merge_region_labels,
    region_records_to_preview,
    region_records_to_svg,
    split_region_label,
)
from .packing import pack_region_sheets
from .project import MarqflowProject
from .regions import selected_region_components

WORKSPACE_MANIFEST = 'workspace.json'
SOURCE_IMAGE = 'source-image'
CANDIDATES_DIR = 'candidates'
DESIGN_LABELS = 'design-labels.npy'

DEFAULT_SEGMENT_LEVELS = (20, 32, 48, 72)
DEFAULT_SMOOTHNESS_LEVELS = (16.0, 24.0, 36.0, 52.0)
DEFAULT_MAX_WORKING_EDGE = 768
DEFAULT_DOWNSCALE_FACTOR = 1
DEFAULT_GRID_ROWS = 4
DEFAULT_GRID_COLS = 4
DEFAULT_SEGMENT_RANGE = (20, 72)
DEFAULT_COMPACTNESS_RANGE = (16.0, 52.0)
DEFAULT_PHYSICAL_SIZE = PhysicalSize(width=1.0, height=1.0, unit='px')


def _json_load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding='utf-8'))


def _json_dump(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile('w', encoding='utf-8', delete=False, dir=path.parent) as tmp:
        json.dump(payload, tmp, indent=2, sort_keys=True)
        tmp.write('\n')
        tmp_path = Path(tmp.name)
    os.replace(tmp_path, path)


def _serialise_path(base_dir: Path, path: Path) -> str:
    try:
        return str(path.relative_to(base_dir))
    except ValueError:
        return str(path)


def _resolve_path(base_dir: Path, value: str | Path) -> Path:
    path = Path(value)
    if path.is_absolute():
        return path
    return base_dir / path


def _linspace_ints(start: int, stop: int, count: int) -> tuple[int, ...]:
    values = np.linspace(start, stop, num=max(1, count))
    return tuple(int(round(value)) for value in values)


def _linspace_floats(start: float, stop: float, count: int) -> tuple[float, ...]:
    values = np.linspace(start, stop, num=max(1, count))
    return tuple(float(value) for value in values)


def _slugify(value: str) -> str:
    slug = ''.join(char.lower() if char.isalnum() else '-' for char in value.strip())
    slug = '-'.join(part for part in slug.split('-') if part)
    return slug or 'candidate'


def _infer_grid_shape(candidates: list[GridCandidate]) -> tuple[int, int]:
    rows = 0
    cols = 0
    for candidate in candidates:
        if candidate.generation != 0:
            continue
        match = re.match(r'^r(\d+)c(\d+)-', candidate.label)
        if match is None:
            continue
        rows = max(rows, int(match.group(1)))
        cols = max(cols, int(match.group(2)))
    return rows or DEFAULT_GRID_ROWS, cols or DEFAULT_GRID_COLS


def _copy_source_image(source_image_path: Path, workspace_dir: Path) -> Path:
    source_dir = workspace_dir / SOURCE_IMAGE
    source_dir.mkdir(parents=True, exist_ok=True)
    target = source_dir / source_image_path.name
    target.write_bytes(source_image_path.read_bytes())
    return target


@lru_cache(maxsize=128)
def _load_project_cached(project_dir: str) -> MarqflowProject:
    """Load a candidate project once and reuse it across composite renders."""

    return MarqflowProject.load(project_dir)


def _write_thumbnail(source_path: Path, thumb_path: Path, max_edge: int = 240) -> Path:
    with Image.open(source_path) as image:
        image = image.convert('RGB')
        image.thumbnail((max_edge, max_edge), Image.Resampling.LANCZOS)
        thumb_path.parent.mkdir(parents=True, exist_ok=True)
        image.save(thumb_path, format='PNG')
    return thumb_path


def _default_composite_design() -> CompositeDesign:
    """Return the baseline persisted final-design aggregate."""

    return CompositeDesign(
        base_candidate_id=None,
        physical_size=DEFAULT_PHYSICAL_SIZE,
        veneer_palette=default_veneer_palette(),
    )


@dataclass(frozen=True, slots=True)
class GridPreset:
    """A single point in the parameter grid."""

    target_segments: int
    compactness: float
    sigma: float = 1.0
    max_working_edge: int = DEFAULT_MAX_WORKING_EDGE
    downscale_factor: int = DEFAULT_DOWNSCALE_FACTOR


@dataclass(slots=True)
class GridCandidate:
    """A generated candidate segmentation and its selections."""

    candidate_id: str
    label: str
    preset: GridPreset
    project_dir: Path
    preview_path: Path
    svg_path: Path
    thumb_path: Path
    region_count: int
    grid_row: int = 0
    grid_col: int = 0
    generation: int = 0
    parent_candidate_id: str | None = None
    kept: bool = False
    selected_region_ids: set[int] = field(default_factory=set)
    selection_revision: int = 0
    selected_at_ns: int = 0

    def to_dict(self) -> dict[str, Any]:
        """Serialize the candidate for the browser API and workspace manifest."""

        return {
            'candidate_id': self.candidate_id,
            'label': self.label,
            'preset': asdict(self.preset),
            'project_dir': str(self.project_dir),
            'preview_path': str(self.preview_path),
            'svg_path': str(self.svg_path),
            'thumb_path': str(self.thumb_path),
            'region_count': self.region_count,
            'grid_row': self.grid_row,
            'grid_col': self.grid_col,
            'generation': self.generation,
            'parent_candidate_id': self.parent_candidate_id,
            'kept': self.kept,
            'selected_region_ids': sorted(self.selected_region_ids),
            'selection_revision': self.selection_revision,
            'selected_at_ns': self.selected_at_ns,
        }

    def to_manifest_dict(self, workspace_dir: Path) -> dict[str, Any]:
        """Serialize the candidate relative to the workspace directory."""

        payload = self.to_dict()
        payload['project_dir'] = _serialise_path(workspace_dir, self.project_dir)
        payload['preview_path'] = _serialise_path(workspace_dir, self.preview_path)
        payload['svg_path'] = _serialise_path(workspace_dir, self.svg_path)
        payload['thumb_path'] = _serialise_path(workspace_dir, self.thumb_path)
        return payload


@dataclass(slots=True)
class GridWorkspace:
    """A gallery of candidate region maps and their composition state."""

    workspace_dir: Path
    source_image_path: Path
    original_image_size: tuple[int, int] = (0, 0)
    grid_rows: int = DEFAULT_GRID_ROWS
    grid_cols: int = DEFAULT_GRID_COLS
    candidates: list[GridCandidate] = field(default_factory=list)
    active_candidate_id: str | None = None
    composite_base_candidate_id: str | None = None
    physical_size: PhysicalSize = DEFAULT_PHYSICAL_SIZE
    veneer_palette: list[VeneerSwatch] = field(default_factory=default_veneer_palette)
    cleanup_settings: CleanupSettings = field(default_factory=CleanupSettings)
    subject_settings: SubjectSettings = field(default_factory=SubjectSettings)
    final_labels: np.ndarray | None = None
    final_region_sources: dict[int, tuple[tuple[str, int], ...]] = field(default_factory=dict)
    final_region_veneer_overrides: dict[int, str] = field(default_factory=dict)
    final_region_contour_overrides: dict[int, tuple[tuple[float, float], ...]] = field(
        default_factory=dict
    )
    final_region_locked_ids: set[int] = field(default_factory=set)
    manual_edits: list[dict[str, Any]] = field(default_factory=list)
    paint_events: list[PaintEvent] = field(default_factory=list)
    composite_design: CompositeDesign | None = None

    @classmethod
    def create(
        cls,
        source_image_path: str | Path,
        workspace_dir: str | Path,
        segment_levels: tuple[int, ...] = DEFAULT_SEGMENT_LEVELS,
        smoothness_levels: tuple[float, ...] = DEFAULT_SMOOTHNESS_LEVELS,
        max_working_edge: int = DEFAULT_MAX_WORKING_EDGE,
        downscale_factor: int = DEFAULT_DOWNSCALE_FACTOR,
    ) -> GridWorkspace:
        """Create a workspace and populate its initial grid.

        The source image is copied into the workspace so the manifest can be
        reopened later without depending on the original file path.
        """

        workspace_path = Path(workspace_dir)
        workspace_path.mkdir(parents=True, exist_ok=True)
        source_path = Path(source_image_path)
        with Image.open(source_path) as source_image:
            original_image_size = (int(source_image.width), int(source_image.height))
        copied_source = _copy_source_image(source_path, workspace_path)
        workspace = cls(
            workspace_dir=workspace_path,
            source_image_path=copied_source,
            original_image_size=original_image_size,
            grid_rows=len(segment_levels),
            grid_cols=len(smoothness_levels),
        )
        workspace.generate_initial_grid(
            segment_levels=segment_levels,
            smoothness_levels=smoothness_levels,
            max_working_edge=max_working_edge,
            downscale_factor=downscale_factor,
        )
        workspace._rebuild_final_partition()
        workspace.save()
        return workspace

    @classmethod
    def load(cls, workspace_dir: str | Path) -> GridWorkspace:
        """Load an existing workspace from disk."""

        workspace_path = Path(workspace_dir)
        manifest = _json_load(workspace_path / WORKSPACE_MANIFEST)
        workspace = cls(
            workspace_dir=workspace_path,
            source_image_path=_resolve_path(workspace_path, manifest['source_image_path']),
            original_image_size=tuple(
                int(value)
                for value in manifest.get('original_image_size', (0, 0))
            ),
            grid_rows=int(manifest.get('grid_rows', DEFAULT_GRID_ROWS)),
            grid_cols=int(manifest.get('grid_cols', DEFAULT_GRID_COLS)),
            active_candidate_id=manifest.get('active_candidate_id'),
            composite_base_candidate_id=manifest.get('composite_base_candidate_id'),
            physical_size=PhysicalSize.from_dict(
                manifest.get('physical_size'), DEFAULT_PHYSICAL_SIZE
            ),
            veneer_palette=[
                VeneerSwatch.from_dict(item) for item in manifest.get('veneer_palette', [])
            ]
            or default_veneer_palette(),
            cleanup_settings=CleanupSettings.from_dict(manifest.get('cleanup_settings')),
            subject_settings=SubjectSettings.from_dict(manifest.get('subject_settings')),
            final_region_veneer_overrides={
                int(region_id): str(veneer_id)
                for region_id, veneer_id in manifest.get(
                    'final_region_veneer_overrides', {}
                ).items()
            },
            final_region_locked_ids={
                int(region_id) for region_id in manifest.get('final_region_locked_ids', [])
            },
            final_region_contour_overrides={
                int(region_id): tuple(
                    (float(point[0]), float(point[1])) for point in points
                )
                for region_id, points in manifest.get('final_region_contour_overrides', {}).items()
            },
            manual_edits=[dict(item) for item in manifest.get('manual_edits', [])],
            paint_events=[PaintEvent.from_dict(item) for item in manifest.get('paint_events', [])],
        )
        if workspace.original_image_size == (0, 0) and workspace.source_image_path.exists():
            with Image.open(workspace.source_image_path) as source_image:
                workspace.original_image_size = (
                    int(source_image.width),
                    int(source_image.height),
                )
        workspace.composite_design = CompositeDesign.from_dict(
            manifest.get('composite_design'),
            fallback=_default_composite_design(),
        )
        workspace._apply_composite_design_state()
        provenance_payload = manifest.get('final_region_sources', {})
        workspace.final_region_sources = {
            int(region_id): tuple(
                (str(candidate_id), int(source_region_id))
                for candidate_id, source_region_id in refs
            )
            for region_id, refs in provenance_payload.items()
        }
        for candidate_data in manifest.get('candidates', []):
            preset_data = candidate_data['preset']
            project_dir = _resolve_path(workspace_path, candidate_data['project_dir'])
            preview_path = _resolve_path(workspace_path, candidate_data['preview_path'])
            svg_path = _resolve_path(workspace_path, candidate_data['svg_path'])
            thumb_value = candidate_data.get('thumb_path')
            thumb_path = (
                _resolve_path(workspace_path, thumb_value)
                if thumb_value is not None
                else project_dir / 'thumb.png'
            )
            if thumb_path == preview_path:
                thumb_path = project_dir / 'thumb.png'
            workspace.candidates.append(
                GridCandidate(
                    candidate_id=candidate_data['candidate_id'],
                    label=candidate_data['label'],
                    preset=GridPreset(
                        target_segments=int(preset_data['target_segments']),
                        compactness=float(preset_data['compactness']),
                        sigma=float(preset_data.get('sigma', 1.0)),
                        max_working_edge=int(
                            preset_data.get('max_working_edge', DEFAULT_MAX_WORKING_EDGE)
                        ),
                        downscale_factor=int(
                            preset_data.get('downscale_factor', DEFAULT_DOWNSCALE_FACTOR)
                        ),
                    ),
                    project_dir=project_dir,
                    preview_path=preview_path,
                    svg_path=svg_path,
                    thumb_path=thumb_path,
                    region_count=int(candidate_data['region_count']),
                    grid_row=int(candidate_data.get('grid_row', 0)),
                    grid_col=int(candidate_data.get('grid_col', 0)),
                    generation=int(candidate_data.get('generation', 0)),
                    parent_candidate_id=candidate_data.get('parent_candidate_id'),
                    kept=bool(candidate_data.get('kept', False)),
                    selected_region_ids={
                        int(region_id)
                        for region_id in candidate_data.get('selected_region_ids', [])
                    },
                    selection_revision=int(candidate_data.get('selection_revision', 0)),
                    selected_at_ns=int(candidate_data.get('selected_at_ns', 0)),
                )
            )
            if not thumb_path.exists():
                _write_thumbnail(preview_path, thumb_path)
        if workspace.paint_events:
            workspace._apply_paint_events()
        else:
            workspace._synthesise_paint_events()
        if workspace.composite_base_candidate_id is None:
            workspace._refresh_composite_base_candidate()
        final_labels_path = workspace_path / DESIGN_LABELS
        if final_labels_path.exists():
            workspace.final_labels = np.load(final_labels_path)
        elif workspace.candidates:
            workspace._rebuild_final_partition()
        workspace._sync_composite_design()
        if 'grid_rows' not in manifest or 'grid_cols' not in manifest:
            workspace.grid_rows, workspace.grid_cols = _infer_grid_shape(workspace.candidates)
        return workspace

    def save(self) -> None:
        """Persist the workspace manifest."""

        self.workspace_dir.mkdir(parents=True, exist_ok=True)
        self._sync_composite_design()
        _json_dump(
            self.workspace_dir / WORKSPACE_MANIFEST,
            {
                'version': 1,
                'source_image_path': _serialise_path(self.workspace_dir, self.source_image_path),
                'original_image_size': list(self.original_image_size),
                'grid_rows': self.grid_rows,
                'grid_cols': self.grid_cols,
                'active_candidate_id': self.active_candidate_id,
                'composite_base_candidate_id': self.composite_base_candidate_id,
                'physical_size': self.physical_size.to_dict(),
                'veneer_palette': [swatch.to_dict() for swatch in self.veneer_palette],
                'cleanup_settings': self.cleanup_settings.to_dict(),
                'subject_settings': self.subject_settings.to_dict(),
                'final_region_veneer_overrides': {
                    str(region_id): veneer_id
                    for region_id, veneer_id in self.final_region_veneer_overrides.items()
                },
                'final_region_locked_ids': sorted(self.final_region_locked_ids),
                'final_region_contour_overrides': {
                    str(region_id): [list(point) for point in points]
                    for region_id, points in self.final_region_contour_overrides.items()
                },
                'manual_edits': self.manual_edits,
                'paint_events': [event.to_dict() for event in self.paint_events],
                'final_region_sources': {
                    str(region_id): [list(ref) for ref in refs]
                    for region_id, refs in self.final_region_sources.items()
                },
                'composite_design': self.composite_design.to_dict()
                if self.composite_design is not None
                else _default_composite_design().to_dict(),
                'candidates': [
                    candidate.to_manifest_dict(self.workspace_dir) for candidate in self.candidates
                ],
            },
        )
        if self.final_labels is not None:
            np.save(self.workspace_dir / DESIGN_LABELS, self.final_labels)

    @property
    def active_candidate(self) -> GridCandidate | None:
        """Return the candidate currently selected in the UI."""

        if self.active_candidate_id is None:
            return self.candidates[0] if self.candidates else None
        for candidate in self.candidates:
            if candidate.candidate_id == self.active_candidate_id:
                return candidate
        return self.candidates[0] if self.candidates else None

    @property
    def kept_candidates(self) -> list[GridCandidate]:
        """Return the candidates that are carried into compose and merge."""

        return [candidate for candidate in self.candidates if candidate.kept]

    def _candidate_id(self, label: str) -> str:
        return f'{_slugify(label)}-{time_ns()}'

    def _partition_validation(self, labels: np.ndarray | None = None) -> dict[str, Any]:
        """Validate the current final partition raster."""

        if labels is None:
            labels = self.final_labels
        if labels is None:
            return {
                'partition_valid': False,
                'unassigned_px': 0,
                'connected_components': 0,
                'disconnected_regions': 0,
                'region_count': 0,
            }

        labels = np.asarray(labels)
        unassigned_px = int(np.count_nonzero(labels <= 0))
        region_ids = [int(value) for value in np.unique(labels) if int(value) > 0]
        disconnected_regions = 0
        connected_component_count = 0
        for region_id in region_ids:
            component_count = int(connected_components(labels == region_id, connectivity=1).max())
            connected_component_count += component_count
            if component_count > 1:
                disconnected_regions += 1
        partition_valid = unassigned_px == 0 and disconnected_regions == 0 and bool(region_ids)
        return {
            'partition_valid': partition_valid,
            'unassigned_px': unassigned_px,
            'connected_components': connected_component_count,
            'disconnected_regions': disconnected_regions,
            'region_count': len(region_ids),
        }

    def _refresh_composite_base_candidate(self) -> None:
        """Keep the persisted composite base aligned with the kept state."""

        if self.composite_base_candidate_id is not None:
            if self.candidate_by_id(self.composite_base_candidate_id) is not None:
                return

        if self.kept_candidates:
            self.composite_base_candidate_id = self.kept_candidates[0].candidate_id
        elif self.candidates:
            self.composite_base_candidate_id = self.candidates[0].candidate_id
        else:
            self.composite_base_candidate_id = None

    def _base_candidate(self) -> GridCandidate | None:
        """Return the candidate that seeds the final partition."""

        if self.composite_base_candidate_id is None:
            self._refresh_composite_base_candidate()
        if self.composite_base_candidate_id is None:
            return None
        return self.candidate_by_id(self.composite_base_candidate_id)

    def _base_project(self) -> MarqflowProject | None:
        """Load the project that seeds the final design."""

        candidate = self._base_candidate()
        if candidate is None:
            return None
        return _load_project_cached(str(candidate.project_dir))

    def _candidate_layers(self) -> list[GridCandidate]:
        """Return the candidate selection layers in the order they should paint."""

        base_id = self.composite_base_candidate_id
        paint_order = self._candidate_paint_order()
        layers = [
            candidate
            for candidate in self.kept_candidates
            if candidate.candidate_id != base_id and candidate.selected_region_ids
        ]
        return sorted(
            layers,
            key=lambda candidate: (
                paint_order.get(
                    candidate.candidate_id,
                    (candidate.selection_revision, candidate.selected_at_ns),
                ),
                candidate.candidate_id,
            ),
        )

    def _candidate_paint_order(self) -> dict[str, tuple[int, int]]:
        """Return the latest ordered paint event for each candidate."""

        order: dict[str, tuple[int, int]] = {}
        for event in self.paint_events:
            order[event.candidate_id] = (event.event_index, event.selected_at_ns)
        return order

    def _record_paint_event(
        self,
        candidate_id: str,
        region_ids: Iterable[int],
        additive: bool,
        kind: str,
    ) -> PaintEvent:
        """Append an ordered paint event."""

        event = PaintEvent(
            event_index=len(self.paint_events),
            candidate_id=candidate_id,
            region_ids=tuple(int(region_id) for region_id in region_ids),
            additive=additive,
            kind=kind,
            selected_at_ns=time_ns(),
        )
        self.paint_events.append(event)
        design = self._ensure_composite_design()
        design.paint_events = list(self.paint_events)
        return event

    def _apply_paint_events(self) -> None:
        """Rebuild candidate selections from the paint-event log."""

        candidate_by_id = {candidate.candidate_id: candidate for candidate in self.candidates}
        for candidate in self.candidates:
            candidate.selected_region_ids = set()
        for event in sorted(self.paint_events, key=lambda item: item.event_index):
            candidate = candidate_by_id.get(event.candidate_id)
            if candidate is None:
                continue
            if event.kind == 'clear':
                candidate.selected_region_ids.clear()
            elif event.additive:
                candidate.selected_region_ids.update(event.region_ids)
            else:
                candidate.selected_region_ids = set(event.region_ids)
            candidate.selection_revision = max(candidate.selection_revision, event.event_index + 1)
            candidate.selected_at_ns = max(candidate.selected_at_ns, event.selected_at_ns)
        design = self._ensure_composite_design()
        design.paint_events = list(self.paint_events)

    def _synthesise_paint_events(self) -> None:
        """Create paint events from older candidate selection state."""

        events: list[PaintEvent] = []
        for candidate in sorted(
            self.candidates,
            key=lambda item: (item.selection_revision, item.selected_at_ns, item.candidate_id),
        ):
            if not candidate.selected_region_ids:
                continue
            events.append(
                PaintEvent(
                    event_index=len(events),
                    candidate_id=candidate.candidate_id,
                    region_ids=tuple(sorted(candidate.selected_region_ids)),
                    additive=False,
                    kind='paint',
                    selected_at_ns=candidate.selected_at_ns or time_ns(),
                )
            )
        self.paint_events = events
        design = self._ensure_composite_design()
        design.paint_events = list(self.paint_events)

    def _build_composite_design(self) -> CompositeDesign:
        """Build the persisted final design aggregate from workspace state."""

        return CompositeDesign(
            base_candidate_id=self.composite_base_candidate_id,
            physical_size=self.physical_size,
            veneer_palette=list(self.veneer_palette),
            cleanup=self.cleanup_settings,
            paint_events=list(self.paint_events),
            final_region_sources=dict(self.final_region_sources),
            final_region_veneer_overrides=dict(self.final_region_veneer_overrides),
            final_region_contour_overrides=dict(self.final_region_contour_overrides),
            final_region_locked_ids=set(self.final_region_locked_ids),
            manual_edits=[dict(item) for item in self.manual_edits],
            validation=self.composite_summary(),
        )

    def _sync_composite_design(self) -> None:
        """Refresh the persisted final design aggregate from workspace state."""

        self.composite_design = self._build_composite_design()

    def _ensure_composite_design(self) -> CompositeDesign:
        """Return the persisted design aggregate, creating one if needed."""

        if self.composite_design is None:
            self.composite_design = self._build_composite_design()
        return self.composite_design

    def _apply_composite_design_state(self) -> None:
        """Copy the persisted design aggregate back onto workspace fields."""

        design = self._ensure_composite_design()
        self.composite_base_candidate_id = design.base_candidate_id
        self.physical_size = design.physical_size
        self.veneer_palette = list(design.veneer_palette)
        self.cleanup_settings = design.cleanup
        self.paint_events = list(design.paint_events)
        self.final_region_sources = dict(design.final_region_sources)
        self.final_region_veneer_overrides = dict(design.final_region_veneer_overrides)
        self.final_region_contour_overrides = dict(design.final_region_contour_overrides)
        self.final_region_locked_ids = set(design.final_region_locked_ids)
        self.manual_edits = [dict(item) for item in design.manual_edits]

    def _final_image_and_labels(
        self,
    ) -> (
        tuple[np.ndarray, np.ndarray, dict[int, tuple[tuple[str, int], ...]]]
        | tuple[None, None, None]
    ):
        """Return the current final raster if the workspace can build one."""

        base_candidate = self._base_candidate()
        base_project = self._base_project()
        if base_candidate is None or base_project is None:
            return None, None, None

        labels = np.array(base_project.labels, copy=True)
        next_label = int(labels.max()) + 1
        provenance: dict[int, tuple[tuple[str, int], ...]] = {
            int(region.region_id): ((base_candidate.candidate_id, int(region.region_id)),)
            for region in base_project.region_map.regions
        }

        for candidate in self._candidate_layers():
            project = _load_project_cached(str(candidate.project_dir))
            for region_id in sorted(candidate.selected_region_ids):
                mask = project.labels == int(region_id)
                if not np.any(mask):
                    continue
                labels[mask] = next_label
                provenance[next_label] = ((candidate.candidate_id, int(region_id)),)
                next_label += 1

        return np.array(base_project.working_image, copy=True), labels, provenance

    def _rebuild_final_partition(self) -> None:
        """Recompute the final partition from the current candidate layers."""

        image_and_labels = self._final_image_and_labels()
        if image_and_labels[0] is None or image_and_labels[1] is None:
            self.final_labels = None
            self.final_region_sources = {}
            return
        _, labels, provenance = image_and_labels
        self.final_labels = labels
        self.final_region_sources = provenance

    def _ensure_final_partition(self) -> tuple[MarqflowProject, np.ndarray]:
        """Return the seeded project and final labels, rebuilding if needed."""

        base_project = self._base_project()
        if base_project is None:
            raise ValueError('no candidates in workspace')
        if self.final_labels is None or self.final_labels.shape != base_project.labels.shape:
            self._rebuild_final_partition()
        if self.final_labels is None:
            raise ValueError('no candidates in workspace')
        return base_project, self.final_labels

    def _replay_manual_edits(self, labels: np.ndarray, base_project: MarqflowProject) -> np.ndarray:
        """Apply persisted manual edits to a freshly rebuilt partition."""

        for edit in self.manual_edits:
            op = str(edit.get('op', ''))
            if op == 'merge':
                region_ids = edit.get('region_ids', [])
                merge_region_labels(labels, region_ids)
            elif op == 'split':
                region_id = int(edit.get('region_id', 0))
                target_segments = int(edit.get('target_segments', 4))
                compactness = edit.get('compactness')
                sigma = edit.get('sigma')
                split_region_label(
                    base_project.working_image,
                    labels,
                    region_id,
                    target_segments=target_segments,
                    compactness=float(compactness) if compactness is not None else None,
                    sigma=float(sigma) if sigma is not None else None,
                )
        return labels

    def _final_region_records(self) -> list[DesignRegion]:
        """Build the final design region records from the current labels."""

        base_project, labels = self._ensure_final_partition()
        labels = np.array(labels, copy=True)
        labels = self._replay_manual_edits(labels, base_project)
        self.final_labels = labels
        base_candidate = self._base_candidate()
        source_prefix = base_candidate.candidate_id if base_candidate is not None else 'base'
        return list(
            build_design_regions(
                base_project.working_image,
                labels,
                physical_size=self.physical_size,
                palette=self.veneer_palette,
                simplify_tolerance=self.cleanup_settings.simplify_tolerance,
                source_prefix=source_prefix,
                source_refs_by_region=self.final_region_sources,
                veneer_overrides=self.final_region_veneer_overrides,
                contour_overrides=self.final_region_contour_overrides,
                locked_region_ids=self.final_region_locked_ids,
            )
        )

    def _generate_candidate(
        self,
        label: str,
        preset: GridPreset,
        generation: int = 0,
        grid_row: int = 0,
        grid_col: int = 0,
        parent_candidate_id: str | None = None,
    ) -> GridCandidate:
        """Generate one candidate workspace from the given preset."""

        candidate_id = self._candidate_id(label)
        candidate_dir = self.workspace_dir / CANDIDATES_DIR / candidate_id
        project = MarqflowProject.create(
            self.source_image_path,
            candidate_dir,
            SegmentationConfig(
                downscale_factor=preset.downscale_factor,
                max_working_edge=preset.max_working_edge,
                superpixels=SuperpixelConfig(
                    target_segments=preset.target_segments,
                    compactness=preset.compactness,
                    sigma=preset.sigma,
                ),
            ),
        )
        preview_path, svg_path = project.export(candidate_dir / 'export')
        thumb_path = candidate_dir / 'thumb.png'
        _write_thumbnail(preview_path, thumb_path)
        return GridCandidate(
            candidate_id=candidate_id,
            label=label,
            preset=preset,
            project_dir=candidate_dir,
            preview_path=preview_path,
            svg_path=svg_path,
            thumb_path=thumb_path,
            region_count=len(project.region_map.regions),
            grid_row=grid_row,
            grid_col=grid_col,
            generation=generation,
            parent_candidate_id=parent_candidate_id,
        )

    def generate_initial_grid(
        self,
        segment_levels: tuple[int, ...] = DEFAULT_SEGMENT_LEVELS,
        smoothness_levels: tuple[float, ...] = DEFAULT_SMOOTHNESS_LEVELS,
        max_working_edge: int = DEFAULT_MAX_WORKING_EDGE,
        downscale_factor: int = DEFAULT_DOWNSCALE_FACTOR,
        progress_callback: Any | None = None,
    ) -> list[GridCandidate]:
        """Generate the first grid of candidate segmentations.

        Rows step through region counts and columns step through smoothness,
        which gives the browser a coarse search surface to start from.
        """

        self.grid_rows = len(segment_levels)
        self.grid_cols = len(smoothness_levels)
        candidates: list[GridCandidate] = []
        total = max(1, len(segment_levels) * len(smoothness_levels))
        produced = 0
        for row, target_segments in enumerate(segment_levels):
            for col, compactness in enumerate(reversed(smoothness_levels)):
                label = f'r{row + 1}c{col + 1}-s{target_segments}-k{compactness:g}'
                candidates.append(
                    self._generate_candidate(
                        label,
                        GridPreset(
                            target_segments=target_segments,
                            compactness=compactness,
                            sigma=1.0,
                            max_working_edge=max_working_edge,
                            downscale_factor=downscale_factor,
                        ),
                        generation=0,
                        grid_row=row,
                        grid_col=col,
                    )
                )
                produced += 1
                if progress_callback is not None:
                    progress_callback(produced / total, f'Generated {produced}/{total} candidates')

        self.candidates = candidates
        self.active_candidate_id = candidates[0].candidate_id if candidates else None
        self.composite_base_candidate_id = self.active_candidate_id
        self._rebuild_final_partition()
        self.save()
        return candidates

    def rebuild_initial_grid(
        self,
        rows: int = DEFAULT_GRID_ROWS,
        cols: int = DEFAULT_GRID_COLS,
        segment_range: tuple[int, int] = DEFAULT_SEGMENT_RANGE,
        compactness_range: tuple[float, float] = DEFAULT_COMPACTNESS_RANGE,
        max_working_edge: int = DEFAULT_MAX_WORKING_EDGE,
        downscale_factor: int = DEFAULT_DOWNSCALE_FACTOR,
        progress_callback: Any | None = None,
    ) -> list[GridCandidate]:
        """Regenerate the coarse search grid with a new matrix size."""

        self.candidates = []
        self.active_candidate_id = None
        self.composite_base_candidate_id = None
        self.final_region_veneer_overrides = {}
        self.final_region_locked_ids = set()
        self.manual_edits = []
        self.final_labels = None
        self.paint_events = []
        self.composite_design = None
        segment_levels = _linspace_ints(segment_range[0], segment_range[1], rows)
        smoothness_levels = _linspace_floats(compactness_range[0], compactness_range[1], cols)
        return self.generate_initial_grid(
            segment_levels=segment_levels,
            smoothness_levels=smoothness_levels,
            max_working_edge=max_working_edge,
            downscale_factor=downscale_factor,
            progress_callback=progress_callback,
        )

    def reset_workspace(
        self,
        rows: int = DEFAULT_GRID_ROWS,
        cols: int = DEFAULT_GRID_COLS,
        segment_range: tuple[int, int] = DEFAULT_SEGMENT_RANGE,
        compactness_range: tuple[float, float] = DEFAULT_COMPACTNESS_RANGE,
        max_working_edge: int = DEFAULT_MAX_WORKING_EDGE,
        downscale_factor: int = DEFAULT_DOWNSCALE_FACTOR,
    ) -> list[GridCandidate]:
        """Delete generated artifacts and rebuild the gallery from scratch.

        The copied source image stays in place. Everything derived from that
        image, including old candidates and selections, is removed and then
        regenerated using the requested grid size.
        """

        candidates_dir = self.workspace_dir / CANDIDATES_DIR
        if candidates_dir.exists():
            shutil.rmtree(candidates_dir)

        manifest_path = self.workspace_dir / WORKSPACE_MANIFEST
        if manifest_path.exists():
            manifest_path.unlink()

        self.candidates = []
        self.active_candidate_id = None
        self.composite_base_candidate_id = None
        self.final_region_veneer_overrides = {}
        self.final_region_locked_ids = set()
        self.manual_edits = []
        self.final_labels = None
        self.paint_events = []
        self.composite_design = None
        return self.rebuild_initial_grid(
            rows=rows,
            cols=cols,
            segment_range=segment_range,
            compactness_range=compactness_range,
            max_working_edge=max_working_edge,
            downscale_factor=downscale_factor,
        )

    def refine_candidate(
        self,
        candidate_id: str,
        progress_callback: Any | None = None,
    ) -> list[GridCandidate]:
        """Generate a tighter 3x3 search grid around an existing candidate."""

        base = self.candidate_by_id(candidate_id)
        if base is None:
            return []

        segment_multipliers = (0.65, 1.0, 1.45)
        smoothness_multipliers = (0.6, 1.0, 1.75)
        candidates: list[GridCandidate] = []
        total = len(segment_multipliers) * len(smoothness_multipliers)
        produced = 0
        for row, seg_factor in enumerate(segment_multipliers):
            for col, smooth_factor in enumerate(smoothness_multipliers):
                target_segments = max(24, int(round(base.preset.target_segments * seg_factor)))
                compactness = max(0.5, float(base.preset.compactness * smooth_factor))
                label = f'{base.label}-r{row + 1}c{col + 1}'
                candidates.append(
                    self._generate_candidate(
                        label,
                        GridPreset(
                            target_segments=target_segments,
                            compactness=compactness,
                            sigma=base.preset.sigma,
                            max_working_edge=base.preset.max_working_edge,
                            downscale_factor=base.preset.downscale_factor,
                        ),
                        generation=base.generation + 1,
                        grid_row=row,
                        grid_col=col,
                        parent_candidate_id=base.candidate_id,
                    )
                )
                produced += 1
                if progress_callback is not None:
                    progress_callback(produced / total, f'Refined {produced}/{total} candidates')

        self.candidates.extend(candidates)
        self.active_candidate_id = candidates[4].candidate_id if len(candidates) >= 5 else None
        self._refresh_composite_base_candidate()
        self.save()
        return candidates

    def candidate_by_id(self, candidate_id: str) -> GridCandidate | None:
        """Look up a candidate by ID."""

        for candidate in self.candidates:
            if candidate.candidate_id == candidate_id:
                return candidate
        return None

    def set_active_candidate(self, candidate_id: str) -> None:
        """Mark a candidate as the one being viewed or edited."""

        if self.candidate_by_id(candidate_id) is not None:
            self.active_candidate_id = candidate_id
            self.save()

    def toggle_keep_candidate(self, candidate_id: str) -> bool:
        """Flip whether a candidate is retained for compose/merge."""

        candidate = self.candidate_by_id(candidate_id)
        if candidate is None:
            return False
        candidate.kept = not candidate.kept
        if candidate.kept:
            if self.composite_base_candidate_id is None:
                self.composite_base_candidate_id = candidate_id
            self.active_candidate_id = candidate_id
        elif self.composite_base_candidate_id == candidate_id:
            self.composite_base_candidate_id = None
            self._refresh_composite_base_candidate()
        self._rebuild_final_partition()
        self.save()
        return candidate.kept

    def set_candidate_selection(
        self,
        candidate_id: str,
        region_ids: Iterable[int],
        additive: bool = False,
    ) -> int:
        """Replace or extend the set of regions painted from a candidate."""

        candidate = self.candidate_by_id(candidate_id)
        if candidate is None:
            return 0

        selected = {int(region_id) for region_id in region_ids}
        if additive:
            candidate.selected_region_ids.update(selected)
        else:
            candidate.selected_region_ids = selected
        candidate.selection_revision += 1
        candidate.selected_at_ns = time_ns()
        self.active_candidate_id = candidate_id
        self._record_paint_event(
            candidate_id=candidate_id,
            region_ids=sorted(candidate.selected_region_ids),
            additive=additive,
            kind='paint',
        )
        self._rebuild_final_partition()
        self.save()
        return len(candidate.selected_region_ids)

    def paint_all_candidate(self, candidate_id: str) -> int:
        """Select every region in a candidate."""

        candidate = self.candidate_by_id(candidate_id)
        if candidate is None:
            return 0

        project = _load_project_cached(str(candidate.project_dir))
        candidate.selected_region_ids = {
            int(region.region_id) for region in project.region_map.regions
        }
        candidate.selection_revision += 1
        candidate.selected_at_ns = time_ns()
        self.active_candidate_id = candidate_id
        self._record_paint_event(
            candidate_id=candidate_id,
            region_ids=sorted(candidate.selected_region_ids),
            additive=False,
            kind='paint-all',
        )
        self._rebuild_final_partition()
        self.save()
        return len(candidate.selected_region_ids)

    def clear_candidate_selection(self, candidate_id: str) -> bool:
        """Clear all painted regions from a candidate."""

        candidate = self.candidate_by_id(candidate_id)
        if candidate is None:
            return False
        candidate.selected_region_ids.clear()
        candidate.selection_revision += 1
        candidate.selected_at_ns = time_ns()
        self._record_paint_event(
            candidate_id=candidate_id,
            region_ids=(),
            additive=False,
            kind='clear',
        )
        self._rebuild_final_partition()
        self.save()
        return True

    def set_physical_size(self, width: float, height: float, unit: str) -> None:
        """Set the physical size of the final piece."""

        self.physical_size = PhysicalSize(width=float(width), height=float(height), unit=unit)
        design = self._ensure_composite_design()
        design.physical_size = self.physical_size
        self.save()

    def set_cleanup_settings(self, settings: CleanupSettings) -> None:
        """Persist cleanup thresholds used for highlighting and export."""

        self.cleanup_settings = settings
        design = self._ensure_composite_design()
        design.cleanup = settings
        self.save()

    def set_subject_settings(self, settings: SubjectSettings) -> None:
        """Persist subject-focus metadata."""

        self.subject_settings = settings
        self.save()

    def set_veneer_palette(self, palette: list[VeneerSwatch]) -> None:
        """Replace the veneer inventory used for suggestions, overrides, and packing."""

        if not palette:
            raise ValueError('veneer palette must contain at least one swatch')
        seen: set[str] = set()
        normalized: list[VeneerSwatch] = []
        for swatch in palette:
            veneer_id = swatch.veneer_id.strip()
            name = swatch.name.strip() or veneer_id
            if not veneer_id:
                raise ValueError('veneer IDs cannot be blank')
            if veneer_id in seen:
                raise ValueError(f'duplicate veneer ID: {veneer_id}')
            seen.add(veneer_id)
            color = tuple(max(0, min(255, int(value))) for value in swatch.color_rgb)
            normalized.append(VeneerSwatch(veneer_id=veneer_id, name=name, color_rgb=color))

        self.veneer_palette = normalized
        valid_ids = {swatch.veneer_id for swatch in normalized}
        self.final_region_veneer_overrides = {
            region_id: veneer_id
            for region_id, veneer_id in self.final_region_veneer_overrides.items()
            if veneer_id in valid_ids
        }
        design = self._ensure_composite_design()
        design.veneer_palette = list(normalized)
        design.final_region_veneer_overrides = dict(self.final_region_veneer_overrides)
        self.save()

    def set_final_region_veneer(self, region_id: int, veneer_id: str | None) -> bool:
        """Assign a veneer to a final region."""

        _, labels = self._ensure_final_partition()
        if int(region_id) not in np.unique(labels):
            return False
        design = self._ensure_composite_design()
        if veneer_id is None:
            self.final_region_veneer_overrides.pop(int(region_id), None)
            design.final_region_veneer_overrides.pop(int(region_id), None)
        else:
            self.final_region_veneer_overrides[int(region_id)] = str(veneer_id)
            design.final_region_veneer_overrides[int(region_id)] = str(veneer_id)
        self.final_labels = labels
        self.save()
        return True

    def set_final_region_locked(self, region_id: int, locked: bool) -> bool:
        """Lock or unlock a final region."""

        _, labels = self._ensure_final_partition()
        if int(region_id) not in np.unique(labels):
            return False
        region_id = int(region_id)
        design = self._ensure_composite_design()
        if locked:
            self.final_region_locked_ids.add(region_id)
            design.final_region_locked_ids.add(region_id)
        else:
            self.final_region_locked_ids.discard(region_id)
            design.final_region_locked_ids.discard(region_id)
        self.final_labels = labels
        self.save()
        return True

    def set_final_region_point(
        self,
        region_id: int,
        point_index: int,
        x: float,
        y: float,
    ) -> bool:
        """Move one contour point in the final design geometry."""

        records = {region.region_id: region for region in self._final_region_records()}
        region = records.get(int(region_id))
        if region is None or not region.contour:
            return False
        contour = [tuple(point) for point in region.contour]
        if point_index < 0 or point_index >= len(contour):
            return False
        contour[point_index] = (float(x), float(y))
        if contour[0] != contour[-1]:
            contour[-1] = contour[0]
        self.final_region_contour_overrides[int(region_id)] = tuple(contour)
        design = self._ensure_composite_design()
        design.final_region_contour_overrides[int(region_id)] = tuple(contour)
        self.save()
        return True

    def smooth_final_region(self, region_id: int, tolerance: float = 1.5) -> bool:
        """Simplify a region contour with a higher tolerance."""

        records = {region.region_id: region for region in self._final_region_records()}
        region = records.get(int(region_id))
        if region is None or not region.contour:
            return False
        simplified = approximate_polygon(np.asarray(region.contour), tolerance=float(tolerance))
        points = [(float(col), float(row)) for row, col in simplified]
        if len(points) < 3:
            return False
        if points[0] != points[-1]:
            points.append(points[0])
        self.final_region_contour_overrides[int(region_id)] = tuple(points)
        design = self._ensure_composite_design()
        design.final_region_contour_overrides[int(region_id)] = tuple(points)
        self.save()
        return True

    def merge_final_regions(self, region_ids: Iterable[int]) -> int:
        """Merge selected final regions in the explicit partition."""

        base_project, labels = self._ensure_final_partition()
        selected = sorted({int(value) for value in region_ids if int(value) in np.unique(labels)})
        if any(region_id in self.final_region_locked_ids for region_id in selected):
            return 0
        components = selected_region_components(labels, selected)
        before_sources = dict(self.final_region_sources)
        merged = merge_region_labels(labels, region_ids)
        if merged <= 0:
            return 0
        self.final_labels = labels
        for component in components:
            if len(component) < 2:
                continue
            target = min(component)
            combined: list[tuple[str, int]] = []
            for region_id in component:
                combined.extend(
                    before_sources.get(
                        region_id, ((self.composite_base_candidate_id or 'final', region_id),)
                    )
                )
            self.final_region_sources[target] = tuple(dict.fromkeys(combined))
            for region_id in component:
                if region_id != target:
                    self.final_region_sources.pop(region_id, None)
        merge_edit = {'op': 'merge', 'region_ids': sorted({int(value) for value in region_ids})}
        self.manual_edits.append(merge_edit)
        design = self._ensure_composite_design()
        design.final_region_sources = dict(self.final_region_sources)
        design.manual_edits.append(dict(merge_edit))
        self.save()
        return merged

    def merge_cleanup_suggestions(self) -> int:
        """Apply all currently valid small/thin merge suggestions."""

        merged_total = 0
        seen_pairs: set[tuple[int, int]] = set()
        while True:
            suggestions = self.composite_summary().get('merge_suggestions', [])
            merged_this_pass = 0
            for suggestion in suggestions:
                region_id = int(suggestion['region_id'])
                target_id = int(suggestion['target_region_id'])
                pair = tuple(sorted((region_id, target_id)))
                if pair in seen_pairs:
                    continue
                seen_pairs.add(pair)
                merged = self.merge_final_regions(pair)
                if merged > 0:
                    merged_total += merged
                    merged_this_pass += merged
                    break
            if merged_this_pass == 0:
                break
        return merged_total

    def split_final_region(
        self,
        region_id: int,
        target_segments: int,
        compactness: float | None = None,
        sigma: float | None = None,
    ) -> int:
        """Split a final region into smaller pieces."""

        base_project, labels = self._ensure_final_partition()
        before_sources = dict(self.final_region_sources)
        before_max_label = int(labels.max())
        if int(region_id) in self.final_region_locked_ids:
            return 0
        changed = split_region_label(
            base_project.working_image,
            labels,
            int(region_id),
            target_segments=int(target_segments),
            compactness=compactness,
            sigma=sigma,
        )
        if changed <= 0:
            return 0
        self.final_labels = labels
        old_sources = before_sources.get(
            int(region_id), ((self.composite_base_candidate_id or 'final', int(region_id)),)
        )
        next_label = before_max_label + 1
        for new_label in range(next_label, next_label + changed):
            self.final_region_sources[new_label] = old_sources
        self.final_region_sources.pop(int(region_id), None)
        split_edit = {
            'op': 'split',
            'region_id': int(region_id),
            'target_segments': int(target_segments),
            'compactness': float(compactness) if compactness is not None else None,
            'sigma': float(sigma) if sigma is not None else None,
        }
        self.manual_edits.append(split_edit)
        design = self._ensure_composite_design()
        design.final_region_sources = dict(self.final_region_sources)
        design.manual_edits.append(dict(split_edit))
        self.save()
        return changed

    def pack_by_veneer(self, output_dir: str | Path) -> list[dict[str, Any]]:
        """Write a veneer-aware packing plan to disk."""

        base_project, labels = self._ensure_final_partition()
        self._assert_exportable(labels)
        packed = pack_region_sheets(
            base_project.working_image,
            labels,
            physical_size=self.physical_size,
            palette=self.veneer_palette,
            simplify_tolerance=self.cleanup_settings.simplify_tolerance,
            veneer_overrides=self.final_region_veneer_overrides,
            contour_overrides=self.final_region_contour_overrides,
        )
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)
        for sheet_index, sheet in enumerate(packed, start=1):
            veneer_dir = output_path / str(sheet['veneer_id'])
            veneer_dir.mkdir(parents=True, exist_ok=True)
            sheet_svg_path = veneer_dir / f'sheet-{sheet_index}.svg'
            sheet_svg_path.write_text(sheet['sheet_svg'], encoding='utf-8')
            sheet['sheet_svg_path'] = str(sheet_svg_path)
            sheet.pop('sheet_svg', None)
            if sheet.get('nest_input_svg'):
                nest_input_path = veneer_dir / f'nest-input-{sheet_index}.svg'
                nest_input_path.write_text(sheet['nest_input_svg'], encoding='utf-8')
                sheet['nest_input_svg_path'] = str(nest_input_path)
                sheet.pop('nest_input_svg', None)
        (output_path / 'pack.json').write_text(
            json.dumps(packed, indent=2, sort_keys=True) + '\n', encoding='utf-8'
        )
        self._write_piece_manifest(output_path)
        return packed

    def _assert_exportable(self, labels: np.ndarray | None = None) -> None:
        """Validate basic fabrication export invariants."""

        if self.physical_size.width <= 0 or self.physical_size.height <= 0:
            raise ValueError('physical size must be positive before export')
        validation = self._partition_validation(labels)
        if not validation['partition_valid']:
            raise ValueError(
                'final partition must have no gaps or disconnected regions before export'
            )

    def _piece_manifest(self) -> list[dict[str, Any]]:
        """Return a traceable bill of pieces for the current final design."""

        pieces: list[dict[str, Any]] = []
        for region in self._final_region_records():
            pieces.append(
                {
                    'region_id': region.region_id,
                    'veneer_id': region.veneer_id,
                    'suggested_veneer_id': region.suggested_veneer_id,
                    'veneer_override_id': region.veneer_override_id,
                    'area_physical': region.area_physical,
                    'perimeter_physical': region.perimeter_physical,
                    'point_count': len(region.contour),
                    'hole_count': region.hole_count,
                    'component_count': region.component_count,
                    'locked': region.locked,
                    'bbox': list(region.bbox),
                    'source_refs': [list(ref) for ref in region.source_refs],
                }
            )
        return sorted(pieces, key=lambda item: (str(item['veneer_id']), int(item['region_id'])))

    def _write_piece_manifest(self, output_path: Path) -> tuple[Path, Path]:
        """Write JSON and CSV piece manifests next to export artifacts."""

        pieces = self._piece_manifest()
        json_path = output_path / 'pieces.json'
        csv_path = output_path / 'pieces.csv'
        json_path.write_text(json.dumps(pieces, indent=2, sort_keys=True) + '\n', encoding='utf-8')
        headers = [
            'region_id',
            'veneer_id',
            'suggested_veneer_id',
            'veneer_override_id',
            'area_physical',
            'perimeter_physical',
            'point_count',
            'hole_count',
            'component_count',
            'locked',
            'bbox',
            'source_refs',
        ]
        with csv_path.open('w', encoding='utf-8', newline='') as csv_file:
            writer = csv.DictWriter(csv_file, fieldnames=headers)
            writer.writeheader()
            for piece in pieces:
                writer.writerow(
                    {
                        'region_id': piece['region_id'],
                        'veneer_id': piece['veneer_id'],
                        'suggested_veneer_id': piece['suggested_veneer_id'],
                        'veneer_override_id': piece['veneer_override_id'] or '',
                        'area_physical': f'{float(piece["area_physical"]):.6f}',
                        'perimeter_physical': f'{float(piece["perimeter_physical"]):.6f}',
                        'point_count': piece['point_count'],
                        'hole_count': piece['hole_count'],
                        'component_count': piece['component_count'],
                        'locked': str(piece['locked']).lower(),
                        'bbox': json.dumps(piece['bbox']),
                        'source_refs': json.dumps(piece['source_refs']),
                    }
                )
        return json_path, csv_path

    def summary(self) -> dict[str, Any]:
        """Return a JSON-friendly summary for the browser UI."""

        active = self.active_candidate
        base_project = self._base_project()
        final_regions: list[DesignRegion] = []
        if base_project is not None:
            try:
                final_regions = self._final_region_records()
            except ValueError:
                final_regions = []
        source_image_size = {'width': 0, 'height': 0}
        if base_project is not None:
            source_image_size = {
                'width': int(base_project.working_image.shape[1]),
                'height': int(base_project.working_image.shape[0]),
            }
        return {
            'workspace_dir': str(self.workspace_dir),
            'source_image_path': str(self.source_image_path),
            'original_image_size': {
                'width': int(self.original_image_size[0]),
                'height': int(self.original_image_size[1]),
            },
            'source_image_size': source_image_size,
            'candidate_count': len(self.candidates),
            'kept_count': len(self.kept_candidates),
            'grid_rows': self.grid_rows,
            'grid_cols': self.grid_cols,
            'active_candidate_id': self.active_candidate_id,
            'composite_base_candidate_id': self.composite_base_candidate_id,
            'active_candidate': active.to_dict() if active is not None else None,
            'candidates': [candidate.to_dict() for candidate in self.candidates],
            'physical_size': self.physical_size.to_dict(),
            'cleanup_settings': self.cleanup_settings.to_dict(),
            'subject_settings': self.subject_settings.to_dict(),
            'veneer_palette': [swatch.to_dict() for swatch in self.veneer_palette],
            'paint_event_count': len(self.paint_events),
            'final_region_count': len(final_regions),
            'partition_validation': self._partition_validation(self.final_labels),
            'composite_design': self.composite_design.to_dict()
            if self.composite_design is not None
            else self._build_composite_design().to_dict(),
            'design_summary': self.composite_summary(),
            'final_regions': [
                {
                    'region_id': region.region_id,
                    'area_px': region.area_px,
                    'area_physical': region.area_physical,
                    'bbox': region.bbox,
                    'point_count': len(region.contour),
                    'neighbors': list(region.neighbors),
                    'veneer_id': region.veneer_id,
                    'suggested_veneer_id': region.suggested_veneer_id,
                    'hole_count': region.hole_count,
                    'component_count': region.component_count,
                    'veneer_override_id': region.veneer_override_id,
                    'locked': region.locked,
                    'source_refs': [list(ref) for ref in region.source_refs],
                    'color_rgb': list(region.color_rgb),
                    'contour': [list(point) for point in region.contour],
                }
                for region in final_regions
            ],
        }

    def candidate_summary(self, candidate_id: str) -> dict[str, Any] | None:
        """Return full region metadata for one candidate."""

        candidate = self.candidate_by_id(candidate_id)
        if candidate is None:
            return None

        project = _load_project_cached(str(candidate.project_dir))
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
            **candidate.to_dict(),
            'size': {'width': region_map.size[0], 'height': region_map.size[1]},
            'region_count': len(region_map.regions),
            'regions': regions,
        }

    def _composite_base_candidate(self) -> GridCandidate | None:
        """Pick the base candidate used for the composite preview canvas."""

        return self._base_candidate()

    def _composite_region_records(self) -> list[DesignRegion]:
        """Return the final regions that make up the design."""

        return self._final_region_records()

    def _cluster_records(self, merge_threshold: float) -> list[dict[str, Any]]:
        """Group final regions by color similarity."""

        records = self._composite_region_records()
        if merge_threshold <= 0:
            return [{'color': record.color_rgb, 'records': [record]} for record in records]

        clusters: list[dict[str, Any]] = []
        for record in records:
            cluster = None
            for existing in clusters:
                distance = (
                    float(
                        ((existing['color'][0] - record.color_rgb[0]) ** 2)
                        + ((existing['color'][1] - record.color_rgb[1]) ** 2)
                        + ((existing['color'][2] - record.color_rgb[2]) ** 2)
                    )
                    ** 0.5
                )
                if distance <= merge_threshold:
                    cluster = existing
                    break
            if cluster is None:
                cluster = {'color': record.color_rgb, 'records': []}
                clusters.append(cluster)
            cluster['records'].append(record)
            colors = np.asarray([item.color_rgb for item in cluster['records']], dtype=float)
            cluster['color'] = tuple(int(round(value)) for value in colors.mean(axis=0))
        return clusters

    def composite_preview(self, merge_threshold: float = 0.0) -> np.ndarray:
        """Render the current kept selections as a preview image."""

        base_project = self._base_project()
        if base_project is None:
            raise ValueError('no candidates in workspace')
        if self.final_labels is None or self.final_labels.shape != base_project.labels.shape:
            self._rebuild_final_partition()
        if self.final_labels is None:
            raise ValueError('no candidates in workspace')
        return region_records_to_preview(
            base_project.working_image,
            self.final_labels,
            merge_threshold=merge_threshold,
        )

    def composite_svg(self, merge_threshold: float = 0.0) -> str:
        """Render the composite SVG, optionally merging nearby colors."""

        base_project = self._base_project()
        if base_project is None:
            raise ValueError('no candidates in workspace')
        if merge_threshold <= 0:
            records = self._final_region_records()
            return design_regions_to_svg(
                records,
                physical_size=self.physical_size,
                image_size=(
                    base_project.working_image.shape[1],
                    base_project.working_image.shape[0],
                ),
            )
        if self.final_labels is None or self.final_labels.shape != base_project.labels.shape:
            self._rebuild_final_partition()
        if self.final_labels is None:
            raise ValueError('no candidates in workspace')
        return region_records_to_svg(
            base_project.working_image,
            self.final_labels,
            physical_size=self.physical_size,
            palette=self.veneer_palette,
            simplify_tolerance=self.cleanup_settings.simplify_tolerance,
            merge_threshold=merge_threshold,
        )

    def composite_summary(self, merge_threshold: float = 0.0) -> dict[str, Any]:
        """Return a small summary for the composite model."""

        records = self._composite_region_records()
        if not records:
            return {
                'path_count': 0,
                'region_count': 0,
                'merge_threshold': float(merge_threshold),
            }

        if merge_threshold <= 0:
            path_count = len(records)
        else:
            path_count = 0
            _, labels = self._ensure_final_partition()
            for cluster in self._cluster_records(merge_threshold):
                mask = np.isin(labels, [record.region_id for record in cluster['records']])
                padded = np.pad(mask.astype(float), 1, mode='constant', constant_values=0.0)
                path_count += sum(
                    1
                    for contour in find_contours(padded, 0.5)
                    if len(contour) >= 3
                )

        small_region_ids: list[int] = []
        thin_region_ids: list[int] = []
        complex_region_ids: list[int] = []
        hole_region_ids: list[int] = []
        disconnected_region_ids: list[int] = []
        merge_suggestions: list[dict[str, Any]] = []
        _, labels = self._ensure_final_partition()
        px_per_unit_x, px_per_unit_y = self.physical_size.pixels_per_unit(
            (labels.shape[1], labels.shape[0])
        )
        region_by_id = {record.region_id: record for record in records}
        for record in records:
            if (
                self.cleanup_settings.highlight_small_area > 0
                and record.area_physical <= self.cleanup_settings.highlight_small_area
            ):
                small_region_ids.append(record.region_id)
            if (
                self.cleanup_settings.highlight_thin_width > 0
                and min(
                    (record.bbox[2] - record.bbox[0]) / max(1.0, px_per_unit_x),
                    (record.bbox[3] - record.bbox[1]) / max(1.0, px_per_unit_y),
                )
                <= self.cleanup_settings.highlight_thin_width
            ):
                thin_region_ids.append(record.region_id)
            if len(record.contour) > 80:
                complex_region_ids.append(record.region_id)
            if record.hole_count > 0:
                hole_region_ids.append(record.region_id)
            if record.component_count > 1:
                disconnected_region_ids.append(record.region_id)
            if record.region_id in small_region_ids or record.region_id in thin_region_ids:
                neighbor_ids = [
                    neighbor
                    for neighbor in record.neighbors
                    if neighbor in region_by_id and neighbor != record.region_id
                ]
                if neighbor_ids:
                    same_veneer = [
                        neighbor
                        for neighbor in neighbor_ids
                        if region_by_id[neighbor].veneer_id == record.veneer_id
                    ]
                    target_id = max(
                        same_veneer or neighbor_ids,
                        key=lambda neighbor_id: region_by_id[neighbor_id].area_physical,
                    )
                    merge_suggestions.append(
                        {
                            'region_id': record.region_id,
                            'target_region_id': target_id,
                            'reason': 'small' if record.region_id in small_region_ids else 'thin',
                            'same_veneer': region_by_id[target_id].veneer_id == record.veneer_id,
                        }
                    )

        partition_validation = self._partition_validation()
        return {
            'path_count': path_count,
            'region_count': len(records),
            'merge_threshold': float(merge_threshold),
            'physical_size': self.physical_size.to_dict(),
            'partition_valid': partition_validation['partition_valid'],
            'partition_validation': partition_validation,
            'small_region_ids': small_region_ids,
            'thin_region_ids': thin_region_ids,
            'complex_region_ids': complex_region_ids,
            'hole_region_ids': hole_region_ids,
            'disconnected_region_ids': disconnected_region_ids,
            'merge_suggestions': merge_suggestions,
            'veneer_counts': {
                veneer.veneer_id: sum(
                    1 for record in records if record.veneer_id == veneer.veneer_id
                )
                for veneer in self.veneer_palette
            },
        }

    def composite_hitmap(self) -> dict[str, Any]:
        """Return the final label raster for canvas hit-testing."""

        _, labels = self._ensure_final_partition()
        return {
            'width': int(labels.shape[1]),
            'height': int(labels.shape[0]),
            'labels': labels.astype(int).tolist(),
        }

    def export_composite(
        self,
        output_dir: str | Path,
        merge_threshold: float = 0.0,
    ) -> tuple[Path, Path]:
        """Export a composite preview and SVG from kept selections."""

        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)
        composite_png = output_path / 'composite.png'
        composite_svg = output_path / 'composite.svg'

        if self._base_candidate() is None:
            raise ValueError('select at least one candidate before exporting')

        _, labels = self._ensure_final_partition()
        self._assert_exportable(labels)
        canvas = self.composite_preview(merge_threshold=merge_threshold)
        svg = self.composite_svg(merge_threshold=merge_threshold)

        Image.fromarray(canvas.astype(np.uint8), mode='RGB').save(composite_png)
        composite_svg.write_text(svg, encoding='utf-8')
        self._write_piece_manifest(output_path)
        if self.final_labels is not None:
            np.save(output_path / DESIGN_LABELS, self.final_labels)
        return composite_png, composite_svg
