import json
import sys
import time
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
    assert summary['grid_rows'] == 3
    assert summary['grid_cols'] == 3
    assert summary['physical_size']['unit'] == 'px'
    assert summary['design_summary']['partition_valid'] is True
    first_compactness = summary['candidates'][0]['preset']['compactness']
    last_compactness = summary['candidates'][-1]['preset']['compactness']
    assert first_compactness > last_compactness
    assert summary['candidates'][0]['grid_row'] == 0
    assert summary['candidates'][0]['grid_col'] == 0
    assert summary['candidates'][0]['parent_candidate_id'] is None
    assert summary['active_candidate_id']
    assert summary['active_candidate']['preview_path']
    assert summary['composite_base_candidate_id']
    assert summary['candidates'][0]['thumb_url'].endswith('/thumb')
    assert summary['original_image_size']['width'] == 48
    assert summary['original_image_size']['height'] == 48
    assert summary['source_image_size']['width'] > 0
    assert summary['source_image_size']['height'] > 0
    assert summary['partition_validation']['partition_valid'] is True

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

    persisted = GridWorkspace.load(workspace_dir)
    assert persisted.paint_events
    assert persisted.paint_events[-1].candidate_id == second_id
    assert persisted.paint_events[-1].kind == 'paint'
    assert persisted.composite_design is not None
    assert persisted.composite_design.paint_events
    assert persisted.candidate_by_id(second_id).selected_region_ids == {
        region['region_id'] for region in second_detail['regions']
    }

    first_final_region_id = persisted.summary()['final_regions'][0]['region_id']
    veneer_response = client.post(
        '/api/workspace/final/veneer',
        json={'region_id': first_final_region_id, 'veneer_id': 'blue'},
    )
    assert veneer_response.status_code == 200
    updated_workspace = veneer_response.json()
    first_region = next(
        region
        for region in updated_workspace['final_regions']
        if region['region_id'] == first_final_region_id
    )
    assert first_region['veneer_id'] == 'blue'
    assert first_region['veneer_override_id'] == 'blue'

    duplicate_palette_response = client.post(
        '/api/workspace/veneer-palette',
        json={
            'swatches': [
                {'veneer_id': 'maple', 'name': 'Maple', 'color_rgb': [220, 205, 172]},
                {'veneer_id': 'maple', 'name': 'Duplicate Maple', 'color_rgb': [200, 190, 160]},
            ]
        },
    )
    assert duplicate_palette_response.status_code == 400

    palette_response = client.post(
        '/api/workspace/veneer-palette',
        json={
            'swatches': [
                {
                    'veneer_id': 'maple',
                    'name': 'Maple',
                    'color_rgb': [220, 205, 172],
                    'sheet_width': 0,
                    'sheet_height': 0,
                    'grain_direction': 'vertical',
                    'notes': 'fallback stock size',
                },
                {
                    'veneer_id': 'walnut',
                    'name': 'Walnut',
                    'color_rgb': [80, 55, 38],
                    'sheet_width': 12.0,
                    'sheet_height': 11.0,
                    'grain_direction': 'horizontal',
                    'notes': 'wide test sheet',
                },
            ]
        },
    )
    assert palette_response.status_code == 200
    palette_payload = palette_response.json()
    assert [swatch['veneer_id'] for swatch in palette_payload['veneer_palette']] == [
        'maple',
        'walnut',
    ]
    walnut = next(
        swatch
        for swatch in palette_payload['veneer_palette']
        if swatch['veneer_id'] == 'walnut'
    )
    assert walnut['sheet_width'] == 12.0
    assert walnut['sheet_height'] == 11.0
    assert walnut['grain_direction'] == 'horizontal'
    assert walnut['notes'] == 'wide test sheet'
    assert first_final_region_id not in {
        int(region_id)
        for region_id in palette_payload['composite_design']['final_region_veneer_overrides']
    }

    veneer_response = client.post(
        '/api/workspace/final/veneer',
        json={'region_id': first_final_region_id, 'veneer_id': 'walnut'},
    )
    assert veneer_response.status_code == 200
    first_region = next(
        region
        for region in veneer_response.json()['final_regions']
        if region['region_id'] == first_final_region_id
    )
    assert first_region['veneer_id'] == 'walnut'

    lock_response = client.post(
        '/api/workspace/final/lock',
        json={'region_id': first_final_region_id, 'locked': True},
    )
    assert lock_response.status_code == 200
    locked_region = next(
        region
        for region in lock_response.json()['final_regions']
        if region['region_id'] == first_final_region_id
    )
    assert locked_region['locked'] is True

    blocked_split = client.post(
        '/api/workspace/final/split',
        json={'region_id': first_final_region_id, 'target_segments': 4},
    )
    assert blocked_split.status_code == 404

    assert (
        client.post(
            '/api/workspace/final/lock',
            json={'region_id': first_final_region_id, 'locked': False},
        ).status_code
        == 200
    )

    region_before = next(
        region
        for region in client.get('/api/workspace').json()['final_regions']
        if region['region_id'] == first_final_region_id
    )
    assert region_before['point_count'] > 0
    original_point = region_before['contour'][0]
    point_response = client.post(
        '/api/workspace/final/point',
        json={
            'region_id': first_final_region_id,
            'point_index': 0,
            'x': float(original_point[0]) + 1.0,
            'y': float(original_point[1]) + 1.0,
        },
    )
    assert point_response.status_code == 200
    edited_region = next(
        region
        for region in point_response.json()['final_regions']
        if region['region_id'] == first_final_region_id
    )
    assert edited_region['contour'][0] != original_point

    smooth_response = client.post(
        '/api/workspace/final/smooth',
        json={'region_id': first_final_region_id, 'tolerance': 2.0},
    )
    assert smooth_response.status_code == 200
    smoothed_region = next(
        region
        for region in smooth_response.json()['final_regions']
        if region['region_id'] == first_final_region_id
    )
    assert smoothed_region['point_count'] <= edited_region['point_count']

    size_response = client.post(
        '/api/workspace/size',
        json={'width': 8.0, 'height': 6.0, 'unit': 'in'},
    )
    assert size_response.status_code == 200
    assert size_response.json()['physical_size']['width'] == 8.0
    assert size_response.json()['physical_size']['unit'] == 'in'
    invalid_size_response = client.post(
        '/api/workspace/size',
        json={'width': 0, 'height': 6.0, 'unit': 'in'},
    )
    assert invalid_size_response.status_code == 422

    cleanup_response = client.post(
        '/api/workspace/cleanup',
        json={
            'simplify_tolerance': 1.0,
            'highlight_small_area': 100.0,
            'highlight_thin_width': 100.0,
            'merge_rgb_threshold': 24.0,
        },
    )
    assert cleanup_response.status_code == 200
    cleanup_summary = cleanup_response.json()['design_summary']
    assert cleanup_summary['small_region_ids']
    assert cleanup_summary['thin_region_ids']

    composite_preview = client.get('/api/workspace/composite/preview?merge_threshold=0')
    assert composite_preview.status_code == 200
    assert composite_preview.headers['content-type'].startswith('image/png')

    merged_preview = client.get('/api/workspace/composite/preview?merge_threshold=80')
    assert merged_preview.status_code == 200
    assert merged_preview.headers['content-type'].startswith('image/png')
    assert merged_preview.content != composite_preview.content

    composite_summary = client.get('/api/workspace/composite/summary?merge_threshold=80')
    assert composite_summary.status_code == 200
    summary_payload = composite_summary.json()
    assert (
        summary_payload['path_count']
        <= client.get('/api/workspace/composite/summary?merge_threshold=0').json()['path_count']
    )
    assert 'complex_region_ids' in summary_payload
    assert 'hole_region_ids' in summary_payload
    assert 'disconnected_region_ids' in summary_payload

    hitmap = client.get('/api/workspace/composite/hitmap')
    assert hitmap.status_code == 200
    hitmap_payload = hitmap.json()
    assert hitmap_payload['width'] > 0
    assert hitmap_payload['height'] > 0
    assert hitmap_payload['labels']

    composite_svg = client.get('/api/workspace/composite/svg?merge_threshold=24')
    assert composite_svg.status_code == 200
    assert '<svg' in composite_svg.text
    assert 'width="8.0"' in composite_svg.text
    assert 'height="6.0"' in composite_svg.text

    final_svg = client.get('/api/workspace/composite/svg')
    assert final_svg.status_code == 200
    assert 'id="veneer-walnut"' in final_svg.text
    assert f'data-region-id="{first_final_region_id}"' in final_svg.text
    assert 'data-veneer-id="walnut"' in final_svg.text

    pack_response = client.post(
        '/api/workspace/pack', json={'output_dir': str(tmp_path / 'packed')}
    )
    assert pack_response.status_code == 200
    packed = pack_response.json()['packed_sheets']
    assert packed
    for sheet in packed:
        assert sheet['packing_backend'] == 'rectpack-bounding-box'
        assert sheet['placement_valid'] is True
        assert sheet['utilization'] > 0
        assert Path(sheet['sheet_svg_path']).exists()
    walnut_sheets = [sheet for sheet in packed if sheet['veneer_id'] == 'walnut']
    assert walnut_sheets
    assert all(sheet['sheet_width'] == 12.0 for sheet in walnut_sheets)
    assert all(sheet['sheet_height'] == 11.0 for sheet in walnut_sheets)
    assert (tmp_path / 'packed' / 'pack.json').exists()
    packed_pieces = json.loads((tmp_path / 'packed' / 'pieces.json').read_text())
    assert packed_pieces
    assert {'region_id', 'veneer_id', 'area_physical'} <= set(packed_pieces[0])
    assert (tmp_path / 'packed' / 'pieces.csv').exists()

    export_dir = tmp_path / 'exported'
    export_response = client.post(
        '/api/workspace/composite/export',
        json={'output_dir': str(export_dir)},
    )
    assert export_response.status_code == 200
    export_payload = export_response.json()
    assert Path(export_payload['composite_png']).exists()
    assert Path(export_payload['composite_svg']).exists()
    exported_pieces = json.loads((export_dir / 'pieces.json').read_text())
    assert exported_pieces
    assert (export_dir / 'pieces.csv').exists()

    rebuild_response = client.post('/api/workspace/grid', json={'rows': 4, 'cols': 4})
    assert rebuild_response.status_code == 200
    rebuilt = rebuild_response.json()
    assert rebuilt['candidate_count'] == 16
    assert rebuilt['grid_rows'] == 4
    assert rebuilt['grid_cols'] == 4

    reset_response = client.post('/api/workspace/reset', json={'rows': 4, 'cols': 4})
    assert reset_response.status_code == 200
    reset = reset_response.json()
    assert reset['candidate_count'] == 16
    assert reset['kept_count'] == 0
    assert reset['grid_rows'] == 4
    assert reset['grid_cols'] == 4
    assert reset['active_candidate']['selected_region_ids'] == []

    grid_job = client.post('/api/workspace/grid-job', json={'rows': 4, 'cols': 4})
    assert grid_job.status_code == 200
    grid_job_id = grid_job.json()['job_id']
    for _ in range(80):
        job = client.get(f'/api/jobs/{grid_job_id}').json()
        if job['status'] == 'complete':
            break
        if job['status'] == 'failed':
            raise AssertionError(job['error'])
        time.sleep(0.05)
    else:
        raise AssertionError('grid job did not complete')
    assert job['result']['candidate_count'] == 16
    refine_target_id = job['result']['active_candidate_id']

    job_response = client.post(
        '/api/workspace/refine-job',
        json={'candidate_id': refine_target_id},
    )
    assert job_response.status_code == 200
    job_id = job_response.json()['job_id']
    for _ in range(200):
        job = client.get(f'/api/jobs/{job_id}').json()
        if job['status'] == 'complete':
            break
        if job['status'] == 'failed':
            raise AssertionError(job['error'])
        time.sleep(0.05)
    else:
        raise AssertionError('job did not complete')
    assert job['result']['candidate_count'] > 16
    refined_candidate = next(
        candidate
        for candidate in job['result']['candidates']
        if candidate['candidate_id'] != refine_target_id and candidate['generation'] > 0
    )
    assert refined_candidate['parent_candidate_id'] == refine_target_id
    assert 'grid_row' in refined_candidate and 'grid_col' in refined_candidate


def test_external_svg_nester_adapter_writes_inputs_and_outputs(
    tmp_path: Path,
    monkeypatch,
) -> None:
    image = np.zeros((32, 32, 3), dtype=np.uint8)
    image[:16, :] = [80, 70, 60]
    image[16:, :] = [190, 170, 140]
    input_path = tmp_path / 'source.png'
    Image.fromarray(image, mode='RGB').save(input_path)

    workspace = GridWorkspace.create(
        input_path,
        tmp_path / 'workspace',
        segment_levels=(2,),
        smoothness_levels=(4.0,),
        max_working_edge=32,
    )
    workspace.set_physical_size(4.0, 4.0, 'in')

    nester = tmp_path / 'fake_nester.py'
    nester.write_text(
        """
import pathlib
import sys

source = pathlib.Path(sys.argv[1])
target = pathlib.Path(sys.argv[2])
target.write_text(source.read_text(encoding='utf-8') + '<!-- external-nested -->', encoding='utf-8')
""".strip(),
        encoding='utf-8',
    )
    monkeypatch.setenv('MARQFLOW_NESTER_CMD', f'{sys.executable} {nester} {{input}} {{output}}')

    packed = workspace.pack_by_veneer(tmp_path / 'packed')

    assert packed
    for sheet in packed:
        assert sheet['packing_backend'] == 'external-svg-nester'
        assert Path(sheet['sheet_svg_path']).read_text(encoding='utf-8').endswith(
            '<!-- external-nested -->'
        )
        assert Path(sheet['nest_input_svg_path']).exists()
        assert 'nest_input_svg' not in sheet


def test_merge_cleanup_suggestions_reduces_piece_count(tmp_path: Path) -> None:
    image = np.zeros((48, 48, 3), dtype=np.uint8)
    image[:24, :24] = [88, 88, 88]
    image[:24, 24:] = [104, 104, 104]
    image[24:, :24] = [120, 120, 120]
    image[24:, 24:] = [136, 136, 136]
    input_path = tmp_path / 'source.png'
    Image.fromarray(image, mode='RGB').save(input_path)

    workspace_dir = tmp_path / 'workspace'
    GridWorkspace.create(
        input_path,
        workspace_dir,
        segment_levels=(4,),
        smoothness_levels=(1.0,),
        max_working_edge=48,
    )
    client = TestClient(create_app(workspace_dir))
    workspace = client.post(
        '/api/workspace/cleanup',
        json={
            'simplify_tolerance': 1.0,
            'highlight_small_area': 100.0,
            'highlight_thin_width': 100.0,
            'merge_rgb_threshold': 24.0,
        },
    ).json()
    before = workspace['design_summary']
    assert before['merge_suggestions']

    response = client.post('/api/workspace/final/merge-suggestions')

    assert response.status_code == 200
    after = response.json()['design_summary']
    assert after['region_count'] < before['region_count']
    assert len(after['merge_suggestions']) <= len(before['merge_suggestions'])


def test_browser_upload_caps_working_resolution(tmp_path: Path) -> None:
    image = np.zeros((900, 1200, 3), dtype=np.uint8)
    image[:, :600] = [90, 90, 90]
    image[:, 600:] = [180, 180, 180]
    input_path = tmp_path / 'large-source.png'
    Image.fromarray(image, mode='RGB').save(input_path)

    client = TestClient(create_app(tmp_path / 'workspaces'))
    with input_path.open('rb') as image_file:
        response = client.post(
            '/api/workspace/open-image',
            files={'image': ('large-source.png', image_file, 'image/png')},
            data={'rows': '1', 'cols': '1'},
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload['original_image_size'] == {'width': 1200, 'height': 900}
    assert max(payload['source_image_size'].values()) <= 768


def test_gallery_starts_blank_and_opens_uploaded_image(tmp_path: Path) -> None:
    image = np.zeros((32, 32, 3), dtype=np.uint8)
    image[:16, :] = [64, 64, 64]
    image[16:, :] = [192, 192, 192]
    input_path = tmp_path / 'source.png'
    Image.fromarray(image, mode='RGB').save(input_path)

    client = TestClient(create_app())

    assert client.get('/api/workspace').status_code == 404

    response = client.post(
        '/api/workspace/open-image',
        data={'rows': '4', 'cols': '4'},
        files={'image': ('source.png', input_path.read_bytes(), 'image/png')},
    )
    assert response.status_code == 200
    workspace = response.json()
    assert workspace['candidate_count'] == 16
    assert workspace['grid_rows'] == 4
    assert workspace['grid_cols'] == 4
    assert client.get('/api/workspace').status_code == 200
