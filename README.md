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

启动 API 后打开 `http://127.0.0.1:8000/` 可使用本地上传评分页面。页面只要求选择 Task 1/Task 2、上传题目照片和输入作文；题目文字由 Qwen 自动识别。Task 1 的同一张照片还会进入图表、流程图或地图识别流程，识别结果和核对提示会显示在评分结果页。

Task 1 命令行读图示例：

```powershell
python scripts/score_essay.py --task task1 --question "Summarise the chart." --essay-file essay.txt --chart-type line_graph --chart-image chart.png
```

API 请求可将题目照片的 Base64 内容放在 `chart_image_base64` 字段中（小于 10 MB）；用户不需要先填写 `chart_type` 或整理 `chart_context`，统一练习服务会先调用本地 Qwen 自动识别。图片读图结果会出现在返回 JSON 的 `chart_understanding` 中，并带有建议核对的警告；特别要核对标注为 `estimated` 的坐标估读值。

官方评分资料整理在 `docs/rubrics/academic_writing_rubric.json`，包含 Academic Task 1 / Task 2 的 80 条 Band 0–9 描述和 8 条评分指引。Task 1 的 General Training 书信描述已排除。索引构建时由 BGE-M3 在 CPU 上生成向量。评分时按 Task 和维度精确取回完整的 Band 0–9 描述，避免只靠语义相似度漏掉相邻档位。

当前已经有纯 Python 单篇评分闭环：按 Task/维度取得官方标准，串行调用 Qwen 四次并校验 JSON。范文仍用于检索和后续参考建议开发，但目前不放入评分提示词，以免模型把范文句子误当作考生证据。Task 1 可提供 `chart_context`，也可提供 `chart_image_base64`；图片评分会先独立识别图表类型、图例和类别，再按这些标签读取数据；必要时对缺失的折线数据做一次精简补读。返回的 `chart_understanding` 会对齐已识别系列和类别，并基于结构化估读生成简短走势摘要。CLI 可使用 `--chart-image`，图片需为小于 10 MB 的 PNG/JPEG/GIF/WebP。没有直接标在数据点旁的数值一律标为 estimated，报告同时提示核对，不可当作精确图表事实。三张本地 Simon 图表固定样本已通过系列、类别/年份和主要趋势检查；未标数的数值仍是坐标估读，堆叠条形图分段值会在无法可靠读取时弃答。10 张多图表类型基准已完成，详细结果见 `docs/architecture/chart-vision-acceptance.md` 和 `docs/architecture/chart-vision-benchmark.md`。报告中的 `essay_band_estimate` 是单篇作文估分，不是官方 Writing 总分。低于 Task 1 150 词或 Task 2 250 词时，系统仍分析已有语言，但 `essay_band_estimate` 为 `null`，`estimate_status` 为 `unreliable_under_minimum_words`，避免把短文误报为高分。

评分输出如果无法通过 JSON Schema、评分维度映射或作文证据校验，程序会中止并提示错误，不会返回默认分数或不完整报告。

图表视觉验收基准位于 `tests/fixtures/chart_benchmark`，包含 10 张图、来源、原始数据、标准答案、容差和逐张 Qwen 结果；运行方式见该目录 README，汇总见 `docs/architecture/chart-vision-benchmark.md`。视觉读图使用 4096 上下文以避免多系列 JSON 被截断。当前基准的结构识别和趋势识别均为 100%，数值精度仍需按报告中的估读与堆叠柱状图限制理解。

Task 1 图片读取现支持统计图表、流程图和地图。流程图会提取步骤与连接关系，地图会提取位置及改造前后内容；Task Achievement 提示会针对流程/地图调整检查重点。当前 6 张流程图/地图基准是项目合成控制图，不代表 IELTS 官方样题。验收指标及流程图漏读节点的限制见 `docs/architecture/process-map-vision-benchmark.md`。用户上传图片后仍需核对识别结果；官方公开样题的独立测试集尚未建立。

Task Achievement / Task Response 结果还包含任务完成度检查：Task 1 检查概览、关键特征、数据、比较和图表范围；Task 2 检查题目覆盖、立场、观点展开、支撑和切题度。各项会标记为 `met`、`partial`、`missing` 或 `not_verifiable` 并提供解释；这份清单用于支撑评分理由，不单独转换成分数。流程图和边界说明见 `docs/architecture/task-fulfilment-review.md`。

三个用户入口现在共享统一练习服务。用户上传模式不需要输入题目文字：Task 1/Task 2 均可通过 `question_image_base64` 上传题目照片，由 Qwen 识别题干并在响应的 `recognized_question` 中返回；Task 1 还会自动识别图表、流程图或地图，视觉事实出现在 `report.chart_understanding`。Task 1 可将同一张照片同时放入 `question_image_base64` 和 `chart_image_base64`，也可以只传前者。`POST /api/v1/task1/inspect` 可单独识别 Task 1 视觉事实；上传照片直接评分时自动识图，并在报告中提示核对识别结果。每日一练和题库练习继续使用系统已有题目，不需要上传题干。统一服务设计见 `docs/architecture/unified-practice-service.md`。

题库和练习会话接口已经接入 SQLite：`GET /api/v1/question-bank` 浏览可用 Academic 题目，`GET /api/v1/question-bank/{question_id}` 查看题目，`POST /api/v1/practice/sessions` 创建每日一练或专项会话，`GET /api/v1/practice/sessions/{session_id}` 查看会话，`POST /api/v1/practice/sessions/{session_id}/submit` 提交作文并保存报告。题库由 `data/corpus_staging` 中通过校验的样本自动同步；本地数据库为 `data/practice.sqlite3`，不会提交到 Git。当前计时字段已保存，但前端倒计时和超时控制仍待实现。

注意：现有范文语料的 Task 1 题目记录多数没有原始图片或完整图表数据。Task 1 题库会话提交时可以直接上传题目照片，系统会自动识图；也可以提供 `chart_context` 或已确认的 `visual_understanding`。三者都缺少时系统会拒绝评分，不会猜测数据。

当前评分流程按提交内容直接评阅，不在提交前拦截或运行独立的截断检测。若作文末尾明确停在半句话、未完成从句或未展开的观点中，模型应明确告诉用户“提交的作文看起来没有写完”，并在相关评分维度的理由或改进建议中解释影响。若最后一句完整但缺少结论段，则按任务结构缺失影响评分，不能把它直接描述成文件被截断。

LangGraph 依赖记录在 `requirements-workflow.txt`，当前已安装并可导入。评分命令增加 `--workflow` 后会使用 LangGraph 编排；不加该参数仍使用已验证的串行入口。若 pip 报错连接
`127.0.0.1:7890`，说明本机代理环境变量指向未运行的代理；FastAPI 与 Uvicorn 已加入基础依赖。请运行
`powershell -ExecutionPolicy Bypass -File scripts/install_workflow.ps1`，脚本只对当前安装进程临时清空代理并直连 PyPI，不会修改系统代理配置。
