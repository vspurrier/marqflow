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
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright

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
            try:
                page.wait_for_function(
                    "document.querySelector('#status')?.textContent?.includes('Workspace ready.')",
                    timeout=15000,
                )
            except PlaywrightTimeoutError as exc:
                raise AssertionError(page.locator('#status').text_content()) from exc

            assert page.locator('#design-canvas').evaluate('node => node.width') == 48
            assert page.locator('.veneer-row').count() >= 1
            assert page.locator('#workspace-list option').count() >= 1

            page.fill('#grid-rows', '2')
            page.fill('#grid-cols', '2')
            page.fill('#min-regions', '4')
            page.fill('#max-regions', '10')
            page.fill('#min-compactness', '4')
            page.fill('#max-compactness', '12')
            page.click('#candidate-grid')
            try:
                page.wait_for_function(
                    (
                        "document.querySelector('#status')?.textContent"
                        "?.includes('Candidate grid ready.')"
                    ),
                    timeout=15000,
                )
            except PlaywrightTimeoutError as exc:
                raise AssertionError(page.locator('#status').text_content()) from exc

            assert page.locator('.candidate').count() >= 4
            page.locator('.candidate button').last.click()
            try:
                page.wait_for_function(
                    (
                        "document.querySelector('#status')?.textContent"
                        "?.includes('Design seeded from')"
                    ),
                    timeout=15000,
                )
            except PlaywrightTimeoutError as exc:
                raise AssertionError(page.locator('#status').text_content()) from exc

            assert page.locator('.region').count() >= 1
            browser.close()
    finally:
        server.should_exit = True
        thread.join(timeout=5)
