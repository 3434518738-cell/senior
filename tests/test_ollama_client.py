"""Offline tests for Ollama request construction and response parsing."""

import httpx
import pytest

from app.config import AppSettings
from app.ollama_client import OllamaClient


@pytest.fixture
def settings() -> AppSettings:
    """Provide deterministic test settings."""

    return AppSettings(
        ollama_base_url="http://testserver",
        llm_model="qwen3.5:latest",
        embedding_model="bge-m3:latest",
        llm_num_gpu=99,
        embedding_num_gpu=0,
    )


def test_generate_uses_gpu_options(settings: AppSettings) -> None:
    """Qwen requests explicitly ask Ollama for GPU layers."""

    def handler(request: httpx.Request) -> httpx.Response:
        payload = request.read()
        assert b'"num_gpu":99' in payload
        assert b'"model":"qwen3.5:latest"' in payload
        return httpx.Response(200, json={"response": "OK"})

    transport = httpx.MockTransport(handler)
    with httpx.Client(base_url="http://testserver", transport=transport) as http_client:
        with OllamaClient(settings=settings, http_client=http_client) as client:
            assert client.generate("hello") == "OK"


def test_generate_can_request_json_format(settings: AppSettings) -> None:
    """Structured scoring requests pass Ollama's JSON format option."""

    def handler(request: httpx.Request) -> httpx.Response:
        payload = request.read()
        assert b'"format":"json"' in payload
        return httpx.Response(200, json={"response": "{}"})

    transport = httpx.MockTransport(handler)
    with httpx.Client(base_url="http://testserver", transport=transport) as http_client:
        with OllamaClient(settings=settings, http_client=http_client) as client:
            assert client.generate("return json", response_format="json") == "{}"


def test_generate_forwards_image_payload(settings: AppSettings) -> None:
    """Vision requests pass base64 images to Ollama generate."""

    def handler(request: httpx.Request) -> httpx.Response:
        payload = request.read()
        assert b'"images":["aW1hZ2U="]' in payload
        return httpx.Response(200, json={"response": "{}"})

    transport = httpx.MockTransport(handler)
    with httpx.Client(base_url="http://testserver", transport=transport) as http_client:
        with OllamaClient(settings=settings, http_client=http_client) as client:
            assert client.generate("read this", images=["aW1hZ2U="]) == "{}"


def test_embed_uses_cpu_options(settings: AppSettings) -> None:
    """BGE requests explicitly disable GPU layers."""

    def handler(request: httpx.Request) -> httpx.Response:
        payload = request.read()
        assert b'"num_gpu":0' in payload
        assert b'"model":"bge-m3:latest"' in payload
        return httpx.Response(200, json={"embeddings": [[0.1, 0.2, 0.3]]})

    transport = httpx.MockTransport(handler)
    with httpx.Client(base_url="http://testserver", transport=transport) as http_client:
        with OllamaClient(settings=settings, http_client=http_client) as client:
            assert client.embed("hello") == [0.1, 0.2, 0.3]


def test_running_models_are_parsed(settings: AppSettings) -> None:
    """The /api/ps response is exposed as a list of model dictionaries."""

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/ps"
        return httpx.Response(
            200,
            json={"models": [{"name": "qwen3.5:latest", "size_vram": 123}]},
        )

    transport = httpx.MockTransport(handler)
    with httpx.Client(base_url="http://testserver", transport=transport) as http_client:
        with OllamaClient(settings=settings, http_client=http_client) as client:
            assert client.list_running_models()[0]["size_vram"] == 123


def test_http_errors_have_actionable_message(settings: AppSettings) -> None:
    """Transport failures are wrapped in a project-level RuntimeError."""

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, text="service unavailable")

    transport = httpx.MockTransport(handler)
    with httpx.Client(base_url="http://testserver", transport=transport) as http_client:
        with OllamaClient(settings=settings, http_client=http_client) as client:
            with pytest.raises(RuntimeError, match="Ollama 请求失败"):
                client.generate("hello")


def test_gateway_error_is_retried_once(settings: AppSettings) -> None:
    """A transient Ollama gateway error gets one retry before succeeding."""
    attempts = 0

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            return httpx.Response(502, text="runner temporarily unavailable")
        return httpx.Response(200, json={"response": "OK"})

    transport = httpx.MockTransport(handler)
    with httpx.Client(base_url="http://testserver", transport=transport) as http_client:
        with OllamaClient(settings=settings, http_client=http_client) as client:
            assert client.generate("hello") == "OK"
    assert attempts == 2


def test_gateway_error_includes_ollama_response_body(settings: AppSettings) -> None:
    """A persistent gateway error exposes Ollama's diagnostic response."""

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(502, text="runner ran out of memory")

    transport = httpx.MockTransport(handler)
    with httpx.Client(base_url="http://testserver", transport=transport) as http_client:
        with OllamaClient(settings=settings, http_client=http_client) as client:
            with pytest.raises(RuntimeError, match="runner ran out of memory"):
                client.generate("hello")
