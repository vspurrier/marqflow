from pathlib import Path

import numpy as np
from fastapi.testclient import TestClient
from PIL import Image

from marqflow.config import SegmentationConfig, SuperpixelConfig
from marqflow.pipeline import build_region_map, build_superpixel_preview
from marqflow.project import MarqflowProject
from marqflow.regions import build_region_neighbors
from marqflow.svg import region_map_to_svg
from marqflow.web import create_app


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


def test_browser_app_routes_support_edits(tmp_path: Path) -> None:
    image = np.zeros((32, 32, 3), dtype=np.uint8)
    image[:16, :] = [255, 0, 0]
    image[16:, :] = [0, 0, 255]

    input_path = tmp_path / 'synthetic.png'
    Image.fromarray(image, mode='RGB').save(input_path)

    project_dir = tmp_path / 'project'
    MarqflowProject.create(
        input_path,
        project_dir,
        SegmentationConfig(
            downscale_factor=1,
            superpixels=SuperpixelConfig(target_segments=1, compactness=20.0, sigma=1.0),
        ),
    )

    client = TestClient(create_app(project_dir))
    root = client.get('/')
    assert root.status_code == 200
    assert 'Marqflow' in root.text

    summary = client.get('/api/project').json()
    assert summary['region_count'] >= 1

    split_response = client.post(
        '/api/project/split',
        json={'region_ids': [summary['regions'][0]['region_id']], 'segments': 4},
    )
    assert split_response.status_code == 200
    split_summary = split_response.json()
    assert split_summary['region_count'] >= summary['region_count']

    pair = next(
        (
            (region['region_id'], neighbor)
            for region in split_summary['regions']
            for neighbor in region['neighbors']
        ),
        None,
    )
    assert pair is not None

    merge_response = client.post('/api/project/merge', json={'region_ids': list(pair)})
    assert merge_response.status_code == 200
    merged_summary = merge_response.json()
    assert merged_summary['region_count'] <= split_summary['region_count']
