from pathlib import Path

import pytest
import web
from fastapi import FastAPI
from fastapi.testclient import TestClient

from openlibrary.utils import request_context


@pytest.mark.usefixtures("render_template")
def test_preview_dialog_renders_once_in_each_fastapi_request(mock_site, monkeypatch):
    monkeypatch.setattr(request_context, "create_site", lambda: mock_site)
    path = Path("openlibrary/macros/BookPreviewFloater.html")
    render = web.template.Template(path.read_text(), filename=str(path))
    app = FastAPI()

    @app.middleware("http")
    async def set_context(request, call_next):
        request.state.lang = "en"
        request_context.set_context_from_fastapi(request)
        return await call_next(request)

    @app.get("/preview")
    async def preview():
        return {"partials": str(render()) + str(render())}

    with TestClient(app) as client:
        responses = [client.get("/preview") for _ in range(2)]

    assert [response.status_code for response in responses] == [200, 200]
    markup = [response.json()["partials"] for response in responses]
    assert all(html.count('id="bookPreview"') == 1 for html in markup)
    assert markup[0] == markup[1]
