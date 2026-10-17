# IELTS Academic Writing RAG 原型

这是一个本地模型原型，当前阶段只负责 IELTS Academic Task 1 / Task 2 范文的校验、向量建库和相似范文检索。

- Qwen3.5 通过 Ollama 使用 GPU 推理。
- BGE-M3 通过 Ollama 使用 CPU 向量化（`num_gpu=0`）。
- Task 1 和 Task 2 使用独立的 Chroma 集合。
- 每条语料必须显式标记 `exam_type=academic`；不会导入 General Training 书信或评分描述。

如果 Ollama 接口可访问但模型列表为空，请检查系统用户变量 `OLLAMA_MODELS` 是否指向包含 `blobs` 和 `manifests` 的模型仓库目录，而不是其下的空子目录。

## 本地运行

```powershell
python -m pip install -r requirements.txt
python -m app.main --check
python scripts/build_index.py --rebuild
python scripts/search_corpus.py --task task1 --query "The line chart compares changes over time" --chart-type line_graph
pytest
```

官方评分资料已经整理为 `docs/rubrics/academic_writing_rubric.json`，包含 Academic Task 1 / Task 2 的 80 条 Band 0–9 描述和关键评分指引。Task 1 的 General Training 书信内容已排除。评分标准尚未进入向量库，运行 `python -m scripts.validate_rubric` 可以先检查结构化资料。
