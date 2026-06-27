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


def _four_region_labels() -> np.ndarray:
    labels = np.zeros((48, 48), dtype=np.int32)
    labels[:24, :24] = 1
    labels[:24, 24:] = 2
    labels[24:, :24] = 3
    labels[24:, 24:] = 4
    return labels


def _textured_focus_image(path: Path) -> None:
    image = np.full((48, 48, 3), [180, 150, 110], dtype=np.uint8)
    yy, xx = np.indices((24, 24))
    texture = ((xx * 9 + yy * 7) % 120).astype(np.uint8)
    image[:24, :24, 0] = 80 + texture
    image[:24, :24, 1] = 70 + (texture // 2)
    image[:24, :24, 2] = 50 + (texture // 3)
    Image.fromarray(image, mode='RGB').save(path)


def _large_fixture_image(path: Path) -> None:
    image = np.zeros((160, 120, 3), dtype=np.uint8)
    image[:, :60] = [225, 205, 165]
    image[:, 60:] = [45, 38, 30]
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
    simplified_svg_path = workspace.export_svg(
        tmp_path / 'design-simplified.svg',
        simplify_tolerance=3.0,
    )
    assert simplified_svg_path.exists()
    coverage_svg_path = workspace.export_coverage_svg(
        tmp_path / 'design-coverage.svg',
        tolerance=1.0,
    )
    coverage_svg = coverage_svg_path.read_text(encoding='utf-8')
    assert 'data-coverage-simplified="true"' in coverage_svg
    reloaded_after_coverage = MarquetryWorkspace.load(workspace.workspace_dir)
    artifact = reloaded_after_coverage.summary()['design']['vector_exports'][0]
    assert artifact['kind'] == 'coverage_svg'
    assert artifact['coverage_valid'] is True
    assert artifact['topology_edge_count'] > 0
    assert reloaded_after_coverage.cleanup_report()['vector_exports'][0]['coverage_valid'] is True

    manifest = workspace.pack(tmp_path / 'packed')
    assert manifest['packing_backend'] == 'shapely-polygon-shelf-rotating'
    assert manifest['sheets']
    assert 'placement' in manifest['sheets'][0]['pieces'][0]
    assert manifest['sheets'][0]['pieces'][0]['physical_contour']
    assert manifest['sheets'][0]['pieces'][0]['physical_svg_path'].startswith('M ')
    assert manifest['sheets'][0]['pieces'][0]['placed_physical_contour']
    assert manifest['sheets'][0]['pieces'][0]['placed_physical_svg_path'].startswith('M ')
    assert manifest['sheets'][0]['recommended_sheet_count'] >= 1
    assert manifest['sheets'][0]['total_piece_area'] > 0
    assert manifest['sheets'][0]['total_bounding_box_area'] > 0
    assert manifest['sheets'][0]['material_utilization'] > 0
    assert (tmp_path / 'packed' / 'pack.json').exists()
    assert (tmp_path / 'packed' / 'design.svg').exists()
    assert (tmp_path / 'packed' / 'design-coverage.svg').exists()
    assert (tmp_path / 'packed' / 'cleanup-report.json').exists()
    report_path = workspace.export_cleanup_report(tmp_path / 'report.json')
    assert report_path.exists()


def test_browser_pack_output_stays_under_workspace(tmp_path: Path) -> None:
    image_path = tmp_path / 'source.png'
    _fixture_image(image_path)
    workspace = MarquetryWorkspace.create(image_path, tmp_path / 'workspace', max_edge=64)
    candidate = workspace.generate_candidate(target_regions=4, compactness=8.0)
    workspace.create_design(candidate.candidate_id, PhysicalSize(width=8, height=8, unit='in'))

    client = TestClient(create_app(workspace.workspace_dir))
    response = client.post('/api/pack', json={'output_dir': './exported'})
    assert response.status_code == 200
    assert (workspace.workspace_dir / 'exported' / 'pack.json').exists()
    assert (workspace.workspace_dir / 'exported' / 'design.svg').exists()
    assert (workspace.workspace_dir / 'exported' / 'design-coverage.svg').exists()

    escaped = client.post('/api/pack', json={'output_dir': str(tmp_path.parent / 'outside')})
    assert escaped.status_code == 400


def test_browser_image_upload_honors_working_size_cap(tmp_path: Path) -> None:
    image_path = tmp_path / 'large.png'
    _large_fixture_image(image_path)
    client = TestClient(create_app(tmp_path / 'workspace'))

    response = client.post(
        '/api/workspace/open-image',
        files={'image': ('large.png', image_path.read_bytes(), 'image/png')},
        data={'target_regions': '4', 'compactness': '8', 'max_edge': '64'},
    )

    assert response.status_code == 200
    source = response.json()['source']
    assert max(source['working_width'], source['working_height']) == 64


def test_candidate_grid_is_source_stage_only(tmp_path: Path) -> None:
    image_path = tmp_path / 'source.png'
    _fixture_image(image_path)
    workspace = MarquetryWorkspace.create(image_path, tmp_path / 'workspace', max_edge=64)
    seed = workspace.generate_candidate(target_regions=4, compactness=8.0)
    workspace.create_design(seed.candidate_id, PhysicalSize(width=8, height=8, unit='in'))
    original_design_source = workspace.design.source_candidate_id

    candidates = workspace.generate_candidate_grid(rows=2, cols=3, min_regions=6, max_regions=18)

    assert len(candidates) == 6
    assert workspace.design.source_candidate_id == original_design_source
    assert len(workspace.candidates) == 7


def test_marquetry_candidate_mode_merges_tiny_source_regions(tmp_path: Path) -> None:
    image_path = tmp_path / 'source.png'
    _fixture_image(image_path)
    workspace = MarquetryWorkspace.create(image_path, tmp_path / 'workspace', max_edge=64)

    candidate = workspace.generate_candidate(
        target_regions=24,
        compactness=14.0,
        marquetry_mode=True,
    )
    labels = workspace.candidate_labels(candidate.candidate_id)
    areas = [
        int(np.count_nonzero(labels == region_id))
        for region_id in np.unique(labels)
        if int(region_id) > 0
    ]

    assert candidate.region_count <= 24
    assert min(areas) >= 4


def test_candidate_generation_can_use_detail_zones(tmp_path: Path) -> None:
    image_path = tmp_path / 'source.png'
    _textured_focus_image(image_path)
    workspace = MarquetryWorkspace.create(image_path, tmp_path / 'workspace', max_edge=64)
    seed = workspace.generate_candidate(target_regions=4, compactness=8.0)
    workspace.create_design(seed.candidate_id, PhysicalSize(width=8, height=8, unit='in'))
    workspace.add_detail_zone('eye detail', (0, 0, 24, 24), detail_multiplier=8)

    plain = workspace.generate_candidate(target_regions=4, compactness=8.0)
    detailed = workspace.generate_candidate(
        target_regions=4,
        compactness=8.0,
        use_detail_zones=True,
    )

    plain_labels = workspace.candidate_labels(plain.candidate_id)
    detailed_labels = workspace.candidate_labels(detailed.candidate_id)
    plain_zone_count = len(np.unique(plain_labels[:24, :24]))
    detailed_zone_count = len(np.unique(detailed_labels[:24, :24]))
    assert detailed.region_count > plain.region_count
    assert detailed_zone_count > plain_zone_count


def test_subject_mask_guides_candidate_generation_and_undo(tmp_path: Path) -> None:
    image_path = tmp_path / 'source.png'
    _fixture_image(image_path)
    workspace = MarquetryWorkspace.create(image_path, tmp_path / 'workspace', max_edge=64)
    candidate = workspace.generate_candidate(target_regions=4, compactness=8.0)
    workspace.create_design(candidate.candidate_id, PhysicalSize(width=8, height=8, unit='in'))
    workspace._write_design_labels(_four_region_labels())
    workspace.save()

    workspace.set_subject_mask_for_regions([1], 'subject')
    workspace.set_subject_mask_for_regions([4], 'background')
    summary = workspace.subject_mask_summary()
    assert summary['subject_px'] == 24 * 24
    assert summary['background_px'] == 24 * 24

    masked = workspace.generate_candidate(
        target_regions=4,
        compactness=8.0,
        use_subject_mask=True,
    )
    mask = workspace.subject_mask()
    masked_labels = workspace.candidate_labels(masked.candidate_id)
    subject_labels = set(int(value) for value in np.unique(masked_labels[mask == 1]))
    background_labels = set(int(value) for value in np.unique(masked_labels[mask == 2]))
    assert subject_labels
    assert background_labels
    assert subject_labels.isdisjoint(background_labels)

    workspace.undo()
    assert workspace.subject_mask_summary()['background_px'] == 0
    workspace.undo()
    assert workspace.subject_mask_summary()['subject_px'] == 0

    workspace.paint_subject_mask_stroke(
        [(4.0, 4.0), (20.0, 20.0)],
        role='subject',
        brush_radius=2.0,
    )
    assert workspace.subject_mask_summary()['subject_px'] > 0
    workspace.undo()
    assert workspace.subject_mask_summary()['subject_px'] == 0


def test_size_and_veneer_inventory_edits_are_persisted_and_undoable(tmp_path: Path) -> None:
    image_path = tmp_path / 'source.png'
    _fixture_image(image_path)
    workspace = MarquetryWorkspace.create(image_path, tmp_path / 'workspace', max_edge=64)
    candidate = workspace.generate_candidate(target_regions=4, compactness=8.0)
    workspace.create_design(candidate.candidate_id, PhysicalSize(width=8, height=8, unit='in'))
    first_region_id = workspace.regions()[0]['region_id']
    workspace.assign_veneer(first_region_id, 'walnut')

    workspace.update_physical_size(PhysicalSize(width=6, height=9, unit='in'))
    assert workspace.summary()['design']['physical_size'] == {
        'width': 6.0,
        'height': 9.0,
        'unit': 'in',
    }
    workspace.undo()
    assert workspace.summary()['design']['physical_size'] == {
        'width': 8.0,
        'height': 8.0,
        'unit': 'in',
    }

    workspace.replace_veneers(
        [
            Veneer('walnut', 'Walnut', (82, 55, 38)),
            Veneer('maple', 'Maple', (221, 204, 164)),
        ]
    )
    assert {veneer['veneer_id'] for veneer in workspace.summary()['design']['veneers']} == {
        'walnut',
        'maple',
    }
    assert workspace.summary()['design']['veneer_assignments'][str(first_region_id)] == 'walnut'
    workspace.undo()
    assert len(workspace.summary()['design']['veneers']) == 5


def test_merge_regions_preserves_partition_and_undo_restores_it(tmp_path: Path) -> None:
    image_path = tmp_path / 'source.png'
    _fixture_image(image_path)
    workspace = MarquetryWorkspace.create(image_path, tmp_path / 'workspace', max_edge=64)
    candidate = workspace.generate_candidate(target_regions=4, compactness=8.0)
    workspace.create_design(candidate.candidate_id, PhysicalSize(width=8, height=8, unit='in'))
    workspace._write_design_labels(_four_region_labels())
    workspace.design.veneer_assignments = {1: 'maple', 2: 'maple', 3: 'walnut', 4: 'black-dyed'}
    workspace.save()

    workspace.merge_regions([1, 2])
    merged_summary = workspace.summary()
    assert merged_summary['validation']['valid'] is True
    assert merged_summary['validation']['region_count'] == 3
    assert len(merged_summary['design']['edit_history']) == 1
    assert merged_summary['regions'][0]['veneer_id'] == 'maple'

    workspace.undo()
    restored_summary = workspace.summary()
    assert restored_summary['validation']['valid'] is True
    assert restored_summary['validation']['region_count'] == 4
    assert restored_summary['design']['veneer_assignments'] == {
        '1': 'maple',
        '2': 'maple',
        '3': 'walnut',
        '4': 'black-dyed',
    }


def test_bulk_assignment_detail_zones_and_boundaries(tmp_path: Path) -> None:
    image_path = tmp_path / 'source.png'
    _fixture_image(image_path)
    workspace = MarquetryWorkspace.create(image_path, tmp_path / 'workspace', max_edge=64)
    candidate = workspace.generate_candidate(target_regions=4, compactness=8.0)
    workspace.create_design(candidate.candidate_id, PhysicalSize(width=8, height=8, unit='in'))
    workspace._write_design_labels(_four_region_labels())
    workspace.save()

    workspace.assign_veneer_many([1, 2], 'walnut')
    summary = workspace.summary()
    assert summary['design']['veneer_assignments']['1'] == 'walnut'
    assert summary['design']['veneer_assignments']['2'] == 'walnut'
    workspace.undo()
    assert workspace.summary()['design']['veneer_assignments']['1'] != 'walnut'

    zone = workspace.add_detail_zone('eyes', (2, 3, 20, 18), detail_multiplier=3)
    assert zone.to_dict() == {
        'zone_id': 1,
        'name': 'eyes',
        'bbox': [2, 3, 20, 18],
        'detail_multiplier': 3.0,
    }
    reloaded = MarquetryWorkspace.load(tmp_path / 'workspace')
    assert reloaded.summary()['design']['detail_zones'][0]['name'] == 'eyes'
    boundary_summary = reloaded.boundary_summary()
    assert boundary_summary['boundary_count'] == 4
    assert all(
        boundary['edge_length_physical'] > 0
        for boundary in boundary_summary['boundaries']
    )
    assert all(boundary['path_count'] >= 1 for boundary in boundary_summary['boundaries'])
    assert all(boundary['physical_paths'] for boundary in boundary_summary['boundaries'])
    assert all(boundary['vertex_count'] >= 2 for boundary in boundary_summary['boundaries'])
    assert all(
        boundary['simplified_vertex_count'] >= 2
        for boundary in boundary_summary['boundaries']
    )
    assert all(boundary['simplified_paths'] for boundary in boundary_summary['boundaries'])
    topology = reloaded.topology_graph()
    assert topology['edge_count'] == 8
    assert topology['vertex_count'] > 0
    assert len([edge for edge in topology['edges'] if edge['exterior']]) == 4
    assert len([edge for edge in topology['edges'] if not edge['exterior']]) == 4
    assert {region['region_id'] for region in topology['regions']} == {1, 2, 3, 4}
    assert all(region['edge_ids'] for region in topology['regions'])
    coverage = reloaded.coverage_summary()
    assert coverage['valid'] is True
    assert coverage['polygon_count'] == 4
    assert coverage['invalid_edge_count'] == 0
    report = reloaded.cleanup_report()
    assert report['region_count'] == 4
    assert 0 <= report['readiness_score'] <= 100
    assert report['readiness'] in {'ready', 'needs-review', 'rough'}
    assert report['boundary_count'] == 4
    assert report['topology']['edge_count'] == 8
    assert report['coverage']['valid'] is True
    assert report['vector_exports'] == []
    assert 'valid_partition' in report
    reloaded.undo()
    assert reloaded.summary()['design']['detail_zones'] == []


def test_vector_graph_artifacts_simplify_reconstruct_and_undo(tmp_path: Path) -> None:
    image_path = tmp_path / 'source.png'
    _fixture_image(image_path)
    workspace = MarquetryWorkspace.create(image_path, tmp_path / 'workspace', max_edge=64)
    candidate = workspace.generate_candidate(target_regions=4, compactness=8.0)
    workspace.create_design(candidate.candidate_id, PhysicalSize(width=8, height=8, unit='in'))
    workspace._write_design_labels(_four_region_labels())
    workspace.save()

    persisted = workspace.persist_topology_graph()
    assert persisted['kind'] == 'raster_topology'
    assert (workspace.workspace_dir / 'vector' / 'raster_topology.json').exists()
    assert workspace.summary()['design']['vector_graphs'][0]['kind'] == 'raster_topology'

    original_vertices = sum(len(edge['path']) for edge in persisted['graph']['edges'])
    simplified = workspace.simplify_vector_graph(tolerance=2.0)
    simplified_vertices = sum(len(edge['path']) for edge in simplified['graph']['edges'])
    assert simplified['kind'] == 'simplified_topology'
    assert simplified['graph']['edge_count'] == persisted['graph']['edge_count']
    assert simplified_vertices <= original_vertices
    assert all(edge['physical_path'] for edge in simplified['graph']['edges'])
    assert any(
        artifact['kind'] == 'simplified_topology'
        for artifact in workspace.summary()['design']['vector_graphs']
    )
    assert workspace.cleanup_report()['vector_graphs']

    graph_svg_path = workspace.export_vector_graph_svg(tmp_path / 'graph.svg')
    graph_svg = graph_svg_path.read_text(encoding='utf-8')
    assert '<svg' in graph_svg
    assert 'data-graph-reconstructed="true"' in graph_svg

    workspace.undo()
    assert not (workspace.workspace_dir / 'vector' / 'simplified_topology.json').exists()
    assert {
        artifact['kind'] for artifact in workspace.summary()['design']['vector_graphs']
    } == {'raster_topology'}
    assert workspace.summary()['validation']['region_count'] == 4


def test_promoted_vector_graph_drives_export_and_pack(tmp_path: Path) -> None:
    image_path = tmp_path / 'source.png'
    _fixture_image(image_path)
    workspace = MarquetryWorkspace.create(image_path, tmp_path / 'workspace', max_edge=64)
    candidate = workspace.generate_candidate(target_regions=4, compactness=8.0)
    workspace.create_design(candidate.candidate_id, PhysicalSize(width=8, height=8, unit='in'))
    workspace._write_design_labels(_four_region_labels())
    workspace.save()

    edited = workspace.simplify_vector_graph_for_regions([1, 2], tolerance=2.0)
    assert edited['kind'] == 'edited_topology'
    assert workspace.summary()['design']['active_vector_graph_kind'] == 'edited_topology'

    svg_path = workspace.export_svg(tmp_path / 'active.svg')
    assert 'data-graph-reconstructed="true"' in svg_path.read_text(encoding='utf-8')
    manifest = workspace.pack(tmp_path / 'packed-vector')
    assert manifest['source_geometry'] == 'edited_topology'
    assert manifest['sheets'][0]['pieces'][0]['source_geometry'] == 'edited_topology'

    workspace.undo()
    assert workspace.summary()['design']['active_vector_graph_kind'] is None
    assert not (workspace.workspace_dir / 'vector' / 'edited_topology.json').exists()


def test_boundary_specific_vector_simplification_is_undoable(tmp_path: Path) -> None:
    image_path = tmp_path / 'source.png'
    _fixture_image(image_path)
    workspace = MarquetryWorkspace.create(image_path, tmp_path / 'workspace', max_edge=64)
    candidate = workspace.generate_candidate(target_regions=4, compactness=8.0)
    workspace.create_design(candidate.candidate_id, PhysicalSize(width=8, height=8, unit='in'))
    workspace._write_design_labels(_four_region_labels())
    workspace.save()

    edited = workspace.simplify_vector_boundary(1, 2, tolerance=2.0)

    assert edited['source'] == 'single_topology_boundary'
    assert edited['graph_validation']['valid'] is True
    assert workspace.summary()['design']['active_vector_graph_kind'] == 'edited_topology'
    workspace.undo()
    assert workspace.summary()['design']['active_vector_graph_kind'] is None


def test_vector_simplification_preview_and_smoothing_are_valid(tmp_path: Path) -> None:
    image_path = tmp_path / 'source.png'
    _fixture_image(image_path)
    workspace = MarquetryWorkspace.create(image_path, tmp_path / 'workspace', max_edge=64)
    candidate = workspace.generate_candidate(target_regions=4, compactness=8.0)
    workspace.create_design(candidate.candidate_id, PhysicalSize(width=8, height=8, unit='in'))
    workspace._write_design_labels(_four_region_labels())
    workspace.save()

    preview = workspace.preview_vector_simplification(
        tolerance=2.0,
        boundary=(1, 2),
    )
    assert preview['valid'] is True
    assert preview['edge_ids']
    assert preview['after_vertex_count'] <= preview['before_vertex_count']

    smoothed = workspace.smooth_vector_boundary(1, 2, strength=0.4, iterations=2)

    assert smoothed['graph_validation']['valid'] is True
    assert workspace.summary()['design']['active_vector_graph_kind'] == 'edited_topology'
    workspace.undo()
    assert workspace.summary()['design']['active_vector_graph_kind'] is None


def test_topology_safe_vertex_move_is_undoable(tmp_path: Path) -> None:
    image_path = tmp_path / 'source.png'
    _fixture_image(image_path)
    workspace = MarquetryWorkspace.create(image_path, tmp_path / 'workspace', max_edge=64)
    candidate = workspace.generate_candidate(target_regions=4, compactness=8.0)
    workspace.create_design(candidate.candidate_id, PhysicalSize(width=8, height=8, unit='in'))
    workspace._write_design_labels(_four_region_labels())
    workspace.save()

    graph = workspace.persist_topology_graph()['graph']
    center = next(vertex for vertex in graph['vertices'] if vertex['point'] == [24, 24])
    preview = workspace.preview_vector_vertex_move(center['vertex_id'], (25, 24))
    assert preview['valid'] is True
    assert preview['changed'] is True
    moved = workspace.move_vector_vertex(center['vertex_id'], (25, 24))

    assert moved['graph_validation']['valid'] is True
    assert workspace.summary()['design']['active_vector_graph_kind'] == 'edited_topology'
    edited_graph = workspace.vector_graph_payload('edited_topology')['graph']
    assert any(vertex['point'] == [25.0, 24.0] for vertex in edited_graph['vertices'])
    workspace.undo()
    assert workspace.summary()['design']['active_vector_graph_kind'] is None

    try:
        workspace.move_vector_vertex(center['vertex_id'], (24, 24))
    except ValueError as exc:
        assert 'did not move' in str(exc)
    else:
        raise AssertionError('no-op vertex move should fail')

    no_op_preview = workspace.preview_vector_vertex_move(center['vertex_id'], (24, 24))
    assert no_op_preview['valid'] is False
    assert no_op_preview['reason'] == 'vertex did not move'


def test_vector_vertex_move_is_clamped_to_design_bounds(tmp_path: Path) -> None:
    image_path = tmp_path / 'source.png'
    _fixture_image(image_path)
    workspace = MarquetryWorkspace.create(image_path, tmp_path / 'workspace', max_edge=64)
    candidate = workspace.generate_candidate(target_regions=4, compactness=8.0)
    workspace.create_design(candidate.candidate_id, PhysicalSize(width=8, height=8, unit='in'))
    workspace._write_design_labels(_four_region_labels())
    workspace.save()

    graph = workspace.persist_topology_graph()['graph']
    corner = next(vertex for vertex in graph['vertices'] if vertex['point'] == [0, 0])

    try:
        workspace.move_vector_vertex(corner['vertex_id'], (-5, -3))
    except ValueError as exc:
        assert 'did not move' in str(exc)
    else:
        raise AssertionError('clamped no-op corner move should fail')


def test_vector_edit_layer_and_cuttability_cleanup(tmp_path: Path) -> None:
    image_path = tmp_path / 'source.png'
    _fixture_image(image_path)
    workspace = MarquetryWorkspace.create(image_path, tmp_path / 'workspace', max_edge=64)
    candidate = workspace.generate_candidate(target_regions=4, compactness=8.0)
    workspace.create_design(candidate.candidate_id, PhysicalSize(width=8, height=8, unit='in'))
    labels = _four_region_labels()
    labels[0:2, 0:2] = 5
    workspace._write_design_labels(labels)
    workspace.design.veneer_assignments = {
        1: 'maple',
        2: 'cherry',
        3: 'walnut',
        4: 'black-dyed',
        5: 'maple',
    }
    workspace.save()

    layer = workspace.vector_edit_layer()
    assert layer['kind'] == 'raster_topology'
    assert layer['vertices']
    assert layer['edges']

    result = workspace.cuttability_cleanup(max_repairs=5, min_area=0.12)

    assert result['repaired_region_count'] >= 1
    assert workspace.summary()['validation']['valid'] is True


def test_remove_boundary_notches_is_undoable(tmp_path: Path) -> None:
    image_path = tmp_path / 'source.png'
    _fixture_image(image_path)
    workspace = MarquetryWorkspace.create(image_path, tmp_path / 'workspace', max_edge=64)
    candidate = workspace.generate_candidate(target_regions=4, compactness=8.0)
    workspace.create_design(candidate.candidate_id, PhysicalSize(width=8, height=8, unit='in'))
    labels = _four_region_labels()
    labels[10, 24] = 1
    workspace._write_design_labels(labels)
    workspace.save()

    changed = workspace.remove_boundary_notches(iterations=1, min_neighbor_votes=5)

    assert changed >= 1
    assert workspace.design_labels()[10, 24] == 2
    assert workspace.summary()['validation']['valid'] is True
    workspace.undo()
    assert workspace.design_labels()[10, 24] == 1


def test_pack_rotates_polygon_when_grain_allows(tmp_path: Path) -> None:
    image_path = tmp_path / 'source.png'
    _fixture_image(image_path)
    workspace = MarquetryWorkspace.create(image_path, tmp_path / 'workspace', max_edge=64)
    candidate = workspace.generate_candidate(target_regions=2, compactness=8.0)
    workspace.create_design(candidate.candidate_id, PhysicalSize(width=8, height=8, unit='in'))
    labels = np.zeros((48, 48), dtype=np.int32)
    labels[:, :12] = 1
    labels[:, 12:] = 2
    workspace._write_design_labels(labels)
    workspace.replace_veneers(
        [
            Veneer(
                'maple',
                'Maple',
                (225, 205, 165),
                sheet_width=8,
                sheet_height=2.5,
                sheet_count=1,
            ),
            Veneer(
                'walnut',
                'Walnut',
                (80, 55, 38),
                sheet_width=8,
                sheet_height=8,
                sheet_count=1,
            ),
        ]
    )
    workspace.design.veneer_assignments = {1: 'maple', 2: 'walnut'}
    workspace.save()

    manifest = workspace.pack(tmp_path / 'rotated-pack')
    maple_piece = next(
        piece
        for sheet in manifest['sheets']
        if sheet['veneer_id'] == 'maple'
        for piece in sheet['pieces']
    )

    assert manifest['packing_backend'] == 'shapely-polygon-shelf-rotating'
    assert maple_piece['packed'] is True
    assert maple_piece['placement']['rotation'] in {90, 270}


def test_split_and_lock_are_undoable(tmp_path: Path) -> None:
    image_path = tmp_path / 'source.png'
    _fixture_image(image_path)
    workspace = MarquetryWorkspace.create(image_path, tmp_path / 'workspace', max_edge=64)
    candidate = workspace.generate_candidate(target_regions=4, compactness=8.0)
    workspace.create_design(candidate.candidate_id, PhysicalSize(width=8, height=8, unit='in'))
    workspace._write_design_labels(_four_region_labels())
    workspace.design.veneer_assignments = {1: 'maple', 2: 'cherry', 3: 'walnut', 4: 'black-dyed'}
    workspace.save()

    workspace.lock_regions([1], locked=True)
    assert workspace.summary()['regions'][0]['locked'] is True
    try:
        workspace.split_region(1, target_parts=3, compactness=8)
    except ValueError as exc:
        assert 'locked' in str(exc)
    else:
        raise AssertionError('locked region split should fail')
    workspace.undo()
    assert workspace.summary()['regions'][0]['locked'] is False

    workspace.split_region(1, target_parts=3, compactness=8)
    split_summary = workspace.summary()
    assert split_summary['validation']['valid'] is True
    assert split_summary['validation']['region_count'] > 4
    split_child_ids = [
        region['region_id']
        for region in split_summary['regions']
        if region['veneer_id'] == 'maple'
    ]
    assert len(split_child_ids) >= 2
    workspace.undo()
    assert workspace.summary()['validation']['region_count'] == 4


def test_focus_zone_from_regions_drives_local_split(tmp_path: Path) -> None:
    image_path = tmp_path / 'source.png'
    _fixture_image(image_path)
    workspace = MarquetryWorkspace.create(image_path, tmp_path / 'workspace', max_edge=64)
    candidate = workspace.generate_candidate(target_regions=4, compactness=8.0)
    workspace.create_design(candidate.candidate_id, PhysicalSize(width=8, height=8, unit='in'))
    workspace._write_design_labels(_four_region_labels())
    workspace.design.veneer_assignments = {1: 'maple', 2: 'cherry', 3: 'walnut', 4: 'black-dyed'}
    workspace.save()

    zone = workspace.add_detail_zone_for_regions([1], name='left eye', detail_multiplier=3)
    assert zone.bbox == (0, 0, 24, 24)
    applied = workspace.apply_detail_zones(max_splits=1, compactness=8)
    assert applied == 1
    assert workspace.summary()['validation']['valid'] is True
    assert workspace.summary()['validation']['region_count'] > 4


def test_repair_small_regions_merges_slivers(tmp_path: Path) -> None:
    image_path = tmp_path / 'source.png'
    _fixture_image(image_path)
    workspace = MarquetryWorkspace.create(image_path, tmp_path / 'workspace', max_edge=64)
    candidate = workspace.generate_candidate(target_regions=4, compactness=8.0)
    workspace.create_design(candidate.candidate_id, PhysicalSize(width=8, height=8, unit='in'))
    labels = _four_region_labels()
    labels[0:2, 0:2] = 5
    workspace._write_design_labels(labels)
    workspace.design.veneer_assignments = {
        1: 'maple',
        2: 'cherry',
        3: 'walnut',
        4: 'black-dyed',
        5: 'maple',
    }
    workspace.save()

    before = workspace.summary()['validation']['region_count']
    repaired = workspace.repair_small_regions(max_area=0.12, max_repairs=5)

    assert repaired == 1
    assert workspace.summary()['validation']['valid'] is True
    assert workspace.summary()['validation']['region_count'] == before - 1


def test_smooth_boundaries_is_valid_and_undoable(tmp_path: Path) -> None:
    image_path = tmp_path / 'source.png'
    _fixture_image(image_path)
    workspace = MarquetryWorkspace.create(image_path, tmp_path / 'workspace', max_edge=64)
    candidate = workspace.generate_candidate(target_regions=4, compactness=8.0)
    workspace.create_design(candidate.candidate_id, PhysicalSize(width=8, height=8, unit='in'))
    labels = _four_region_labels()
    labels[12, 12] = 2
    workspace._write_design_labels(labels)
    workspace.design.veneer_assignments = {1: 'maple', 2: 'cherry', 3: 'walnut', 4: 'black-dyed'}
    workspace.save()

    changed = workspace.smooth_boundaries(iterations=1)

    assert changed == 1
    assert workspace.design_labels()[12, 12] == 1
    assert workspace.summary()['validation']['valid'] is True
    workspace.undo()
    assert workspace.design_labels()[12, 12] == 2


def test_smooth_boundaries_can_be_limited_to_regions(tmp_path: Path) -> None:
    image_path = tmp_path / 'source.png'
    _fixture_image(image_path)
    workspace = MarquetryWorkspace.create(image_path, tmp_path / 'workspace', max_edge=64)
    candidate = workspace.generate_candidate(target_regions=4, compactness=8.0)
    workspace.create_design(candidate.candidate_id, PhysicalSize(width=8, height=8, unit='in'))
    labels = _four_region_labels()
    labels[12, 12] = 2
    workspace._write_design_labels(labels)
    workspace.design.veneer_assignments = {1: 'maple', 2: 'cherry', 3: 'walnut', 4: 'black-dyed'}
    workspace.save()

    changed = workspace.smooth_boundaries(iterations=1, region_ids=[2])

    assert changed == 1
    assert workspace.design_labels()[12, 12] == 1
    assert workspace.design_labels()[36, 36] == 4


def test_merge_requires_connected_regions(tmp_path: Path) -> None:
    image_path = tmp_path / 'source.png'
    _fixture_image(image_path)
    workspace = MarquetryWorkspace.create(image_path, tmp_path / 'workspace', max_edge=64)
    candidate = workspace.generate_candidate(target_regions=4, compactness=8.0)
    workspace.create_design(candidate.candidate_id, PhysicalSize(width=8, height=8, unit='in'))
    workspace._write_design_labels(_four_region_labels())

    try:
        workspace.merge_regions([1, 4])
    except ValueError as exc:
        assert 'connected' in str(exc)
    else:
        raise AssertionError('disconnected merge should fail')


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
    assert manifest['sheets'][0]['recommended_sheet_count'] >= 1
    assert manifest['sheets'][0]['stock_shortfall_count'] >= 1
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

    mask_response = client.post(
        '/api/design/subject-mask-for-regions',
        json={'region_ids': [region_id], 'role': 'subject'},
    )
    assert mask_response.status_code == 200
    assert mask_response.json()['subject_mask']['subject_px'] > 0

    hitmap_response = client.get('/api/design/hitmap')
    assert hitmap_response.status_code == 200
    assert np.count_nonzero(np.asarray(hitmap_response.json()['subject_mask']) == 1) > 0

    svg_response = client.get('/api/design.svg?simplify_tolerance=2')
    assert svg_response.status_code == 200
    assert svg_response.headers['content-type'].startswith('image/svg+xml')

    coverage_svg_response = client.get('/api/design-coverage.svg?tolerance=1')
    assert coverage_svg_response.status_code == 200
    assert 'data-coverage-simplified="true"' in coverage_svg_response.text

    persist_topology_response = client.post('/api/design/topology/persist')
    assert persist_topology_response.status_code == 200
    assert persist_topology_response.json()['kind'] == 'raster_topology'
    simplify_topology_response = client.post(
        '/api/design/topology/simplify',
        json={'tolerance': 2.0},
    )
    assert simplify_topology_response.status_code == 200
    assert simplify_topology_response.json()['kind'] == 'simplified_topology'
    promote_topology_response = client.post(
        '/api/design/topology/promote',
        json={'kind': 'simplified_topology'},
    )
    assert promote_topology_response.status_code == 200
    assert (
        promote_topology_response.json()['design']['active_vector_graph_kind']
        == 'simplified_topology'
    )
    simplify_selected_response = client.post(
        '/api/design/topology/simplify-selected',
        json={'region_ids': [region_id], 'tolerance': 2.0},
    )
    assert simplify_selected_response.status_code == 200
    assert (
        simplify_selected_response.json()['design']['active_vector_graph_kind']
        == 'edited_topology'
    )
    edit_layer = client.get('/api/design/topology/edit-layer').json()
    vertex = next(
        item
        for item in edit_layer['vertices']
        if 0 < item['point'][0] < payload['source']['working_width']
        and 0 < item['point'][1] < payload['source']['working_height']
    )
    preview_move_response = client.post(
        '/api/design/topology/preview-move-vertex',
        json={
            'vertex_id': vertex['vertex_id'],
            'point': [vertex['point'][0] + 1, vertex['point'][1]],
        },
    )
    assert preview_move_response.status_code == 200
    assert 'valid' in preview_move_response.json()
    graph_svg_response = client.get('/api/design-graph.svg?kind=simplified_topology')
    assert graph_svg_response.status_code == 200
    assert 'data-graph-reconstructed="true"' in graph_svg_response.text

    pack_response = client.post('/api/pack', json={'output_dir': str(tmp_path / 'packed')})
    assert pack_response.status_code == 200
    assert pack_response.json()['sheets']

    grid_response = client.post(
        '/api/candidate-grid',
        json={
            'rows': 1,
            'cols': 2,
            'min_regions': 4,
            'max_regions': 8,
            'min_compactness': 4,
            'max_compactness': 8,
        },
    )
    assert grid_response.status_code == 200
    assert len(grid_response.json()['candidates']) == 3

    preview_response = client.get(
        f"/api/workspace-file/{grid_response.json()['candidates'][0]['preview_path']}"
    )
    assert preview_response.status_code == 200


def test_api_workspace_lifecycle(tmp_path: Path) -> None:
    image_path = tmp_path / 'source.png'
    _fixture_image(image_path)
    client = TestClient(create_app(tmp_path / 'active'))

    created = client.post(
        '/api/workspace/open-image',
        files={'image': ('source.png', image_path.read_bytes(), 'image/png')},
        data={'target_regions': '4', 'compactness': '8', 'workspace_name': 'Bennett Portrait'},
    )
    assert created.status_code == 200
    assert Path(created.json()['workspace_dir']).name == 'Bennett-Portrait'

    listed = client.get('/api/workspaces')
    assert listed.status_code == 200
    assert listed.json()['workspaces'][0]['name'] == 'Bennett-Portrait'
    assert listed.json()['workspaces'][0]['active'] is True

    opened = client.post('/api/workspace/open', json={'name': 'Bennett-Portrait'})
    assert opened.status_code == 200
    assert opened.json()['validation']['valid'] is True

    deleted = client.delete('/api/workspace/Bennett-Portrait')
    assert deleted.status_code == 200
    assert client.get('/api/workspace').status_code == 404
    assert client.get('/api/workspaces').json()['workspaces'] == []


def test_api_merge_undo_and_hitmap(tmp_path: Path) -> None:
    image_path = tmp_path / 'source.png'
    _fixture_image(image_path)
    workspace = MarquetryWorkspace.create(image_path, tmp_path / 'workspace', max_edge=64)
    candidate = workspace.generate_candidate(target_regions=4, compactness=8.0)
    workspace.create_design(candidate.candidate_id, PhysicalSize(width=8, height=8, unit='in'))
    workspace._write_design_labels(_four_region_labels())
    workspace.save()
    client = TestClient(create_app(tmp_path / 'workspace'))

    hitmap_response = client.get('/api/design/hitmap')
    assert hitmap_response.status_code == 200
    assert hitmap_response.json()['width'] == 48
    assert hitmap_response.json()['height'] == 48

    merge_response = client.post('/api/design/merge', json={'region_ids': [1, 2]})
    assert merge_response.status_code == 200
    assert merge_response.json()['validation']['region_count'] == 3

    undo_response = client.post('/api/design/undo')
    assert undo_response.status_code == 200
    assert undo_response.json()['validation']['region_count'] == 4

    bulk_response = client.post(
        '/api/design/veneer-bulk',
        json={'region_ids': [1, 2], 'veneer_id': 'walnut'},
    )
    assert bulk_response.status_code == 200
    assert bulk_response.json()['design']['veneer_assignments']['1'] == 'walnut'

    zone_response = client.post(
        '/api/design/detail-zone',
        json={'name': 'eyes', 'bbox': [0, 0, 12, 12], 'detail_multiplier': 2.5},
    )
    assert zone_response.status_code == 200
    assert zone_response.json()['design']['detail_zones'][0]['name'] == 'eyes'

    boundaries_response = client.get('/api/design/boundaries')
    assert boundaries_response.status_code == 200
    assert boundaries_response.json()['boundary_count'] == 4
    simplify_boundary_response = client.post(
        '/api/design/topology/simplify-boundary',
        json={'region_a': 1, 'region_b': 2, 'tolerance': 2.0},
    )
    assert simplify_boundary_response.status_code == 200
    assert (
        simplify_boundary_response.json()['design']['active_vector_graph_kind']
        == 'edited_topology'
    )

    topology_response = client.get('/api/design/topology')
    assert topology_response.status_code == 200
    assert topology_response.json()['edge_count'] == 8
    edit_layer_response = client.get('/api/design/topology/edit-layer')
    assert edit_layer_response.status_code == 200
    assert edit_layer_response.json()['vertices']

    report_response = client.get('/api/cleanup-report')
    assert report_response.status_code == 200
    assert report_response.json()['region_count'] == 4

    cleanup_response = client.post(
        '/api/design/apply-merge-suggestions',
        json={'max_merges': 2},
    )
    assert cleanup_response.status_code == 200
    assert 'applied_merge_count' in cleanup_response.json()

    cuttability_response = client.post(
        '/api/design/cuttability-cleanup',
        json={'max_repairs': 2, 'min_area': 0.01, 'smooth_iterations': 1},
    )
    assert cuttability_response.status_code == 200
    assert 'cuttability_cleanup' in cuttability_response.json()

    lock_response = client.post('/api/design/lock', json={'region_ids': [1], 'locked': True})
    assert lock_response.status_code == 200
    assert lock_response.json()['regions'][0]['locked'] is True

    unlock_response = client.post('/api/design/lock', json={'region_ids': [1], 'locked': False})
    assert unlock_response.status_code == 200
    assert unlock_response.json()['regions'][0]['locked'] is False

    split_response = client.post(
        '/api/design/split',
        json={'region_id': 1, 'target_parts': 3, 'compactness': 8},
    )
    assert split_response.status_code == 200
    assert split_response.json()['validation']['region_count'] > 4

    client.post('/api/design/undo')
    focus_response = client.post(
        '/api/design/detail-zone-for-regions',
        json={'region_ids': [1], 'name': 'eye', 'detail_multiplier': 3},
    )
    assert focus_response.status_code == 200
    assert focus_response.json()['design']['detail_zones'][-1]['name'] == 'eye'

    apply_focus_response = client.post(
        '/api/design/apply-detail-zones',
        json={'max_splits': 1, 'compactness': 8},
    )
    assert apply_focus_response.status_code == 200
    assert apply_focus_response.json()['applied_detail_split_count'] == 1

    repair_response = client.post(
        '/api/design/repair-small-regions',
        json={'max_area': 0.05, 'max_repairs': 2},
    )
    assert repair_response.status_code == 200
    assert 'repaired_region_count' in repair_response.json()

    smooth_response = client.post(
        '/api/design/smooth-boundaries',
        json={'iterations': 1, 'region_ids': [1]},
    )
    assert smooth_response.status_code == 200
    assert 'smoothed_pixel_count' in smooth_response.json()


def test_api_size_and_veneer_inventory(tmp_path: Path) -> None:
    image_path = tmp_path / 'source.png'
    _fixture_image(image_path)
    workspace = MarquetryWorkspace.create(image_path, tmp_path / 'workspace', max_edge=64)
    candidate = workspace.generate_candidate(target_regions=4, compactness=8.0)
    workspace.create_design(candidate.candidate_id, PhysicalSize(width=8, height=8, unit='in'))
    workspace.save()
    client = TestClient(create_app(tmp_path / 'workspace'))

    size_response = client.post(
        '/api/design/size',
        json={'width': 5, 'height': 7, 'unit': 'in'},
    )
    assert size_response.status_code == 200
    assert size_response.json()['design']['physical_size']['width'] == 5

    veneers_response = client.post(
        '/api/design/veneers',
        json=[
            {
                'veneer_id': 'maple',
                'name': 'Maple',
                'color_rgb': [221, 204, 164],
                'sheet_width': 4,
                'sheet_height': 8,
                'sheet_count': 2,
                'texture_url': 'https://example.com/maple.jpg',
            }
        ],
    )
    assert veneers_response.status_code == 200
    assert veneers_response.json()['design']['veneers'][0]['sheet_count'] == 2
    assert (
        veneers_response.json()['design']['veneers'][0]['texture_url']
        == 'https://example.com/maple.jpg'
    )

    duplicate_response = client.post(
        '/api/design/veneers',
        json=[
            {'veneer_id': 'maple', 'name': 'Maple', 'color_rgb': [221, 204, 164]},
            {'veneer_id': 'maple', 'name': 'Duplicate', 'color_rgb': [200, 180, 140]},
        ],
    )
    assert duplicate_response.status_code == 400
