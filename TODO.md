# TODO

## 进行中

- [x] 创建本地模型 Python 原型
- [x] 验证 Qwen3.5 GPU 推理
- [x] 验证 BGE-M3 CPU 向量化

## 计划中

- [x] 创建 IELTS Academic 范文加载、校验与样本级检索文档
- [x] 加入 BGE-M3 CPU 向量调用和 Chroma 索引/检索代码
- [x] 对每条语料强制验证 `exam_type=academic`，拒绝 General Training 混入
- [x] 连接本地 Chroma 并用模拟向量完成持久化建库与检索烟测
- [x] 使用真实 Ollama 模型完成批量嵌入和 GPU/CPU 设备验收
- [x] 找到并核验 IELTS 官方英文评分资料（Updated May 2023）
- [x] 按 Task、评分维度和 Band 结构化 Academic 评分描述；Task 1 排除 General Training 子句
- [ ] 建立 Academic 评分标准向量索引并接入评分提示词
- [ ] 加入 LangGraph 四维评分工作流
- [ ] 加入 FastAPI 接口
- [ ] 加入 React 前端

## 语料策略

- IELTS 模块固定为 Academic，配置只接受 `EXAM_TYPE=academic`。
- `task1_014` 使用与图表一致的已修正题干，并保留源文错配标记。
- `task1_016`（题干不完整）与 `task2_028`（源文末尾不完整）保留在源语料，但默认排除出检索索引。
- 目前按整篇范文加题干建立一个检索文档，不伪造段落边界。
- Academic Task Achievement / Task Response 标准在完成逐 band 结构化前不进入向量索引；混合页不能直接入库。
- 当前小作文 PDF 为 41 页，但核实只有 36 篇完整范文；要补到 41 篇需找齐缺少的 5 篇或确认另一版来源。
