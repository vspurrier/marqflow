"""High-level marquetry preparation pipeline."""

from __future__ import annotations

from pathlib import Path

import numpy as np
from skimage.segmentation import slic

from .config import SegmentationConfig
from .image import downscale_image, load_rgb_image, save_rgb_image
from .regions import RegionMap, build_regions, labels_to_palette_image
from .svg import region_map_to_svg


def prepare_image(input_path: str | Path, config: SegmentationConfig) -> np.ndarray:
    """Load and downscale the source image."""

    config.validate()
    image_rgb = load_rgb_image(input_path)
    return downscale_image(image_rgb, config.downscale_factor)


def build_region_map(input_path: str | Path, config: SegmentationConfig) -> RegionMap:
    """Prepare a region map from a raster image."""

    image_rgb = prepare_image(input_path, config)
    labels = slic(
        image_rgb,
        n_segments=config.superpixels.target_segments,
        compactness=config.superpixels.compactness,
        sigma=config.superpixels.sigma,
        start_label=1,
        convert2lab=True,
    )
    regions = build_regions(image_rgb, labels)
    return RegionMap(
        image_rgb=image_rgb,
        labels=labels,
        regions=regions,
        source_path=Path(input_path),
    )


def build_superpixel_preview(region_map: RegionMap) -> np.ndarray:
    """Generate a flat-color preview of the segmentation."""

    return labels_to_palette_image(region_map.image_rgb, region_map.labels)


def write_pipeline_outputs(
    input_path: str | Path,
    output_dir: str | Path,
    config: SegmentationConfig,
) -> RegionMap:
    """Write the main derived artifacts for the current pipeline state."""

    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    region_map = build_region_map(input_path, config)
    preview = build_superpixel_preview(region_map)

    save_rgb_image(output_path / 'preview.png', preview)
    (output_path / 'regions.svg').write_text(region_map_to_svg(region_map), encoding='utf-8')
    return region_map
