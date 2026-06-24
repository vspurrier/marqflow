"""Packing adapter for final marquetry regions.

This module intentionally keeps nesting behind a small seam so the design model
can stay stable if the packing backend changes. The built-in backend creates
deterministic bounding-box sheets with traceable piece paths. For real
irregular nesting, set ``MARQFLOW_NESTER_CMD`` to a command that accepts
``{input}`` and ``{output}`` placeholders and writes a nested SVG.
"""

from __future__ import annotations

import os
import shlex
import subprocess
import tempfile
from collections import defaultdict
from html import escape
from pathlib import Path
from typing import Any

import numpy as np
from shapely import affinity
from shapely.geometry import Polygon

from .marquetry import (
    DesignRegion,
    PhysicalSize,
    VeneerSwatch,
    _render_sheet_svg,
    build_design_regions,
    default_veneer_palette,
    labels_to_svg_path,
    sheet_size_for_veneer,
)
from .marquetry import pack_region_sheets as _pack_region_sheets

EXTERNAL_NESTER_ENV = 'MARQFLOW_NESTER_CMD'


def _physical_contour(
    contour: tuple[tuple[float, float], ...],
    px_per_unit_x: float,
    px_per_unit_y: float,
) -> tuple[tuple[float, float], ...]:
    return tuple(
        (
            float(point_x) / max(1.0, px_per_unit_x),
            float(point_y) / max(1.0, px_per_unit_y),
        )
        for point_x, point_y in contour
    )


def _piece_record(
    region: DesignRegion,
    veneer_id: str,
    px_per_unit_x: float,
    px_per_unit_y: float,
) -> dict[str, Any]:
    x0, y0, x1, y1 = region.bbox
    contour = _physical_contour(region.contour, px_per_unit_x, px_per_unit_y)
    return {
        'region_id': region.region_id,
        'source_refs': [list(ref) for ref in region.source_refs],
        'x': None,
        'y': None,
        'width': max(1.0, float(x1 - x0) / max(1.0, px_per_unit_x)),
        'height': max(1.0, float(y1 - y0) / max(1.0, px_per_unit_y)),
        'origin_x': float(x0) / max(1.0, px_per_unit_x),
        'origin_y': float(y0) / max(1.0, px_per_unit_y),
        'veneer_id': veneer_id,
        'contour': contour,
        'fill': '#{:02x}{:02x}{:02x}'.format(*region.color_rgb),
        'bin_index': None,
        'placement_known': False,
    }


def _safe_polygon(points: tuple[tuple[float, float], ...]) -> Polygon | None:
    if len(points) < 3:
        return None
    polygon = Polygon(points)
    if not polygon.is_valid:
        polygon = polygon.buffer(0)
    if polygon.is_empty:
        return None
    return polygon


def _annotate_sheet_metrics(sheets: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Add geometry metrics to packed sheets without changing placements."""

    for sheet in sheets:
        placed_polygons = []
        piece_area = 0.0
        for piece in sheet.get('pieces', []):
            polygon = _safe_polygon(tuple((float(x), float(y)) for x, y in piece['contour']))
            if polygon is None:
                continue
            piece_area += float(polygon.area)
            if piece.get('x') is None or piece.get('y') is None:
                continue
            polygon = affinity.translate(
                polygon,
                xoff=float(piece['x']) - float(piece['origin_x']),
                yoff=float(piece['y']) - float(piece['origin_y']),
            )
            placed_polygons.append(polygon)

        overlap_area = 0.0
        for index, left in enumerate(placed_polygons):
            for right in placed_polygons[index + 1 :]:
                if left.bounds[2] < right.bounds[0] or right.bounds[2] < left.bounds[0]:
                    continue
                intersection = left.intersection(right)
                if not intersection.is_empty:
                    overlap_area += float(intersection.area)

        sheet_area = max(0.0, float(sheet['sheet_width']) * float(sheet['sheet_height']))
        sheet['piece_area'] = piece_area
        sheet['utilization'] = piece_area / sheet_area if sheet_area else 0.0
        sheet['overlap_area'] = overlap_area
        sheet['placement_valid'] = overlap_area <= 1e-6
    return sheets


def _split_rectpack_bins(sheets: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Convert rectpack bins into separate physical sheet records."""

    split_sheets: list[dict[str, Any]] = []
    for sheet in sheets:
        pieces_by_bin: dict[int, list[dict[str, Any]]] = defaultdict(list)
        for piece in sheet.get('pieces', []):
            pieces_by_bin[int(piece.get('bin_index') or 0)].append(piece)
        if len(pieces_by_bin) <= 1:
            split_sheets.append(sheet)
            continue
        for bin_index, pieces in sorted(pieces_by_bin.items()):
            split_sheet = dict(sheet)
            split_sheet['source_bin_index'] = bin_index
            split_sheet['pieces'] = pieces
            split_sheet['sheet_svg'] = _render_sheet_svg(
                float(sheet['sheet_width']),
                float(sheet['sheet_height']),
                pieces,
            )
            split_sheets.append(split_sheet)
    return split_sheets


def _nest_input_svg(
    veneer_id: str,
    pieces: list[dict[str, Any]],
    sheet_width: float,
    sheet_height: float,
) -> str:
    paths = [
        f'<rect id="sheet-{escape(veneer_id)}" x="0" y="0" '
        f'width="{sheet_width}" height="{sheet_height}" fill="none" '
        'stroke="#222" data-marqflow-role="sheet" />'
    ]
    for piece in pieces:
        path = labels_to_svg_path(tuple((float(x), float(y)) for x, y in piece['contour']))
        paths.append(
            f'<path id="piece-{piece["region_id"]}" d="{path}" '
            f'fill="{piece["fill"]}" stroke="#111" stroke-width="0.2" '
            f'data-region-id="{piece["region_id"]}" '
            f'data-veneer-id="{escape(str(piece["veneer_id"]))}" '
            f'data-origin-x="{piece["origin_x"]:.6f}" '
            f'data-origin-y="{piece["origin_y"]:.6f}" />'
        )
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{sheet_width}" '
        f'height="{sheet_height}" viewBox="0 0 {sheet_width} {sheet_height}">'
        + ''.join(paths)
        + '</svg>'
    )


def _run_external_nester(command_template: str, input_svg: str) -> str:
    with tempfile.TemporaryDirectory(prefix='marqflow-nest-') as tmp_dir:
        tmp_path = Path(tmp_dir)
        input_path = tmp_path / 'input.svg'
        output_path = tmp_path / 'output.svg'
        input_path.write_text(input_svg, encoding='utf-8')

        if '{input}' not in command_template or '{output}' not in command_template:
            raise ValueError(
                f'{EXTERNAL_NESTER_ENV} must include {{input}} and {{output}} placeholders'
            )
        command = command_template.format(input=input_path, output=output_path)
        result = subprocess.run(
            shlex.split(command),
            check=False,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            raise RuntimeError(
                'external nester failed with exit code '
                f'{result.returncode}: {result.stderr.strip() or result.stdout.strip()}'
            )
        if not output_path.exists():
            raise RuntimeError('external nester did not write the expected output SVG')
        return output_path.read_text(encoding='utf-8')


def _pack_with_external_nester(
    image_rgb: np.ndarray,
    labels: np.ndarray,
    physical_size: PhysicalSize,
    palette: list[VeneerSwatch],
    simplify_tolerance: float,
    veneer_overrides: dict[int, str] | None,
    contour_overrides: dict[int, tuple[tuple[float, float], ...]] | None,
    command_template: str,
) -> list[dict[str, Any]]:
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
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for region in regions:
        grouped[region.veneer_id].append(
            _piece_record(region, region.veneer_id, px_per_unit_x, px_per_unit_y)
        )

    fallback_sheet = (
        physical_size.width if physical_size.unit != 'px' else float(labels.shape[1]),
        physical_size.height if physical_size.unit != 'px' else float(labels.shape[0]),
    )
    sheets: list[dict[str, Any]] = []
    for veneer_id, pieces in sorted(grouped.items()):
        sheet_width, sheet_height = sheet_size_for_veneer(
            veneer_id,
            palette,
            physical_size,
            fallback_sheet,
        )
        nest_input_svg = _nest_input_svg(veneer_id, pieces, sheet_width, sheet_height)
        sheet_svg = _run_external_nester(command_template, nest_input_svg)
        sheets.append(
            {
                'veneer_id': veneer_id,
                'sheet_width': sheet_width,
                'sheet_height': sheet_height,
                'pieces': pieces,
                'sheet_svg': sheet_svg,
                'nest_input_svg': nest_input_svg,
                'packing_backend': 'external-svg-nester',
                'external_command': command_template,
            }
        )
    return _annotate_sheet_metrics(sheets)


def pack_region_sheets(
    image_rgb: np.ndarray,
    labels: np.ndarray,
    physical_size: PhysicalSize,
    palette: list[VeneerSwatch] | None = None,
    simplify_tolerance: float = 1.0,
    veneer_overrides: dict[int, str] | None = None,
    contour_overrides: dict[int, tuple[tuple[float, float], ...]] | None = None,
) -> list[dict[str, Any]]:
    """Pack final regions by veneer using the configured packing backend."""

    palette = palette or default_veneer_palette()
    external_command = os.environ.get(EXTERNAL_NESTER_ENV)
    if external_command:
        return _pack_with_external_nester(
            image_rgb,
            labels,
            physical_size=physical_size,
            palette=palette,
            simplify_tolerance=simplify_tolerance,
            veneer_overrides=veneer_overrides,
            contour_overrides=contour_overrides,
            command_template=external_command,
        )

    sheets = _pack_region_sheets(
        image_rgb,
        labels,
        physical_size=physical_size,
        palette=palette,
        simplify_tolerance=simplify_tolerance,
        veneer_overrides=veneer_overrides,
        contour_overrides=contour_overrides,
    )
    sheets = _split_rectpack_bins(sheets)
    for sheet in sheets:
        sheet['packing_backend'] = 'rectpack-bounding-box'
    return _annotate_sheet_metrics(sheets)
