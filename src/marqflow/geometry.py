"""Geometry and export helpers for marquetry partitions."""

from __future__ import annotations

import math
from collections import defaultdict
from html import escape
from typing import Any

import numpy as np
from PIL import Image
from skimage.measure import approximate_polygon, find_contours
from skimage.measure import label as connected_components

from .models import MarquetryDesign, PhysicalSize, Region, Veneer


def normalize_labels(labels: np.ndarray) -> np.ndarray:
    """Return positive contiguous labels, preserving the partition shape."""

    output = np.zeros(labels.shape, dtype=np.int32)
    for next_id, value in enumerate(sorted(int(v) for v in np.unique(labels)), start=1):
        output[labels == value] = next_id
    return output


def partition_validation(labels: np.ndarray) -> dict[str, Any]:
    """Validate the key marquetry invariant for a raster partition."""

    unassigned_px = int(np.count_nonzero(labels <= 0))
    region_ids = [int(value) for value in np.unique(labels) if int(value) > 0]
    disconnected = []
    for region_id in region_ids:
        components = int(connected_components(labels == region_id, connectivity=1).max())
        if components > 1:
            disconnected.append(region_id)
    return {
        'valid': unassigned_px == 0 and not disconnected and bool(region_ids),
        'unassigned_px': unassigned_px,
        'region_count': len(region_ids),
        'disconnected_region_ids': disconnected,
    }


def region_neighbors(labels: np.ndarray) -> dict[int, set[int]]:
    """Find 4-connected region adjacency."""

    neighbors: dict[int, set[int]] = defaultdict(set)
    right = labels[:, 1:] != labels[:, :-1]
    for y, x in zip(*np.nonzero(right), strict=False):
        left_id = int(labels[y, x])
        right_id = int(labels[y, x + 1])
        neighbors[left_id].add(right_id)
        neighbors[right_id].add(left_id)
    down = labels[1:, :] != labels[:-1, :]
    for y, x in zip(*np.nonzero(down), strict=False):
        top_id = int(labels[y, x])
        bottom_id = int(labels[y + 1, x])
        neighbors[top_id].add(bottom_id)
        neighbors[bottom_id].add(top_id)
    return neighbors


def contour_for_mask(mask: np.ndarray, tolerance: float = 1.0) -> tuple[tuple[float, float], ...]:
    """Extract one closed contour for a mask."""

    padded = np.pad(mask.astype(float), 1, mode='constant', constant_values=0.0)
    contours = find_contours(padded, 0.5)
    if not contours:
        return ()
    contour = max(contours, key=len)
    points = tuple((float(col - 1), float(row - 1)) for row, col in contour)
    if tolerance > 0 and len(points) >= 4:
        simplified = approximate_polygon(np.asarray([(y, x) for x, y in points]), tolerance)
        points = tuple((float(x), float(y)) for y, x in simplified)
    if len(points) >= 3 and points[0] != points[-1]:
        points = (*points, points[0])
    return points


def average_color(image: np.ndarray, mask: np.ndarray) -> tuple[int, int, int]:
    pixels = image[mask]
    if pixels.size == 0:
        return (0, 0, 0)
    color = pixels.mean(axis=0)
    return tuple(int(round(v)) for v in color[:3])


def nearest_veneer(color: tuple[int, int, int], veneers: list[Veneer]) -> Veneer:
    if not veneers:
        return Veneer('default', 'Default', color)
    return min(
        veneers,
        key=lambda veneer: math.dist(color, veneer.color_rgb),
    )


def build_regions(
    image: np.ndarray,
    labels: np.ndarray,
    design: MarquetryDesign,
    simplify_tolerance: float = 1.0,
) -> list[Region]:
    """Build physical region records from the current design labels."""

    px_per_unit_x, px_per_unit_y = design.physical_size.pixels_per_unit(
        (labels.shape[1], labels.shape[0])
    )
    area_scale = 1.0 / max(px_per_unit_x * px_per_unit_y, 1e-9)
    neighbors = region_neighbors(labels)
    records: list[Region] = []
    for raw_id in sorted(int(value) for value in np.unique(labels) if int(value) > 0):
        mask = labels == raw_id
        ys, xs = np.nonzero(mask)
        if not len(xs):
            continue
        color = average_color(image, mask)
        suggested = nearest_veneer(color, design.veneers)
        veneer_id = design.veneer_assignments.get(raw_id, suggested.veneer_id)
        bbox = (int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1)
        area_px = int(mask.sum())
        width_physical = (bbox[2] - bbox[0]) / max(px_per_unit_x, 1e-9)
        height_physical = (bbox[3] - bbox[1]) / max(px_per_unit_y, 1e-9)
        warnings = []
        if min(width_physical, height_physical) < 0.08:
            warnings.append('thin')
        if area_px * area_scale < 0.05:
            warnings.append('small')
        records.append(
            Region(
                region_id=raw_id,
                veneer_id=veneer_id,
                suggested_veneer_id=suggested.veneer_id,
                color_rgb=color,
                area_px=area_px,
                area_physical=area_px * area_scale,
                bbox=bbox,
                contour=contour_for_mask(mask, tolerance=simplify_tolerance),
                neighbors=tuple(sorted(neighbors.get(raw_id, set()))),
                locked=raw_id in design.locked_region_ids,
                warnings=tuple(warnings),
            )
        )
    return records


def preview_image(image: np.ndarray, labels: np.ndarray) -> Image.Image:
    """Render a flat-color preview from average region colors."""

    output = np.zeros_like(image)
    for region_id in sorted(int(value) for value in np.unique(labels) if int(value) > 0):
        mask = labels == region_id
        output[mask] = average_color(image, mask)
    return Image.fromarray(output.astype(np.uint8), mode='RGB')


def svg_path(points: tuple[tuple[float, float], ...], scale_x: float, scale_y: float) -> str:
    if len(points) < 3:
        return ''
    first_x, first_y = points[0]
    commands = [f'M {first_x / scale_x:.4f} {first_y / scale_y:.4f}']
    for x, y in points[1:]:
        commands.append(f'L {x / scale_x:.4f} {y / scale_y:.4f}')
    commands.append('Z')
    return ' '.join(commands)


def design_to_svg(
    regions: list[Region],
    physical_size: PhysicalSize,
    image_size: tuple[int, int],
) -> str:
    """Export final cut paths grouped by veneer."""

    px_per_unit_x, px_per_unit_y = physical_size.pixels_per_unit(image_size)
    groups: dict[str, list[str]] = defaultdict(list)
    for region in regions:
        path = svg_path(region.contour, px_per_unit_x, px_per_unit_y)
        if not path:
            continue
        groups[region.veneer_id].append(
            f'<path id="region-{region.region_id}" d="{path}" '
            f'fill="#{region.color_rgb[0]:02x}{region.color_rgb[1]:02x}{region.color_rgb[2]:02x}" '
            'stroke="#111" stroke-width="0.01" '
            f'data-region-id="{region.region_id}" data-veneer-id="{escape(region.veneer_id)}" />'
        )
    body = ''.join(
        f'<g id="veneer-{escape(veneer_id)}" data-veneer-id="{escape(veneer_id)}">'
        + ''.join(paths)
        + '</g>'
        for veneer_id, paths in sorted(groups.items())
    )
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" '
        f'width="{physical_size.width}{physical_size.unit}" '
        f'height="{physical_size.height}{physical_size.unit}" '
        f'viewBox="0 0 {physical_size.width} {physical_size.height}">{body}</svg>'
    )
