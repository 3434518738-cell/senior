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
python -m app.main --check
python scripts/build_index.py --rebuild
python scripts/search_corpus.py --task task1 --query "The line chart compares changes over time" --chart-type line_graph
python scripts/build_rubric_index.py
python scripts/search_rubric.py --task task1 --criterion task_achievement
pytest
```

官方评分资料整理在 `docs/rubrics/academic_writing_rubric.json`，包含 Academic Task 1 / Task 2 的 80 条 Band 0–9 描述和 8 条评分指引。Task 1 的 General Training 书信描述已排除。索引构建时由 BGE-M3 在 CPU 上生成向量。评分时按 Task 和维度精确取回完整的 Band 0–9 描述，避免只靠语义相似度漏掉相邻档位。

当前还没有将检索上下文交给 Qwen，也没有实现自动评分工作流。单篇作文评分闭环是接下来的开发阶段。
