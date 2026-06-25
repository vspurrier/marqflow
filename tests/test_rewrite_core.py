from __future__ import annotations

from pathlib import Path

import numpy as np
from fastapi.testclient import TestClient
from PIL import Image

from marqflow.gallery_web import create_app
from marqflow.models import PhysicalSize, Veneer
from marqflow.workspace import MarquetryWorkspace


def _fixture_image(path: Path) -> None:
    image = np.zeros((48, 48, 3), dtype=np.uint8)
    image[:24, :24] = [225, 205, 165]
    image[:24, 24:] = [150, 90, 55]
    image[24:, :24] = [80, 55, 38]
    image[24:, 24:] = [30, 28, 25]
    Image.fromarray(image, mode='RGB').save(path)


def test_workspace_creates_valid_design_and_exports(tmp_path: Path) -> None:
    image_path = tmp_path / 'source.png'
    _fixture_image(image_path)

    workspace = MarquetryWorkspace.create(image_path, tmp_path / 'workspace', max_edge=64)
    candidate = workspace.generate_candidate(target_regions=4, compactness=8.0)
    workspace.create_design(candidate.candidate_id, PhysicalSize(width=8, height=8, unit='in'))

    summary = workspace.summary()
    assert summary['validation']['valid'] is True
    assert summary['validation']['region_count'] >= 2
    assert summary['regions']
    assert all(region['veneer_id'] for region in summary['regions'])

    first_region_id = summary['regions'][0]['region_id']
    workspace.assign_veneer(first_region_id, 'walnut')
    assert workspace.summary()['regions'][0]['veneer_id'] == 'walnut'

    svg_path = workspace.export_svg(tmp_path / 'design.svg')
    svg = svg_path.read_text(encoding='utf-8')
    assert '<svg' in svg
    assert 'data-veneer-id=' in svg
    assert 'width="8in"' in svg

    manifest = workspace.pack(tmp_path / 'packed')
    assert manifest['packing_backend'] == 'simple-grouped-manifest'
    assert manifest['sheets']
    assert (tmp_path / 'packed' / 'pack.json').exists()
    assert (tmp_path / 'packed' / 'design.svg').exists()


def test_stock_overage_is_reported(tmp_path: Path) -> None:
    image_path = tmp_path / 'source.png'
    _fixture_image(image_path)
    workspace = MarquetryWorkspace.create(image_path, tmp_path / 'workspace', max_edge=64)
    candidate = workspace.generate_candidate(target_regions=4, compactness=8.0)
    workspace.create_design(
        candidate.candidate_id,
        PhysicalSize(width=8, height=8, unit='in'),
        veneers=[Veneer('tiny', 'Tiny stock', (200, 180, 150), sheet_count=0)],
    )
    for region in workspace.regions():
        workspace.assign_veneer(region['region_id'], 'tiny')

    manifest = workspace.pack(tmp_path / 'packed')
    assert manifest['sheets'][0]['available_sheet_count'] == 0
    assert manifest['sheets'][0]['over_stock_capacity'] is False


def test_api_vertical_slice(tmp_path: Path) -> None:
    image_path = tmp_path / 'source.png'
    _fixture_image(image_path)
    client = TestClient(create_app(tmp_path / 'workspace'))

    assert client.get('/').status_code == 200
    assert client.get('/static/gallery.css').status_code == 200
    assert client.get('/api/workspace').status_code == 404

    response = client.post(
        '/api/workspace/open-image',
        files={'image': ('source.png', image_path.read_bytes(), 'image/png')},
        data={'target_regions': '4', 'compactness': '8'},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload['validation']['valid'] is True
    assert payload['candidates'][0]['region_count'] >= 2
    assert payload['regions']

    region_id = payload['regions'][0]['region_id']
    veneer_id = payload['design']['veneers'][0]['veneer_id']
    assign_response = client.post(
        '/api/design/veneer',
        json={'region_id': region_id, 'veneer_id': veneer_id},
    )
    assert assign_response.status_code == 200
    assert assign_response.json()['regions'][0]['veneer_id'] == veneer_id

    svg_response = client.get('/api/design.svg')
    assert svg_response.status_code == 200
    assert svg_response.headers['content-type'].startswith('image/svg+xml')

    pack_response = client.post('/api/pack', json={'output_dir': str(tmp_path / 'packed')})
    assert pack_response.status_code == 200
    assert pack_response.json()['sheets']
