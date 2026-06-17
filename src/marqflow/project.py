"""Persistent marquetry project state."""

from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
from skimage.segmentation import slic

from .config import SegmentationConfig, SuperpixelConfig
from .image import downscale_image, load_rgb_image, save_rgb_image
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
        'superpixels': asdict(config.superpixels),
    }


def _config_from_dict(data: dict[str, Any]) -> SegmentationConfig:
    superpixels = data.get('superpixels', {})
    return SegmentationConfig(
        downscale_factor=int(data.get('downscale_factor', 4)),
        superpixels=SuperpixelConfig(
            target_segments=int(superpixels.get('target_segments', 20)),
            compactness=float(superpixels.get('compactness', 20.0)),
            sigma=float(superpixels.get('sigma', 1.0)),
        ),
    )


def _json_load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding='utf-8'))


def _json_dump(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding='utf-8')


@dataclass(slots=True)
class MarqflowProject:
    """Editable region state and its persistence layer."""

    project_dir: Path
    source_image_path: Path
    config: SegmentationConfig
    working_image: np.ndarray
    labels: np.ndarray
    edits: list[EditRecord] = field(default_factory=list)

    @property
    def region_map(self) -> RegionMap:
        regions = build_regions(self.working_image, self.labels)
        return RegionMap(
            image_rgb=self.working_image,
            labels=self.labels,
            regions=regions,
            source_path=self.source_image_path,
        )

    @property
    def preview(self) -> np.ndarray:
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
        working_image = np.asarray(load_rgb_image(project_path / manifest['working_image']))
        labels = np.load(project_path / manifest['labels'])
        edits = [EditRecord(**record) for record in manifest.get('edits', [])]
        return cls(
            project_dir=project_path,
            source_image_path=Path(manifest['source_image']),
            config=config,
            working_image=working_image,
            labels=labels,
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
                'source_image': str(self.source_image_path),
                'working_image': WORKING_IMAGE,
                'labels': LABELS_PATH,
                'config': _config_to_dict(self.config),
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
        """Refine selected regions by running local superpixel segmentation."""

        compactness = (
            compactness if compactness is not None else self.config.superpixels.compactness
        )
        sigma = sigma if sigma is not None else self.config.superpixels.sigma
        selected_ids = sorted({int(region_id) for region_id in region_ids})
        next_label = int(self.labels.max()) + 1
        changed = 0

        for region_id in selected_ids:
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

            sublabels = slic(
                crop_image,
                n_segments=max(2, int(target_segments)),
                compactness=compactness,
                sigma=sigma,
                start_label=1,
                convert2lab=True,
                mask=crop_mask,
            )

            unique = [int(value) for value in np.unique(sublabels[crop_mask]) if int(value) > 0]
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
        """Merge connected selected regions into coarser pieces."""

        selected = sorted({int(region_id) for region_id in region_ids})
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
