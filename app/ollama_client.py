"""Small, typed HTTP client for the local Ollama service."""

from __future__ import annotations

from typing import Any

import httpx

from app.config import AppSettings, get_settings


class OllamaClient:
    """Call Qwen3.5 on the GPU and BGE-M3 on the CPU through Ollama."""

    def __init__(
        self,
        settings: AppSettings | None = None,
        http_client: httpx.Client | None = None,
    ) -> None:
        """Create a client, optionally using an injected HTTP client for tests."""

        self.settings = settings or get_settings()
        self._owns_http_client = http_client is None
        self._http = http_client or httpx.Client(
            base_url=self.settings.ollama_base_url.rstrip("/"),
            timeout=self.settings.request_timeout,
        )

    def __enter__(self) -> "OllamaClient":
        return self

    def __exit__(self, *_args: object) -> None:
        self.close()

    def close(self) -> None:
        """Close the underlying HTTP connection when this client owns it."""

        if self._owns_http_client:
            self._http.close()

    def generate(self, prompt: str) -> str:
        """Generate a response with Qwen3.5 using GPU layers."""

        if not prompt.strip():
            raise ValueError("prompt 不能为空")

        payload = {
            "model": self.settings.llm_model,
            "prompt": prompt,
            "stream": False,
            "think": False,
            "keep_alive": self.settings.keep_alive,
            "options": {
                "num_gpu": self.settings.llm_num_gpu,
                "num_ctx": self.settings.llm_context_length,
                "temperature": self.settings.llm_temperature,
            },
        }
        response = self._post("/api/generate", payload)
        result = response.get("response")
        if not isinstance(result, str):
            raise RuntimeError("Ollama generate 响应缺少 response 文本")
        return result

    def embed(self, text: str) -> list[float]:
        """Create a BGE-M3 embedding while forcing CPU execution."""

        if not text.strip():
            raise ValueError("text 不能为空")

        payload = {
            "model": self.settings.embedding_model,
            "input": text,
            "keep_alive": self.settings.keep_alive,
            "options": {"num_gpu": self.settings.embedding_num_gpu},
        }
        response = self._post("/api/embed", payload)
        embeddings = response.get("embeddings")
        if not isinstance(embeddings, list) or not embeddings:
            raise RuntimeError("Ollama embed 响应缺少 embeddings")
        vector = embeddings[0]
        if not isinstance(vector, list) or not all(
            isinstance(value, (int, float)) for value in vector
        ):
            raise RuntimeError("Ollama embed 返回的向量格式无效")
        return [float(value) for value in vector]

    def list_running_models(self) -> list[dict[str, Any]]:
        """Return models currently loaded by Ollama and their VRAM usage."""

        response = self._get("/api/ps")
        models = response.get("models", [])
        if not isinstance(models, list):
            raise RuntimeError("Ollama /api/ps 响应格式无效")
        return [model for model in models if isinstance(model, dict)]

    def list_available_models(self) -> list[dict[str, Any]]:
        """Return models installed in the local Ollama model store."""

        response = self._get("/api/tags")
        models = response.get("models", [])
        if not isinstance(models, list):
            raise RuntimeError("Ollama /api/tags 响应格式无效")
        return [model for model in models if isinstance(model, dict)]

    def _get(self, path: str) -> dict[str, Any]:
        try:
            response = self._http.get(path)
            response.raise_for_status()
            data = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise RuntimeError(f"Ollama 请求失败: {exc}") from exc
        if not isinstance(data, dict):
            raise RuntimeError("Ollama 响应必须是 JSON 对象")
        return data

    def _post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        try:
            response = self._http.post(path, json=payload)
            response.raise_for_status()
            data = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise RuntimeError(f"Ollama 请求失败: {exc}") from exc
        if not isinstance(data, dict):
            raise RuntimeError("Ollama 响应必须是 JSON 对象")
        return data
