# IELTS 本地模型 Python 原型

这是项目的第一阶段：验证本地 Ollama 模型调用和设备分配。

- Qwen3.5：通过 /api/generate 使用 GPU。
- BGE-M3：通过 /api/embed 使用 CPU。
- HTTP 客户端：HTTPX。
- 配置：Pydantic Settings + .env。

## 环境要求

- Windows 10/11
- Python 3.11+（当前已使用 Python 3.12.14）
- Ollama 服务运行在 http://localhost:11434
- 已安装 qwen3.5:latest 和 bge-m3:latest
- NVIDIA GPU（用于验证 Qwen3.5 显存占用）

## 初始化

    .\.venv\Scripts\Activate.ps1
    $env:HTTP_PROXY=$null
    $env:HTTPS_PROXY=$null
    .\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt --index-url https://pypi.org/simple

当前项目已经完成依赖安装；上面的命令用于重建环境。

## 运行环境检查

    .\.venv\Scripts\python.exe -m app.main --check
    .\.venv\Scripts\python.exe scripts\check_environment.py

成功时应看到：

    Qwen3.5 VRAM: <positive number> bytes
    BGE-M3 VRAM: 0 bytes
    检查通过：Qwen3.5 使用 GPU，BGE-M3 使用 CPU。

也可以在另一个终端运行 nvidia-smi，观察 Qwen3.5 推理时的显存占用。

## 测试和质量检查

    .\.venv\Scripts\python.exe -m pytest
    .\.venv\Scripts\python.exe -m compileall app scripts tests
    .\.venv\Scripts\python.exe -m black --check app scripts tests
    .\.venv\Scripts\python.exe -m flake8 app scripts tests
    .\.venv\Scripts\python.exe -m mypy app

## 设备配置说明

设备分配由每次 API 请求中的 options.num_gpu 控制：

- LLM_NUM_GPU=99：允许 Ollama 将 Qwen3.5 的模型层放到 GPU。
- EMBEDDING_NUM_GPU=0：强制 BGE-M3 不使用 GPU。

程序还会读取 Ollama 的 /api/ps：Qwen3.5 必须有正的 size_vram，BGE-M3 必须是 size_vram=0。

## 后续路线

1. 增加 LlamaIndex 和 Chroma，构建范文检索。
2. 增加 LangGraph，构建四维评分工作流。
3. 增加 FastAPI、数据库和前端。
