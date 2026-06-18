import json
from pathlib import Path

import numpy as np
from fastapi.testclient import TestClient
from PIL import Image

from marqflow.gallery_web import create_app
from marqflow.workspace import GridWorkspace


def test_grid_workspace_gallery_flow(tmp_path: Path) -> None:
    image = np.zeros((48, 48, 3), dtype=np.uint8)
    image[:24, :24] = [88, 88, 88]
    image[:24, 24:] = [104, 104, 104]
    image[24:, :24] = [120, 120, 120]
    image[24:, 24:] = [136, 136, 136]

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
    manifest = json.loads((workspace_dir / 'workspace.json').read_text(encoding='utf-8'))
    assert not Path(manifest['source_image_path']).is_absolute()
    assert not Path(manifest['candidates'][0]['project_dir']).is_absolute()
    assert not Path(manifest['candidates'][0]['preview_path']).is_absolute()
    assert not Path(manifest['candidates'][0]['thumb_path']).is_absolute()

    reloaded = GridWorkspace.load(workspace_dir)
    assert reloaded.source_image_path.exists()
    assert reloaded.candidates[0].thumb_path.exists()

    client = TestClient(create_app(workspace_dir))

    summary = client.get('/api/workspace').json()
    assert summary['candidate_count'] == 9
    assert summary['active_candidate_id']
    assert summary['active_candidate']['preview_path']
    assert summary['composite_base_candidate_id']
    assert summary['candidates'][0]['thumb_url'].endswith('/thumb')

    active_id = summary['active_candidate_id']
    candidate = client.get(f'/api/workspace/candidates/{active_id}').json()
    assert candidate['regions']
    assert candidate['preview_url'].endswith('/preview')
    assert candidate['svg_url'].endswith('/svg')
    assert client.get(candidate['thumb_url']).status_code == 200

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

    kept_summary = client.get('/api/workspace').json()
    kept_id = kept_summary['active_candidate_id']
    second_id = kept_summary['candidates'][1]['candidate_id']
    assert client.post('/api/workspace/keep', json={'candidate_id': second_id}).status_code == 200

    kept_detail = client.get(f'/api/workspace/candidates/{kept_id}').json()
    second_detail = client.get(f'/api/workspace/candidates/{second_id}').json()
    paint_all_response = client.post(
        '/api/workspace/selection',
        json={
            'candidate_id': kept_id,
            'region_ids': [region['region_id'] for region in kept_detail['regions']],
            'additive': False,
        },
    )
    assert paint_all_response.status_code == 200

    clear_response = client.post('/api/workspace/selection/clear', json={'candidate_id': kept_id})
    assert clear_response.status_code == 200
    assert clear_response.json()['active_candidate']['selected_region_ids'] == []

    second_paint_response = client.post(
        '/api/workspace/selection',
        json={
            'candidate_id': second_id,
            'region_ids': [region['region_id'] for region in second_detail['regions']],
            'additive': False,
        },
    )
    assert second_paint_response.status_code == 200

    composite_preview = client.get('/api/workspace/composite/preview?merge_threshold=0')
    assert composite_preview.status_code == 200
    assert composite_preview.headers['content-type'].startswith('image/png')

    merged_preview = client.get('/api/workspace/composite/preview?merge_threshold=80')
    assert merged_preview.status_code == 200
    assert merged_preview.headers['content-type'].startswith('image/png')
    assert merged_preview.content != composite_preview.content

    composite_summary = client.get('/api/workspace/composite/summary?merge_threshold=80')
    assert composite_summary.status_code == 200
    assert composite_summary.json()['path_count'] <= client.get(
        '/api/workspace/composite/summary?merge_threshold=0'
    ).json()['path_count']

    composite_svg = client.get('/api/workspace/composite/svg?merge_threshold=24')
    assert composite_svg.status_code == 200
    assert '<svg' in composite_svg.text

    export_dir = tmp_path / 'exported'
    export_response = client.post(
        '/api/workspace/composite/export',
        json={'output_dir': str(export_dir), 'merge_threshold': 24},
    )
    assert export_response.status_code == 200
    export_payload = export_response.json()
    assert Path(export_payload['composite_png']).exists()
    assert Path(export_payload['composite_svg']).exists()
