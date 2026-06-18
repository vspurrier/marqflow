"""Persistent marquetry project state.

This module stores the editable, single-candidate side of the workflow:
the working image, region labels, edit history, and persistence helpers
for split/merge/lock operations.
"""

from __future__ import annotations

import json
import os
import tempfile
from collections.abc import Iterable
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
from skimage.segmentation import felzenszwalb, slic

from .config import SegmentationConfig, SuperpixelConfig
from .image import downscale_image, load_rgb_image, resize_to_max_edge, save_rgb_image
from .regions import (
    RegionMap,
    build_regions,
    labels_to_palette_image,
    selected_region_components,
)
from .svg import region_map_to_svg

PROJECT_MANIFEST = 'project.json'
WORKING_IMAGE = 'working.png'
LABELS_PATH = 'labels.npy'


@dataclass(slots=True)
class EditRecord:
    """A human-readable log entry for a project mutation."""

    op: str
    data: dict[str, Any] = field(default_factory=dict)


def _config_to_dict(config: SegmentationConfig) -> dict[str, Any]:
    return {
        'downscale_factor': config.downscale_factor,
        'max_working_edge': config.max_working_edge,
        'superpixels': asdict(config.superpixels),
    }


def _config_from_dict(data: dict[str, Any]) -> SegmentationConfig:
    superpixels = data.get('superpixels', {})
    return SegmentationConfig(
        downscale_factor=int(data.get('downscale_factor', 1)),
        max_working_edge=int(data.get('max_working_edge', 384)),
        superpixels=SuperpixelConfig(
            target_segments=int(superpixels.get('target_segments', 32)),
            compactness=float(superpixels.get('compactness', 20.0)),
            sigma=float(superpixels.get('sigma', 1.0)),
        ),
    )


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


@dataclass(slots=True)
class MarqflowProject:
    """Editable region state and its persistence layer."""

    project_dir: Path
    source_image_path: Path
    config: SegmentationConfig
    working_image: np.ndarray
    labels: np.ndarray
    locked_region_ids: set[int] = field(default_factory=set)
    edits: list[EditRecord] = field(default_factory=list)

    @property
    def region_map(self) -> RegionMap:
        """Build a fresh region map view from the current labels."""

        regions = build_regions(self.working_image, self.labels)
        return RegionMap(
            image_rgb=self.working_image,
            labels=self.labels,
            regions=regions,
            source_path=self.source_image_path,
        )

    @property
    def preview(self) -> np.ndarray:
        """Return the flat-color preview for the current labels."""

        return labels_to_palette_image(self.working_image, self.labels)

    @classmethod
    def create(
        cls,
        source_image_path: str | Path,
        project_dir: str | Path,
        config: SegmentationConfig,
    ) -> MarqflowProject:
        """Create a new project from a source image."""

        source_path = Path(source_image_path)
        project_path = Path(project_dir)
        config.validate()

        working_image = downscale_image(load_rgb_image(source_path), config.downscale_factor)
        working_image = resize_to_max_edge(working_image, config.max_working_edge)
        labels = slic(
            working_image,
            n_segments=config.superpixels.target_segments,
            compactness=config.superpixels.compactness,
            sigma=config.superpixels.sigma,
            start_label=1,
            convert2lab=True,
        )
        project = cls(
            project_dir=project_path,
            source_image_path=source_path,
            config=config,
            working_image=working_image,
            labels=labels,
            edits=[EditRecord(op='create')],
        )
        project.save()
        return project

    @classmethod
    def load(cls, project_dir: str | Path) -> MarqflowProject:
        """Load an existing project from disk."""

        project_path = Path(project_dir)
        manifest = _json_load(project_path / PROJECT_MANIFEST)
        config = _config_from_dict(manifest['config'])
        working_image = np.asarray(
            load_rgb_image(_resolve_path(project_path, manifest['working_image']))
        )
        labels = np.load(_resolve_path(project_path, manifest['labels']))
        edits = [EditRecord(**record) for record in manifest.get('edits', [])]
        return cls(
            project_dir=project_path,
            source_image_path=_resolve_path(project_path, manifest['source_image']),
            config=config,
            working_image=working_image,
            labels=labels,
            locked_region_ids={int(value) for value in manifest.get('locked_region_ids', [])},
            edits=edits,
        )

    def save(self) -> None:
        """Persist the project manifest and arrays."""

        self.project_dir.mkdir(parents=True, exist_ok=True)
        save_rgb_image(self.project_dir / WORKING_IMAGE, self.working_image)
        np.save(self.project_dir / LABELS_PATH, self.labels)
        _json_dump(
            self.project_dir / PROJECT_MANIFEST,
            {
                'version': 1,
                'source_image': _serialise_path(self.project_dir, self.source_image_path),
                'working_image': WORKING_IMAGE,
                'labels': LABELS_PATH,
                'config': _config_to_dict(self.config),
                'locked_region_ids': sorted(self.locked_region_ids),
                'edits': [asdict(edit) for edit in self.edits],
            },
        )

    def export(self, output_dir: str | Path) -> tuple[Path, Path]:
        """Write preview and SVG artifacts for the current state."""

        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)
        preview_path = output_path / 'preview.png'
        svg_path = output_path / 'regions.svg'
        save_rgb_image(preview_path, self.preview)
        svg_path.write_text(region_map_to_svg(self.region_map), encoding='utf-8')
        return preview_path, svg_path

    def split_regions(
        self,
        region_ids: Iterable[int],
        target_segments: int,
        compactness: float | None = None,
        sigma: float | None = None,
    ) -> int:
        """Refine selected regions by running local superpixel segmentation.

        Each selected region is segmented inside its own bounding box. The
        fallback from `felzenszwalb` to `slic` keeps the operation useful when
        the local crop is small or low-contrast.
        """

        compactness = (
            compactness if compactness is not None else self.config.superpixels.compactness
        )
        sigma = sigma if sigma is not None else self.config.superpixels.sigma
        selected_ids = sorted({int(region_id) for region_id in region_ids})
        next_label = int(self.labels.max()) + 1
        changed = 0

        for region_id in selected_ids:
            if region_id in self.locked_region_ids:
                continue
            mask = self.labels == region_id
            if not np.any(mask):
                continue

            ys, xs = np.nonzero(mask)
            y0, y1 = int(ys.min()), int(ys.max()) + 1
            x0, x1 = int(xs.min()), int(xs.max()) + 1

            crop_image = self.working_image[y0:y1, x0:x1]
            crop_mask = mask[y0:y1, x0:x1]
            if int(crop_mask.sum()) < 2:
                continue

            masked_pixels = int(crop_mask.sum())
            next_target = max(2, int(target_segments))
            base_scale = max(40, masked_pixels // next_target)
            scale = max(20, int(base_scale * (float(compactness) / 20.0)))
            sublabels = felzenszwalb(
                crop_image,
                scale=scale,
                sigma=sigma,
                min_size=max(2, masked_pixels // max(4, next_target * 2)),
            )

            unique = [int(value) for value in np.unique(sublabels[crop_mask]) if int(value) > 0]
            if len(unique) <= 1:
                sublabels = slic(
                    crop_image,
                    n_segments=max(2, int(target_segments)),
                    compactness=float(compactness),
                    sigma=sigma,
                    start_label=1,
                    convert2lab=True,
                    mask=crop_mask,
                )
                unique = [
                    int(value) for value in np.unique(sublabels[crop_mask]) if int(value) > 0
                ]

            if len(unique) <= 1:
                continue

            self.labels[mask] = 0
            crop_labels = self.labels[y0:y1, x0:x1]
            for sublabel in unique:
                submask = sublabels == sublabel
                if not np.any(submask):
                    continue
                crop_labels[submask] = next_label
                next_label += 1
            changed += 1

        if changed:
            self.edits.append(
                EditRecord(
                    op='split',
                    data={
                        'region_ids': selected_ids,
                        'target_segments': int(target_segments),
                        'compactness': float(compactness),
                        'sigma': float(sigma),
                    },
                )
            )
            self.save()
        return changed

    def merge_regions(self, region_ids: Iterable[int]) -> int:
        """Merge connected selected regions into coarser pieces.

        Only connected components are merged together so a selection spanning
        multiple disconnected islands does not collapse into one label.
        """

        selected = sorted(
            {
                int(region_id)
                for region_id in region_ids
                if int(region_id) not in self.locked_region_ids
            }
        )
        if len(selected) < 2:
            return 0

        components = selected_region_components(self.labels, selected)
        merged_groups = 0
        for component in components:
            if len(component) < 2:
                continue
            target = min(component)
            mask = np.isin(self.labels, list(component))
            self.labels[mask] = target
            merged_groups += 1

        if merged_groups:
            self.edits.append(
                EditRecord(op='merge', data={'region_ids': selected, 'groups': merged_groups})
            )
            self.save()
        return merged_groups

    def lock_regions(self, region_ids: Iterable[int]) -> int:
        """Protect selected regions from later split/merge edits."""

        selected = {int(region_id) for region_id in region_ids}
        before = len(self.locked_region_ids)
        self.locked_region_ids.update(selected)
        changed = len(self.locked_region_ids) - before
        if changed:
            self.edits.append(EditRecord(op='lock', data={'region_ids': sorted(selected)}))
            self.save()
        return changed

    def unlock_regions(self, region_ids: Iterable[int]) -> int:
        """Remove protection from selected regions."""

        selected = {int(region_id) for region_id in region_ids}
        before = len(self.locked_region_ids)
        self.locked_region_ids.difference_update(selected)
        changed = before - len(self.locked_region_ids)
        if changed:
            self.edits.append(EditRecord(op='unlock', data={'region_ids': sorted(selected)}))
            self.save()
        return changed
