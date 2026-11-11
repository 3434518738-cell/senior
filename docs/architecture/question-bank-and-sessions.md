# Academic 题库与练习会话

## 数据来源

题库从 `data/corpus_staging/task1` 和 `task2` 读取已经通过 Academic 校验的语料。缺少必要字段、标记为不适合检索的源文记录不会进入题库。当前可练数量为 Task 1 34 道和 Task 2 27 道，Task 1 必须有原图；范文的题目、题型、图表类型、主题和来源页码写入 SQLite。

SQLite 数据库为 `data/practice.sqlite3`，包含：

- `questions`：Academic 题目和筛选元数据；
- `practice_sessions`：每日或专项练习会话、计时字段和状态；
- `session_items`：会话中的题目、作文、提交时间和 JSON 评分报告。

数据库在应用启动时自动创建，并用当前经过校验的语料执行幂等同步。数据库和本地语料都在 `.gitignore` 中，不会上传到 GitHub。

## 每日一练

用户在 `/daily` 先按来源题型或关键词筛选、预览并选择一道 Task 1 和一道 Task 2；点击开始后，通过 `{"mode":"daily","question_ids":["task1_028","task2_002"],"duration_seconds":3600}` 创建会话。后端验证两题存在、可练、不重复且各属于一种 Task，始终按 Task 1、Task 2 顺序保存。缺少选择时返回 422。题目开始后固定，已移除刷新路由和相关业务方法。

Task 1 以 `chart_type` 为主要分类，包含 7 类；Task 2 以 `question_type` 分类，包含 8 类，保留原资料的混合题型标签。前端 `question-bank.js` 映射中文名称并按当前可练记录统计数量，题型与关键词筛选共同生效；关键词可匹配标题、题干、主题及中文题型。预览只提供题干与 Task 1 原图，不包含范文正文。每日一练仍使用 `daily` 模式，评分后可获得独立范文学习建议。

新的数据库不再创建刷新字段；已有 SQLite 数据库中的历史刷新字段保留，但不读取、修改或暴露到会话响应。既有会话、作文和报告保持可读，不作破坏性迁移。

## 专项练习

创建 `mode=question_bank` 会话时必须传入 `task_type` 和 `question_id`。服务会核对题目确实属于对应的 Academic Task，然后创建单题会话。提交时，服务从会话取回原题，避免客户端篡改题目文本后再评分。

## 提交与评分

会话提交复用统一练习服务：Task 1 可以直接上传题目照片，服务自动调用本地 Qwen 识别图表、流程图或地图，再按官方 Academic 四项标准评分；识别结果和“建议核对”警告会随评分报告保存。若客户端已经提供并确认 `visual_understanding`，服务会直接使用确认后的事实。每日会话的两篇作文可以分别提交；全部项目提交后会话状态变为 `submitted`。

可练 Task 1 的原图由 `frontend/assets/question-images/source_manifest.json` 映射，提交会话时自动载入并识图。没有原图的来源记录可以继续用于范文检索，但不进入可练题库。调用独立统一评分接口时，也可提供图片、`chart_context` 或已确认的 `visual_understanding`。

当前前端提供选题、确认后的倒计时与逐句评分反馈；选题过程中不计时，超时后的页面提交会被锁定。后端尚未把超时写入独立状态，也没有草稿自动保存、用户账户和历史趋势页面，这些属于下一阶段产品功能。
