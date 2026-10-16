"""Command-line entry point for the local model prototype."""

from __future__ import annotations

import argparse
import platform
import sys
from collections.abc import Iterable
from typing import Any

from app.ollama_client import OllamaClient


def _model_name(model: dict[str, Any]) -> str:
    value = model.get("name") or model.get("model")
    return str(value) if value is not None else "<unknown>"


def _find_model(models: Iterable[dict[str, Any]], name: str) -> dict[str, Any] | None:
    """Find a model by its Ollama name or model field."""

    for model in models:
        if model.get("name") == name or model.get("model") == name:
            return model
    return None


def run_check() -> int:
    """Run service, model, device-placement, and embedding checks."""

    print("=== IELTS 本地模型环境检查 ===")
    print(f"Python: {platform.python_version()}")

    with OllamaClient() as client:
        available = client.list_available_models()
        available_names = {_model_name(model) for model in available}
        settings = client.settings
        required = (settings.llm_model, settings.embedding_model)
        missing = [name for name in required if name not in available_names]
        if missing:
            raise RuntimeError(f"Ollama 缺少模型: {', '.join(missing)}")
        print(f"Ollama: OK ({settings.ollama_base_url})")
        print(f"已安装模型: {', '.join(sorted(available_names))}")

        answer = client.generate("Reply with exactly OK.")
        print(f"Qwen3.5 GPU 推理: {answer.strip() or '<empty>'}")

        vector = client.embed("IELTS writing environment check")
        print(f"BGE-M3 CPU 向量化: dimension={len(vector)}")
        if len(vector) != 1024:
            raise RuntimeError(f"BGE-M3 向量维度异常: {len(vector)}，预期 1024")

        running = client.list_running_models()
        qwen = _find_model(running, settings.llm_model)
        bge = _find_model(running, settings.embedding_model)
        if qwen is None:
            raise RuntimeError("Qwen3.5 未出现在 Ollama 运行模型列表中")
        if bge is None:
            raise RuntimeError("BGE-M3 未出现在 Ollama 运行模型列表中")

        qwen_vram = int(qwen.get("size_vram", 0) or 0)
        bge_vram = int(bge.get("size_vram", 0) or 0)
        print(f"Qwen3.5 VRAM: {qwen_vram:,} bytes")
        print(f"BGE-M3 VRAM: {bge_vram:,} bytes")
        if qwen_vram <= 0:
            raise RuntimeError("Qwen3.5 没有使用显卡显存")
        if bge_vram != 0:
            raise RuntimeError("BGE-M3 仍占用显存，CPU 配置未生效")

    print("检查通过：Qwen3.5 使用 GPU，BGE-M3 使用 CPU。")
    return 0


def main() -> int:
    """Parse command-line arguments and run the requested operation."""

    parser = argparse.ArgumentParser(description="IELTS 本地模型原型")
    parser.add_argument(
        "--check",
        action="store_true",
        help="检查 Ollama 和模型设备分配",
    )
    args = parser.parse_args()
    if not args.check:
        parser.print_help()
        return 0
    try:
        return run_check()
    except (RuntimeError, ValueError) as exc:
        print(f"检查失败: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
