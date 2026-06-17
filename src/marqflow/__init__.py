"""Marqflow: region-based marquetry planning tools."""

from .config import SegmentationConfig, SuperpixelConfig
from .pipeline import build_region_map, build_superpixel_preview, prepare_image
from .regions import Region, RegionMap

__all__ = [
    'Region',
    'RegionMap',
    'SegmentationConfig',
    'SuperpixelConfig',
    'build_region_map',
    'build_superpixel_preview',
    'prepare_image',
]
