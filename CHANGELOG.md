# Changelog

## [Unreleased]

### Added

- 本地 Ollama 客户端原型。
- Qwen3.5 GPU 推理检查。
- BGE-M3 CPU 向量化检查。
- 离线单元测试和环境检查脚本。

### Changed

- 将下一阶段检索范围锁定为 IELTS Academic，并为 Task 1、Task 2 使用独立 Chroma 集合。
- 新增语料校验、样本级索引、重建入口和命令行相似范文检索。
- 强制逐条 Academic 模块校验，清除增量索引中的过期记录。
- 新增 IELTS Academic 官方评分标准校验与独立 Chroma 集合，记录 80 条 Band 描述和 8 条指引的来源页码及版本。
- 评分上下文按 Task 和维度精确检索完整 Band 0–9 描述；Task 1 使用 Task Achievement，Task 2 使用 Task Response。
- 新增严格的 Academic 评分请求/结果模型、原文证据校验、半分档聚合和一次 JSON 修复重试。
- 新增纯 Python 串行评分管线及 `scripts/score_essay.py`；四项评分全部通过后才返回单篇 `essay_band_estimate`。
- 使用 Ollama JSON Schema 约束评分维度和字段，并在真实 Task 2 冒烟测试中验证 Qwen 输出可解析、证据引用可校验。
