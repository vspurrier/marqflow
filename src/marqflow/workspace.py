"""Grid-search workspace for candidate marquetry region maps."""

from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import asdict, dataclass, field
from pathlib import Path
from time import time_ns
from typing import Any

import numpy as np
from PIL import Image

from .config import SegmentationConfig, SuperpixelConfig
from .project import MarqflowProject

WORKSPACE_MANIFEST = 'workspace.json'
SOURCE_IMAGE = 'source-image'
CANDIDATES_DIR = 'candidates'

DEFAULT_SEGMENT_LEVELS = (192, 256, 320)
DEFAULT_SMOOTHNESS_LEVELS = (16.0, 12.0, 8.0)
DEFAULT_MAX_WORKING_EDGE = 1536
DEFAULT_DOWNSCALE_FACTOR = 1


def _json_load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding='utf-8'))


def _json_dump(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding='utf-8')


def _slugify(value: str) -> str:
    slug = ''.join(char.lower() if char.isalnum() else '-' for char in value.strip())
    slug = '-'.join(part for part in slug.split('-') if part)
    return slug or 'candidate'


def _copy_source_image(source_image_path: Path, workspace_dir: Path) -> Path:
    source_dir = workspace_dir / SOURCE_IMAGE
    source_dir.mkdir(parents=True, exist_ok=True)
    target = source_dir / source_image_path.name
    target.write_bytes(source_image_path.read_bytes())
    return target


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
    region_count: int
    generation: int = 0
    kept: bool = False
    selected_region_ids: set[int] = field(default_factory=set)

    def to_dict(self) -> dict[str, Any]:
        return {
            'candidate_id': self.candidate_id,
            'label': self.label,
            'preset': asdict(self.preset),
            'project_dir': str(self.project_dir),
            'preview_path': str(self.preview_path),
            'svg_path': str(self.svg_path),
            'region_count': self.region_count,
            'generation': self.generation,
            'kept': self.kept,
            'selected_region_ids': sorted(self.selected_region_ids),
        }


@dataclass(slots=True)
class GridWorkspace:
    """A gallery of candidate region maps and their composition state."""

    workspace_dir: Path
    source_image_path: Path
    candidates: list[GridCandidate] = field(default_factory=list)
    active_candidate_id: str | None = None

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
        """Create a workspace and populate its initial grid."""

        workspace_path = Path(workspace_dir)
        workspace_path.mkdir(parents=True, exist_ok=True)
        source_path = Path(source_image_path)
        copied_source = _copy_source_image(source_path, workspace_path)
        workspace = cls(
            workspace_dir=workspace_path,
            source_image_path=copied_source,
        )
        workspace.generate_initial_grid(
            segment_levels=segment_levels,
            smoothness_levels=smoothness_levels,
            max_working_edge=max_working_edge,
            downscale_factor=downscale_factor,
        )
        workspace.save()
        return workspace

    @classmethod
    def load(cls, workspace_dir: str | Path) -> GridWorkspace:
        """Load an existing workspace from disk."""

        workspace_path = Path(workspace_dir)
        manifest = _json_load(workspace_path / WORKSPACE_MANIFEST)
        workspace = cls(
            workspace_dir=workspace_path,
            source_image_path=Path(manifest['source_image_path']),
            active_candidate_id=manifest.get('active_candidate_id'),
        )
        for candidate_data in manifest.get('candidates', []):
            preset_data = candidate_data['preset']
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
                    project_dir=Path(candidate_data['project_dir']),
                    preview_path=Path(candidate_data['preview_path']),
                    svg_path=Path(candidate_data['svg_path']),
                    region_count=int(candidate_data['region_count']),
                    generation=int(candidate_data.get('generation', 0)),
                    kept=bool(candidate_data.get('kept', False)),
                    selected_region_ids={
                        int(region_id)
                        for region_id in candidate_data.get('selected_region_ids', [])
                    },
                )
            )
        return workspace

    def save(self) -> None:
        """Persist the workspace manifest."""

        self.workspace_dir.mkdir(parents=True, exist_ok=True)
        _json_dump(
            self.workspace_dir / WORKSPACE_MANIFEST,
            {
                'version': 1,
                'source_image_path': str(self.source_image_path),
                'active_candidate_id': self.active_candidate_id,
                'candidates': [candidate.to_dict() for candidate in self.candidates],
            },
        )

    @property
    def active_candidate(self) -> GridCandidate | None:
        if self.active_candidate_id is None:
            return self.candidates[0] if self.candidates else None
        for candidate in self.candidates:
            if candidate.candidate_id == self.active_candidate_id:
                return candidate
        return self.candidates[0] if self.candidates else None

    @property
    def kept_candidates(self) -> list[GridCandidate]:
        return [candidate for candidate in self.candidates if candidate.kept]

    def _candidate_id(self, label: str) -> str:
        return f'{_slugify(label)}-{time_ns()}'

    def _generate_candidate(
        self,
        label: str,
        preset: GridPreset,
        generation: int = 0,
    ) -> GridCandidate:
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
        return GridCandidate(
            candidate_id=candidate_id,
            label=label,
            preset=preset,
            project_dir=candidate_dir,
            preview_path=preview_path,
            svg_path=svg_path,
            region_count=len(project.region_map.regions),
            generation=generation,
        )

    def generate_initial_grid(
        self,
        segment_levels: tuple[int, ...] = DEFAULT_SEGMENT_LEVELS,
        smoothness_levels: tuple[float, ...] = DEFAULT_SMOOTHNESS_LEVELS,
        max_working_edge: int = DEFAULT_MAX_WORKING_EDGE,
        downscale_factor: int = DEFAULT_DOWNSCALE_FACTOR,
    ) -> list[GridCandidate]:
        """Generate the first grid of candidate segmentations."""

        candidates: list[GridCandidate] = []
        for row, target_segments in enumerate(segment_levels):
            for col, compactness in enumerate(smoothness_levels):
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
                    )
                )

        self.candidates = candidates
        self.active_candidate_id = candidates[0].candidate_id if candidates else None
        self.save()
        return candidates

    def refine_candidate(self, candidate_id: str) -> list[GridCandidate]:
        """Generate a tighter 3x3 search grid around an existing candidate."""

        base = self.candidate_by_id(candidate_id)
        if base is None:
            return []

        segment_multipliers = (0.8, 1.0, 1.2)
        smoothness_multipliers = (0.85, 1.0, 1.15)
        candidates: list[GridCandidate] = []
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
                    )
                )

        self.candidates.extend(candidates)
        self.active_candidate_id = candidates[4].candidate_id if len(candidates) >= 5 else None
        self.save()
        return candidates

    def candidate_by_id(self, candidate_id: str) -> GridCandidate | None:
        for candidate in self.candidates:
            if candidate.candidate_id == candidate_id:
                return candidate
        return None

    def set_active_candidate(self, candidate_id: str) -> None:
        if self.candidate_by_id(candidate_id) is not None:
            self.active_candidate_id = candidate_id
            self.save()

    def toggle_keep_candidate(self, candidate_id: str) -> bool:
        candidate = self.candidate_by_id(candidate_id)
        if candidate is None:
            return False
        candidate.kept = not candidate.kept
        if candidate.kept:
            self.active_candidate_id = candidate_id
        self.save()
        return candidate.kept

    def set_candidate_selection(
        self,
        candidate_id: str,
        region_ids: Iterable[int],
        additive: bool = False,
    ) -> int:
        candidate = self.candidate_by_id(candidate_id)
        if candidate is None:
            return 0

        selected = {int(region_id) for region_id in region_ids}
        if additive:
            candidate.selected_region_ids.update(selected)
        else:
            candidate.selected_region_ids = selected
        self.active_candidate_id = candidate_id
        self.save()
        return len(candidate.selected_region_ids)

    def clear_candidate_selection(self, candidate_id: str) -> bool:
        candidate = self.candidate_by_id(candidate_id)
        if candidate is None:
            return False
        candidate.selected_region_ids.clear()
        self.save()
        return True

    def summary(self) -> dict[str, Any]:
        """Return a JSON-friendly summary for the browser UI."""

        active = self.active_candidate
        return {
            'workspace_dir': str(self.workspace_dir),
            'source_image_path': str(self.source_image_path),
            'candidate_count': len(self.candidates),
            'kept_count': len(self.kept_candidates),
            'active_candidate_id': self.active_candidate_id,
            'active_candidate': active.to_dict() if active is not None else None,
            'candidates': [candidate.to_dict() for candidate in self.candidates],
        }

    def candidate_summary(self, candidate_id: str) -> dict[str, Any] | None:
        candidate = self.candidate_by_id(candidate_id)
        if candidate is None:
            return None

        project = MarqflowProject.load(candidate.project_dir)
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

    def _composite_canvas(self) -> tuple[np.ndarray, tuple[int, int]]:
        if not self.candidates:
            raise ValueError('no candidates in workspace')
        project = MarqflowProject.load(self.candidates[0].project_dir)
        size = project.preview.shape[:2]
        canvas = np.full((size[0], size[1], 3), 235, dtype=np.uint8)
        return canvas, size[::-1]

    def export_composite(self, output_dir: str | Path) -> tuple[Path, Path]:
        """Export a composite preview and SVG from kept selections."""

        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)
        composite_png = output_path / 'composite.png'
        composite_svg = output_path / 'composite.svg'

        if not self.kept_candidates:
            raise ValueError('select at least one candidate before exporting')

        base_project = MarqflowProject.load(self.kept_candidates[0].project_dir)
        canvas = np.full_like(base_project.preview, 235, dtype=np.uint8)
        svg_paths: list[str] = []

        for candidate in self.kept_candidates:
            project = MarqflowProject.load(candidate.project_dir)
            region_lookup = {region.region_id: region for region in project.region_map.regions}
            for region_id in sorted(candidate.selected_region_ids):
                region = region_lookup.get(region_id)
                if region is None or len(region.contour) < 3:
                    continue
                mask = project.labels == region_id
                canvas[mask] = project.preview[mask]
                points = region.contour
                commands = [f'M{points[0][0]:.2f},{points[0][1]:.2f}']
                for x, y in points[1:]:
                    commands.append(f'L{x:.2f},{y:.2f}')
                commands.append('Z')
                svg_paths.append(
                    f'<path d="{" ".join(commands)}" fill="{region.fill}" '
                    f'data-candidate="{candidate.candidate_id}" '
                    f'data-region-id="{region.region_id}" />'
                )

        Image.fromarray(canvas.astype(np.uint8), mode='RGB').save(composite_png)

        width, height = base_project.region_map.size
        svg = (
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
            f'viewBox="0 0 {width} {height}">' + ''.join(svg_paths) + '</svg>'
        )
        composite_svg.write_text(svg, encoding='utf-8')
        return composite_png, composite_svg
