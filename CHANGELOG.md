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
