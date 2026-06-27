from __future__ import annotations

import socket
import threading
import time
from pathlib import Path

import numpy as np
import pytest
import uvicorn
from PIL import Image
from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import Page, sync_playwright
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

from marqflow.gallery_web import create_app


def _fixture_image(path: Path) -> None:
    image = np.zeros((48, 48, 3), dtype=np.uint8)
    image[:24, :24] = [225, 205, 165]
    image[:24, 24:] = [150, 90, 55]
    image[24:, :24] = [80, 55, 38]
    image[24:, 24:] = [30, 28, 25]
    Image.fromarray(image, mode='RGB').save(path)


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(('127.0.0.1', 0))
        return int(sock.getsockname()[1])


def _wait_for_status(page: Page, text: str) -> None:
    try:
        page.wait_for_function(
            (
                "expected => document.querySelector('#status')?.textContent"
                "?.includes(expected)"
            ),
            arg=text,
            timeout=15000,
        )
    except PlaywrightTimeoutError as exc:
        raise AssertionError(page.locator('#status').text_content()) from exc


def _click_canvas_center(page: Page) -> None:
    canvas = page.locator('#design-canvas')
    canvas.scroll_into_view_if_needed()
    box = canvas.bounding_box()
    if box is None:
        raise AssertionError('design canvas is not visible')
    canvas.click(position={'x': box['width'] / 2, 'y': box['height'] / 2})


def _drag_canvas(page: Page, start_fraction: float, end_fraction: float) -> None:
    canvas = page.locator('#design-canvas')
    canvas.scroll_into_view_if_needed()
    box = canvas.bounding_box()
    if box is None:
        raise AssertionError('design canvas is not visible')
    start = {'x': box['width'] * start_fraction, 'y': box['height'] * start_fraction}
    end = {'x': box['width'] * end_fraction, 'y': box['height'] * end_fraction}
    canvas.hover(position=start)
    page.mouse.down()
    canvas.hover(position=end)
    page.mouse.up()


def _drag_first_vector_handle(page: Page) -> None:
    canvas = page.locator('#design-canvas')
    canvas.scroll_into_view_if_needed()
    box = canvas.bounding_box()
    if box is None:
        raise AssertionError('design canvas is not visible')
    layer = page.evaluate(
        "() => fetch('/api/design/topology/edit-layer').then(response => response.json())"
    )
    vertices = layer.get('vertices') or []
    edges = layer.get('edges') or []
    if not vertices:
        raise AssertionError('no topology vertices available')
    canvas_width = page.locator('#design-canvas').evaluate('node => node.width')
    canvas_height = page.locator('#design-canvas').evaluate('node => node.height')
    vertex_use_count = {}
    for edge in edges:
        for vertex_id in edge.get('vertex_ids') or []:
            vertex_use_count[vertex_id] = vertex_use_count.get(vertex_id, 0) + 1
    vertex = next(
        (
            item
            for item in vertices
            if 0 < item['point'][0] < canvas_width and 0 < item['point'][1] < canvas_height
            and vertex_use_count.get(item['vertex_id'], 0) >= 3
        ),
        None,
    )
    if vertex is None:
        vertex = next(
            (
                item
                for item in vertices
                if 0 < item['point'][0] < canvas_width and 0 < item['point'][1] < canvas_height
            ),
            vertices[0],
        )
    start = {
        'x': box['width'] * vertex['point'][0] / canvas_width,
        'y': box['height'] * vertex['point'][1] / canvas_height,
    }
    end = {
        'x': min(box['width'] - 1, start['x'] + max(4, box['width'] / canvas_width)),
        'y': start['y'],
    }
    canvas.hover(position=start)
    page.mouse.down()
    canvas.hover(position=end)
    page.mouse.up()


def _click_first_vector_edge(page: Page) -> None:
    canvas = page.locator('#design-canvas')
    canvas.scroll_into_view_if_needed()
    box = canvas.bounding_box()
    if box is None:
        raise AssertionError('design canvas is not visible')
    layer = page.evaluate(
        "() => fetch('/api/design/topology/edit-layer').then(response => response.json())"
    )
    edges = layer.get('edges') or []
    edge = next((item for item in edges if not item.get('exterior')), None)
    if edge is None:
        edge = next(iter(edges), None)
    if edge is None:
        raise AssertionError('no topology edges available')
    path = edge.get('path') or []
    if len(path) < 2:
        raise AssertionError('topology edge has no drawable path')
    point = path[len(path) // 2]
    canvas_width = page.locator('#design-canvas').evaluate('node => node.width')
    canvas_height = page.locator('#design-canvas').evaluate('node => node.height')
    canvas.click(
        position={
            'x': box['width'] * point[0] / canvas_width,
            'y': box['height'] * point[1] / canvas_height,
        },
        modifiers=['Shift'],
    )


def test_browser_can_create_workspace_from_image(tmp_path: Path) -> None:
    image_path = tmp_path / 'source.png'
    _fixture_image(image_path)
    port = _free_port()
    server = uvicorn.Server(
        uvicorn.Config(
            create_app(tmp_path / 'active'),
            host='127.0.0.1',
            port=port,
            log_level='warning',
        )
    )
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.monotonic() + 10
    while not server.started and time.monotonic() < deadline:
        time.sleep(0.05)
    if not server.started:
        raise AssertionError('browser test server did not start')

    try:
        with sync_playwright() as playwright:
            try:
                browser = playwright.chromium.launch()
            except PlaywrightError as exc:
                pytest.skip(f'Playwright Chromium is not installed: {exc}')
            page = browser.new_page()
            page.goto(f'http://127.0.0.1:{port}/', wait_until='networkidle')
            page.fill('#workspace-name', 'browser smoke')
            page.set_input_files('#image-input', str(image_path))
            page.fill('#target-regions', '4')
            page.fill('#compactness', '8')
            page.click('#open-image')
            _wait_for_status(page, 'Workspace ready.')

            assert page.locator('#design-canvas').evaluate('node => node.width') == 48
            assert page.locator('.veneer-row').count() >= 1
            assert page.locator('#workspace-list option').count() >= 1
            page.select_option('#selection-mode', 'vector-edit')
            _drag_first_vector_handle(page)
            _wait_for_status(page, 'Preview valid')
            page.click('#accept-vertex-preview')
            _wait_for_status(page, 'Moved vector vertex')
            page.click('#undo')
            _wait_for_status(page, 'Undid last edit.')
            page.click('#preview-vector-simplify')
            _wait_for_status(page, 'Preview valid')
            _click_first_vector_edge(page)
            _wait_for_status(page, 'Selected 1 vector edge')
            page.click('#smooth-vector-selected')
            _wait_for_status(page, 'Smoothed selected vector edge')
            page.click('#undo')
            _wait_for_status(page, 'Undid last edit.')
            page.select_option('#selection-mode', 'box')

            page.fill('#grid-rows', '2')
            page.fill('#grid-cols', '2')
            page.fill('#min-regions', '4')
            page.fill('#max-regions', '10')
            page.fill('#min-compactness', '4')
            page.fill('#max-compactness', '12')
            page.click('#candidate-grid')
            _wait_for_status(page, 'Candidate grid ready.')

            assert page.locator('.candidate').count() >= 4
            page.locator('.candidate button').last.click()
            _wait_for_status(page, 'Design seeded from')

            assert page.locator('.region').count() >= 1
            _click_canvas_center(page)
            page.wait_for_function(
                (
                    "document.querySelector('#selection-status')?.textContent"
                    "?.includes('Selected ')"
                ),
                timeout=15000,
            )
            page.click('#mark-subject')
            _wait_for_status(page, 'Marked ')
            page.select_option('#selection-mode', 'mask-background')
            _drag_canvas(page, 0.1, 0.2)
            _wait_for_status(page, 'Painted background mask.')
            page.select_option('#selection-mode', 'box')
            if page.locator('#selected-veneer option').count() > 1:
                veneer_id = page.locator('#selected-veneer option').nth(1).get_attribute('value')
                page.select_option('#selected-veneer', veneer_id)
            page.click('#assign-selected')
            _wait_for_status(page, 'Assigned ')
            page.click('#undo')
            _wait_for_status(page, 'Undid last edit.')
            page.click('#remove-notches')
            _wait_for_status(page, 'Removed ')
            page.click('#zoom-in')
            assert page.locator('#zoom-label').text_content() == '125%'
            page.click('#zoom-fit')
            assert page.locator('#zoom-label').text_content() == '100%'
            page.click('#clear-selection')
            page.select_option('#selection-mode', 'lasso')
            _drag_canvas(page, 0.2, 0.8)
            page.wait_for_function(
                (
                    "document.querySelector('#selection-status')?.textContent"
                    "?.includes('Selected ')"
                ),
                timeout=15000,
            )
            page.click('#clear-selection')
            page.select_option('#selection-mode', 'box')
            before_merge_count = page.locator('.region').count()
            assert before_merge_count > 1
            _drag_canvas(page, 0.05, 0.95)
            page.click('#merge-selected')
            _wait_for_status(page, 'Merged ')
            assert page.locator('.region').count() < before_merge_count
            page.click('#undo')
            _wait_for_status(page, 'Undid last edit.')
            with page.expect_popup() as popup:
                page.click('#view-svg')
            svg_page = popup.value
            svg_page.wait_for_load_state()
            assert '<svg' in svg_page.content()
            svg_page.close()
            page.click('#pack')
            _wait_for_status(page, 'Pack manifest written')
            assert page.locator('.pack-card').count() >= 1
            browser.close()
    finally:
        server.should_exit = True
        thread.join(timeout=5)
