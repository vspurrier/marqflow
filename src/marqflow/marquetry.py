"""Final marquetry design helpers.

This module keeps the candidate-search layer separate from the final design
layer. The final design is a measured planar partition with explicit physical
size, veneer palette, and geometry metrics.
"""

from __future__ import annotations

import math
from collections.abc import Iterable
from dataclasses import asdict, dataclass, field
from typing import Any

import numpy as np
from rectpack import newPacker
from skimage.color import rgb2lab
from skimage.measure import approximate_polygon, find_contours
from skimage.measure import label as connected_components
from skimage.segmentation import felzenszwalb, slic

from .regions import build_region_neighbors, build_regions, labels_to_palette_image


@dataclass(frozen=True, slots=True)
class PhysicalSize:
    """Physical dimensions for the finished piece."""

    width: float
    height: float
    unit: str = 'px'

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None, fallback: PhysicalSize) -> PhysicalSize:
        if not data:
            return fallback
        return cls(
            width=float(data.get('width', fallback.width)),
            height=float(data.get('height', fallback.height)),
            unit=str(data.get('unit', fallback.unit)),
        )

    def pixels_per_unit(self, image_size: tuple[int, int]) -> tuple[float, float]:
        width_px, height_px = image_size
        if self.width <= 0 or self.height <= 0:
            return 1.0, 1.0
        return width_px / self.width, height_px / self.height

    def area_scale(self, image_size: tuple[int, int]) -> float:
        px_per_unit_x, px_per_unit_y = self.pixels_per_unit(image_size)
        if px_per_unit_x <= 0 or px_per_unit_y <= 0:
            return 1.0
        return 1.0 / (px_per_unit_x * px_per_unit_y)


@dataclass(frozen=True, slots=True)
class VeneerSwatch:
    """A named veneer color suggestion."""

    veneer_id: str
    name: str
    color_rgb: tuple[int, int, int]

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload['color_rgb'] = list(self.color_rgb)
        return payload

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> VeneerSwatch:
        return cls(
            veneer_id=str(data['veneer_id']),
            name=str(data.get('name', data['veneer_id'])),
            color_rgb=tuple(int(value) for value in data.get('color_rgb', (0, 0, 0))),
        )


@dataclass(frozen=True, slots=True)
class CleanupSettings:
    """Thresholds for cleanup and highlighting."""

    simplify_tolerance: float = 1.0
    highlight_small_area: float = 0.0
    highlight_thin_width: float = 0.0
    merge_rgb_threshold: float = 24.0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> CleanupSettings:
        if not data:
            return cls()
        return cls(
            simplify_tolerance=float(data.get('simplify_tolerance', 1.0)),
            highlight_small_area=float(data.get('highlight_small_area', 0.0)),
            highlight_thin_width=float(data.get('highlight_thin_width', 0.0)),
            merge_rgb_threshold=float(data.get('merge_rgb_threshold', 24.0)),
        )


@dataclass(frozen=True, slots=True)
class SubjectSettings:
    """High-level subject prioritization for portrait work."""

    detail_budget: float = 0.5
    notes: str = ''
    protect_eyes: bool = True
    protect_nose: bool = True

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> SubjectSettings:
        if not data:
            return cls()
        return cls(
            detail_budget=float(data.get('detail_budget', 0.5)),
            notes=str(data.get('notes', '')),
            protect_eyes=bool(data.get('protect_eyes', True)),
            protect_nose=bool(data.get('protect_nose', True)),
        )


@dataclass(slots=True)
class DesignRegion:
    """A final region in the partition."""

    region_id: int
    area_px: int
    area_physical: float
    perimeter_px: float
    perimeter_physical: float
    bbox: tuple[int, int, int, int]
    contour: tuple[tuple[float, float], ...]
    neighbors: tuple[int, ...]
    color_rgb: tuple[int, int, int]
    source_refs: tuple[tuple[str, int], ...]
    veneer_id: str
    suggested_veneer_id: str
    hole_count: int = 0
    component_count: int = 1
    veneer_override_id: str | None = None
    locked: bool = False

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload['source_refs'] = [list(ref) for ref in self.source_refs]
        payload['contour'] = [list(point) for point in self.contour]
        payload['color_rgb'] = list(self.color_rgb)
        return payload


@dataclass(slots=True)
class CompositeDesign:
    """Persisted final marquetry design aggregate."""

    base_candidate_id: str | None
    physical_size: PhysicalSize
    veneer_palette: list[VeneerSwatch] = field(default_factory=list)
    cleanup: CleanupSettings = field(default_factory=CleanupSettings)
    paint_events: list[PaintEvent] = field(default_factory=list)
    final_region_sources: dict[int, tuple[tuple[str, int], ...]] = field(default_factory=dict)
    final_region_veneer_overrides: dict[int, str] = field(default_factory=dict)
    final_region_contour_overrides: dict[int, tuple[tuple[float, float], ...]] = field(
        default_factory=dict
    )
    final_region_locked_ids: set[int] = field(default_factory=set)
    manual_edits: list[dict[str, Any]] = field(default_factory=list)
    validation: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            'base_candidate_id': self.base_candidate_id,
            'physical_size': self.physical_size.to_dict(),
            'veneer_palette': [swatch.to_dict() for swatch in self.veneer_palette],
            'cleanup': self.cleanup.to_dict(),
            'paint_events': [event.to_dict() for event in self.paint_events],
            'final_region_sources': {
                str(region_id): [list(ref) for ref in refs]
                for region_id, refs in self.final_region_sources.items()
            },
            'final_region_veneer_overrides': {
                str(region_id): veneer_id
                for region_id, veneer_id in self.final_region_veneer_overrides.items()
            },
            'final_region_contour_overrides': {
                str(region_id): [list(point) for point in points]
                for region_id, points in self.final_region_contour_overrides.items()
            },
            'final_region_locked_ids': sorted(self.final_region_locked_ids),
            'manual_edits': self.manual_edits,
            'validation': self.validation,
        }

    @classmethod
    def from_dict(
        cls,
        data: dict[str, Any] | None,
        fallback: CompositeDesign,
    ) -> CompositeDesign:
        if not data:
            return fallback
        return cls(
            base_candidate_id=data.get('base_candidate_id', fallback.base_candidate_id),
            physical_size=PhysicalSize.from_dict(data.get('physical_size'), fallback.physical_size),
            veneer_palette=[VeneerSwatch.from_dict(item) for item in data.get('veneer_palette', [])]
            or fallback.veneer_palette,
            cleanup=CleanupSettings.from_dict(data.get('cleanup')),
            paint_events=[PaintEvent.from_dict(item) for item in data.get('paint_events', [])],
            final_region_sources={
                int(region_id): tuple(
                    (str(candidate_id), int(source_region_id))
                    for candidate_id, source_region_id in refs
                )
                for region_id, refs in data.get('final_region_sources', {}).items()
            },
            final_region_veneer_overrides={
                int(region_id): str(veneer_id)
                for region_id, veneer_id in data.get('final_region_veneer_overrides', {}).items()
            },
            final_region_contour_overrides={
                int(region_id): tuple(
                    (float(point[0]), float(point[1])) for point in points
                )
                for region_id, points in data.get('final_region_contour_overrides', {}).items()
            },
            final_region_locked_ids={
                int(region_id) for region_id in data.get('final_region_locked_ids', [])
            },
            manual_edits=[dict(item) for item in data.get('manual_edits', [])],
            validation=dict(data.get('validation', {})),
        )


@dataclass(frozen=True, slots=True)
class PaintEvent:
    """An ordered paint operation used to rebuild the final design."""

    event_index: int
    candidate_id: str
    region_ids: tuple[int, ...]
    additive: bool = False
    kind: str = 'paint'
    selected_at_ns: int = 0

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload['region_ids'] = list(self.region_ids)
        return payload

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PaintEvent:
        return cls(
            event_index=int(data.get('event_index', 0)),
            candidate_id=str(data['candidate_id']),
            region_ids=tuple(int(value) for value in data.get('region_ids', [])),
            additive=bool(data.get('additive', False)),
            kind=str(data.get('kind', 'paint')),
            selected_at_ns=int(data.get('selected_at_ns', 0)),
        )


def default_veneer_palette() -> list[VeneerSwatch]:
    """Return a compact, fabrication-friendly default palette."""

    return [
        VeneerSwatch('light', 'Light', (220, 205, 172)),
        VeneerSwatch('mid', 'Mid', (171, 134, 92)),
        VeneerSwatch('dark', 'Dark', (78, 56, 42)),
        VeneerSwatch('black', 'Black', (34, 30, 28)),
        VeneerSwatch('red', 'Red Brown', (139, 74, 52)),
        VeneerSwatch('blue', 'Blue Gray', (82, 104, 130)),
    ]


def _rgb_to_lab(color_rgb: tuple[int, int, int]) -> np.ndarray:
    rgb = np.asarray([[color_rgb]], dtype=np.float32) / 255.0
    return rgb2lab(rgb)[0, 0]


def _lab_distance(left: tuple[int, int, int], right: tuple[int, int, int]) -> float:
    left_lab = _rgb_to_lab(left)
    right_lab = _rgb_to_lab(right)
    return float(np.linalg.norm(left_lab - right_lab))


def choose_veneer(color_rgb: tuple[int, int, int], palette: list[VeneerSwatch]) -> VeneerSwatch:
    """Pick the closest veneer color from the current palette."""

    if not palette:
        return VeneerSwatch('default', 'Default', color_rgb)
    return min(palette, key=lambda swatch: _lab_distance(color_rgb, swatch.color_rgb))


def veneer_by_id(veneer_id: str | None, palette: list[VeneerSwatch]) -> VeneerSwatch | None:
    """Look up a veneer swatch by ID."""

    if veneer_id is None:
        return None
    for swatch in palette:
        if swatch.veneer_id == veneer_id:
            return swatch
    return None


def _contour_length(points: tuple[tuple[float, float], ...]) -> float:
    if len(points) < 2:
        return 0.0
    total = 0.0
    for left, right in zip(points, points[1:], strict=False):
        total += math.dist(left, right)
    return total


def _scale_points(
    points: tuple[tuple[float, float], ...],
    scale_x: float,
    scale_y: float,
) -> tuple[tuple[float, float], ...]:
    """Scale a contour into another coordinate system."""

    if not points:
        return points
    return tuple((float(x) / max(1.0, scale_x), float(y) / max(1.0, scale_y)) for x, y in points)


def _simplify_contour(
    contour: tuple[tuple[float, float], ...],
    tolerance: float,
) -> tuple[tuple[float, float], ...]:
    if len(contour) < 4 or tolerance <= 0:
        return contour
    simplified = approximate_polygon(np.asarray(contour), tolerance=tolerance)
    points = [(float(col), float(row)) for row, col in simplified]
    if len(points) >= 3 and points[0] != points[-1]:
        points.append(points[0])
    return tuple(points)


def _contour_for_mask(
    mask: np.ndarray, simplify_tolerance: float = 1.0
) -> tuple[tuple[float, float], ...]:
    padded = np.pad(mask.astype(float), 1, mode='constant', constant_values=0.0)
    contours = find_contours(padded, 0.5)
    if not contours:
        return ()
    contour = max(contours, key=len)
    points = [(float(col - 1), float(row - 1)) for row, col in contour]
    if len(points) >= 3 and points[0] != points[-1]:
        points.append(points[0])
    return _simplify_contour(tuple(points), tolerance=simplify_tolerance)


def build_design_regions(
    image_rgb: np.ndarray,
    labels: np.ndarray,
    physical_size: PhysicalSize,
    palette: list[VeneerSwatch] | None = None,
    simplify_tolerance: float = 1.0,
    source_prefix: str = 'source',
    source_refs_by_region: dict[int, tuple[tuple[str, int], ...]] | None = None,
    locked_region_ids: set[int] | None = None,
    veneer_overrides: dict[int, str] | None = None,
    contour_overrides: dict[int, tuple[tuple[float, float], ...]] | None = None,
) -> tuple[DesignRegion, ...]:
    """Compute final design regions from a completed label raster."""

    palette = palette or default_veneer_palette()
    locked_region_ids = locked_region_ids or set()
    veneer_overrides = veneer_overrides or {}
    contour_overrides = contour_overrides or {}
    neighbors = build_region_neighbors(labels)
    regions: list[DesignRegion] = []
    for raw_label in sorted(np.unique(labels)):
        region_id = int(raw_label)
        mask = labels == region_id
        ys, xs = np.nonzero(mask)
        if xs.size == 0 or ys.size == 0:
            continue
        x0 = int(xs.min())
        x1 = int(xs.max()) + 1
        y0 = int(ys.min())
        y1 = int(ys.max()) + 1
        pixels = image_rgb[mask]
        mean_color = tuple(int(round(value)) for value in pixels.mean(axis=0))
        contour_count = len(find_contours(np.pad(mask.astype(float), 1), 0.5))
        component_count = int(connected_components(mask, connectivity=1).max())
        contour = contour_overrides.get(region_id) or _contour_for_mask(
            mask, simplify_tolerance=simplify_tolerance
        )
        area_px = int(mask.sum())
        area_physical = area_px * physical_size.area_scale((labels.shape[1], labels.shape[0]))
        perimeter_px = _contour_length(contour)
        px_per_unit_x, px_per_unit_y = physical_size.pixels_per_unit(
            (labels.shape[1], labels.shape[0])
        )
        perimeter_physical = perimeter_px / max(1.0, (px_per_unit_x + px_per_unit_y) / 2.0)
        suggested_veneer = choose_veneer(mean_color, palette)
        override_veneer = veneer_by_id(veneer_overrides.get(region_id), palette)
        veneer = override_veneer or suggested_veneer
        regions.append(
            DesignRegion(
                region_id=region_id,
                area_px=area_px,
                area_physical=area_physical,
                perimeter_px=perimeter_px,
                perimeter_physical=perimeter_physical,
                bbox=(x0, y0, x1, y1),
                contour=contour,
                neighbors=tuple(sorted(neighbors[region_id])),
                color_rgb=mean_color,
                source_refs=source_refs_by_region.get(region_id, ((source_prefix, region_id),))
                if source_refs_by_region is not None
                else ((source_prefix, region_id),),
                veneer_id=veneer.veneer_id,
                suggested_veneer_id=suggested_veneer.veneer_id,
                hole_count=max(0, contour_count - max(1, component_count)),
                component_count=max(1, component_count),
                veneer_override_id=(
                    override_veneer.veneer_id if override_veneer is not None else None
                ),
                locked=region_id in locked_region_ids,
            )
        )
    return tuple(regions)


def labels_to_preview(image_rgb: np.ndarray, labels: np.ndarray) -> np.ndarray:
    """Render a raster preview from final labels."""

    return labels_to_palette_image(image_rgb, labels)


def _region_mask(labels: np.ndarray, region_id: int) -> np.ndarray:
    return labels == region_id


def _relabel_region(
    labels: np.ndarray,
    region_ids: set[int],
    target_label: int,
) -> None:
    mask = np.isin(labels, list(region_ids))
    labels[mask] = target_label


def merge_region_labels(labels: np.ndarray, region_ids: Iterable[int]) -> int:
    """Merge connected regions in a final partition raster."""

    selected = sorted({int(region_id) for region_id in region_ids})
    if len(selected) < 2:
        return 0
    adjacency = build_region_neighbors(labels)
    remaining = set(selected)
    groups: list[set[int]] = []

    while remaining:
        seed = remaining.pop()
        group = {seed}
        stack = [seed]
        while stack:
            current = stack.pop()
            for neighbor in adjacency.get(current, set()):
                if neighbor in remaining:
                    remaining.remove(neighbor)
                    group.add(neighbor)
                    stack.append(neighbor)
        groups.append(group)

    merged = 0
    for group in groups:
        if len(group) < 2:
            continue
        target = min(group)
        _relabel_region(labels, group, target)
        merged += 1
    return merged


def split_region_label(
    image_rgb: np.ndarray,
    labels: np.ndarray,
    region_id: int,
    target_segments: int,
    compactness: float | None = None,
    sigma: float | None = None,
) -> int:
    """Split one final region into smaller labels."""

    compactness = 20.0 if compactness is None else float(compactness)
    sigma = 1.0 if sigma is None else float(sigma)
    mask = labels == int(region_id)
    if not np.any(mask):
        return 0

    ys, xs = np.nonzero(mask)
    y0, y1 = int(ys.min()), int(ys.max()) + 1
    x0, x1 = int(xs.min()), int(xs.max()) + 1

    crop_image = image_rgb[y0:y1, x0:x1]
    crop_mask = mask[y0:y1, x0:x1]
    if int(crop_mask.sum()) < 2:
        return 0

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
        unique = [int(value) for value in np.unique(sublabels[crop_mask]) if int(value) > 0]

    if len(unique) <= 1:
        return 0

    next_label = int(labels.max()) + 1
    labels[mask] = 0
    crop_labels = labels[y0:y1, x0:x1]
    changed = 0
    for sublabel in unique:
        submask = sublabels == sublabel
        if not np.any(submask):
            continue
        crop_labels[submask] = next_label
        next_label += 1
        changed += 1
    return changed


def labels_to_svg_path(points: tuple[tuple[float, float], ...]) -> str:
    """Convert a polygon contour to SVG path commands."""

    if not points:
        return ''
    commands = [f'M{points[0][0]:.2f},{points[0][1]:.2f}']
    for x, y in points[1:]:
        commands.append(f'L{x:.2f},{y:.2f}')
    commands.append('Z')
    return ' '.join(commands)


def _render_sheet_svg(
    sheet_width: float,
    sheet_height: float,
    pieces: list[dict[str, Any]],
) -> str:
    paths: list[str] = [
        f'<rect x="0" y="0" width="{sheet_width}" height="{sheet_height}" '
        'fill="#0f0d0b" stroke="#3d352f" stroke-width="0.6" />'
    ]
    for piece in pieces:
        contour = piece['contour']
        x_offset = float(piece['x']) - float(piece['origin_x'])
        y_offset = float(piece['y']) - float(piece['origin_y'])
        points = tuple((float(x) + x_offset, float(y) + y_offset) for x, y in contour)
        fill = piece['fill']
        paths.append(
            f'<path d="{labels_to_svg_path(points)}" fill="{fill}" '
            f'stroke="#f6efe6" stroke-width="0.3" data-region-id="{piece["region_id"]}" '
            f'data-veneer-id="{piece["veneer_id"]}" />'
        )
        paths.append(
            f'<text x="{float(piece["x"]) + 1.2}" y="{float(piece["y"]) + 6}" '
            'fill="#f6efe6" font-size="5" font-family="monospace">'
            f'{piece["region_id"]}</text>'
        )
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{sheet_width}" height="{sheet_height}" '
        f'viewBox="0 0 {sheet_width} {sheet_height}">' + ''.join(paths) + '</svg>'
    )


def region_records_to_preview(
    image_rgb: np.ndarray,
    labels: np.ndarray,
    merge_threshold: float = 0.0,
) -> np.ndarray:
    """Render a merged or unmerged preview from final labels."""

    preview = labels_to_palette_image(image_rgb, labels)
    if merge_threshold <= 0:
        return preview

    regions = build_regions(image_rgb, labels)
    grouped: list[dict[str, Any]] = []
    for region in regions:
        cluster = None
        for existing in grouped:
            if (
                float(np.linalg.norm(np.asarray(existing['color']) - np.asarray(region.color_rgb)))
                <= merge_threshold
            ):
                cluster = existing
                break
        if cluster is None:
            cluster = {'color': region.color_rgb, 'region_ids': []}
            grouped.append(cluster)
        cluster['region_ids'].append(region.region_id)
        colors = np.asarray(
            [region.color_rgb for region in regions if region.region_id in cluster['region_ids']]
        )
        cluster['color'] = tuple(int(round(value)) for value in colors.mean(axis=0))

    output = np.array(preview, copy=True)
    for cluster in grouped:
        mask = np.isin(labels, cluster['region_ids'])
        output[mask] = np.asarray(cluster['color'], dtype=np.uint8)
    return output


def region_records_to_svg(
    image_rgb: np.ndarray,
    labels: np.ndarray,
    physical_size: PhysicalSize,
    palette: list[VeneerSwatch] | None = None,
    simplify_tolerance: float = 1.0,
    merge_threshold: float = 0.0,
    veneer_overrides: dict[int, str] | None = None,
) -> str:
    """Render final labels to an SVG string."""

    palette = palette or default_veneer_palette()
    width_px = labels.shape[1]
    height_px = labels.shape[0]
    width = physical_size.width if physical_size.unit != 'px' else width_px
    height = physical_size.height if physical_size.unit != 'px' else height_px
    px_per_unit_x, px_per_unit_y = physical_size.pixels_per_unit((width_px, height_px))
    regions = build_regions(image_rgb, labels)

    if merge_threshold > 0:
        groups: list[dict[str, Any]] = []
        for region in regions:
            cluster = None
            for existing in groups:
                if (
                    float(
                        np.linalg.norm(np.asarray(existing['color']) - np.asarray(region.color_rgb))
                    )
                    <= merge_threshold
                ):
                    cluster = existing
                    break
            if cluster is None:
                cluster = {'color': region.color_rgb, 'region_ids': []}
                groups.append(cluster)
            cluster['region_ids'].append(region.region_id)
            colors = np.asarray(
                [
                    region.color_rgb
                    for region in regions
                    if region.region_id in cluster['region_ids']
                ]
            )
            cluster['color'] = tuple(int(round(value)) for value in colors.mean(axis=0))

        paths: list[str] = []
        for index, cluster in enumerate(groups, start=1):
            mask = np.isin(labels, cluster['region_ids'])
            padded = np.pad(mask.astype(float), 1, mode='constant', constant_values=0.0)
            contours = find_contours(padded, 0.5)
            for contour in contours:
                if len(contour) < 3:
                    continue
                simplified = approximate_polygon(contour, tolerance=simplify_tolerance)
                points = [(float(col - 1), float(row - 1)) for row, col in simplified]
                if len(points) >= 3 and points[0] != points[-1]:
                    points.append(points[0])
                fill = '#{:02x}{:02x}{:02x}'.format(*cluster['color'])
                if physical_size.unit != 'px':
                    points = _scale_points(tuple(points), px_per_unit_x, px_per_unit_y)
                paths.append(
                    f'<path d="{labels_to_svg_path(tuple(points))}" fill="{fill}" '
                    f'data-merged-group="{index}" />'
                )
        return (
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
            f'viewBox="0 0 {width} {height}">' + ''.join(paths) + '</svg>'
        )

    paths = []
    for region in regions:
        if len(region.contour) < 3:
            continue
        veneer = veneer_by_id((veneer_overrides or {}).get(region.region_id), palette)
        veneer = veneer or choose_veneer(region.color_rgb, palette)
        contour = region.contour
        if physical_size.unit != 'px':
            contour = _scale_points(contour, px_per_unit_x, px_per_unit_y)
        paths.append(
            f'<path d="{labels_to_svg_path(contour)}" '
            f'fill="#{veneer.color_rgb[0]:02x}{veneer.color_rgb[1]:02x}{veneer.color_rgb[2]:02x}" '
            f'data-region-id="{region.region_id}" data-veneer-id="{veneer.veneer_id}" '
            f'data-area="{region.area}" />'
        )
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}">' + ''.join(paths) + '</svg>'
    )


def design_regions_to_svg(
    regions: Iterable[DesignRegion],
    physical_size: PhysicalSize,
    image_size: tuple[int, int],
) -> str:
    """Render finalized design regions to an SVG string."""

    width_px, height_px = image_size
    width = physical_size.width if physical_size.unit != 'px' else width_px
    height = physical_size.height if physical_size.unit != 'px' else height_px
    px_per_unit_x, px_per_unit_y = physical_size.pixels_per_unit(image_size)
    grouped_paths: dict[str, list[str]] = {}
    for region in regions:
        if len(region.contour) < 3:
            continue
        contour = region.contour
        if physical_size.unit != 'px':
            contour = _scale_points(contour, px_per_unit_x, px_per_unit_y)
        fill = '#{:02x}{:02x}{:02x}'.format(*region.color_rgb)
        path = (
            f'<path d="{labels_to_svg_path(contour)}" fill="{fill}" '
            f'data-region-id="{region.region_id}" data-veneer-id="{region.veneer_id}" '
            f'data-area="{region.area_physical:.6f}" />'
        )
        grouped_paths.setdefault(region.veneer_id, []).append(path)

    groups = ''.join(
        f'<g id="veneer-{veneer_id}" data-veneer-id="{veneer_id}">'
        + ''.join(paths)
        + '</g>'
        for veneer_id, paths in sorted(grouped_paths.items())
    )
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}">' + groups + '</svg>'
    )


def pack_region_sheets(
    image_rgb: np.ndarray,
    labels: np.ndarray,
    physical_size: PhysicalSize,
    palette: list[VeneerSwatch] | None = None,
    simplify_tolerance: float = 1.0,
    veneer_overrides: dict[int, str] | None = None,
    contour_overrides: dict[int, tuple[tuple[float, float], ...]] | None = None,
) -> list[dict[str, Any]]:
    """Create a simple veneer-aware packing plan.

    This uses a maintained rectangle packer and writes one SVG sheet per
    packed veneer bin.
    """

    palette = palette or default_veneer_palette()
    contour_overrides = contour_overrides or {}
    px_per_unit_x, px_per_unit_y = physical_size.pixels_per_unit(
        (labels.shape[1], labels.shape[0])
    )
    regions = build_design_regions(
        image_rgb,
        labels,
        physical_size=physical_size,
        palette=palette,
        simplify_tolerance=simplify_tolerance,
        veneer_overrides=veneer_overrides,
        contour_overrides=contour_overrides,
    )
    grouped: dict[str, list[DesignRegion]] = {}
    for region in regions:
        grouped.setdefault(region.veneer_id, []).append(region)

    sheets: list[dict[str, Any]] = []
    for veneer_id, items in grouped.items():
        items = sorted(items, key=lambda region: region.area_px, reverse=True)
        sheet_width = physical_size.width if physical_size.unit != 'px' else float(labels.shape[1])
        sheet_height = (
            physical_size.height if physical_size.unit != 'px' else float(labels.shape[0])
        )
        packer = newPacker(rotation=False)
        contour_bounds: dict[int, tuple[float, float, float, float]] = {}
        for region in items:
            contour = tuple(
                (
                    float(point_x) / max(1.0, px_per_unit_x),
                    float(point_y) / max(1.0, px_per_unit_y),
                )
                for point_x, point_y in region.contour
            )
            if contour:
                xs = [point[0] for point in contour]
                ys = [point[1] for point in contour]
                min_x = min(xs)
                min_y = min(ys)
                max_x = max(xs)
                max_y = max(ys)
            else:
                x0, y0, x1, y1 = region.bbox
                min_x = float(x0) / max(1.0, px_per_unit_x)
                min_y = float(y0) / max(1.0, px_per_unit_y)
                max_x = float(x1) / max(1.0, px_per_unit_x)
                max_y = float(y1) / max(1.0, px_per_unit_y)
            contour_bounds[region.region_id] = (min_x, min_y, max_x, max_y)
            width_piece = max(1.0, max_x - min_x)
            height_piece = max(1.0, max_y - min_y)
            packer.add_rect(width_piece, height_piece, rid=region.region_id)
        packer.add_bin(sheet_width, sheet_height, len(items) or 1)
        packer.pack()

        packed_items: list[dict[str, Any]] = []
        for bin_index, x, y, width_piece, height_piece, region_id in packer.rect_list():
            region = next(item for item in items if item.region_id == region_id)
            min_x, min_y, _, _ = contour_bounds[region.region_id]
            contour = tuple(
                (
                    float(point_x) / max(1.0, px_per_unit_x),
                    float(point_y) / max(1.0, px_per_unit_y),
                )
                for point_x, point_y in region.contour
            )
            fill = '#{:02x}{:02x}{:02x}'.format(*region.color_rgb)
            packed_items.append(
                {
                    'region_id': region.region_id,
                    'source_refs': [list(ref) for ref in region.source_refs],
                    'x': float(x),
                    'y': float(y),
                    'width': float(width_piece),
                    'height': float(height_piece),
                    'origin_x': min_x,
                    'origin_y': min_y,
                    'veneer_id': veneer_id,
                    'contour': contour,
                    'fill': fill,
                    'bin_index': int(bin_index),
                }
            )
        sheet_svg = _render_sheet_svg(sheet_width, sheet_height, packed_items)
        sheets.append(
            {
                'veneer_id': veneer_id,
                'sheet_width': sheet_width,
                'sheet_height': sheet_height,
                'pieces': packed_items,
                'sheet_svg': sheet_svg,
            }
        )
    return sheets
