# 开发日志

## 2026-10-15

### 完成

- 创建本地模型 Python 原型。
- 使用 Python 3.12.14 重建虚拟环境。
- 配置 Qwen3.5 GPU 和 BGE-M3 CPU 请求。
- 添加离线客户端测试和本地设备检查。

### 说明

- Python 3.11 安装器在 Windows 安装阶段被进程锁定，改用已存在的 Python 3.12.14。

## 2026-10-17

### 完成

- 建立 `feature/rag-indexing` 功能分支。
- 新增 IELTS Academic 语料校验、样本级文档构建、Chroma 适配器、索引构建和相似范文检索模块。
- 检索数据固定写入 Academic Task 1 / Task 2 独立集合，并在查询条件中强制过滤 `exam_type=academic`。
- staging JSON 与 manifest 逐条新增 `exam_type=academic`；加载器现在要求显式模块标记及 Academic Task 1 图表类型，拒绝跨模块误导入。
- 增量索引会删除已删除或新近排除的过期向量，避免旧记录绕过语料审核状态。
- 将题干不完整的 Task 1 样本和源文末尾异常的 Task 2 样本排除出默认索引；保留在源数据。
- 评分 PDF 已确认同时含 Academic 与 General Training 描述；Task 1 评分标准索引暂缓，避免混入培训类子句。

### 验证限制

- `pytest` 覆盖 loader、切分、筛选、索引编排与检索过滤。
- 已在当前虚拟环境安装 `chromadb 1.5.9`；使用 1024 维模拟向量完成持久化建库、跨进程重开和 Task 过滤检索烟测。
- Ollama 模型列表为空的原因是用户环境变量 `OLLAMA_MODELS` 指向空的 `D:\ollama\models` 子目录，实际模型清单和权重位于 `D:\ollama`。
- 将用户级 `OLLAMA_MODELS` 修正为 `D:\ollama` 并重启服务后，Qwen3.5 9B Q4_K_M 和 BGE-M3 均被重新识别；没有移动或重新下载模型。
- 真实环境检查通过：Qwen3.5 返回文本并占用 5,537,131,396 bytes VRAM；BGE-M3 返回 1024 维向量，`size_vram=0`。
- 使用真实 BGE-M3 完成 35 篇 Task 1 与 27 篇 Task 2 的持久化索引，并在独立进程中分别检索成功；`task1_016`、`task2_028` 未入库。
- Black、Flake8、compileall 通过；13 项离线测试通过。
- 重新核对 Task 1 PDF 全部 41 页后确认其中有 36 篇完整题目及范文；文件名中的“41篇”与当前版本内容不一致。

### 评分资料更新

- 核验新的官方评分资料：`ielts-writing-band-descriptors.pdf`（9 页）和 `ielts-writing-key-assessment-criteria.pdf`（4 页），均标注 Updated May 2023。
- 两份资料覆盖 Task 1 / Task 2 的 Band 0–9 和四项评分维度。后续只提取 Academic Task 1 图表类描述、Task 2 描述以及 CC、LR、GRA，排除 General Training Task 1 书信描述。
- 新增 `docs/rubrics/academic_writing_rubric.json`，包含 80 条 Academic 描述（两类 Task 各 4 个维度 × Band 0–9）和 8 条评分操作指引。
- 新增评分标准加载校验、提取脚本和 4 项离线测试；已验证 Academic Task 1 描述不含 General Training、bullet points 或 letter 内容。
- 评分资料尚未写入向量库，也尚未接入自动评分工作流；下一步建立 rubric 检索集合并接入评分提示词。

### Academic 评分标准索引

- 为评分标准新增独立的 `ielts_academic_rubric` Chroma 集合，与两类范文集合分离。
- 将 80 条 Band 描述和 8 条官方指引作为 88 条可追溯记录入库，元数据包含 Academic 标记、Task/维度、Band、来源文件、页码和版本。
- BGE-M3 仍通过 Ollama `num_gpu=0` 在 CPU 向量化；建库先完成全部向量与维度检查，再重建现有集合。
- 评分上下文采用 task + criterion 的精确筛选，返回全部 Band 0–9 和相应的 Task 专属/共享指引。相似度不用于代替官方 band 描述比较。
- 加强 rubric loader，校验记录数量、唯一 ID、来源文件/页码、Band 类型及 Academic 关键策略。
- 新增命令 `python scripts/build_rubric_index.py` 和 `python scripts/search_rubric.py --task task1 --criterion task_achievement`。
- 实际使用本地 BGE-M3 构建成功；Chroma rubric 集合包含 88 条记录（80 个描述 + 8 条指引）。
- 真实集合检索验收：Task 1 返回 TA 的 Band 0–9，来源页 3–5；Task 2 返回 TR 的 Band 0–9；未发生 Task 或维度串用。
- 建库完成后 Ollama 运行列表显示 `bge-m3:latest size_vram=0`，确认本阶段向量化仍使用 CPU。
- 评分标准阶段测试：24 项离线测试通过；Black、Flake8、mypy、compileall 通过。

### 单篇评分核心

- 新增 `app/scoring/schemas.py`：严格限制 Academic Task 1/Task 2 输入、四项评分维度、0–9 的整数/半分档，以及禁止额外字段。
- 新增 `app/scoring/prompts.py` 和 `app/scoring/pipeline.py`：按 Task/维度取官方 Band 0–9、检索同 Task 范文，串行调用 Qwen，并要求每条 evidence/issues 引用必须逐字出现在作文中。
- Ollama `/api/generate` 增加可选 `format="json"`；模型输出解析失败时最多修复一次，仍失败则中止，不给默认分数、不返回残缺报告。
- `essay_band_estimate` 使用明确的半分档 half-up 舍入，只表示单篇作文估分；尚未实现 Task 1/Task 2 的正式 1:2 总分。
- 新增 `scripts/score_essay.py`，可以从文本文件启动本地评分；Task 1 必须提供图表类型和图表文字/数据描述。
- 新增 `requirements-workflow.txt` 记录 LangGraph 依赖。
- 排查出 pip 无法安装的直接原因是 `HTTP_PROXY`/`HTTPS_PROXY` 指向未运行的 `127.0.0.1:7890`；临时清空代理并指定 PyPI 后，已安装 LangGraph 1.2.16 及其依赖。
- 新增 `scripts/install_workflow.ps1`，用于在不修改系统代理配置的前提下重复安装工作流依赖。
- 评分核心测试后总计 34 项通过；Black、Flake8、mypy、compileall 通过。
- 真实 Task 2 冒烟测试通过：本地 Qwen 返回四项可解析评分，严格 JSON Schema 约束和一次修复重试生效；短于 250 词的作文生成 warning，不影响报告完整性。
- 冒烟测试后设备状态仍为 `qwen3.5:latest size_vram=5,537,131,396`、`bge-m3:latest size_vram=0`。
- LangGraph 导入验证通过：`StateGraph`、`START`、`END` 均可用；当前测试总计 34 项通过。
- 新增 `app.scoring.workflow`：先校验输入并完成一次检索，再按任务维度顺序运行四个评分节点，最后生成完整报告；Task 1 自动使用 Task Achievement，Task 2 自动使用 Task Response。
- `scripts/score_essay.py` 增加 `--workflow` 入口；工作流离线测试覆盖 Task 1/Task 2，测试总计 36 项通过。
- 下一阶段新增 FastAPI 应用：`GET /health`、`POST /api/v1/score`，启动时构造 LangGraph、Ollama、Academic 范文与 rubric 服务，关闭时释放 Ollama HTTP 客户端。
- 增加输入拒绝和完整评分报告 API 测试；FastAPI 0.143.3 安装成功，全部 39 项离线测试通过。
- 增强评分边界控制：Task 1 少于 150 词、Task 2 少于 250 词时，评分报告返回 `essay_band_estimate=null` 和 `estimate_status=unreliable_under_minimum_words`；四项结果仅用于已有语言的诊断，并在提示词中禁止模型把任务声明当作充分论证。
- 新增短作文边界测试，全部 40 项离线测试通过。任务完成度、论证充分性和疑似截断检测列为下一轮边界控制工作。
