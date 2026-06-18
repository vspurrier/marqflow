"""Grid-search workspace for candidate marquetry region maps.

The workspace is the gallery layer on top of the single-project pipeline.
It owns a grid of segmentation presets, tracks which candidates are kept,
and stores the region selections that feed the compose/merge stages.
"""

from __future__ import annotations

import json
import os
import tempfile
from collections.abc import Iterable
from dataclasses import asdict, dataclass, field
from pathlib import Path
from time import time_ns
from typing import Any

import numpy as np
from PIL import Image
from skimage.measure import approximate_polygon, find_contours

from .config import SegmentationConfig, SuperpixelConfig
from .project import MarqflowProject

WORKSPACE_MANIFEST = 'workspace.json'
SOURCE_IMAGE = 'source-image'
CANDIDATES_DIR = 'candidates'

DEFAULT_SEGMENT_LEVELS = (56, 88, 132, 192)
DEFAULT_SMOOTHNESS_LEVELS = (4.0, 9.0, 18.0, 30.0)
DEFAULT_MAX_WORKING_EDGE = 1536
DEFAULT_DOWNSCALE_FACTOR = 1


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


def _write_thumbnail(source_path: Path, thumb_path: Path, max_edge: int = 240) -> Path:
    with Image.open(source_path) as image:
        image = image.convert('RGB')
        image.thumbnail((max_edge, max_edge), Image.Resampling.LANCZOS)
        thumb_path.parent.mkdir(parents=True, exist_ok=True)
        image.save(thumb_path, format='PNG')
    return thumb_path


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
    generation: int = 0
    kept: bool = False
    selected_region_ids: set[int] = field(default_factory=set)

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
            'generation': self.generation,
            'kept': self.kept,
            'selected_region_ids': sorted(self.selected_region_ids),
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
    candidates: list[GridCandidate] = field(default_factory=list)
    active_candidate_id: str | None = None
    composite_base_candidate_id: str | None = None

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
            source_image_path=_resolve_path(workspace_path, manifest['source_image_path']),
            active_candidate_id=manifest.get('active_candidate_id'),
            composite_base_candidate_id=manifest.get('composite_base_candidate_id'),
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
                    project_dir=_resolve_path(workspace_path, candidate_data['project_dir']),
                    preview_path=_resolve_path(workspace_path, candidate_data['preview_path']),
                    svg_path=_resolve_path(workspace_path, candidate_data['svg_path']),
                    thumb_path=_resolve_path(
                        workspace_path,
                        candidate_data.get('thumb_path', candidate_data['preview_path']),
                    ),
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
                'source_image_path': _serialise_path(self.workspace_dir, self.source_image_path),
                'active_candidate_id': self.active_candidate_id,
                'composite_base_candidate_id': self.composite_base_candidate_id,
                'candidates': [
                    candidate.to_manifest_dict(self.workspace_dir) for candidate in self.candidates
                ],
            },
        )

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

    def _generate_candidate(
        self,
        label: str,
        preset: GridPreset,
        generation: int = 0,
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
            generation=generation,
        )

    def generate_initial_grid(
        self,
        segment_levels: tuple[int, ...] = DEFAULT_SEGMENT_LEVELS,
        smoothness_levels: tuple[float, ...] = DEFAULT_SMOOTHNESS_LEVELS,
        max_working_edge: int = DEFAULT_MAX_WORKING_EDGE,
        downscale_factor: int = DEFAULT_DOWNSCALE_FACTOR,
    ) -> list[GridCandidate]:
        """Generate the first grid of candidate segmentations.

        Rows step through region counts and columns step through smoothness,
        which gives the browser a coarse search surface to start from.
        """

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
        self.composite_base_candidate_id = self.active_candidate_id
        self.save()
        return candidates

    def refine_candidate(self, candidate_id: str) -> list[GridCandidate]:
        """Generate a tighter 3x3 search grid around an existing candidate."""

        base = self.candidate_by_id(candidate_id)
        if base is None:
            return []

        segment_multipliers = (0.65, 1.0, 1.45)
        smoothness_multipliers = (0.6, 1.0, 1.75)
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
        self.active_candidate_id = candidate_id
        self.save()
        return len(candidate.selected_region_ids)

    def paint_all_candidate(self, candidate_id: str) -> int:
        """Select every region in a candidate."""

        candidate = self.candidate_by_id(candidate_id)
        if candidate is None:
            return 0

        project = MarqflowProject.load(candidate.project_dir)
        candidate.selected_region_ids = {
            int(region.region_id) for region in project.region_map.regions
        }
        self.active_candidate_id = candidate_id
        self.save()
        return len(candidate.selected_region_ids)

    def clear_candidate_selection(self, candidate_id: str) -> bool:
        """Clear all painted regions from a candidate."""

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
            'composite_base_candidate_id': self.composite_base_candidate_id,
            'active_candidate': active.to_dict() if active is not None else None,
            'candidates': [candidate.to_dict() for candidate in self.candidates],
        }

    def candidate_summary(self, candidate_id: str) -> dict[str, Any] | None:
        """Return full region metadata for one candidate."""

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

    def _composite_base_candidate(self) -> GridCandidate | None:
        """Pick the base candidate used for the composite preview canvas."""

        if self.composite_base_candidate_id is None:
            self._refresh_composite_base_candidate()
        if self.composite_base_candidate_id is None:
            return None
        return self.candidate_by_id(self.composite_base_candidate_id)

    def _composite_region_records(self) -> list[dict[str, Any]]:
        """Collect the regions that should appear in the composite model.

        The first kept candidate acts as the base layer and contributes every
        one of its regions. Additional kept candidates contribute only the
        regions the user explicitly selected from them.
        """

        records: list[dict[str, Any]] = []
        base_candidate = self._composite_base_candidate()
        if base_candidate is None:
            return records

        base_project = MarqflowProject.load(base_candidate.project_dir)
        for region in sorted(base_project.region_map.regions, key=lambda item: item.region_id):
            if len(region.contour) < 3:
                continue
            records.append(
                {
                    'candidate': base_candidate,
                    'project': base_project,
                    'region': region,
                    'mask': base_project.labels == region.region_id,
                }
            )

        for candidate in self.kept_candidates[1:]:
            project = MarqflowProject.load(candidate.project_dir)
            region_lookup = {region.region_id: region for region in project.region_map.regions}
            for region_id in sorted(candidate.selected_region_ids):
                region = region_lookup.get(region_id)
                if region is None or len(region.contour) < 3:
                    continue
                records.append(
                    {
                        'candidate': candidate,
                        'project': project,
                        'region': region,
                        'mask': project.labels == region_id,
                    }
                )
        return records

    def _cluster_records(self, merge_threshold: float) -> list[dict[str, Any]]:
        """Group composite records by color similarity."""

        records = self._composite_region_records()
        if merge_threshold <= 0:
            return [
                {
                    'color': record['region'].color_rgb,
                    'records': [record],
                }
                for record in records
            ]

        clusters: list[dict[str, Any]] = []
        for record in records:
            region = record['region']
            color = region.color_rgb
            cluster = None
            for existing in clusters:
                if self._rgb_distance(existing['color'], color) <= merge_threshold:
                    cluster = existing
                    break
            if cluster is None:
                cluster = {'color': color, 'records': []}
                clusters.append(cluster)
            cluster['records'].append(record)
            colors = [item['region'].color_rgb for item in cluster['records']]
            cluster['color'] = tuple(
                int(round(sum(channel) / len(colors))) for channel in zip(*colors, strict=False)
            )
        return clusters

    @staticmethod
    def _mask_to_contours(mask: np.ndarray) -> list[tuple[tuple[float, float], ...]]:
        padded = np.pad(mask.astype(float), 1, mode='constant', constant_values=0.0)
        contours = find_contours(padded, 0.5)
        output: list[tuple[tuple[float, float], ...]] = []
        for contour in contours:
            if len(contour) < 3:
                continue
            simplified = approximate_polygon(contour, tolerance=1.0)
            points: list[tuple[float, float]] = []
            for row, col in simplified:
                points.append((float(col - 1), float(row - 1)))
            if len(points) >= 3 and points[0] != points[-1]:
                points.append(points[0])
            if len(points) >= 4:
                output.append(tuple(points))
        return output

    @staticmethod
    def _rgb_distance(left: tuple[int, int, int], right: tuple[int, int, int]) -> float:
        return float(
            ((left[0] - right[0]) ** 2 + (left[1] - right[1]) ** 2 + (left[2] - right[2]) ** 2)
            ** 0.5
        )

    def composite_preview(self, merge_threshold: float = 0.0) -> np.ndarray:
        """Render the current kept selections as a preview image."""

        base_candidate = self._composite_base_candidate()
        if base_candidate is None:
            raise ValueError('no candidates in workspace')

        base_project = MarqflowProject.load(base_candidate.project_dir)
        canvas = np.array(base_project.preview, copy=True)

        if merge_threshold <= 0:
            for record in self._composite_region_records():
                project = record['project']
                mask = record['mask']
                canvas[mask] = project.preview[mask]
            return canvas

        for cluster in self._cluster_records(merge_threshold):
            mask = np.zeros(base_project.labels.shape, dtype=bool)
            colors = []
            for record in cluster['records']:
                mask |= record['mask']
                colors.append(record['project'].preview[record['mask']])
            if not colors:
                continue
            stacked = np.concatenate(colors, axis=0)
            mean_color = np.round(stacked.mean(axis=0)).astype(np.uint8)
            canvas[mask] = mean_color
        return canvas

    def composite_svg(self, merge_threshold: float = 0.0) -> str:
        """Render the composite SVG, optionally merging nearby colors."""

        base_candidate = self._composite_base_candidate()
        if base_candidate is None:
            raise ValueError('no candidates in workspace')

        base_project = MarqflowProject.load(base_candidate.project_dir)
        width, height = base_project.region_map.size
        records = self._composite_region_records()

        if not records:
            return (
                f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
                f'viewBox="0 0 {width} {height}"></svg>'
            )

        if merge_threshold <= 0:
            paths: list[str] = []
            for record in records:
                region = record['region']
                points = region.contour
                commands = [f'M{points[0][0]:.2f},{points[0][1]:.2f}']
                for x, y in points[1:]:
                    commands.append(f'L{x:.2f},{y:.2f}')
                commands.append('Z')
                paths.append(
                    f'<path d="{" ".join(commands)}" fill="{region.fill}" '
                    f'data-candidate="{record["candidate"].candidate_id}" '
                    f'data-region-id="{region.region_id}" />'
                )
        else:
            paths = []
            for index, cluster in enumerate(self._cluster_records(merge_threshold), start=1):
                mask = np.zeros(base_project.labels.shape, dtype=bool)
                for record in cluster['records']:
                    mask |= record['mask']
                for contour in self._mask_to_contours(mask):
                    commands = [f'M{contour[0][0]:.2f},{contour[0][1]:.2f}']
                    for x, y in contour[1:]:
                        commands.append(f'L{x:.2f},{y:.2f}')
                    commands.append('Z')
                    fill = '#{:02x}{:02x}{:02x}'.format(*cluster['color'])
                    paths.append(
                        f'<path d="{" ".join(commands)}" fill="{fill}" '
                        f'data-merged-group="{index}" />'
                    )

        return (
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
            f'viewBox="0 0 {width} {height}">' + ''.join(paths) + '</svg>'
        )

    def composite_summary(self, merge_threshold: float = 0.0) -> dict[str, Any]:
        """Return a small summary for the composite model."""

        records = self._composite_region_records()
        if not records:
            return {'path_count': 0, 'region_count': 0, 'merge_threshold': float(merge_threshold)}

        if merge_threshold <= 0:
            path_count = len(records)
        else:
            base_candidate = self._composite_base_candidate()
            if base_candidate is None:
                return {
                    'path_count': 0,
                    'region_count': 0,
                    'merge_threshold': float(merge_threshold),
                }
            base_project = MarqflowProject.load(base_candidate.project_dir)
            path_count = 0
            for cluster in self._cluster_records(merge_threshold):
                mask = np.zeros(base_project.labels.shape, dtype=bool)
                for record in cluster['records']:
                    mask |= record['mask']
                path_count += len(self._mask_to_contours(mask))

        return {
            'path_count': path_count,
            'region_count': len(records),
            'merge_threshold': float(merge_threshold),
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

        if not self.kept_candidates:
            raise ValueError('select at least one candidate before exporting')

        canvas = self.composite_preview(merge_threshold=merge_threshold)
        svg = self.composite_svg(merge_threshold=merge_threshold)

        Image.fromarray(canvas.astype(np.uint8), mode='RGB').save(composite_png)
        composite_svg.write_text(svg, encoding='utf-8')
        return composite_png, composite_svg
