# IELTS Academic Writing RAG 原型

这是一个本地模型原型，当前阶段提供 IELTS Academic Task 1 / Task 2 范文检索，以及官方评分标准结构化、独立建库和按维度取回完整 Band 描述的能力。

- Qwen3.5 通过 Ollama 使用 GPU 推理。
- BGE-M3 通过 Ollama 使用 CPU 向量化（`num_gpu=0`）。
- Task 1 和 Task 2 使用独立的 Chroma 集合。
- 官方评分标准使用单独的 `ielts_academic_rubric` 集合，与范文集合隔离。
- 每条语料必须显式标记 `exam_type=academic`；不会导入 General Training 书信或评分描述。

如果 Ollama 接口可访问但模型列表为空，请检查系统用户变量 `OLLAMA_MODELS` 是否指向包含 `blobs` 和 `manifests` 的模型仓库目录，而不是其下的空子目录。

## 本地运行

```powershell
python -m pip install -r requirements.txt
# LangGraph 工作流依赖（若本机代理不可用，请使用项目脚本）
powershell -ExecutionPolicy Bypass -File scripts/install_workflow.ps1
python -m app.main --check
python scripts/build_index.py --rebuild
python scripts/search_corpus.py --task task1 --query "The line chart compares changes over time" --chart-type line_graph
python scripts/build_rubric_index.py
python scripts/search_rubric.py --task task1 --criterion task_achievement
python scripts/score_essay.py --task task2 --question "Discuss both views." --essay-file essay.txt
python scripts/score_essay.py --workflow --task task2 --question "Discuss both views." --essay-file essay.txt
uvicorn app.api:app --host 127.0.0.1 --port 8000
pytest
```

启动 API 后可在 `http://127.0.0.1:8000/docs` 查看交互式文档。`GET /health` 检查服务状态；`POST /api/v1/score` 接收 Academic 作文并返回完整评分报告。无效输入返回 422，评分模型或本地检索服务失败返回 502。

官方评分资料整理在 `docs/rubrics/academic_writing_rubric.json`，包含 Academic Task 1 / Task 2 的 80 条 Band 0–9 描述和 8 条评分指引。Task 1 的 General Training 书信描述已排除。索引构建时由 BGE-M3 在 CPU 上生成向量。评分时按 Task 和维度精确取回完整的 Band 0–9 描述，避免只靠语义相似度漏掉相邻档位。

当前已经有纯 Python 单篇评分闭环：按 Task/维度取得官方标准和同 Task 范文，串行调用 Qwen 四次并校验 JSON。Task 1 命令还需要 `--chart-type` 和 `--chart-context`。报告中的 `essay_band_estimate` 是单篇作文估分，不是官方 Writing 总分。

评分输出如果无法通过 JSON Schema、评分维度映射或作文证据校验，程序会中止并提示错误，不会返回默认分数或不完整报告。

LangGraph 依赖记录在 `requirements-workflow.txt`，当前已安装并可导入。评分命令增加 `--workflow` 后会使用 LangGraph 编排；不加该参数仍使用已验证的串行入口。若 pip 报错连接
`127.0.0.1:7890`，说明本机代理环境变量指向未运行的代理；FastAPI 与 Uvicorn 已加入基础依赖。请运行
`powershell -ExecutionPolicy Bypass -File scripts/install_workflow.ps1`，脚本只对当前安装进程临时清空代理并直连 PyPI，不会修改系统代理配置。
