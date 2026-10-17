# IELTS Academic 范文检索（第一阶段）

本阶段搭建本地范文检索，不进行作文自动评分，也不开发 Web 界面。项目将
`exam_type` 固定为 `academic`，Task 1 和 Task 2 使用不同的 Chroma 集合。

## 已实现的数据流程

1. 从 `data/corpus_staging/task1` 与 `task2` 读取拆分后的 JSON。
2. 校验 `sample_id`、Task 类型、题干、答案和来源页码。
3. 为每篇作文构建一个“任务类型 + 标题 + 题干 + 完整范文”的检索文档。
   当前答案未保存可靠的段落边界，所以先按整篇作文索引，不推测段落。
4. 使用现有 `OllamaClient.embed()` 调用 BGE-M3，显式设置 `num_gpu=0`。
5. 把向量和扁平元数据写入 Chroma 持久化目录。
6. 按 Task 类型、Academic 模块和可选图表类型过滤后检索。

每条语料必须显式标记 `exam_type: "academic"`；加载器拒绝 General Training、缺失模块标记，以及缺少 Academic Task 1 图表类型的记录。默认将 `task1_016` 与 `task2_028` 留在源文件中，但排除在范文向量索引外。
`task1_014` 使用校正后的图表题干参与检索，同时保留来源错配标记。

## 评分标准范围

当前采用用户提供的 IELTS 官方资料：

- `ielts-writing-band-descriptors.pdf`：Updated May 2023，提供 Task 1 / Task 2 的 Band 0–9 描述。
- `ielts-writing-key-assessment-criteria.pdf`：Updated May 2023，说明四项评分维度、最低字数、Academic Task 1 的信息转述要求，以及 Task 2 的评分关注点。

两份资料同时包含 Academic 和 General Training。建立评分标准资料库时，只保留 Academic
Task 1 的图表、流程图、地图等信息转述描述，排除 General Training Task 1 的书信描述；
Task 2 保留其通用描述。原始分页抽取文本不会直接写入向量集合，必须先按任务、评分维度
和 band 结构化并人工复核。

当前结构化文件为 `docs/rubrics/academic_writing_rubric.json`。可用下面的命令检查覆盖范围：

```powershell
python -m scripts.validate_rubric
```

文件包含 80 条 Band 0–9 描述和 8 条关键评分指引。评分标准向量集合尚未建立，后续会在确认这份结构化内容后单独建库，避免与范文集合混用。

如果以后更换官方 PDF，需要额外安装 `requirements-rubric.txt` 后运行 `scripts/extract_academic_rubric.py` 重新生成该文件；日常运行和测试不依赖 PDF 解析库。

## 安装与运行

联网安装依赖后，在项目根目录运行：

```powershell
python -m pip install -r requirements.txt
python scripts/build_index.py --rebuild
python scripts/search_corpus.py --task task1 --query "The line chart compares changes over time" --chart-type line_graph
python scripts/search_corpus.py --task task2 --query "Should governments fund the arts?"
```

索引集合：

- `ielts_academic_task1_samples`
- `ielts_academic_task2_samples`

Chroma 默认保存在被 Git 忽略的 `data/chroma_db`。`--rebuild` 会清空这两个集合后重新嵌入所有合格作文；不带该选项会更新现有记录，并清理已从源语料删除或新近标记为不合格的过期记录。

## 验收标准

- Task 1 检索不会返回 Task 2，反之亦然。
- 所有集合与查询强制携带 `exam_type=academic`。
- `task1_016` 与 `task2_028` 默认不在集合中。
- BGE-M3 输出维度为 1024，并由 Ollama 请求配置保持 CPU 推理。
- `task1_014` 的错配标记会保存在 Chroma 元数据中。
