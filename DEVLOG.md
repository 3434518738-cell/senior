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

### Academic 任务完成度与论证质量

- 在 Task Achievement 和 Task Response 的结果中增加结构化 `task_review`：每项检查记录 `met` / `partial` / `missing`、说明及可选的作文原文引句。
- Task 1 逐项检查概览、关键特征选择、图表数据准确性、比较和是否超出图表信息；数据核对只使用用户提供的图表上下文，不允许模型补造数据。
- Task 2 逐项检查题目各部分覆盖、立场、观点展开、支撑和切题度；明确禁止把“我将讨论……”之类路线预告当成实际论证。
- 输出模型强制要求任务专属检查项完整且不重复；程序验证检查项与 Task 匹配，并校验检查中的引句确实出现在作文里。
- 检查清单只作为评分证据和解释，不增加官方评分维度，也不设置清单到 Band 的硬编码映射；最低字数边界保持不变。
- 新增流程图与解释文档：`docs/architecture/task-fulfilment-review.md`。
- 按用户决定，不实现提交前的作文截断检测/拦截；评分模型在末尾明确停在半句话、未完成从句或未展开观点时，必须明确说明“提交的作文看起来没有写完”，并在相关维度反馈影响。完整句子但缺少结论段时，按任务结构缺失评分，不直接声称文件被截断，也不另设截断扣分。
- 本地 Qwen 端到端验收发现模型偶尔把检索范文中的文本误引为考生作文证据，触发严格引用校验并中断报告。当前将范文从评分提示中隔离；恢复范文辅助改进建议前，应将参考范文设计成单独署名/归因字段，避免与考生原文证据混淆。
- 后续验收修正：无法逐字核实的模型引句现在置空并保留反馈，不再截短成看似真实的引文，也不因单条引文错误中断整份报告。
- 提示词明确 Academic Task 1 不要求结论段；Task 2 明确要求把末尾未完成分句对论证展开的实际影响纳入 Task Response 描述符判断，不施加额外的“截断扣分”。
- Task 1 图表数据描述现在会以边界标记传入；对于“系列：百分比 in 年份”的简单数据格式，额外解析为系列/年份/数值清单，降低数值归属混淆。
- 离线测试覆盖结构化图表事实和未完成作文指导。当前 47 项测试通过；真实 Qwen 验收仍未通过：三次 Task 1 试跑出现将明确给出的图表值误说成缺失/错误的情况，须继续改进并复验，不能视为已校准评分。
- 新增 Task 1 图片输入：API 请求支持 Base64 图片，CLI 支持 `--chart-image`；评分前调用本地 Qwen 视觉输入抽取摘要、类别、系列/数据点及不确定项，并将读图结构附在最终报告。
- 真实 Ollama 视觉冒烟测试证明 Qwen3.5 9B 可接收并读懂清晰折线图，但 80%/55% 数据估读成约 78%/54%。因此加入 `explicit` / `estimated` 精度标记，估读值与模糊项会提示用户核对，不能作为精确事实断言。
- 当前读图链路已实现但视觉准确率验收未通过/未完成：仍需用带答案的多种真实雅思图表做基准集，前端需呈现读图结果供用户确认；Task 1 数据准确性不得仅凭 Qwen 的估读给出确定错误结论。
- 本轮离线测试 51 项通过；Black、Flake8、mypy、compileall 与 diff 检查通过。
- 读图验收使用本地 Simon PDF 中的第 2、11、12 页三张图表（裁剪掉范文正文，模型只看图表）。结构 JSON 3/3、图表大类 3/3；系列识别 5/8，趋势方向 2/3，估读不确定性处理 2/3。奖牌堆叠条形图漏掉 Gold/Silver/Bronze 并把美国与苏联排名说反，因此视觉验收未通过。
- 两张折线图的系列/年份识别较好，但图内无逐点精确标签，不能诚实计算精确数值准确率；坐标估读已标注 estimated。新增 `docs/architecture/chart-vision-acceptance.md` 记录样本、口径、结果和下一步。


### 2026-10-18：Task 1 图表读图准确性修复

- 将图片读图拆成两次视觉调用：先抽取标题、图例、类别/年份和是否存在数据点直标值；再以结构读取结果为标签键抽取点值。
- 增加输出一致性校验：系列名称与类别被结构结果约束，不存在的类别点会移除并说明；未读到数值的已识别系列保留为空点，不伪造数值。
- 折线图首轮遗漏数值时增加一次精简补读。图中没有数据点直标值时，所有读数由程序强制标记为 `estimated`，并在报告中提示估读不确定性。
- 图表摘要和走势改由对齐后的类别/数值生成，避免摘要单独带入不在结构化数据中的数值主张。
- 修复验收图裁剪范围：老龄人口图完整包含第三条 USA 图例；三张裁图重新放大。固定样本复验：系列 8/8、可见类别/年份标签 28/28；电话图 6 个关键估读点、老龄人口图 18 个关键估读点与人工图表走势核对相符；奖牌图系列和排序识别正确，但色段值继续弃答。
- 这三张练习图未提供逐点精确数值，因此没有宣称数值精确率百分比；下一步仍需构建至少 10 张含标准答案的异类型图表基准集。
- 更新 `docs/architecture/chart-vision-acceptance.md`、README、TODO 和 CHANGELOG。

### 2026-10-18：构建 10 张图表视觉基准并复测

- 建立覆盖折线图、普通/堆叠柱状图、饼图和表格的 10 张 Academic Task 1 图表基准；每个样本保存来源链接/类型、原始数据、图片标准答案及数值容差。
- 其中 4 张逐项核对 World Bank API 当前数据，元数据同时保存原始值和图表显示值；另 6 张为合成控制样本，并明确标记为非真题。
- 通过 Ollama 本地 Qwen3.5 GPU 逐图识别；对被截断 JSON 增加一次紧凑输出重试，对饼图约束单一数值系列和分类扇区。
- 首轮验收暴露堆叠柱图小色段估读问题；改为清晰标注各分段的测试图后复测 16/16 分段值正确。
- 修正图表摘要逻辑：仅在年份类时间轴上判断升降趋势，避免按饼图扇区/国家排序虚构趋势。
- 最新一轮 10/10 图片结构化解析成功；图表类型 10/10、系列 19/19、类别/年份 46/46、时间序列趋势 10/10、可读数值在容差内 76/84（90.5%）、数值覆盖 84/84、精度标记 84/84、不确定性处理 10/10。
- 新增逐张 JSON 结果和汇总报告；这些视觉结果不等同作文评分准确率，未确认的估读值仍不能单独作为 Task Achievement 确定扣分依据。
- 验证：54 项测试通过；Black、Flake8、mypy 和 diff 检查通过。

### 2026-10-18：扩展 Task 1 流程图与地图识别

- 将图片结构识别扩展为 chart / process / map 三类；流程图结构记录有序步骤和箭头分支，地图结构记录方位及改造前后状态。
- Task Achievement 提示按视觉类型切换重点，流程图核对步骤/分支，地图核对位置/前后变化，不要求它们提供并不存在的数值趋势。
- 新增 3 张流程图和 3 张地图合成控制图，逐张保存图像、标准答案和本地模型输出。
- 本地 Qwen3.5 GPU 验收：类型 6/6；流程节点文字 14/15，顺序整图通过 2/3，箭头关系 12/12；地图变化位置/内容 9/9，before/after 字段 18/18。
- 分支流程图仍漏读一个节点标签；当前样本为简单、清晰的项目合成图，不能代表 IELTS 官方题或真实照片表现。
- 更新 `TODO.md`，将“官方公开样题”单独保留为待办；新增 `docs/architecture/process-map-vision-benchmark.md` 和样本目录说明。
- 验证：58 项测试通过；Black、Flake8、mypy、compileall 和 `git diff --check` 通过。

### 2026-10-19：整合三种练习入口的统一服务

- 新增 `PracticeService`，统一处理 `daily`、`question_bank` 和 `upload` 三种模式。
- 新增 `/api/v1/task1/inspect` 图片识别接口；识图和评分分离，用户必须确认 `visual_understanding` 后才能评分。
- 新增 `/api/v1/practice/score` 统一提交接口；返回评分报告、已确认视觉事实和相关 Academic 范文引用。
- 已确认的视觉事实作为评分上下文使用，原图不再重复发送给 Qwen；估读或不确定项继续保留警告。
- 增加统一请求/响应模型、API 测试和服务层测试；三条入口都复用现有 LangGraph 评分、Academic 标准检索和范文检索。
- 验证：63 项测试通过；Black、Flake8、mypy、compileall 和 `git diff --check` 通过。

### 2026-10-19：建立 Academic 题库与练习会话

- 新增 SQLite 题库仓储，从已审核语料同步 36 篇可用 Task 1 和 27 篇可用 Task 2。
- 新增题库筛选、题目详情、每日一练会话和专项练习会话接口；每日会话按日期稳定选择一篇 Task 1 与一篇 Task 2。
- 新增会话项目提交和报告持久化；客户端提交时从会话恢复原题，避免篡改题目文本后评分。
- 保存会话状态、计时字段、作文、提交时间和统一评分报告；用户账户、草稿自动保存、前端倒计时仍待后续。
- 发现并记录一个题库边界：现有 Task 1 范文元数据多数没有原始图像/完整图表数据，Task 1 会话提交必须补充 `chart_context` 或确认视觉事实，不能用题干猜测数据。
- 统一服务进一步适配真实用户流程：用户只上传 Task 1 题目照片即可提交，不需要手写 `chart_context` 或先调用识图接口；服务自动调用 Qwen 读取图表、流程图或地图，将结构化事实放入评分上下文，并在报告中提示核对自动识别结果。已确认的视觉事实仍可直接复用，评分阶段不会重复发送原图。
- 扩展上传题目流程：Task 1 和 Task 2 都通过视觉模型从照片识别题干，用户无需手动输入问题；Task 1 的同一张照片还会提取图表/流程图/地图事实。评分响应提供 `recognized_question` 和不确定文字，报告提示核对识别结果。
- 新增 `frontend/` 本地浏览器页面并由 FastAPI 根路径提供：用户选择任务、上传图片和输入作文后，可直接看到识别题干、评分维度、亮点、改进建议、Task 1 视觉 JSON 和不确定项提示。
- 修复启动文档：系统 PATH 中的 `uvicorn` 可能来自 Python 3.14，而项目依赖在 `.venv`；新增 `scripts/run_server.ps1`，固定使用项目虚拟环境启动服务。
- 针对 Ollama 视觉请求偶发 HTTP 502 增加一次短暂重试；若网关持续失败，错误会包含 Ollama 返回正文。用用户提供的 Task 2 页面截图重放完整识题流程，Qwen 成功识别题目。
- 用户再次遇到偶发 502 后，从页面截图提取题目预览图重放识图成功；将 Ollama 502/503/504 重试扩展为最多 3 次、递增等待，并增加连续两次网关失败后恢复的回归测试。
- 为本地 Ollama HTTP 客户端关闭环境代理读取，避免 VPN 的 `HTTP_PROXY`/`HTTPS_PROXY` 干扰 `localhost:11434`；增加代理隔离回归测试。
- 发现同一篇 Task 1 作文重复提交时估分从 7.0 波动到 6.5；原因包括未固定 Ollama seed，以及每次提交都会重新估读图表。先加入默认 `LLM_SEED=42` 降低模型输出波动，后续继续实现图表识别结果缓存。
- 新增 `docs/architecture/question-bank-and-sessions.md` 说明数据模型和边界。
- 验证：68 项测试通过；Black、Flake8、mypy、compileall 和 `git diff --check` 通过。
