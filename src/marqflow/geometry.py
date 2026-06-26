"""Geometry and export helpers for marquetry partitions."""

from __future__ import annotations

import math
from collections import defaultdict
from html import escape
from typing import Any

import numpy as np
from PIL import Image
from shapely import coverage_invalid_edges, coverage_is_valid, coverage_simplify, unary_union
from shapely.geometry import LineString, Polygon
from shapely.ops import polygonize
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


def merge_labels(labels: np.ndarray, region_ids: set[int]) -> tuple[np.ndarray, dict[int, int]]:
    """Merge selected labels and return normalized labels plus old-to-new id map."""

    if len(region_ids) < 2:
        raise ValueError('choose at least two regions to merge')
    existing = {int(value) for value in np.unique(labels) if int(value) > 0}
    missing = sorted(region_ids - existing)
    if missing:
        raise ValueError(f'unknown region ids: {missing}')

    target_id = min(region_ids)
    merged = labels.copy()
    for region_id in region_ids:
        merged[labels == region_id] = target_id

    normalized = normalize_labels(merged)
    id_map: dict[int, int] = {}
    for old_id in existing:
        old_mask = labels == old_id
        if not np.any(old_mask):
            continue
        new_values = np.unique(normalized[old_mask])
        if len(new_values) != 1:
            raise ValueError(f'region {old_id} did not map to one merged label')
        id_map[old_id] = int(new_values[0])
    return normalized, id_map


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


def shared_boundaries(labels: np.ndarray) -> list[dict[str, Any]]:
    """Return raster shared-boundary metrics for each adjacent region pair."""

    boundaries: dict[tuple[int, int], int] = defaultdict(int)
    right = labels[:, 1:] != labels[:, :-1]
    for y, x in zip(*np.nonzero(right), strict=False):
        pair = tuple(sorted((int(labels[y, x]), int(labels[y, x + 1]))))
        boundaries[pair] += 1
    down = labels[1:, :] != labels[:-1, :]
    for y, x in zip(*np.nonzero(down), strict=False):
        pair = tuple(sorted((int(labels[y, x]), int(labels[y + 1, x]))))
        boundaries[pair] += 1
    return [
        {'region_a': region_a, 'region_b': region_b, 'edge_px': edge_px}
        for (region_a, region_b), edge_px in sorted(boundaries.items())
        if region_a > 0 and region_b > 0
    ]


Point = tuple[int, int]
Segment = tuple[Point, Point]


def _chain_segments(segments: list[Segment]) -> list[list[Point]]:
    """Chain axis-aligned unit boundary segments into shared polylines."""

    unused = set(range(len(segments)))
    by_point: dict[Point, set[int]] = defaultdict(set)
    for index, segment in enumerate(segments):
        by_point[segment[0]].add(index)
        by_point[segment[1]].add(index)

    paths: list[list[Point]] = []
    while unused:
        index = unused.pop()
        start, end = segments[index]
        path = [start, end]
        for prepend in (False, True):
            while True:
                endpoint = path[0] if prepend else path[-1]
                candidates = by_point[endpoint] & unused
                if not candidates:
                    break
                next_index = candidates.pop()
                unused.remove(next_index)
                segment_start, segment_end = segments[next_index]
                next_point = segment_end if segment_start == endpoint else segment_start
                if prepend:
                    path.insert(0, next_point)
                else:
                    path.append(next_point)
        paths.append(path)
    return paths


def shared_boundary_paths(labels: np.ndarray) -> list[dict[str, Any]]:
    """Return shared boundary geometry as grid-line polylines per adjacent pair."""

    segments_by_pair = boundary_segments(labels, include_exterior=False)
    return [
        {
            'region_a': region_a,
            'region_b': region_b,
            'paths': [
                [[x, y] for x, y in path]
                for path in _chain_segments(segments)
            ],
        }
        for (region_a, region_b), segments in sorted(segments_by_pair.items())
    ]


def boundary_segments(
    labels: np.ndarray,
    include_exterior: bool = True,
) -> dict[tuple[int, int], list[Segment]]:
    """Return unit grid-line boundary segments grouped by adjacent region pair."""

    segments_by_pair: dict[tuple[int, int], list[Segment]] = defaultdict(list)
    height, width = labels.shape
    right = labels[:, 1:] != labels[:, :-1]
    for y, x in zip(*np.nonzero(right), strict=False):
        pair = tuple(sorted((int(labels[y, x]), int(labels[y, x + 1]))))
        if pair[0] <= 0 or pair[1] <= 0:
            continue
        boundary_x = int(x + 1)
        segments_by_pair[pair].append(((boundary_x, int(y)), (boundary_x, int(y + 1))))
    down = labels[1:, :] != labels[:-1, :]
    for y, x in zip(*np.nonzero(down), strict=False):
        pair = tuple(sorted((int(labels[y, x]), int(labels[y + 1, x]))))
        if pair[0] <= 0 or pair[1] <= 0:
            continue
        boundary_y = int(y + 1)
        segments_by_pair[pair].append(((int(x), boundary_y), (int(x + 1), boundary_y)))
    if include_exterior:
        for x in range(width):
            top = int(labels[0, x])
            bottom = int(labels[height - 1, x])
            if top > 0:
                segments_by_pair[(0, top)].append(((x, 0), (x + 1, 0)))
            if bottom > 0:
                segments_by_pair[(0, bottom)].append(((x, height), (x + 1, height)))
        for y in range(height):
            left = int(labels[y, 0])
            right_label = int(labels[y, width - 1])
            if left > 0:
                segments_by_pair[(0, left)].append(((0, y), (0, y + 1)))
            if right_label > 0:
                segments_by_pair[(0, right_label)].append(((width, y), (width, y + 1)))
    return segments_by_pair


def boundary_graph(labels: np.ndarray, physical_size: PhysicalSize) -> dict[str, Any]:
    """Build a topology graph from shared and exterior boundary grid lines."""

    px_per_unit_x, px_per_unit_y = physical_size.pixels_per_unit(
        (labels.shape[1], labels.shape[0])
    )
    vertex_ids: dict[Point, int] = {}
    vertices = []
    edges = []
    region_edge_ids: dict[int, list[int]] = defaultdict(list)

    def vertex_id(point: Point) -> int:
        if point not in vertex_ids:
            next_id = len(vertex_ids) + 1
            vertex_ids[point] = next_id
            x, y = point
            vertices.append(
                {
                    'vertex_id': next_id,
                    'point': [x, y],
                    'physical_point': [
                        x / max(px_per_unit_x, 1e-9),
                        y / max(px_per_unit_y, 1e-9),
                    ],
                }
            )
        return vertex_ids[point]

    for (region_a, region_b), segments in sorted(boundary_segments(labels).items()):
        for path in _chain_segments(segments):
            physical_path = [
                [
                    x / max(px_per_unit_x, 1e-9),
                    y / max(px_per_unit_y, 1e-9),
                ]
                for x, y in path
            ]
            edge_id = len(edges) + 1
            edge = {
                'edge_id': edge_id,
                'region_a': region_a,
                'region_b': region_b,
                'exterior': region_a == 0 or region_b == 0,
                'vertex_ids': [vertex_id(point) for point in path],
                'path': [[x, y] for x, y in path],
                'physical_path': physical_path,
                'length_px': max(0, len(path) - 1),
                'length_physical': sum(
                    math.dist(physical_path[index - 1], physical_path[index])
                    for index in range(1, len(physical_path))
                ),
            }
            edges.append(edge)
            if region_a > 0:
                region_edge_ids[region_a].append(edge_id)
            if region_b > 0:
                region_edge_ids[region_b].append(edge_id)

    region_ids = sorted(int(value) for value in np.unique(labels) if int(value) > 0)
    return {
        'vertex_count': len(vertices),
        'edge_count': len(edges),
        'vertices': vertices,
        'edges': edges,
        'regions': [
            {'region_id': region_id, 'edge_ids': region_edge_ids.get(region_id, [])}
            for region_id in region_ids
        ],
    }


def coverage_summary(
    regions: list[Region],
    physical_size: PhysicalSize,
    image_size: tuple[int, int],
) -> dict[str, Any]:
    """Validate independently exported region polygons as a Shapely coverage."""

    px_per_unit_x, px_per_unit_y = physical_size.pixels_per_unit(image_size)
    polygons = []
    skipped_region_ids = []
    for region in regions:
        points = [
            (x / max(px_per_unit_x, 1e-9), y / max(px_per_unit_y, 1e-9))
            for x, y in region.contour
        ]
        polygon = Polygon(points)
        if polygon.is_empty or not polygon.is_valid or polygon.area <= 0:
            skipped_region_ids.append(region.region_id)
            continue
        polygons.append(polygon)
    if not polygons:
        return {
            'valid': False,
            'polygon_count': 0,
            'skipped_region_ids': skipped_region_ids,
            'invalid_edge_count': 0,
            'invalid_edge_length': 0.0,
        }
    valid = bool(coverage_is_valid(polygons))
    invalid_edges = coverage_invalid_edges(polygons)
    invalid_edge_lengths = [
        float(edge.length)
        for edge in invalid_edges
        if not edge.is_empty
    ]
    return {
        'valid': valid and not skipped_region_ids,
        'polygon_count': len(polygons),
        'skipped_region_ids': skipped_region_ids,
        'invalid_edge_count': len(invalid_edge_lengths),
        'invalid_edge_length': sum(invalid_edge_lengths),
    }


def _region_polygon(
    region: Region,
    physical_size: PhysicalSize,
    image_size: tuple[int, int],
) -> Polygon | None:
    px_per_unit_x, px_per_unit_y = physical_size.pixels_per_unit(image_size)
    points = [
        (x / max(px_per_unit_x, 1e-9), y / max(px_per_unit_y, 1e-9))
        for x, y in region.contour
    ]
    polygon = Polygon(points)
    if polygon.is_empty or not polygon.is_valid or polygon.area <= 0:
        return None
    return polygon


def _physical_path(points: list[tuple[float, float]]) -> str:
    if len(points) < 3:
        return ''
    commands = [f'M {points[0][0]:.4f} {points[0][1]:.4f}']
    for x, y in points[1:]:
        commands.append(f'L {x:.4f} {y:.4f}')
    commands.append('Z')
    return ' '.join(commands)


def coverage_simplified_svg(
    regions: list[Region],
    physical_size: PhysicalSize,
    image_size: tuple[int, int],
    tolerance: float,
) -> str:
    """Export a Shapely coverage-simplified SVG with shared edges preserved."""

    polygons = []
    polygon_regions = []
    skipped = []
    for region in regions:
        polygon = _region_polygon(region, physical_size, image_size)
        if polygon is None:
            skipped.append(region.region_id)
            continue
        polygons.append(polygon)
        polygon_regions.append(region)
    if skipped:
        raise ValueError(f'cannot coverage-simplify invalid regions: {skipped}')
    if not coverage_is_valid(polygons):
        raise ValueError('region polygons are not a valid coverage')
    simplified = coverage_simplify(polygons, tolerance=max(0.0, float(tolerance)))
    groups: dict[str, list[str]] = defaultdict(list)
    for region, polygon in zip(polygon_regions, simplified, strict=True):
        path = _physical_path([(float(x), float(y)) for x, y in polygon.exterior.coords])
        if not path:
            continue
        groups[region.veneer_id].append(
            f'<path id="region-{region.region_id}" d="{path}" '
            f'fill="#{region.color_rgb[0]:02x}{region.color_rgb[1]:02x}{region.color_rgb[2]:02x}" '
            'stroke="#111" stroke-width="0.01" '
            f'data-region-id="{region.region_id}" data-veneer-id="{escape(region.veneer_id)}" '
            'data-coverage-simplified="true" />'
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


def simplify_topology_graph(
    graph: dict[str, Any],
    tolerance: float,
    physical_size: PhysicalSize,
    image_size: tuple[int, int],
) -> dict[str, Any]:
    """Return a copy of a topology graph with simplified edge paths."""

    simplified = json_safe_graph(graph)
    vertices_by_id = {vertex['vertex_id']: vertex for vertex in simplified['vertices']}
    for edge in simplified['edges']:
        path = edge['path']
        if len(path) > 2 and tolerance > 0:
            simplified_path = approximate_polygon(np.asarray(path, dtype=float), tolerance)
            path = [[float(x), float(y)] for x, y in simplified_path]
        else:
            path = [[float(x), float(y)] for x, y in path]
        # Preserve endpoints exactly so adjacency references remain stable.
        start_vertex = vertices_by_id[edge['vertex_ids'][0]]
        end_vertex = vertices_by_id[edge['vertex_ids'][-1]]
        path[0] = [float(start_vertex['point'][0]), float(start_vertex['point'][1])]
        path[-1] = [float(end_vertex['point'][0]), float(end_vertex['point'][1])]
        edge['path'] = path
    return reindex_topology_graph(simplified, physical_size, image_size)


def reindex_topology_graph(
    graph: dict[str, Any],
    physical_size: PhysicalSize,
    image_size: tuple[int, int],
) -> dict[str, Any]:
    """Rebuild vertex IDs and physical edge metadata from edge paths."""

    px_per_unit_x, px_per_unit_y = physical_size.pixels_per_unit(image_size)
    cleaned = json_safe_graph(graph)
    vertex_ids: dict[tuple[float, float], int] = {}
    vertices = []

    def vertex_id(point: list[float]) -> int:
        key = (round(float(point[0]), 6), round(float(point[1]), 6))
        if key not in vertex_ids:
            next_id = len(vertex_ids) + 1
            vertex_ids[key] = next_id
            vertices.append(
                {
                    'vertex_id': next_id,
                    'point': [key[0], key[1]],
                    'physical_point': [
                        key[0] / max(px_per_unit_x, 1e-9),
                        key[1] / max(px_per_unit_y, 1e-9),
                    ],
                }
            )
        return vertex_ids[key]

    for edge in cleaned['edges']:
        path = [[float(x), float(y)] for x, y in edge['path']]
        edge['path'] = path
        edge['vertex_ids'] = [vertex_id(point) for point in path]
        edge['length_px'] = sum(
            math.dist(path[index - 1], path[index]) for index in range(1, len(path))
        )
        physical_path = [
            [
                point[0] / max(px_per_unit_x, 1e-9),
                point[1] / max(px_per_unit_y, 1e-9),
            ]
            for point in path
        ]
        edge['physical_path'] = physical_path
        edge['length_physical'] = sum(
            math.dist(physical_path[index - 1], physical_path[index])
            for index in range(1, len(physical_path))
        )
    cleaned['vertices'] = vertices
    cleaned['vertex_count'] = len(vertices)
    cleaned['edge_count'] = len(cleaned['edges'])
    return cleaned


def _graph_polygons(
    graph: dict[str, Any],
    labels: np.ndarray,
    physical_size: PhysicalSize,
) -> list[tuple[int, Polygon]]:
    px_per_unit_x, px_per_unit_y = physical_size.pixels_per_unit(
        (labels.shape[1], labels.shape[0])
    )
    lines = []
    for edge in graph['edges']:
        path = edge['path']
        if len(path) < 2:
            continue
        lines.append(
            LineString(
                [
                    (
                        float(x) / max(px_per_unit_x, 1e-9),
                        float(y) / max(px_per_unit_y, 1e-9),
                    )
                    for x, y in path
                ]
            )
        )

    polygons: list[tuple[int, Polygon]] = []
    for polygon in polygonize(lines):
        if polygon.is_empty or not polygon.is_valid or polygon.area <= 0:
            continue
        sample = polygon.representative_point()
        x = max(0, min(labels.shape[1] - 1, int(sample.x * px_per_unit_x)))
        y = max(0, min(labels.shape[0] - 1, int(sample.y * px_per_unit_y)))
        region_id = int(labels[y, x])
        if region_id > 0:
            polygons.append((region_id, polygon))
    return polygons


def graph_region_polygons(
    graph: dict[str, Any],
    labels: np.ndarray,
    physical_size: PhysicalSize,
) -> list[dict[str, Any]]:
    """Return filled region polygons reconstructed from graph linework."""

    return [
        {
            'region_id': region_id,
            'area_physical': float(polygon.area),
            'bounds': [float(value) for value in polygon.bounds],
            'physical_contour': [
                [float(x), float(y)] for x, y in polygon.exterior.coords
            ],
            'physical_svg_path': _physical_path(
                [(float(x), float(y)) for x, y in polygon.exterior.coords]
            ),
        }
        for region_id, polygon in _graph_polygons(graph, labels, physical_size)
    ]


def validate_topology_graph(
    graph: dict[str, Any],
    labels: np.ndarray,
    physical_size: PhysicalSize,
    area_tolerance: float = 0.01,
) -> dict[str, Any]:
    """Validate that graph linework reconstructs one non-overlapping full puzzle."""

    polygons = _graph_polygons(graph, labels, physical_size)
    region_ids = [int(value) for value in np.unique(labels) if int(value) > 0]
    polygon_region_ids = [region_id for region_id, _polygon in polygons]
    duplicate_region_ids = sorted(
        region_id
        for region_id in set(polygon_region_ids)
        if polygon_region_ids.count(region_id) > 1
    )
    missing_region_ids = sorted(set(region_ids) - set(polygon_region_ids))
    extra_region_ids = sorted(set(polygon_region_ids) - set(region_ids))
    shapely_polygons = [polygon for _region_id, polygon in polygons]
    coverage_valid = bool(shapely_polygons) and bool(coverage_is_valid(shapely_polygons))
    union = unary_union(shapely_polygons) if shapely_polygons else Polygon()
    expected_area = physical_size.width * physical_size.height
    area_delta = abs(float(union.area) - expected_area)
    valid = (
        coverage_valid
        and not duplicate_region_ids
        and not missing_region_ids
        and not extra_region_ids
        and area_delta <= max(area_tolerance, expected_area * 0.01)
    )
    return {
        'valid': valid,
        'polygon_count': len(polygons),
        'region_count': len(region_ids),
        'coverage_valid': coverage_valid,
        'duplicate_region_ids': duplicate_region_ids,
        'missing_region_ids': missing_region_ids,
        'extra_region_ids': extra_region_ids,
        'union_area': float(union.area),
        'expected_area': expected_area,
        'area_delta': area_delta,
    }


def move_topology_vertex(
    graph: dict[str, Any],
    vertex_id: int,
    point: tuple[float, float],
    physical_size: PhysicalSize,
    image_size: tuple[int, int],
) -> dict[str, Any]:
    """Move one graph vertex everywhere it appears and rebuild graph metadata."""

    moved = json_safe_graph(graph)
    vertex_id = int(vertex_id)
    next_point = [float(point[0]), float(point[1])]
    touched = False
    for edge in moved['edges']:
        for index, edge_vertex_id in enumerate(edge['vertex_ids']):
            if int(edge_vertex_id) == vertex_id:
                edge['path'][index] = next_point
                touched = True
    if not touched:
        raise ValueError(f'vertex not found: {vertex_id}')
    return reindex_topology_graph(moved, physical_size, image_size)


def simplify_topology_edges(
    graph: dict[str, Any],
    edge_ids: set[int],
    tolerance: float,
    physical_size: PhysicalSize,
    image_size: tuple[int, int],
) -> dict[str, Any]:
    """Simplify selected graph edges while keeping all other edge paths unchanged."""

    edited = json_safe_graph(graph)
    selected = {int(edge_id) for edge_id in edge_ids}
    for edge in edited['edges']:
        if int(edge['edge_id']) not in selected:
            continue
        path = edge['path']
        if len(path) <= 2 or tolerance <= 0:
            continue
        simplified_path = approximate_polygon(np.asarray(path, dtype=float), tolerance)
        path = [[float(x), float(y)] for x, y in simplified_path]
        path[0] = edge['path'][0]
        path[-1] = edge['path'][-1]
        edge['path'] = path
    return reindex_topology_graph(edited, physical_size, image_size)


def json_safe_graph(graph: dict[str, Any]) -> dict[str, Any]:
    """Round-trip a graph through plain JSON-compatible objects."""

    return {
        'vertex_count': int(graph['vertex_count']),
        'edge_count': int(graph['edge_count']),
        'vertices': [dict(vertex) for vertex in graph['vertices']],
        'edges': [
            {
                **dict(edge),
                'vertex_ids': [int(value) for value in edge['vertex_ids']],
                'path': [[float(x), float(y)] for x, y in edge['path']],
                'physical_path': [
                    [float(x), float(y)] for x, y in edge.get('physical_path', [])
                ],
            }
            for edge in graph['edges']
        ],
        'regions': [
            {
                'region_id': int(region['region_id']),
                'edge_ids': [int(edge_id) for edge_id in region['edge_ids']],
            }
            for region in graph['regions']
        ],
    }


def graph_to_svg(
    graph: dict[str, Any],
    labels: np.ndarray,
    regions: list[Region],
    physical_size: PhysicalSize,
) -> str:
    """Reconstruct region polygons from topology graph edges and export SVG."""

    px_per_unit_x, px_per_unit_y = physical_size.pixels_per_unit(
        (labels.shape[1], labels.shape[0])
    )
    region_by_id = {region.region_id: region for region in regions}
    lines = []
    for edge in graph['edges']:
        path = edge['path']
        if len(path) < 2:
            continue
        physical_path = [
            (
                float(x) / max(px_per_unit_x, 1e-9),
                float(y) / max(px_per_unit_y, 1e-9),
            )
            for x, y in path
        ]
        lines.append(LineString(physical_path))

    groups: dict[str, list[str]] = defaultdict(list)
    for polygon in polygonize(lines):
        if polygon.is_empty or polygon.area <= 0:
            continue
        sample = polygon.representative_point()
        x = max(0, min(labels.shape[1] - 1, int(sample.x * px_per_unit_x)))
        y = max(0, min(labels.shape[0] - 1, int(sample.y * px_per_unit_y)))
        region_id = int(labels[y, x])
        region = region_by_id.get(region_id)
        if region is None:
            continue
        path = _physical_path([(float(x), float(y)) for x, y in polygon.exterior.coords])
        if not path:
            continue
        groups[region.veneer_id].append(
            f'<path id="region-{region.region_id}" d="{path}" '
            f'fill="#{region.color_rgb[0]:02x}{region.color_rgb[1]:02x}{region.color_rgb[2]:02x}" '
            'stroke="#111" stroke-width="0.01" '
            f'data-region-id="{region.region_id}" data-veneer-id="{escape(region.veneer_id)}" '
            'data-graph-reconstructed="true" />'
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
        shortest_side = min(width_physical, height_physical)
        longest_side = max(width_physical, height_physical)
        if shortest_side < 0.08:
            warnings.append('thin')
        if area_px * area_scale < 0.05:
            warnings.append('small')
        if longest_side / max(shortest_side, 1e-9) > 8:
            warnings.append('high-aspect')
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
