"""Region model and region-graph helpers."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from skimage.measure import find_contours


@dataclass(frozen=True, slots=True)
class Region:
    """A single region in the working graph."""

    region_id: int
    color_rgb: tuple[int, int, int]
    area: int
    bbox: tuple[int, int, int, int]
    contour: tuple[tuple[float, float], ...]
    neighbors: tuple[int, ...]

    @property
    def fill(self) -> str:
        return '#{:02x}{:02x}{:02x}'.format(*self.color_rgb)


@dataclass(frozen=True, slots=True)
class RegionMap:
    """The region graph plus the raster source it came from."""

    image_rgb: np.ndarray
    labels: np.ndarray
    regions: tuple[Region, ...]
    source_path: Path | None = None

    @property
    def size(self) -> tuple[int, int]:
        height, width = self.labels.shape
        return width, height


def build_region_neighbors(labels: np.ndarray) -> dict[int, set[int]]:
    """Compute 4-connected adjacency between labels."""

    neighbors: dict[int, set[int]] = {int(label): set() for label in np.unique(labels)}

    right = labels[:, :-1] != labels[:, 1:]
    if np.any(right):
        left_labels = labels[:, :-1][right]
        right_labels = labels[:, 1:][right]
        for a, b in zip(left_labels.flat, right_labels.flat, strict=False):
            if a == b:
                continue
            neighbors[int(a)].add(int(b))
            neighbors[int(b)].add(int(a))

    down = labels[:-1, :] != labels[1:, :]
    if np.any(down):
        top_labels = labels[:-1, :][down]
        bottom_labels = labels[1:, :][down]
        for a, b in zip(top_labels.flat, bottom_labels.flat, strict=False):
            if a == b:
                continue
            neighbors[int(a)].add(int(b))
            neighbors[int(b)].add(int(a))

    return neighbors


def _contour_for_label(labels: np.ndarray, label: int) -> tuple[tuple[float, float], ...]:
    mask = labels == label
    contours = find_contours(mask.astype(float), 0.5)
    if not contours:
        return ()

    contour = max(contours, key=len)
    points: list[tuple[float, float]] = []
    for row, col in contour:
        points.append((float(col), float(row)))

    if points and points[0] != points[-1]:
        points.append(points[0])
    return tuple(points)


def build_regions(image_rgb: np.ndarray, labels: np.ndarray) -> tuple[Region, ...]:
    """Build per-label region records from a raster image and labels."""

    neighbors = build_region_neighbors(labels)
    regions: list[Region] = []
    for raw_label in sorted(np.unique(labels)):
        label = int(raw_label)
        mask = labels == label
        ys, xs = np.nonzero(mask)
        if xs.size == 0 or ys.size == 0:
            continue

        x0 = int(xs.min())
        x1 = int(xs.max()) + 1
        y0 = int(ys.min())
        y1 = int(ys.max()) + 1
        region_pixels = image_rgb[mask]
        mean_color = tuple(int(round(value)) for value in region_pixels.mean(axis=0))
        contour = _contour_for_label(labels, label)
        regions.append(
            Region(
                region_id=label,
                color_rgb=mean_color,
                area=int(mask.sum()),
                bbox=(x0, y0, x1, y1),
                contour=contour,
                neighbors=tuple(sorted(neighbors[label])),
            )
        )

    return tuple(regions)


def labels_to_palette_image(image_rgb: np.ndarray, labels: np.ndarray) -> np.ndarray:
    """Paint each label with its region mean color."""

    output = np.empty_like(image_rgb)
    for raw_label in np.unique(labels):
        label = int(raw_label)
        mask = labels == label
        region_pixels = image_rgb[mask]
        mean_color = np.round(region_pixels.mean(axis=0)).astype(np.uint8)
        output[mask] = mean_color
    return output


def iter_region_ids(regions: Iterable[Region]) -> list[int]:
    return [region.region_id for region in regions]
