"""SVG serialization for region maps."""

from __future__ import annotations

from xml.etree import ElementTree as ET

from .regions import RegionMap


def _path_data(points: tuple[tuple[float, float], ...]) -> str:
    if not points:
        return ''

    commands = [f'M{points[0][0]:.2f},{points[0][1]:.2f}']
    for x, y in points[1:]:
        commands.append(f'L{x:.2f},{y:.2f}')
    commands.append('Z')
    return ' '.join(commands)


def region_map_to_svg(region_map: RegionMap) -> str:
    """Convert a region map to a standalone SVG string."""

    width, height = region_map.size
    svg = ET.Element(
        'svg',
        {
            'xmlns': 'http://www.w3.org/2000/svg',
            'version': '1.1',
            'width': str(width),
            'height': str(height),
            'viewBox': f'0 0 {width} {height}',
        },
    )

    for region in region_map.regions:
        if len(region.contour) < 3:
            continue
        ET.SubElement(
            svg,
            'path',
            {
                'd': _path_data(region.contour),
                'fill': region.fill,
                'data-region-id': str(region.region_id),
                'data-area': str(region.area),
            },
        )

    return ET.tostring(svg, encoding='unicode')
