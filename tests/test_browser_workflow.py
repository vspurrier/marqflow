from __future__ import annotations

import socket
import threading
import time
from pathlib import Path

import numpy as np
import pytest
import uvicorn
from PIL import Image
from playwright.sync_api import sync_playwright

from marqflow.gallery_web import create_app


def _pick_port() -> int:
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        return int(sock.getsockname()[1])


@pytest.fixture()
def browser_server() -> tuple[str, uvicorn.Server]:
    app = create_app()
    port = _pick_port()
    config = uvicorn.Config(app, host='127.0.0.1', port=port, log_level='warning')
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.time() + 10.0
    while time.time() < deadline:
        if server.started:
            break
        time.sleep(0.05)
    else:  # pragma: no cover - defensive timeout guard
        server.should_exit = True
        thread.join(timeout=5.0)
        raise RuntimeError('server did not start')
    try:
        yield f'http://127.0.0.1:{port}', server
    finally:
        server.should_exit = True
        thread.join(timeout=5.0)


def test_browser_workflow_smoke(tmp_path: Path, browser_server: tuple[str, uvicorn.Server]) -> None:
    base_url, _ = browser_server
    image = np.zeros((64, 64, 3), dtype=np.uint8)
    image[:32, :32] = [88, 88, 88]
    image[:32, 32:] = [124, 124, 124]
    image[32:, :32] = [160, 160, 160]
    image[32:, 32:] = [192, 192, 192]
    input_path = tmp_path / 'source.png'
    Image.fromarray(image, mode='RGB').save(input_path)

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(viewport={'width': 1440, 'height': 1200})
        page.goto(base_url, wait_until='networkidle')

        page.set_input_files('#source-image-input', str(input_path))
        page.click('#open-image-btn')
        page.locator('#workspace-pill').wait_for()
        page.wait_for_function(
            "() => document.querySelector('#image-summary').textContent.includes('Original image')"
        )
        page.click('#shapes-tab-btn')
        page.wait_for_selector('.candidate', state='attached')
        assert 'candidates' in page.locator('#workspace-pill').text_content()

        first_keep = page.locator('.candidate button', has_text='Keep').first
        first_keep.click()
        page.wait_for_selector('#kept-strip .kept-card', state='attached')
        assert page.locator('#compose-kept-count').text_content() == '1'

        page.click('#hues-tab-btn')
        page.wait_for_selector('.compose-candidate')
        page.wait_for_selector('.veneer-row')
        first_veneer = page.locator('.veneer-row').first
        first_veneer.locator('.veneer-sheet-width').fill('14')
        first_veneer.locator('.veneer-sheet-height').fill('9')
        first_veneer.locator('.veneer-grain').fill('vertical')
        first_veneer.locator('.veneer-notes').fill('browser stock note')
        page.click('#save-veneer-palette-btn')
        page.wait_for_function(
            "() => document.querySelector('#status-pill').textContent.includes('Saved veneer')"
        )
        material_workspace = page.evaluate(
            "() => fetch('/api/workspace').then((response) => response.json())"
        )
        first_swatch = material_workspace['veneer_palette'][0]
        assert first_swatch['sheet_width'] == 14
        assert first_swatch['sheet_height'] == 9
        assert first_swatch['grain_direction'] == 'vertical'
        assert first_swatch['notes'] == 'browser stock note'
        page.locator('#compose-summary').wait_for()
        page.locator('.compose-candidate .paint-btn', has_text='Paint all').first.click()
        summary_wait = (
            "() => document.querySelector('#compose-summary')"
            ".textContent.includes('Final partition preview')"
        )
        page.wait_for_function(summary_wait)
        assert 'Final partition preview' in page.locator('#compose-summary').text_content()

        page.click('#cleanup-tab-btn')
        page.wait_for_function(
            "() => document.querySelector('#merge-summary').textContent.includes('Partition')"
        )
        page.locator('#small-area').fill('100')
        page.locator('#thin-width').fill('20')
        page.click('#save-cleanup-btn')
        page.wait_for_function(
            "() => document.querySelector('#status-pill').textContent.includes('Saved cleanup')"
        )
        cleanup_text = page.locator('#merge-summary').text_content()
        assert 'Partition' in cleanup_text
        merge_box = page.locator('#merge-canvas').bounding_box()
        assert merge_box is not None
        page.mouse.move(merge_box['x'] + 20, merge_box['y'] + 20)
        page.mouse.down()
        page.mouse.move(merge_box['x'] + 120, merge_box['y'] + 120)
        page.mouse.up()
        page.wait_for_timeout(200)
        assert page.locator('.final-region-item.selected').count() >= 1

        workspace = page.evaluate(
            "() => fetch('/api/workspace').then((response) => response.json())"
        )
        final_regions = workspace['final_regions']
        editable_region = next(
            (region for region in final_regions if region['point_count'] > 0),
            None,
        )
        assert editable_region is not None
        region_id = editable_region['region_id']
        page.locator(f".final-region-item[data-region-id='{region_id}']").click()
        page.locator(f".final-region-item[data-region-id='{region_id}']").locator('select').select_option(
            'blue'
        )
        page.locator('#final-point-index').fill('0')
        page.locator('#final-point-x').fill(str(float(editable_region['contour'][0][0]) + 1.0))
        page.locator('#final-point-y').fill(str(float(editable_region['contour'][0][1]) + 1.0))
        page.click('#final-point-move-btn')
        page.wait_for_timeout(250)
        page.click('#final-smooth-btn')
        page.wait_for_timeout(250)
        assert 'Region' in page.locator('#final-region-editor-note').text_content()

        merge_pair = None
        for region in final_regions:
            neighbors = region.get('neighbors') or []
            if neighbors:
                merge_pair = (region['region_id'], neighbors[0])
                break
        assert merge_pair is not None
        first_id, second_id = merge_pair
        initial_region_count = len(final_regions)
        page.locator(f".final-region-item[data-region-id='{first_id}']").click()
        page.locator(f".final-region-item[data-region-id='{second_id}']").click()
        merged_workspace = page.evaluate(
            """async ([firstRegionId, secondRegionId]) => {
                const response = await fetch('/api/workspace/final/merge', {
                  method: 'POST',
                  headers: {'Content-Type': 'application/json'},
                  body: JSON.stringify({region_ids: [firstRegionId, secondRegionId]}),
                });
                if (!response.ok) {
                  throw new Error(await response.text());
                }
                return response.json();
            }""",
            [first_id, second_id],
        )
        assert merged_workspace['final_region_count'] < initial_region_count
        page.reload(wait_until='networkidle')
        page.click('#cleanup-tab-btn')
        page.wait_for_function(
            "() => document.querySelector('#merge-summary').textContent.includes('Partition')"
        )
        merged_text = page.locator('#merge-summary').text_content()
        assert 'Partition' in merged_text

        page.click('#pack-tab-btn')
        page.wait_for_selector('#pack-summary')
        assert 'Physical size' in page.locator('#pack-summary').text_content()

        browser.close()
