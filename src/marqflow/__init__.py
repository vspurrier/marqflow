"""Marqflow: region-based marquetry planning tools."""

from .config import SegmentationConfig, SuperpixelConfig
from .pipeline import build_region_map, build_superpixel_preview, prepare_image
from .project import MarqflowProject
from .regions import Region, RegionMap
from .workspace import GridCandidate, GridPreset, GridWorkspace

__all__ = [
    'GridCandidate',
    'GridPreset',
    'GridWorkspace',
    'Region',
    'RegionMap',
    'MarqflowProject',
    'SegmentationConfig',
    'SuperpixelConfig',
    'build_region_map',
    'build_superpixel_preview',
    'prepare_image',
]
