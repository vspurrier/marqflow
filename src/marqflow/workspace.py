"""Workspace persistence for the marquetry-first rewrite."""

from __future__ import annotations

import json
import os
import shutil
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image, ImageOps
from rectpack import newPacker
from skimage.segmentation import slic

from .geometry import (
    build_regions,
    design_to_svg,
    merge_labels,
    normalize_labels,
    partition_validation,
    preview_image,
    region_neighbors,
    shared_boundaries,
)
from .models import (
    Candidate,
    DetailZone,
    EditOperation,
    MarquetryDesign,
    PhysicalSize,
    SourceImage,
    Veneer,
    default_veneers,
)

MANIFEST = 'workspace.json'
SOURCE_IMAGE = 'source.png'
DESIGN_LABELS = 'design-labels.npy'
HISTORY_DIR = 'history'


def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile('w', encoding='utf-8', delete=False, dir=path.parent) as tmp:
        json.dump(payload, tmp, indent=2, sort_keys=True)
        tmp.write('\n')
        tmp_path = Path(tmp.name)
    os.replace(tmp_path, path)


def _load_image(path: Path, max_edge: int) -> tuple[Image.Image, SourceImage]:
    original = ImageOps.exif_transpose(Image.open(path)).convert('RGB')
    working = original.copy()
    working.thumbnail((max_edge, max_edge), Image.Resampling.LANCZOS)
    metadata = SourceImage(
        path=SOURCE_IMAGE,
        original_width=original.width,
        original_height=original.height,
        working_width=working.width,
        working_height=working.height,
    )
    return working, metadata


@dataclass(slots=True)
class MarquetryWorkspace:
    """Owns source image, generated candidates, and one final marquetry design."""

    workspace_dir: Path
    source: SourceImage
    candidates: list[Candidate] = field(default_factory=list)
    design: MarquetryDesign | None = None

    @property
    def source_path(self) -> Path:
        return self.workspace_dir / self.source.path

    @classmethod
    def create(
        cls,
        image_path: str | Path,
        workspace_dir: str | Path,
        max_edge: int = 768,
    ) -> MarquetryWorkspace:
        workspace_path = Path(workspace_dir)
        workspace_path.mkdir(parents=True, exist_ok=True)
        working, source = _load_image(Path(image_path), max_edge=max_edge)
        working.save(workspace_path / SOURCE_IMAGE)
        workspace = cls(workspace_dir=workspace_path, source=source)
        workspace.save()
        return workspace

    @classmethod
    def load(cls, workspace_dir: str | Path) -> MarquetryWorkspace:
        workspace_path = Path(workspace_dir)
        manifest = json.loads((workspace_path / MANIFEST).read_text(encoding='utf-8'))
        design_data = manifest.get('design')
        return cls(
            workspace_dir=workspace_path,
            source=SourceImage.from_dict(manifest['source']),
            candidates=[Candidate.from_dict(item) for item in manifest.get('candidates', [])],
            design=MarquetryDesign.from_dict(design_data) if design_data else None,
        )

    def save(self) -> None:
        _atomic_json(
            self.workspace_dir / MANIFEST,
            {
                'source': self.source.to_dict(),
                'candidates': [candidate.to_dict() for candidate in self.candidates],
                'design': self.design.to_dict() if self.design else None,
            },
        )

    def source_array(self) -> np.ndarray:
        return np.asarray(Image.open(self.source_path).convert('RGB'))

    def _candidate_by_id(self, candidate_id: str) -> Candidate:
        for candidate in self.candidates:
            if candidate.candidate_id == candidate_id:
                return candidate
        raise ValueError(f'candidate not found: {candidate_id}')

    def candidate_labels(self, candidate_id: str) -> np.ndarray:
        candidate = self._candidate_by_id(candidate_id)
        return np.load(self.workspace_dir / candidate.labels_path)

    def design_labels(self) -> np.ndarray:
        if self.design is None:
            raise ValueError('create a design from a candidate first')
        return np.load(self.workspace_dir / self.design.labels_path)

    def _write_design_labels(self, labels: np.ndarray) -> None:
        if self.design is None:
            raise ValueError('create a design first')
        np.save(self.workspace_dir / self.design.labels_path, labels)

    def _next_op_id(self) -> int:
        if self.design is None:
            raise ValueError('create a design first')
        return len(self.design.edit_history) + 1

    def _snapshot_labels(self, op_id: int) -> str:
        path = Path(HISTORY_DIR) / f'op-{op_id}-labels.npy'
        (self.workspace_dir / path).parent.mkdir(parents=True, exist_ok=True)
        np.save(self.workspace_dir / path, self.design_labels())
        return str(path)

    def generate_candidate(
        self,
        target_regions: int = 80,
        compactness: float = 18.0,
    ) -> Candidate:
        """Generate one SLIC candidate partition."""

        image = self.source_array()
        labels = slic(
            image,
            n_segments=max(2, int(target_regions)),
            compactness=float(compactness),
            sigma=1.0,
            start_label=1,
            channel_axis=-1,
        )
        labels = normalize_labels(labels)
        candidate_id = f'candidate-{len(self.candidates) + 1}'
        candidate_dir = self.workspace_dir / 'candidates' / candidate_id
        candidate_dir.mkdir(parents=True, exist_ok=True)
        labels_path = Path('candidates') / candidate_id / 'labels.npy'
        preview_path = Path('candidates') / candidate_id / 'preview.png'
        np.save(self.workspace_dir / labels_path, labels)
        preview_image(image, labels).save(self.workspace_dir / preview_path)
        candidate = Candidate(
            candidate_id=candidate_id,
            labels_path=str(labels_path),
            preview_path=str(preview_path),
            target_regions=int(target_regions),
            compactness=float(compactness),
            region_count=int(len(np.unique(labels))),
        )
        self.candidates.append(candidate)
        self.save()
        return candidate

    def generate_candidate_grid(
        self,
        rows: int = 4,
        cols: int = 4,
        min_regions: int = 20,
        max_regions: int = 140,
        min_compactness: float = 4.0,
        max_compactness: float = 28.0,
    ) -> list[Candidate]:
        """Generate a coarse-to-detailed candidate grid without changing the design."""

        rows = max(1, int(rows))
        cols = max(1, int(cols))
        region_values = np.linspace(
            max(2, int(min_regions)),
            max(2, int(max_regions)),
            rows,
        )
        compactness_values = np.linspace(
            max(0.1, float(min_compactness)),
            max(0.1, float(max_compactness)),
            cols,
        )
        candidates = []
        for target_regions in region_values:
            for compactness in compactness_values:
                candidates.append(
                    self.generate_candidate(
                        target_regions=int(round(target_regions)),
                        compactness=float(compactness),
                    )
                )
        return candidates

    def create_design(
        self,
        candidate_id: str,
        physical_size: PhysicalSize,
        veneers: list[Veneer] | None = None,
    ) -> MarquetryDesign:
        """Seed the durable design from a candidate partition."""

        labels = self.candidate_labels(candidate_id)
        np.save(self.workspace_dir / DESIGN_LABELS, labels)
        self.design = MarquetryDesign(
            source_candidate_id=candidate_id,
            labels_path=DESIGN_LABELS,
            physical_size=physical_size,
            veneers=veneers or default_veneers(),
        )
        self._auto_assign_veneers(overwrite=True)
        self.save()
        return self.design

    def update_physical_size(self, physical_size: PhysicalSize) -> None:
        """Update finished dimensions used by cuttability metrics and SVG export."""

        if self.design is None:
            raise ValueError('create a design first')
        previous_size = self.design.physical_size
        self.design.physical_size = physical_size
        self.design.edit_history.append(
            EditOperation(
                op_id=self._next_op_id(),
                kind='update_physical_size',
                payload={
                    'physical_size': physical_size.to_dict(),
                    'previous_physical_size': previous_size.to_dict(),
                },
            )
        )
        self.save()

    def replace_veneers(self, veneers: list[Veneer]) -> None:
        """Replace available veneers and repair assignments that reference removed stock."""

        if self.design is None:
            raise ValueError('create a design first')
        if not veneers:
            raise ValueError('at least one veneer is required')
        previous_veneers = [veneer.to_dict() for veneer in self.design.veneers]
        previous_assignments = dict(self.design.veneer_assignments)
        self.design.veneers = veneers
        valid_ids = {veneer.veneer_id for veneer in veneers}
        self.design.veneer_assignments = {
            region_id: veneer_id
            for region_id, veneer_id in self.design.veneer_assignments.items()
            if veneer_id in valid_ids
        }
        self._auto_assign_veneers(overwrite=False)
        self.design.edit_history.append(
            EditOperation(
                op_id=self._next_op_id(),
                kind='replace_veneers',
                payload={
                    'previous_veneers': previous_veneers,
                    'previous_veneer_assignments': {
                        str(region_id): veneer_id
                        for region_id, veneer_id in sorted(previous_assignments.items())
                    },
                },
            )
        )
        self.save()

    def _auto_assign_veneers(self, overwrite: bool = False) -> None:
        if self.design is None:
            return
        image = self.source_array()
        labels = self.design_labels()
        regions = build_regions(image, labels, self.design)
        if overwrite:
            self.design.veneer_assignments = {}
        for region in regions:
            self.design.veneer_assignments.setdefault(region.region_id, region.suggested_veneer_id)

    def assign_veneer(self, region_id: int, veneer_id: str) -> None:
        if self.design is None:
            raise ValueError('create a design first')
        if veneer_id not in {veneer.veneer_id for veneer in self.design.veneers}:
            raise ValueError(f'unknown veneer: {veneer_id}')
        if int(region_id) not in set(int(value) for value in np.unique(self.design_labels())):
            raise ValueError(f'unknown region: {region_id}')
        previous_veneer = self.design.veneer_assignments.get(int(region_id))
        self.design.veneer_assignments[int(region_id)] = veneer_id
        self.design.edit_history.append(
            EditOperation(
                op_id=self._next_op_id(),
                kind='assign_veneer',
                payload={
                    'region_id': int(region_id),
                    'veneer_id': veneer_id,
                    'previous_veneer_id': previous_veneer,
                },
            )
        )
        self.save()

    def assign_veneer_many(self, region_ids: list[int] | set[int], veneer_id: str) -> None:
        """Assign one veneer to multiple current regions as one undoable edit."""

        if self.design is None:
            raise ValueError('create a design first')
        selected_region_ids = {int(region_id) for region_id in region_ids}
        if not selected_region_ids:
            raise ValueError('choose at least one region')
        if veneer_id not in {veneer.veneer_id for veneer in self.design.veneers}:
            raise ValueError(f'unknown veneer: {veneer_id}')
        existing = {int(value) for value in np.unique(self.design_labels()) if int(value) > 0}
        missing = sorted(selected_region_ids - existing)
        if missing:
            raise ValueError(f'unknown region ids: {missing}')

        previous = {
            region_id: self.design.veneer_assignments.get(region_id)
            for region_id in selected_region_ids
        }
        for region_id in selected_region_ids:
            self.design.veneer_assignments[region_id] = veneer_id
        self.design.edit_history.append(
            EditOperation(
                op_id=self._next_op_id(),
                kind='assign_veneer_many',
                payload={
                    'region_ids': sorted(selected_region_ids),
                    'veneer_id': veneer_id,
                    'previous_veneer_ids': {
                        str(region_id): previous_veneer
                        for region_id, previous_veneer in sorted(previous.items())
                    },
                },
            )
        )
        self.save()

    def add_detail_zone(
        self,
        name: str,
        bbox: tuple[int, int, int, int],
        detail_multiplier: float = 2.0,
    ) -> DetailZone:
        """Persist a rectangular focus zone in source-image pixel coordinates."""

        if self.design is None:
            raise ValueError('create a design first')
        x0, y0, x1, y1 = bbox
        clipped = (
            max(0, min(int(x0), self.source.working_width - 1)),
            max(0, min(int(y0), self.source.working_height - 1)),
            max(1, min(int(x1), self.source.working_width)),
            max(1, min(int(y1), self.source.working_height)),
        )
        if clipped[0] >= clipped[2] or clipped[1] >= clipped[3]:
            raise ValueError('detail zone must have positive area')
        zone = DetailZone(
            zone_id=len(self.design.detail_zones) + 1,
            name=name or f'Zone {len(self.design.detail_zones) + 1}',
            bbox=clipped,
            detail_multiplier=max(1.0, float(detail_multiplier)),
        )
        self.design.detail_zones.append(zone)
        self.design.edit_history.append(
            EditOperation(
                op_id=self._next_op_id(),
                kind='add_detail_zone',
                payload={'zone': zone.to_dict()},
            )
        )
        self.save()
        return zone

    def add_detail_zone_for_regions(
        self,
        region_ids: list[int] | set[int],
        name: str = 'Focus zone',
        detail_multiplier: float = 2.0,
    ) -> DetailZone:
        """Create a rectangular focus zone around the selected current regions."""

        if self.design is None:
            raise ValueError('create a design first')
        selected_region_ids = {int(region_id) for region_id in region_ids}
        if not selected_region_ids:
            raise ValueError('choose at least one region')
        labels = self.design_labels()
        missing = sorted(selected_region_ids - self._current_region_ids())
        if missing:
            raise ValueError(f'unknown region ids: {missing}')
        mask = np.isin(labels, list(selected_region_ids))
        ys, xs = np.nonzero(mask)
        if not len(xs):
            raise ValueError('selected regions have no pixels')
        return self.add_detail_zone(
            name=name,
            bbox=(int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1),
            detail_multiplier=detail_multiplier,
        )

    def _current_region_ids(self) -> set[int]:
        return {int(value) for value in np.unique(self.design_labels()) if int(value) > 0}

    def lock_regions(self, region_ids: list[int] | set[int], locked: bool = True) -> None:
        """Lock or unlock current regions as one undoable edit."""

        if self.design is None:
            raise ValueError('create a design first')
        selected_region_ids = {int(region_id) for region_id in region_ids}
        if not selected_region_ids:
            raise ValueError('choose at least one region')
        missing = sorted(selected_region_ids - self._current_region_ids())
        if missing:
            raise ValueError(f'unknown region ids: {missing}')

        previous_locked = sorted(self.design.locked_region_ids)
        if locked:
            self.design.locked_region_ids.update(selected_region_ids)
        else:
            self.design.locked_region_ids.difference_update(selected_region_ids)
        self.design.edit_history.append(
            EditOperation(
                op_id=self._next_op_id(),
                kind='lock_regions',
                payload={
                    'region_ids': sorted(selected_region_ids),
                    'locked': bool(locked),
                    'previous_locked_region_ids': previous_locked,
                },
            )
        )
        self.save()

    def _selected_regions_are_connected(
        self,
        selected_region_ids: set[int],
        neighbors: dict[int, set[int]],
    ) -> bool:
        start = next(iter(selected_region_ids))
        seen = {start}
        stack = [start]
        while stack:
            current = stack.pop()
            for neighbor in neighbors.get(current, set()):
                if neighbor in selected_region_ids and neighbor not in seen:
                    seen.add(neighbor)
                    stack.append(neighbor)
        return seen == selected_region_ids

    def _remap_veneer_assignments(
        self,
        id_map: dict[int, int],
        selected_region_ids: set[int],
        labels_before: np.ndarray,
    ) -> dict[int, str]:
        if self.design is None:
            raise ValueError('create a design first')
        remapped: dict[int, str] = {}
        selected_areas = {
            region_id: int(np.count_nonzero(labels_before == region_id))
            for region_id in selected_region_ids
        }
        selected_with_veneers = [
            (selected_areas[region_id], self.design.veneer_assignments[region_id])
            for region_id in selected_region_ids
            if region_id in self.design.veneer_assignments
        ]
        merged_veneer = (
            max(selected_with_veneers, key=lambda item: item[0])[1]
            if selected_with_veneers
            else None
        )
        merged_id = id_map[min(selected_region_ids)]

        for old_id, new_id in id_map.items():
            if old_id in selected_region_ids:
                continue
            veneer_id = self.design.veneer_assignments.get(old_id)
            if veneer_id is not None:
                remapped[new_id] = veneer_id
        if merged_veneer is not None:
            remapped[merged_id] = merged_veneer
        return remapped

    def merge_regions(self, region_ids: list[int] | set[int]) -> None:
        """Merge connected regions while preserving the full raster partition."""

        if self.design is None:
            raise ValueError('create a design first')
        selected_region_ids = {int(region_id) for region_id in region_ids}
        if len(selected_region_ids) < 2:
            raise ValueError('choose at least two regions to merge')
        locked = selected_region_ids & self.design.locked_region_ids
        if locked:
            raise ValueError(f'locked regions cannot be merged: {sorted(locked)}')

        labels_before = self.design_labels()
        neighbors = region_neighbors(labels_before)
        if not self._selected_regions_are_connected(selected_region_ids, neighbors):
            raise ValueError('merge selection must be connected')

        op_id = self._next_op_id()
        previous_labels_path = self._snapshot_labels(op_id)
        previous_assignments = dict(self.design.veneer_assignments)
        previous_locked = sorted(self.design.locked_region_ids)
        labels_after, id_map = merge_labels(labels_before, selected_region_ids)
        validation = partition_validation(labels_after)
        if not validation['valid']:
            raise ValueError(f'merge would create invalid partition: {validation}')

        self._write_design_labels(labels_after)
        self.design.veneer_assignments = self._remap_veneer_assignments(
            id_map,
            selected_region_ids,
            labels_before,
        )
        self.design.locked_region_ids = {
            id_map[region_id]
            for region_id in self.design.locked_region_ids
            if region_id in id_map
        }
        self.design.edit_history.append(
            EditOperation(
                op_id=op_id,
                kind='merge_regions',
                payload={
                    'region_ids': sorted(selected_region_ids),
                    'previous_labels_path': previous_labels_path,
                    'previous_veneer_assignments': {
                        str(region_id): veneer_id
                        for region_id, veneer_id in sorted(previous_assignments.items())
                    },
                    'previous_locked_region_ids': previous_locked,
                },
            )
        )
        self.save()

    def split_region(
        self,
        region_id: int,
        target_parts: int = 3,
        compactness: float = 12.0,
    ) -> None:
        """Subdivide one region inside its current mask while preserving the partition."""

        if self.design is None:
            raise ValueError('create a design first')
        region_id = int(region_id)
        if region_id in self.design.locked_region_ids:
            raise ValueError(f'locked region cannot be split: {region_id}')
        labels_before = self.design_labels()
        mask = labels_before == region_id
        if not np.any(mask):
            raise ValueError(f'unknown region: {region_id}')

        ys, xs = np.nonzero(mask)
        x0, x1 = int(xs.min()), int(xs.max()) + 1
        y0, y1 = int(ys.min()), int(ys.max()) + 1
        crop_image = self.source_array()[y0:y1, x0:x1]
        crop_mask = mask[y0:y1, x0:x1]
        if int(crop_mask.sum()) < 4:
            raise ValueError('region is too small to split')

        split_labels = slic(
            crop_image,
            n_segments=max(2, int(target_parts)),
            compactness=float(compactness),
            sigma=0.5,
            start_label=1,
            channel_axis=-1,
            mask=crop_mask,
        )
        split_ids = [int(value) for value in np.unique(split_labels) if int(value) > 0]
        if len(split_ids) < 2:
            raise ValueError('split did not create multiple regions')

        op_id = self._next_op_id()
        previous_labels_path = self._snapshot_labels(op_id)
        previous_assignments = dict(self.design.veneer_assignments)
        previous_locked = sorted(self.design.locked_region_ids)
        labels_after = labels_before.copy()
        next_id = int(labels_before.max()) + 1
        for index, split_id in enumerate(split_ids):
            child_mask = np.zeros_like(labels_before, dtype=bool)
            child_mask[y0:y1, x0:x1] = split_labels == split_id
            labels_after[child_mask] = region_id if index == 0 else next_id
            next_id += 1
        labels_after = normalize_labels(labels_after)
        validation = partition_validation(labels_after)
        if not validation['valid']:
            raise ValueError(f'split would create invalid partition: {validation}')

        self._write_design_labels(labels_after)
        split_child_ids = {
            int(value) for value in np.unique(labels_after[mask]) if int(value) > 0
        }
        split_veneer = previous_assignments.get(region_id)
        remapped: dict[int, str] = {}
        for old_id, veneer_id in previous_assignments.items():
            if old_id == region_id:
                continue
            old_mask = labels_before == old_id
            new_values = np.unique(labels_after[old_mask])
            if len(new_values) == 1:
                remapped[int(new_values[0])] = veneer_id
        if split_veneer is not None:
            for child_id in split_child_ids:
                remapped[child_id] = split_veneer
        self.design.veneer_assignments = remapped
        self.design.locked_region_ids = {
            int(np.unique(labels_after[labels_before == locked_id])[0])
            for locked_id in self.design.locked_region_ids
            if locked_id != region_id and np.any(labels_before == locked_id)
        }
        self.design.edit_history.append(
            EditOperation(
                op_id=op_id,
                kind='split_region',
                payload={
                    'region_id': region_id,
                    'target_parts': int(target_parts),
                    'compactness': float(compactness),
                    'previous_labels_path': previous_labels_path,
                    'previous_locked_region_ids': previous_locked,
                    'previous_veneer_assignments': {
                        str(previous_region_id): veneer_id
                        for previous_region_id, veneer_id in sorted(previous_assignments.items())
                    },
                },
            )
        )
        self.save()

    def apply_detail_zones(self, max_splits: int = 10, compactness: float = 10.0) -> int:
        """Split unlocked regions intersecting persisted detail zones."""

        if self.design is None:
            raise ValueError('create a design first')
        applied = 0
        for zone in self.design.detail_zones:
            if applied >= max_splits:
                break
            labels = self.design_labels()
            x0, y0, x1, y1 = zone.bbox
            zone_labels = labels[y0:y1, x0:x1]
            region_ids = [
                int(value)
                for value in np.unique(zone_labels)
                if int(value) > 0 and int(value) not in self.design.locked_region_ids
            ]
            if not region_ids:
                continue
            region_ids.sort(
                key=lambda region_id: int(np.count_nonzero(labels == region_id)),
                reverse=True,
            )
            for region_id in region_ids:
                if applied >= max_splits:
                    break
                target_parts = max(2, int(round(zone.detail_multiplier)))
                try:
                    self.split_region(
                        region_id,
                        target_parts=target_parts,
                        compactness=compactness,
                    )
                except ValueError:
                    continue
                applied += 1
                break
        return applied

    def undo(self) -> None:
        """Undo the most recent persisted design edit."""

        if self.design is None:
            raise ValueError('create a design first')
        if not self.design.edit_history:
            raise ValueError('nothing to undo')
        edit = self.design.edit_history.pop()
        if edit.kind == 'assign_veneer':
            region_id = int(edit.payload['region_id'])
            previous_veneer = edit.payload.get('previous_veneer_id')
            if previous_veneer is None:
                self.design.veneer_assignments.pop(region_id, None)
            else:
                self.design.veneer_assignments[region_id] = str(previous_veneer)
        elif edit.kind == 'assign_veneer_many':
            for region_id, previous_veneer in edit.payload['previous_veneer_ids'].items():
                if previous_veneer is None:
                    self.design.veneer_assignments.pop(int(region_id), None)
                else:
                    self.design.veneer_assignments[int(region_id)] = str(previous_veneer)
        elif edit.kind == 'merge_regions':
            labels_path = self.workspace_dir / str(edit.payload['previous_labels_path'])
            self._write_design_labels(np.load(labels_path))
            self.design.veneer_assignments = {
                int(region_id): str(veneer_id)
                for region_id, veneer_id in edit.payload[
                    'previous_veneer_assignments'
                ].items()
            }
            if 'previous_locked_region_ids' in edit.payload:
                self.design.locked_region_ids = {
                    int(region_id) for region_id in edit.payload['previous_locked_region_ids']
                }
        elif edit.kind == 'split_region':
            labels_path = self.workspace_dir / str(edit.payload['previous_labels_path'])
            self._write_design_labels(np.load(labels_path))
            self.design.veneer_assignments = {
                int(region_id): str(veneer_id)
                for region_id, veneer_id in edit.payload[
                    'previous_veneer_assignments'
                ].items()
            }
            self.design.locked_region_ids = {
                int(region_id) for region_id in edit.payload['previous_locked_region_ids']
            }
        elif edit.kind == 'lock_regions':
            self.design.locked_region_ids = {
                int(region_id) for region_id in edit.payload['previous_locked_region_ids']
            }
        elif edit.kind == 'update_physical_size':
            self.design.physical_size = PhysicalSize.from_dict(
                edit.payload['previous_physical_size']
            )
        elif edit.kind == 'replace_veneers':
            self.design.veneers = [
                Veneer.from_dict(item) for item in edit.payload['previous_veneers']
            ]
            self.design.veneer_assignments = {
                int(region_id): str(veneer_id)
                for region_id, veneer_id in edit.payload[
                    'previous_veneer_assignments'
                ].items()
            }
        elif edit.kind == 'add_detail_zone':
            zone_id = int(edit.payload['zone']['zone_id'])
            self.design.detail_zones = [
                zone for zone in self.design.detail_zones if zone.zone_id != zone_id
            ]
        else:
            raise ValueError(f'cannot undo edit kind: {edit.kind}')
        self.save()

    def merge_suggestions(self) -> list[dict[str, Any]]:
        """Suggest neighbor merges for regions that are physically hard to cut."""

        if self.design is None:
            return []
        regions = build_regions(self.source_array(), self.design_labels(), self.design)
        by_id = {region.region_id: region for region in regions}
        suggestions = []
        for region in regions:
            if region.locked or not region.warnings:
                continue
            neighbor_regions = [
                by_id[neighbor_id]
                for neighbor_id in region.neighbors
                if neighbor_id in by_id and not by_id[neighbor_id].locked
            ]
            if not neighbor_regions:
                continue
            same_veneer = [
                neighbor for neighbor in neighbor_regions if neighbor.veneer_id == region.veneer_id
            ]
            target = max(same_veneer or neighbor_regions, key=lambda item: item.area_px)
            suggestions.append(
                {
                    'region_id': region.region_id,
                    'target_region_id': target.region_id,
                    'reason': ', '.join(region.warnings),
                    'same_veneer': target.veneer_id == region.veneer_id,
                    'area_physical': region.area_physical,
                }
            )
        return suggestions

    def apply_merge_suggestions(self, max_merges: int = 10) -> int:
        """Apply connected small/thin merge suggestions until no safe suggestions remain."""

        applied = 0
        for _ in range(max(0, int(max_merges))):
            suggestions = self.merge_suggestions()
            if not suggestions:
                break
            suggestion = suggestions[0]
            try:
                self.merge_regions([suggestion['region_id'], suggestion['target_region_id']])
            except ValueError:
                break
            applied += 1
        return applied

    def regions(self) -> list[dict[str, Any]]:
        if self.design is None:
            return []
        return [
            region.to_dict()
            for region in build_regions(self.source_array(), self.design_labels(), self.design)
        ]

    def validation(self) -> dict[str, Any]:
        if self.design is None:
            return {'valid': False, 'reason': 'missing design'}
        return partition_validation(self.design_labels())

    def boundary_summary(self) -> dict[str, Any]:
        """Return shared-boundary metrics used by cleanup and merge prioritization."""

        if self.design is None:
            return {'boundary_count': 0, 'boundaries': []}
        labels = self.design_labels()
        boundaries = shared_boundaries(labels)
        px_per_unit_x, px_per_unit_y = self.design.physical_size.pixels_per_unit(
            (labels.shape[1], labels.shape[0])
        )
        avg_px_per_unit = (px_per_unit_x + px_per_unit_y) / 2
        for boundary in boundaries:
            boundary['edge_length_physical'] = boundary['edge_px'] / max(avg_px_per_unit, 1e-9)
        return {'boundary_count': len(boundaries), 'boundaries': boundaries}

    def export_svg(self, output_path: str | Path) -> Path:
        if self.design is None:
            raise ValueError('create a design first')
        validation = self.validation()
        if not validation['valid']:
            raise ValueError(f'invalid partition: {validation}')
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        svg = design_to_svg(
            build_regions(self.source_array(), self.design_labels(), self.design),
            self.design.physical_size,
            (self.source.working_width, self.source.working_height),
        )
        path.write_text(svg, encoding='utf-8')
        return path

    def pack(self, output_dir: str | Path) -> dict[str, Any]:
        """Write a traceable physical packing manifest grouped by veneer."""

        if self.design is None:
            raise ValueError('create a design first')
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)
        regions = build_regions(self.source_array(), self.design_labels(), self.design)
        by_veneer: dict[str, list[dict[str, Any]]] = {}
        for region in regions:
            by_veneer.setdefault(region.veneer_id, []).append(region.to_dict())
        sheets = []
        for veneer in self.design.veneers:
            pieces = by_veneer.get(veneer.veneer_id, [])
            if not pieces:
                continue
            sheet_width = veneer.sheet_width or self.design.physical_size.width
            sheet_height = veneer.sheet_height or self.design.physical_size.height
            available_count = veneer.sheet_count or max(1, len(pieces))
            packer = newPacker(rotation=True)
            scale = 1000
            for piece in pieces:
                x0, y0, x1, y1 = piece['bbox']
                width_px = max(1, x1 - x0)
                height_px = max(1, y1 - y0)
                px_per_unit_x, px_per_unit_y = self.design.physical_size.pixels_per_unit(
                    (self.source.working_width, self.source.working_height)
                )
                width_units = width_px / max(px_per_unit_x, 1e-9)
                height_units = height_px / max(px_per_unit_y, 1e-9)
                packer.add_rect(
                    max(1, int(round(width_units * scale))),
                    max(1, int(round(height_units * scale))),
                    piece['region_id'],
                )
            packer.add_bin(
                max(1, int(round(sheet_width * scale))),
                max(1, int(round(sheet_height * scale))),
                count=available_count,
            )
            packer.pack()
            placements_by_region = {}
            for bin_index, x, y, width, height, region_id in packer.rect_list():
                placements_by_region[int(region_id)] = {
                    'sheet_index': int(bin_index),
                    'x': x / scale,
                    'y': y / scale,
                    'width': width / scale,
                    'height': height / scale,
                }
            placed_count = len(placements_by_region)
            sheet_count_used = (
                max(
                    (placement['sheet_index'] for placement in placements_by_region.values()),
                    default=-1,
                )
                + 1
            )
            packed_pieces = [
                {
                    **piece,
                    'placement': placements_by_region.get(piece['region_id']),
                    'packed': piece['region_id'] in placements_by_region,
                }
                for piece in pieces
            ]
            sheets.append(
                {
                    'veneer_id': veneer.veneer_id,
                    'piece_count': len(pieces),
                    'placed_piece_count': placed_count,
                    'sheet_width': sheet_width,
                    'sheet_height': sheet_height,
                    'available_sheet_count': veneer.sheet_count,
                    'sheet_count_used': sheet_count_used,
                    'over_stock_capacity': placed_count < len(pieces),
                    'pieces': packed_pieces,
                }
            )
        manifest = {'packing_backend': 'rectpack-bounding-box', 'sheets': sheets}
        (output_path / 'pack.json').write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + '\n',
            encoding='utf-8',
        )
        self.export_svg(output_path / 'design.svg')
        return manifest

    def summary(self) -> dict[str, Any]:
        return {
            'workspace_dir': str(self.workspace_dir),
            'source': self.source.to_dict(),
            'candidates': [candidate.to_dict() for candidate in self.candidates],
            'design': self.design.to_dict() if self.design else None,
            'regions': self.regions(),
            'merge_suggestions': self.merge_suggestions(),
            'validation': self.validation(),
            'boundaries': self.boundary_summary(),
        }

    def copy_to(self, output_dir: str | Path) -> None:
        """Copy the whole workspace for debugging or fixtures."""

        output_path = Path(output_dir)
        if output_path.exists():
            shutil.rmtree(output_path)
        shutil.copytree(self.workspace_dir, output_path)
