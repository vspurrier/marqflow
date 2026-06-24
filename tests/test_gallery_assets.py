from pathlib import Path

from fastapi.testclient import TestClient

from marqflow.gallery_web import create_app


def test_gallery_static_assets_are_served(tmp_path: Path) -> None:
    workspace_dir = tmp_path / 'workspace'
    workspace_dir.mkdir()

    client = TestClient(create_app(workspace_dir))

    html = client.get('/').text
    assert '<link rel="stylesheet" href="/static/gallery.css" />' in html
    assert '<script defer src="/static/gallery.js"></script>' in html

    css = client.get('/static/gallery.css')
    assert css.status_code == 200
    assert 'workspace-body' in css.text

    js = client.get('/static/gallery.js')
    assert js.status_code == 200
    assert 'renderHuesTab' in js.text
    assert 'renderCleanupTab' in js.text
