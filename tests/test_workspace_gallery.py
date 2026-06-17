from pathlib import Path

import numpy as np
from fastapi.testclient import TestClient
from PIL import Image

from marqflow.gallery_web import create_app
from marqflow.workspace import GridWorkspace


def test_grid_workspace_gallery_flow(tmp_path: Path) -> None:
    image = np.zeros((48, 48, 3), dtype=np.uint8)
    image[:24, :24] = [255, 0, 0]
    image[:24, 24:] = [0, 255, 0]
    image[24:, :24] = [0, 0, 255]
    image[24:, 24:] = [255, 255, 0]

    input_path = tmp_path / 'source.png'
    Image.fromarray(image, mode='RGB').save(input_path)

    workspace_dir = tmp_path / 'workspace'
    workspace = GridWorkspace.create(
        input_path,
        workspace_dir,
        segment_levels=(4, 6, 8),
        smoothness_levels=(1.0, 3.0, 5.0),
        max_working_edge=48,
    )

    assert len(workspace.candidates) == 9

    client = TestClient(create_app(workspace_dir))

    summary = client.get('/api/workspace').json()
    assert summary['candidate_count'] == 9
    assert summary['active_candidate_id']
    assert summary['active_candidate']['preview_path']

    active_id = summary['active_candidate_id']
    candidate = client.get(f'/api/workspace/candidates/{active_id}').json()
    assert candidate['regions']
    assert candidate['preview_url'].endswith('/preview')
    assert candidate['svg_url'].endswith('/svg')

    selected_ids = [candidate['regions'][0]['region_id']]
    if len(candidate['regions']) > 1:
        selected_ids.append(candidate['regions'][1]['region_id'])

    selection_response = client.post(
        '/api/workspace/selection',
        json={
            'candidate_id': active_id,
            'region_ids': selected_ids,
            'additive': False,
        },
    )
    assert selection_response.status_code == 200
    updated = selection_response.json()
    assert updated['active_candidate']['selected_region_ids'] == sorted(selected_ids)

    keep_response = client.post('/api/workspace/keep', json={'candidate_id': active_id})
    assert keep_response.status_code == 200

    export_dir = tmp_path / 'exported'
    export_response = client.post('/api/workspace/export', json={'output_dir': str(export_dir)})
    assert export_response.status_code == 200
    export_payload = export_response.json()
    assert Path(export_payload['composite_png']).exists()
    assert Path(export_payload['composite_svg']).exists()
