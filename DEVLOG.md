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
