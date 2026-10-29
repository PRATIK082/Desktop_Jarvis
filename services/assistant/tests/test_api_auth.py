"""Regression tests for sidecar REST auth + model selection (E3b).

Covers the smoking-gun E3b finding: backend endpoint params
`authorization: str | None = None` bound the *query string only*, while the
UI sends `Authorization: Bearer <token>` headers — so every frontend REST
call 401'd whenever a real token was set. All REST endpoints now resolve the
token from header-or-query via the `_auth_token` dependency.

Also covers POST /v1/models/select (frontend selection must reach the
sidecar's `settings.ollama_chat_model`, which the chat path actually uses).

Hermetic: Ollama is stubbed (no live server needed); settings mutated via
monkeypatch (auto-restored).
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from starlette import status as http_status

import jarvis.api.app as app_module
from jarvis.api.app import create_app
from jarvis.config import settings


class _FakeOllama:
    def __init__(self, models: list[str]) -> None:
        self._models = models

    async def list_models(self) -> list[str]:
        return list(self._models)


@pytest.fixture()
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setattr(settings, "auth_token", "secret123")
    monkeypatch.setattr(settings, "ollama_chat_model", "")
    monkeypatch.setattr(app_module, "_ollama_client", _FakeOllama(["qwen3:14b", "bge-m3"]))
    return TestClient(create_app())


def test_health_accepts_bearer_header(client: TestClient) -> None:
    resp = client.get("/health", headers={"Authorization": "Bearer secret123"})
    assert resp.status_code == http_status.HTTP_200_OK, resp.text


def test_health_accepts_query_param(client: TestClient) -> None:
    resp = client.get("/health", params={"authorization": "secret123"})
    assert resp.status_code == http_status.HTTP_200_OK, resp.text


def test_health_rejects_missing_and_wrong_token(client: TestClient) -> None:
    assert client.get("/health").status_code == http_status.HTTP_401_UNAUTHORIZED
    assert (
        client.get("/health", headers={"Authorization": "Bearer wrong"}).status_code
        == http_status.HTTP_401_UNAUTHORIZED
    )


def test_models_accepts_bearer_header(client: TestClient) -> None:
    resp = client.get("/v1/models", headers={"Authorization": "Bearer secret123"})
    assert resp.status_code == http_status.HTTP_200_OK, resp.text
    body = resp.json()
    assert body["models"] == ["qwen3:14b", "bge-m3"]
    assert body["selected"] == ""
    assert body["healthy"] is True


def test_select_model_persists_selection(client: TestClient) -> None:
    resp = client.post(
        "/v1/models/select",
        headers={"Authorization": "Bearer secret123"},
        json={"model": "qwen3:14b"},
    )
    assert resp.status_code == http_status.HTTP_200_OK, resp.text
    assert resp.json()["selected"] == "qwen3:14b"
    assert settings.ollama_chat_model == "qwen3:14b"
    # Selection is reflected by the listing endpoint.
    listed = client.get("/v1/models", headers={"Authorization": "Bearer secret123"}).json()
    assert listed["selected"] == "qwen3:14b"


def test_select_unknown_model_rejected(client: TestClient) -> None:
    resp = client.post(
        "/v1/models/select",
        headers={"Authorization": "Bearer secret123"},
        json={"model": "nope:not-a-model"},
    )
    assert resp.status_code == http_status.HTTP_400_BAD_REQUEST, resp.text


def test_select_empty_model_rejected(client: TestClient) -> None:
    resp = client.post(
        "/v1/models/select",
        headers={"Authorization": "Bearer secret123"},
        json={"model": "   "},
    )
    assert resp.status_code == http_status.HTTP_400_BAD_REQUEST, resp.text


def test_select_requires_auth(client: TestClient) -> None:
    resp = client.post("/v1/models/select", json={"model": "qwen3:14b"})
    assert resp.status_code == http_status.HTTP_401_UNAUTHORIZED
