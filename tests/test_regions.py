from pathlib import Path

import numpy as np

from marqflow.config import SegmentationConfig
from marqflow.pipeline import build_region_map, build_superpixel_preview
from marqflow.regions import build_region_neighbors
from marqflow.svg import region_map_to_svg


def test_build_region_neighbors_detects_shared_edges() -> None:
    labels = np.array([[1, 1, 2], [1, 3, 2], [4, 3, 3]])

    neighbors = build_region_neighbors(labels)

    assert neighbors[1] == {2, 3, 4}
    assert neighbors[2] == {1, 3}
    assert neighbors[3] == {1, 2, 4}
    assert neighbors[4] == {1, 3}


def test_pipeline_builds_region_map_and_svg(tmp_path: Path) -> None:
    image = np.zeros((24, 24, 3), dtype=np.uint8)
    image[:12, :12] = [255, 0, 0]
    image[:12, 12:] = [0, 255, 0]
    image[12:, :12] = [0, 0, 255]
    image[12:, 12:] = [255, 255, 0]

    input_path = tmp_path / 'synthetic.png'
    from PIL import Image

    Image.fromarray(image, mode='RGB').save(input_path)

    config = SegmentationConfig(downscale_factor=1)
    region_map = build_region_map(input_path, config)
    preview = build_superpixel_preview(region_map)
    svg = region_map_to_svg(region_map)

    assert region_map.size == (24, 24)
    assert preview.shape == image.shape
    assert len(region_map.regions) >= 4
    assert svg.startswith('<svg')
    assert svg.count('<path') >= 1
