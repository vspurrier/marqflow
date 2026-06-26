"""Workspace persistence for the marquetry-first rewrite."""

from __future__ import annotations

import json
import math
import os
import shutil
import tempfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image, ImageOps
from rectpack import newPacker
from skimage.measure import approximate_polygon
from skimage.segmentation import slic

from .geometry import (
    boundary_graph,
    build_regions,
    coverage_simplified_svg,
    coverage_summary,
    design_to_svg,
    graph_region_polygons,
    graph_to_svg,
    merge_labels,
    move_topology_vertex,
    normalize_labels,
    partition_validation,
    preview_image,
    region_neighbors,
    shared_boundaries,
    shared_boundary_paths,
    simplify_topology_edges,
    simplify_topology_graph,
    svg_path,
    validate_topology_graph,
)
from .models import (
    Candidate,
    DetailZone,
    EditOperation,
    ExportArtifact,
    MarquetryDesign,
    PhysicalSize,
    SourceImage,
    VectorGraphArtifact,
    Veneer,
    default_veneers,
)

MANIFEST = 'workspace.json'
SOURCE_IMAGE = 'source.png'
DESIGN_LABELS = 'design-labels.npy'
SUBJECT_MASK = 'subject-mask.npy'
HISTORY_DIR = 'history'
VECTOR_DIR = 'vector'


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
        self.design.active_vector_graph_kind = None

    def _next_op_id(self) -> int:
        if self.design is None:
            raise ValueError('create a design first')
        return len(self.design.edit_history) + 1

    def _snapshot_labels(self, op_id: int) -> str:
        path = Path(HISTORY_DIR) / f'op-{op_id}-labels.npy'
        (self.workspace_dir / path).parent.mkdir(parents=True, exist_ok=True)
        np.save(self.workspace_dir / path, self.design_labels())
        return str(path)

    def subject_mask(self) -> np.ndarray:
        """Return the persisted source-stage subject/background mask."""

        if self.design is None or self.design.subject_mask_path is None:
            return np.zeros(
                (self.source.working_height, self.source.working_width),
                dtype=np.uint8,
            )
        return np.load(self.workspace_dir / self.design.subject_mask_path)

    def _write_subject_mask(self, mask: np.ndarray) -> None:
        if self.design is None:
            raise ValueError('create a design first')
        np.save(self.workspace_dir / SUBJECT_MASK, mask.astype(np.uint8))
        self.design.subject_mask_path = SUBJECT_MASK

    def _snapshot_subject_mask(self, op_id: int) -> str | None:
        if self.design is None or self.design.subject_mask_path is None:
            return None
        path = Path(HISTORY_DIR) / f'op-{op_id}-subject-mask.npy'
        (self.workspace_dir / path).parent.mkdir(parents=True, exist_ok=True)
        np.save(self.workspace_dir / path, self.subject_mask())
        return str(path)

    def generate_candidate(
        self,
        target_regions: int = 80,
        compactness: float = 18.0,
        use_detail_zones: bool = False,
        use_subject_mask: bool = True,
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
        if use_detail_zones and self.design is not None:
            labels = self._apply_detail_zones_to_candidate(
                labels,
                target_regions=max(2, int(target_regions)),
                compactness=float(compactness),
            )
        if use_subject_mask and self.design is not None and self.design.subject_mask_path:
            labels = self._apply_subject_mask_to_candidate(
                labels,
                target_regions=max(2, int(target_regions)),
                compactness=float(compactness),
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
        use_detail_zones: bool = False,
        use_subject_mask: bool = True,
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
                        use_detail_zones=use_detail_zones,
                        use_subject_mask=use_subject_mask,
                    )
                )
        return candidates

    def _apply_subject_mask_to_candidate(
        self,
        labels: np.ndarray,
        target_regions: int,
        compactness: float,
    ) -> np.ndarray:
        """Overlay separate local labels for subject/background mask areas."""

        mask = self.subject_mask()
        if not np.any(mask):
            return labels
        image = self.source_array()
        height, width = labels.shape
        refined = labels.copy()
        next_label = int(refined.max()) + 1
        image_area = max(1, height * width)
        for mask_value in (1, 2):
            ys, xs = np.nonzero(mask == mask_value)
            if not len(xs):
                continue
            x0, x1 = int(xs.min()), int(xs.max()) + 1
            y0, y1 = int(ys.min()), int(ys.max()) + 1
            crop_mask = mask[y0:y1, x0:x1] == mask_value
            crop = image[y0:y1, x0:x1]
            if crop.shape[0] < 2 or crop.shape[1] < 2:
                continue
            local_area = int(np.count_nonzero(crop_mask))
            local_segments = int(round(target_regions * (local_area / image_area)))
            if mask_value == 1:
                local_segments = int(round(local_segments * 1.5))
            local_segments = max(1, min(local_segments, max(1, local_area // 4)))
            region = refined[y0:y1, x0:x1]
            if local_segments < 2:
                region[crop_mask] = next_label
                next_label += 1
                continue
            local = slic(
                crop,
                n_segments=local_segments,
                compactness=compactness,
                sigma=0.75,
                start_label=0,
                channel_axis=-1,
            )
            local_values = sorted(int(value) for value in np.unique(local[crop_mask]))
            remapped = np.zeros_like(local, dtype=np.int32)
            for value in local_values:
                value_mask = crop_mask & (local == value)
                if not np.any(value_mask):
                    continue
                remapped[value_mask] = next_label
                next_label += 1
            region[crop_mask] = remapped[crop_mask]
        return refined

    def _apply_detail_zones_to_candidate(
        self,
        labels: np.ndarray,
        target_regions: int,
        compactness: float,
    ) -> np.ndarray:
        """Overlay denser local SLIC labels in persisted detail zones."""

        if self.design is None or not self.design.detail_zones:
            return labels
        image = self.source_array()
        height, width = labels.shape
        refined = labels.copy()
        next_label = int(refined.max()) + 1
        image_area = max(1, height * width)
        for zone in self.design.detail_zones:
            x0, y0, x1, y1 = zone.bbox
            x0 = max(0, min(width - 1, int(x0)))
            y0 = max(0, min(height - 1, int(y0)))
            x1 = max(x0 + 1, min(width, int(x1)))
            y1 = max(y0 + 1, min(height, int(y1)))
            crop = image[y0:y1, x0:x1]
            if crop.shape[0] < 2 or crop.shape[1] < 2:
                continue
            zone_area = crop.shape[0] * crop.shape[1]
            local_segments = int(
                round(target_regions * (zone_area / image_area) * zone.detail_multiplier)
            )
            local_segments = max(2, min(local_segments, max(2, zone_area // 4)))
            local = slic(
                crop,
                n_segments=local_segments,
                compactness=compactness,
                sigma=0.75,
                start_label=0,
                channel_axis=-1,
            )
            local = normalize_labels(local)
            local_values = sorted(int(value) for value in np.unique(local) if int(value) > 0)
            remapped = np.zeros_like(local, dtype=np.int32)
            for value in local_values:
                remapped[local == value] = next_label
                next_label += 1
            refined[y0:y1, x0:x1] = remapped
        return refined

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
        veneer_ids = [veneer.veneer_id for veneer in veneers]
        if len(set(veneer_ids)) != len(veneer_ids):
            raise ValueError('veneer IDs must be unique')
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

    def set_subject_mask_for_regions(self, region_ids: list[int], role: str) -> None:
        """Mark selected design regions as subject or background source mask pixels."""

        if self.design is None:
            raise ValueError('create a design first')
        role_value = {'subject': 1, 'background': 2}.get(role)
        if role_value is None:
            raise ValueError('role must be subject or background')
        if not region_ids:
            raise ValueError('choose at least one region')
        labels = self.design_labels()
        existing = {int(value) for value in np.unique(labels) if int(value) > 0}
        missing = sorted(set(region_ids) - existing)
        if missing:
            raise ValueError(f'unknown region ids: {missing}')

        op_id = self._next_op_id()
        previous_mask_path = self._snapshot_subject_mask(op_id)
        previous_subject_mask_path = self.design.subject_mask_path
        mask = self.subject_mask()
        selected = np.isin(labels, list(region_ids))
        mask[selected] = role_value
        self._write_subject_mask(mask)
        self.design.edit_history.append(
            EditOperation(
                op_id=op_id,
                kind='set_subject_mask',
                payload={
                    'region_ids': [int(region_id) for region_id in region_ids],
                    'role': role,
                    'previous_mask_path': previous_mask_path,
                    'previous_subject_mask_path': previous_subject_mask_path,
                },
            )
        )
        self.save()

    def paint_subject_mask_stroke(
        self,
        points: list[tuple[float, float]],
        role: str,
        brush_radius: float = 4.0,
    ) -> None:
        """Paint subject/background mask pixels along a freehand source-space stroke."""

        if self.design is None:
            raise ValueError('create a design first')
        role_value = {'subject': 1, 'background': 2}.get(role)
        if role_value is None:
            raise ValueError('role must be subject or background')
        if not points:
            raise ValueError('stroke needs at least one point')

        op_id = self._next_op_id()
        previous_mask_path = self._snapshot_subject_mask(op_id)
        previous_subject_mask_path = self.design.subject_mask_path
        mask = self.subject_mask()
        height, width = mask.shape
        radius = max(0.5, float(brush_radius))
        radius_int = int(math.ceil(radius))
        for point_index, point in enumerate(points):
            x, y = point
            if point_index > 0:
                prev_x, prev_y = points[point_index - 1]
                steps = max(int(math.ceil(max(abs(x - prev_x), abs(y - prev_y)))), 1)
                for step in range(steps + 1):
                    t = step / steps
                    self._paint_mask_disk(
                        mask,
                        prev_x + (x - prev_x) * t,
                        prev_y + (y - prev_y) * t,
                        radius,
                        radius_int,
                        role_value,
                    )
            else:
                self._paint_mask_disk(mask, x, y, radius, radius_int, role_value)
        self._write_subject_mask(mask)
        self.design.edit_history.append(
            EditOperation(
                op_id=op_id,
                kind='paint_subject_mask_stroke',
                payload={
                    'role': role,
                    'brush_radius': radius,
                    'point_count': len(points),
                    'previous_mask_path': previous_mask_path,
                    'previous_subject_mask_path': previous_subject_mask_path,
                },
            )
        )
        self.save()

    @staticmethod
    def _paint_mask_disk(
        mask: np.ndarray,
        center_x: float,
        center_y: float,
        radius: float,
        radius_int: int,
        value: int,
    ) -> None:
        height, width = mask.shape
        cx = int(round(center_x))
        cy = int(round(center_y))
        x0 = max(0, cx - radius_int)
        x1 = min(width, cx + radius_int + 1)
        y0 = max(0, cy - radius_int)
        y1 = min(height, cy + radius_int + 1)
        yy, xx = np.ogrid[y0:y1, x0:x1]
        disk = (xx - center_x) ** 2 + (yy - center_y) ** 2 <= radius**2
        region = mask[y0:y1, x0:x1]
        region[disk] = value

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
        elif edit.kind == 'smooth_boundaries':
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
        elif edit.kind in {'set_subject_mask', 'paint_subject_mask_stroke'}:
            previous_mask_path = edit.payload.get('previous_mask_path')
            previous_subject_mask_path = edit.payload.get('previous_subject_mask_path')
            if previous_mask_path is None:
                (self.workspace_dir / SUBJECT_MASK).unlink(missing_ok=True)
                self.design.subject_mask_path = None
            else:
                previous = np.load(self.workspace_dir / str(previous_mask_path))
                np.save(self.workspace_dir / SUBJECT_MASK, previous)
                self.design.subject_mask_path = (
                    str(previous_subject_mask_path)
                    if previous_subject_mask_path is not None
                    else SUBJECT_MASK
                )
        elif edit.kind in {'simplify_vector_graph', 'edit_vector_graph'}:
            target_kind = str(edit.payload['target_kind'])
            target_path = self.workspace_dir / str(edit.payload['target_path'])
            previous_payload_path = edit.payload.get('previous_payload_path')
            previous_artifact = edit.payload.get('previous_artifact')
            previous_active_kind = edit.payload.get('previous_active_vector_graph_kind')
            self.design.vector_graphs = [
                artifact
                for artifact in self.design.vector_graphs
                if artifact.kind != target_kind
            ]
            if previous_payload_path and previous_artifact:
                shutil.copyfile(self.workspace_dir / str(previous_payload_path), target_path)
                self.design.vector_graphs.append(
                    VectorGraphArtifact.from_dict(previous_artifact)
                )
            else:
                target_path.unlink(missing_ok=True)
            if 'previous_active_vector_graph_kind' in edit.payload:
                self.design.active_vector_graph_kind = (
                    str(previous_active_kind) if previous_active_kind is not None else None
                )
        elif edit.kind == 'promote_vector_graph':
            previous_active_kind = edit.payload.get('previous_active_vector_graph_kind')
            self.design.active_vector_graph_kind = (
                str(previous_active_kind) if previous_active_kind is not None else None
            )
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

    def repair_small_regions(
        self,
        max_area: float = 0.05,
        max_repairs: int = 25,
    ) -> int:
        """Merge regions below a physical area threshold into a neighboring region."""

        if self.design is None:
            raise ValueError('create a design first')
        applied = 0
        for _ in range(max(0, int(max_repairs))):
            regions = build_regions(self.source_array(), self.design_labels(), self.design)
            by_id = {region.region_id: region for region in regions}
            small_regions = [
                region
                for region in regions
                if region.area_physical <= max_area and not region.locked
            ]
            if not small_regions:
                break
            boundaries = self.boundary_summary()['boundaries']
            boundary_lengths: dict[tuple[int, int], float] = {}
            for boundary in boundaries:
                pair = tuple(sorted((int(boundary['region_a']), int(boundary['region_b']))))
                boundary_lengths[pair] = float(boundary['edge_length_physical'])
            small_regions.sort(key=lambda region: region.area_physical)
            repaired = False
            for region in small_regions:
                neighbors = [
                    by_id[neighbor_id]
                    for neighbor_id in region.neighbors
                    if neighbor_id in by_id and not by_id[neighbor_id].locked
                ]
                if not neighbors:
                    continue
                same_veneer = [
                    neighbor for neighbor in neighbors if neighbor.veneer_id == region.veneer_id
                ]
                candidates = same_veneer or neighbors
                target = max(
                    candidates,
                    key=lambda neighbor: (
                        boundary_lengths.get(
                            tuple(sorted((region.region_id, neighbor.region_id))),
                            0.0,
                        ),
                        neighbor.area_physical,
                    ),
                )
                try:
                    self.merge_regions([region.region_id, target.region_id])
                except ValueError:
                    continue
                applied += 1
                repaired = True
                break
            if not repaired:
                break
        return applied

    def smooth_boundaries(
        self,
        iterations: int = 1,
        region_ids: list[int] | set[int] | None = None,
    ) -> int:
        """Denoise unlocked boundary pixels with local neighbor voting."""

        if self.design is None:
            raise ValueError('create a design first')
        labels_before = self.design_labels()
        labels_after = labels_before.copy()
        locked_ids = set(self.design.locked_region_ids)
        selected_region_ids = {int(region_id) for region_id in region_ids or []}
        if selected_region_ids:
            missing = sorted(selected_region_ids - self._current_region_ids())
            if missing:
                raise ValueError(f'unknown region ids: {missing}')
        changed_total = 0

        for _ in range(max(1, int(iterations))):
            candidate = labels_after.copy()
            changed = 0
            for y in range(1, labels_after.shape[0] - 1):
                for x in range(1, labels_after.shape[1] - 1):
                    current = int(labels_after[y, x])
                    if current in locked_ids:
                        continue
                    if selected_region_ids and current not in selected_region_ids:
                        continue
                    neighbors = [
                        int(labels_after[y - 1, x]),
                        int(labels_after[y + 1, x]),
                        int(labels_after[y, x - 1]),
                        int(labels_after[y, x + 1]),
                    ]
                    if len(set(neighbors)) == 1 and neighbors[0] != current:
                        candidate[y, x] = neighbors[0]
                        changed += 1
                        continue
                    counts = {
                        neighbor: neighbors.count(neighbor)
                        for neighbor in set(neighbors)
                        if neighbor not in locked_ids
                    }
                    if not counts:
                        continue
                    winner, count = max(counts.items(), key=lambda item: item[1])
                    if count >= 3 and winner != current:
                        candidate[y, x] = winner
                        changed += 1
            if changed == 0:
                break
            validation = partition_validation(candidate)
            if not validation['valid']:
                break
            labels_after = candidate
            changed_total += changed

        if changed_total == 0:
            return 0
        op_id = self._next_op_id()
        previous_labels_path = self._snapshot_labels(op_id)
        self._write_design_labels(labels_after)
        self.design.edit_history.append(
            EditOperation(
                op_id=op_id,
                kind='smooth_boundaries',
                payload={
                    'iterations': int(iterations),
                    'region_ids': sorted(selected_region_ids),
                    'changed_px': changed_total,
                    'previous_labels_path': previous_labels_path,
                    'previous_veneer_assignments': {
                        str(region_id): veneer_id
                        for region_id, veneer_id in sorted(self.design.veneer_assignments.items())
                    },
                    'previous_locked_region_ids': sorted(self.design.locked_region_ids),
                },
            )
        )
        self.save()
        return changed_total

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
        vector_paths = {
            (item['region_a'], item['region_b']): item['paths']
            for item in shared_boundary_paths(labels)
        }
        for boundary in boundaries:
            boundary['edge_length_physical'] = boundary['edge_px'] / max(avg_px_per_unit, 1e-9)
            paths = vector_paths.get((boundary['region_a'], boundary['region_b']), [])
            boundary['paths'] = paths
            boundary['physical_paths'] = [
                [
                    [x / max(px_per_unit_x, 1e-9), y / max(px_per_unit_y, 1e-9)]
                    for x, y in path
                ]
                for path in paths
            ]
            boundary['path_count'] = len(paths)
            simplified_paths = [
                self._simplify_boundary_path(path, tolerance_px=1.25)
                for path in paths
            ]
            vertex_count = sum(len(path) for path in paths)
            simplified_vertex_count = sum(len(path) for path in simplified_paths)
            boundary['vertex_count'] = vertex_count
            boundary['simplified_vertex_count'] = simplified_vertex_count
            boundary['simplified_vertex_reduction'] = max(
                0,
                vertex_count - simplified_vertex_count,
            )
            boundary['simplified_paths'] = simplified_paths
            boundary['simplified_physical_paths'] = [
                [
                    [x / max(px_per_unit_x, 1e-9), y / max(px_per_unit_y, 1e-9)]
                    for x, y in path
                ]
                for path in simplified_paths
            ]
        return {'boundary_count': len(boundaries), 'boundaries': boundaries}

    @staticmethod
    def _simplify_boundary_path(path: list[list[int]], tolerance_px: float) -> list[list[float]]:
        if len(path) <= 2:
            return [[float(x), float(y)] for x, y in path]
        simplified = approximate_polygon(np.asarray(path, dtype=float), tolerance_px)
        return [[float(x), float(y)] for x, y in simplified]

    def topology_graph(self) -> dict[str, Any]:
        """Return the current topology graph derived from raster boundaries."""

        if self.design is None:
            raise ValueError('create a design first')
        return boundary_graph(self.design_labels(), self.design.physical_size)

    def persist_topology_graph(self, kind: str = 'raster_topology') -> dict[str, Any]:
        """Persist the current topology graph as a versioned vector artifact."""

        if self.design is None:
            raise ValueError('create a design first')
        graph = self.topology_graph()
        coverage = self.coverage_summary()
        path = Path(VECTOR_DIR) / f'{kind}.json'
        payload = {
            'schema_version': 1,
            'kind': kind,
            'source': 'raster_labels',
            'physical_size': self.design.physical_size.to_dict(),
            'coverage': coverage,
            'graph': graph,
        }
        _atomic_json(self.workspace_dir / path, payload)
        self._record_vector_graph_artifact(
            kind=kind,
            path=path,
            graph=graph,
            coverage_valid=bool(coverage['valid']),
        )
        self.save()
        return payload

    def _record_vector_graph_artifact(
        self,
        kind: str,
        path: Path,
        graph: dict[str, Any],
        coverage_valid: bool,
    ) -> None:
        if self.design is None:
            raise ValueError('create a design first')
        self.design.vector_graphs = [
            artifact for artifact in self.design.vector_graphs if artifact.kind != kind
        ]
        self.design.vector_graphs.append(
            VectorGraphArtifact(
                kind=kind,
                path=str(path),
                topology_vertex_count=int(graph['vertex_count']),
                topology_edge_count=int(graph['edge_count']),
                coverage_valid=bool(coverage_valid),
                created_at=datetime.now(timezone.utc).isoformat(),
            )
        )

    def vector_graph_payload(self, kind: str = 'raster_topology') -> dict[str, Any]:
        """Load a persisted graph artifact, creating the raster graph if needed."""

        if self.design is None:
            raise ValueError('create a design first')
        for artifact in self.design.vector_graphs:
            if artifact.kind == kind:
                return json.loads(
                    (self.workspace_dir / artifact.path).read_text(encoding='utf-8')
                )
        if kind == 'raster_topology':
            return self.persist_topology_graph(kind=kind)
        raise ValueError(f'vector graph not found: {kind}')

    def active_vector_graph_payload(self) -> dict[str, Any] | None:
        """Return the promoted vector geometry, if the design has one."""

        if self.design is None or self.design.active_vector_graph_kind is None:
            return None
        return self.vector_graph_payload(self.design.active_vector_graph_kind)

    def _write_vector_graph_payload(
        self,
        payload: dict[str, Any],
        kind: str,
    ) -> None:
        if self.design is None:
            raise ValueError('create a design first')
        validation = validate_topology_graph(
            payload['graph'],
            self.design_labels(),
            self.design.physical_size,
        )
        if not validation['valid']:
            raise ValueError(f'vector graph is not a valid puzzle: {validation}')
        payload['graph_validation'] = validation
        path = Path(VECTOR_DIR) / f'{kind}.json'
        _atomic_json(self.workspace_dir / path, payload)
        self._record_vector_graph_artifact(
            kind=kind,
            path=path,
            graph=payload['graph'],
            coverage_valid=bool(validation['valid']),
        )

    def _snapshot_vector_artifact(
        self,
        kind: str,
        op_id: int,
    ) -> tuple[str | None, dict[str, Any] | None]:
        if self.design is None:
            raise ValueError('create a design first')
        for artifact in self.design.vector_graphs:
            if artifact.kind != kind:
                continue
            existing = self.workspace_dir / artifact.path
            if not existing.exists():
                return None, artifact.to_dict()
            snapshot_path = Path(HISTORY_DIR) / f'op-{op_id}-{kind}.json'
            (self.workspace_dir / snapshot_path).parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(existing, self.workspace_dir / snapshot_path)
            return str(snapshot_path), artifact.to_dict()
        return None, None

    def simplify_vector_graph(
        self,
        tolerance: float = 1.25,
        source_kind: str = 'raster_topology',
        target_kind: str = 'simplified_topology',
    ) -> dict[str, Any]:
        """Persist a simplified shared-boundary graph without changing raster labels."""

        if self.design is None:
            raise ValueError('create a design first')
        source_payload = self.vector_graph_payload(source_kind)
        labels = self.design_labels()
        graph = simplify_topology_graph(
            source_payload['graph'],
            tolerance=max(0.0, float(tolerance)),
            physical_size=self.design.physical_size,
            image_size=(labels.shape[1], labels.shape[0]),
        )
        coverage = self.coverage_summary()
        path = Path(VECTOR_DIR) / f'{target_kind}.json'
        op_id = self._next_op_id()
        previous_payload_path, previous_artifact = self._snapshot_vector_artifact(
            target_kind,
            op_id,
        )
        payload = {
            'schema_version': 1,
            'kind': target_kind,
            'source': 'topology_graph',
            'source_kind': source_kind,
            'tolerance': max(0.0, float(tolerance)),
            'physical_size': self.design.physical_size.to_dict(),
            'coverage': coverage,
            'graph': graph,
        }
        self._write_vector_graph_payload(payload, target_kind)
        self.design.edit_history.append(
            EditOperation(
                op_id=op_id,
                kind='simplify_vector_graph',
                payload={
                    'source_kind': source_kind,
                    'target_kind': target_kind,
                    'target_path': str(path),
                    'tolerance': max(0.0, float(tolerance)),
                    'previous_payload_path': (
                        str(previous_payload_path)
                        if previous_payload_path is not None
                        else None
                    ),
                    'previous_artifact': previous_artifact,
                },
            )
        )
        self.save()
        return payload

    def simplify_vector_graph_for_regions(
        self,
        region_ids: list[int] | set[int],
        tolerance: float = 1.25,
        source_kind: str | None = None,
        target_kind: str = 'edited_topology',
    ) -> dict[str, Any]:
        """Simplify graph edges touching selected regions as an undoable vector edit."""

        if self.design is None:
            raise ValueError('create a design first')
        selected_region_ids = {int(region_id) for region_id in region_ids}
        if not selected_region_ids:
            raise ValueError('choose at least one region')
        missing = sorted(selected_region_ids - self._current_region_ids())
        if missing:
            raise ValueError(f'unknown region ids: {missing}')
        source = source_kind or self.design.active_vector_graph_kind or 'raster_topology'
        source_payload = self.vector_graph_payload(source)
        edge_ids = {
            int(edge['edge_id'])
            for edge in source_payload['graph']['edges']
            if int(edge['region_a']) in selected_region_ids
            or int(edge['region_b']) in selected_region_ids
        }
        if not edge_ids:
            raise ValueError('selected regions have no vector edges')
        labels = self.design_labels()
        graph = simplify_topology_edges(
            source_payload['graph'],
            edge_ids=edge_ids,
            tolerance=max(0.0, float(tolerance)),
            physical_size=self.design.physical_size,
            image_size=(labels.shape[1], labels.shape[0]),
        )
        op_id = self._next_op_id()
        previous_payload_path, previous_artifact = self._snapshot_vector_artifact(
            target_kind,
            op_id,
        )
        previous_active_kind = self.design.active_vector_graph_kind
        payload = {
            'schema_version': 1,
            'kind': target_kind,
            'source': 'selected_topology_edges',
            'source_kind': source,
            'region_ids': sorted(selected_region_ids),
            'edge_ids': sorted(edge_ids),
            'tolerance': max(0.0, float(tolerance)),
            'physical_size': self.design.physical_size.to_dict(),
            'graph': graph,
        }
        self._write_vector_graph_payload(payload, target_kind)
        self.design.active_vector_graph_kind = target_kind
        self.design.edit_history.append(
            EditOperation(
                op_id=op_id,
                kind='edit_vector_graph',
                payload={
                    'operation': 'simplify_region_edges',
                    'source_kind': source,
                    'target_kind': target_kind,
                    'target_path': str(Path(VECTOR_DIR) / f'{target_kind}.json'),
                    'previous_payload_path': previous_payload_path,
                    'previous_artifact': previous_artifact,
                    'previous_active_vector_graph_kind': previous_active_kind,
                },
            )
        )
        self.save()
        return payload

    def move_vector_vertex(
        self,
        vertex_id: int,
        point: tuple[float, float],
        source_kind: str | None = None,
        target_kind: str = 'edited_topology',
    ) -> dict[str, Any]:
        """Move one graph vertex and promote the edited graph if it remains valid."""

        if self.design is None:
            raise ValueError('create a design first')
        source = source_kind or self.design.active_vector_graph_kind or 'raster_topology'
        source_payload = self.vector_graph_payload(source)
        labels = self.design_labels()
        graph = move_topology_vertex(
            source_payload['graph'],
            vertex_id=int(vertex_id),
            point=point,
            physical_size=self.design.physical_size,
            image_size=(labels.shape[1], labels.shape[0]),
        )
        op_id = self._next_op_id()
        previous_payload_path, previous_artifact = self._snapshot_vector_artifact(
            target_kind,
            op_id,
        )
        previous_active_kind = self.design.active_vector_graph_kind
        payload = {
            'schema_version': 1,
            'kind': target_kind,
            'source': 'move_topology_vertex',
            'source_kind': source,
            'vertex_id': int(vertex_id),
            'point': [float(point[0]), float(point[1])],
            'physical_size': self.design.physical_size.to_dict(),
            'graph': graph,
        }
        self._write_vector_graph_payload(payload, target_kind)
        self.design.active_vector_graph_kind = target_kind
        self.design.edit_history.append(
            EditOperation(
                op_id=op_id,
                kind='edit_vector_graph',
                payload={
                    'operation': 'move_vertex',
                    'source_kind': source,
                    'target_kind': target_kind,
                    'target_path': str(Path(VECTOR_DIR) / f'{target_kind}.json'),
                    'previous_payload_path': previous_payload_path,
                    'previous_artifact': previous_artifact,
                    'previous_active_vector_graph_kind': previous_active_kind,
                },
            )
        )
        self.save()
        return payload

    def promote_vector_graph(self, kind: str) -> None:
        """Make a persisted graph artifact the authoritative export geometry."""

        if self.design is None:
            raise ValueError('create a design first')
        payload = self.vector_graph_payload(kind)
        validation = validate_topology_graph(
            payload['graph'],
            self.design_labels(),
            self.design.physical_size,
        )
        if not validation['valid']:
            raise ValueError(f'vector graph is not a valid puzzle: {validation}')
        previous_active_kind = self.design.active_vector_graph_kind
        self.design.active_vector_graph_kind = kind
        self.design.edit_history.append(
            EditOperation(
                op_id=self._next_op_id(),
                kind='promote_vector_graph',
                payload={
                    'kind': kind,
                    'previous_active_vector_graph_kind': previous_active_kind,
                },
            )
        )
        self.save()

    def export_vector_graph_svg(
        self,
        output_path: str | Path,
        kind: str = 'simplified_topology',
    ) -> Path:
        """Reconstruct filled region polygons from a persisted vector graph."""

        if self.design is None:
            raise ValueError('create a design first')
        payload = self.vector_graph_payload(kind)
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        svg = graph_to_svg(
            payload['graph'],
            self.design_labels(),
            build_regions(
                self.source_array(),
                self.design_labels(),
                self.design,
                simplify_tolerance=0.0,
            ),
            self.design.physical_size,
        )
        path.write_text(svg, encoding='utf-8')
        return path

    def coverage_summary(self) -> dict[str, Any]:
        """Return Shapely coverage validation for exported physical region polygons."""

        if self.design is None:
            raise ValueError('create a design first')
        return coverage_summary(
            build_regions(
                self.source_array(),
                self.design_labels(),
                self.design,
                simplify_tolerance=0.0,
            ),
            self.design.physical_size,
            (self.source.working_width, self.source.working_height),
        )

    def export_svg(self, output_path: str | Path, simplify_tolerance: float = 1.0) -> Path:
        if self.design is None:
            raise ValueError('create a design first')
        validation = self.validation()
        if not validation['valid']:
            raise ValueError(f'invalid partition: {validation}')
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        active_graph = self.active_vector_graph_payload()
        if active_graph is not None:
            svg = graph_to_svg(
                active_graph['graph'],
                self.design_labels(),
                build_regions(
                    self.source_array(),
                    self.design_labels(),
                    self.design,
                    simplify_tolerance=0.0,
                ),
                self.design.physical_size,
            )
        else:
            svg = design_to_svg(
                build_regions(
                    self.source_array(),
                    self.design_labels(),
                    self.design,
                    simplify_tolerance=max(0.0, float(simplify_tolerance)),
                ),
                self.design.physical_size,
                (self.source.working_width, self.source.working_height),
            )
        path.write_text(svg, encoding='utf-8')
        return path

    def export_coverage_svg(self, output_path: str | Path, tolerance: float = 1.0) -> Path:
        """Export a Shapely coverage-simplified SVG that preserves shared edges."""

        if self.design is None:
            raise ValueError('create a design first')
        validation = self.validation()
        if not validation['valid']:
            raise ValueError(f'invalid partition: {validation}')
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        svg = coverage_simplified_svg(
            build_regions(
                self.source_array(),
                self.design_labels(),
                self.design,
                simplify_tolerance=0.0,
            ),
            self.design.physical_size,
            (self.source.working_width, self.source.working_height),
            tolerance=tolerance,
        )
        path.write_text(svg, encoding='utf-8')
        topology = self.topology_graph()
        coverage = self.coverage_summary()
        try:
            relative_path = str(path.relative_to(self.workspace_dir))
        except ValueError:
            relative_path = str(path)
        self.design.vector_exports = [
            artifact
            for artifact in self.design.vector_exports
            if not (artifact.kind == 'coverage_svg' and artifact.path == relative_path)
        ]
        self.design.vector_exports.append(
            ExportArtifact(
                kind='coverage_svg',
                path=relative_path,
                tolerance=float(tolerance),
                coverage_valid=bool(coverage['valid']),
                topology_vertex_count=int(topology['vertex_count']),
                topology_edge_count=int(topology['edge_count']),
                created_at=datetime.now(timezone.utc).isoformat(),
            )
        )
        self.save()
        return path

    def pack(self, output_dir: str | Path) -> dict[str, Any]:
        """Write a traceable physical packing manifest grouped by veneer."""

        if self.design is None:
            raise ValueError('create a design first')
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)
        regions = build_regions(self.source_array(), self.design_labels(), self.design)
        active_graph = self.active_vector_graph_payload()
        graph_pieces = None
        if active_graph is not None:
            graph_pieces_by_id = {
                int(piece['region_id']): piece
                for piece in graph_region_polygons(
                    active_graph['graph'],
                    self.design_labels(),
                    self.design.physical_size,
                )
            }
            graph_pieces = []
            for region in regions:
                piece = graph_pieces_by_id.get(region.region_id)
                if piece is None:
                    continue
                graph_pieces.append(
                    {
                        **region.to_dict(),
                        'area_physical': piece['area_physical'],
                        'bbox_physical': piece['bounds'],
                        'physical_contour': piece['physical_contour'],
                        'physical_svg_path': piece['physical_svg_path'],
                        'source_geometry': self.design.active_vector_graph_kind,
                    }
                )
        by_veneer: dict[str, list[dict[str, Any]]] = {}
        for region in graph_pieces or [region.to_dict() for region in regions]:
            by_veneer.setdefault(region['veneer_id'], []).append(region)
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
            px_per_unit_x, px_per_unit_y = self.design.physical_size.pixels_per_unit(
                (self.source.working_width, self.source.working_height)
            )
            bbox_area_total = 0.0
            piece_area_total = 0.0
            for piece in pieces:
                if 'bbox_physical' in piece:
                    x0, y0, x1, y1 = piece['bbox_physical']
                    width_units = max(1e-6, float(x1) - float(x0))
                    height_units = max(1e-6, float(y1) - float(y0))
                else:
                    x0, y0, x1, y1 = piece['bbox']
                    width_px = max(1, x1 - x0)
                    height_px = max(1, y1 - y0)
                    width_units = width_px / max(px_per_unit_x, 1e-9)
                    height_units = height_px / max(px_per_unit_y, 1e-9)
                bbox_area_total += width_units * height_units
                piece_area_total += float(piece['area_physical'])
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
            sheet_area = sheet_width * sheet_height
            area_sheet_count = math.ceil(bbox_area_total / sheet_area) if sheet_area else 0
            recommended_sheet_count = max(sheet_count_used, area_sheet_count, 1 if pieces else 0)
            stock_shortfall_count = max(0, recommended_sheet_count - veneer.sheet_count)
            material_area_available = sheet_area * veneer.sheet_count
            material_area_used = sheet_area * sheet_count_used
            material_utilization = (
                bbox_area_total / material_area_used if material_area_used else 0.0
            )
            packed_pieces = [
                {
                    **piece,
                    'physical_contour': piece.get('physical_contour')
                    or [
                        [
                            point[0] / max(px_per_unit_x, 1e-9),
                            point[1] / max(px_per_unit_y, 1e-9),
                        ]
                        for point in piece['contour']
                    ],
                    'physical_svg_path': piece.get('physical_svg_path')
                    or svg_path(
                        tuple((float(point[0]), float(point[1])) for point in piece['contour']),
                        px_per_unit_x,
                        px_per_unit_y,
                    ),
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
                    'recommended_sheet_count': recommended_sheet_count,
                    'stock_shortfall_count': stock_shortfall_count,
                    'sheet_area': sheet_area,
                    'material_area_available': material_area_available,
                    'material_area_used': material_area_used,
                    'total_piece_area': piece_area_total,
                    'total_bounding_box_area': bbox_area_total,
                    'material_utilization': material_utilization,
                    'over_stock_capacity': placed_count < len(pieces),
                    'pieces': packed_pieces,
                }
            )
        manifest = {
            'packing_backend': 'rectpack-bounding-box',
            'source_geometry': (
                self.design.active_vector_graph_kind
                if self.design and self.design.active_vector_graph_kind
                else 'raster_labels'
            ),
            'sheets': sheets,
        }
        (output_path / 'pack.json').write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + '\n',
            encoding='utf-8',
        )
        self.export_cleanup_report(output_path / 'cleanup-report.json')
        self.export_svg(output_path / 'design.svg')
        self.export_coverage_svg(output_path / 'design-coverage.svg')
        return manifest

    def export_cleanup_report(self, output_path: str | Path) -> Path:
        """Write the cut-readiness report as JSON."""

        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(self.cleanup_report(), indent=2, sort_keys=True) + '\n',
            encoding='utf-8',
        )
        return path

    def cleanup_report(self) -> dict[str, Any]:
        """Return a single cut-readiness report for the current design."""

        if self.design is None:
            raise ValueError('create a design first')
        regions = self.regions()
        boundaries = self.boundary_summary()['boundaries']
        merge_suggestions = self.merge_suggestions()
        warning_counts: dict[str, int] = {}
        for region in regions:
            for warning in region['warnings']:
                warning_counts[warning] = warning_counts.get(warning, 0) + 1
        jagged_boundaries = [
            boundary
            for boundary in boundaries
            if boundary.get('simplified_vertex_reduction', 0) > 0
        ]
        jagged_boundaries.sort(
            key=lambda boundary: (
                int(boundary.get('simplified_vertex_reduction', 0)),
                float(boundary.get('edge_length_physical', 0.0)),
            ),
            reverse=True,
        )
        veneer_counts: dict[str, int] = {}
        for region in regions:
            veneer_counts[region['veneer_id']] = veneer_counts.get(region['veneer_id'], 0) + 1
        topology = self.topology_graph()
        score = 100
        score -= min(30, len(merge_suggestions) * 5)
        score -= min(30, len(jagged_boundaries) * 2)
        score -= min(20, len([region for region in regions if region['warnings']]) * 3)
        if not self.validation()['valid']:
            score = 0
        readiness = 'ready' if score >= 85 else 'needs-review' if score >= 60 else 'rough'
        return {
            'readiness_score': max(0, score),
            'readiness': readiness,
            'region_count': len(regions),
            'locked_region_count': sum(1 for region in regions if region['locked']),
            'warning_counts': warning_counts,
            'small_or_thin_region_ids': [
                region['region_id'] for region in regions if region['warnings']
            ],
            'merge_suggestion_count': len(merge_suggestions),
            'top_merge_suggestions': merge_suggestions[:10],
            'boundary_count': len(boundaries),
            'jagged_boundary_count': len(jagged_boundaries),
            'top_jagged_boundaries': [
                {
                    'region_a': boundary['region_a'],
                    'region_b': boundary['region_b'],
                    'edge_length_physical': boundary['edge_length_physical'],
                    'vertex_count': boundary['vertex_count'],
                    'simplified_vertex_count': boundary['simplified_vertex_count'],
                    'simplified_vertex_reduction': boundary['simplified_vertex_reduction'],
                }
                for boundary in jagged_boundaries[:10]
            ],
            'veneer_region_counts': dict(sorted(veneer_counts.items())),
            'subject_mask': self.subject_mask_summary(),
            'vector_graphs': [
                artifact.to_dict() for artifact in self.design.vector_graphs
            ],
            'vector_exports': [
                artifact.to_dict() for artifact in self.design.vector_exports
            ],
            'topology': {
                'vertex_count': topology['vertex_count'],
                'edge_count': topology['edge_count'],
            },
            'coverage': self.coverage_summary(),
            'valid_partition': self.validation(),
        }

    def summary(self) -> dict[str, Any]:
        return {
            'workspace_dir': str(self.workspace_dir),
            'source': self.source.to_dict(),
            'candidates': [candidate.to_dict() for candidate in self.candidates],
            'design': self.design.to_dict() if self.design else None,
            'subject_mask': self.subject_mask_summary(),
            'regions': self.regions(),
            'merge_suggestions': self.merge_suggestions(),
            'validation': self.validation(),
            'boundaries': self.boundary_summary(),
        }

    def subject_mask_summary(self) -> dict[str, int]:
        mask = self.subject_mask()
        return {
            'subject_px': int(np.count_nonzero(mask == 1)),
            'background_px': int(np.count_nonzero(mask == 2)),
            'unknown_px': int(np.count_nonzero(mask == 0)),
        }

    def copy_to(self, output_dir: str | Path) -> None:
        """Copy the whole workspace for debugging or fixtures."""

        output_path = Path(output_dir)
        if output_path.exists():
            shutil.rmtree(output_path)
        shutil.copytree(self.workspace_dir, output_path)
