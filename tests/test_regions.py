from pathlib import Path

import numpy as np
from PIL import Image

from marqflow.config import SegmentationConfig, SuperpixelConfig
from marqflow.pipeline import build_region_map, build_superpixel_preview
from marqflow.project import MarqflowProject
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


def test_project_split_merge_round_trip(tmp_path: Path) -> None:
    image = np.zeros((32, 32, 3), dtype=np.uint8)
    image[:16, :16] = [255, 0, 0]
    image[:16, 16:] = [0, 255, 0]
    image[16:, :16] = [0, 0, 255]
    image[16:, 16:] = [255, 255, 0]

    input_path = tmp_path / 'synthetic.png'
    Image.fromarray(image, mode='RGB').save(input_path)

    project_dir = tmp_path / 'project'
    project = MarqflowProject.create(
        input_path,
        project_dir,
        SegmentationConfig(downscale_factor=1),
    )
    initial_count = len(project.region_map.regions)

    first_region = project.region_map.regions[0].region_id
    assert project.split_regions([first_region], target_segments=4) == 1

    reloaded = MarqflowProject.load(project_dir)
    split_count = len(reloaded.region_map.regions)
    assert split_count > initial_count

    pair = next(
        (
            (region.region_id, neighbor)
            for region in reloaded.region_map.regions
            for neighbor in region.neighbors
        ),
        None,
    )
    assert pair is not None
    assert reloaded.merge_regions(pair) == 1

    merged = MarqflowProject.load(project_dir)
    assert len(merged.region_map.regions) <= split_count
    assert (project_dir / 'project.json').exists()
    assert (project_dir / 'working.png').exists()
    assert (project_dir / 'labels.npy').exists()


def test_project_lock_state_persists_and_blocks_edits(tmp_path: Path) -> None:
    image = np.zeros((32, 32, 3), dtype=np.uint8)
    image[:16, :] = [255, 0, 0]
    image[16:, :] = [0, 0, 255]

    input_path = tmp_path / 'synthetic.png'
    Image.fromarray(image, mode='RGB').save(input_path)

    project_dir = tmp_path / 'project'
    project = MarqflowProject.create(
        input_path,
        project_dir,
        SegmentationConfig(downscale_factor=1, superpixels=SuperpixelConfig(target_segments=1)),
    )

    region_id = project.region_map.regions[0].region_id
    assert project.lock_regions([region_id]) == 1

    reloaded = MarqflowProject.load(project_dir)
    assert region_id in reloaded.locked_region_ids
    assert reloaded.split_regions([region_id], target_segments=4) == 0
    assert reloaded.merge_regions([region_id]) == 0

    reloaded.unlock_regions([region_id])
    assert region_id not in MarqflowProject.load(project_dir).locked_region_ids
