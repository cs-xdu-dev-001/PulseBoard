# LLM Yesterday Finalization and Filter Performance Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 按北京时间持续校准昨天的官方LLM每日汇总，并让供应商、Key和时间筛选快速且无竞态。

**Architecture:** 后端复用`llm_usage_daily`和现有质量字段，增加精确目标日期采集及每小时重试，写入时保护高质量行。前端用AbortSignal、TTL Promise缓存和路由懒加载减少重复网络、失效解析和初始包体。

**Tech Stack:** FastAPI、SQLAlchemy、APScheduler、httpx、React、ECharts、pytest、Vitest。

---

### Task 1: 保护每日完整数据

**Files:**
- Modify: `backend/app/llm_daily.py`
- Test: `backend/tests/test_llm_daily.py`

- [ ] 写失败测试：已有`complete`的`__total__`行不能被`sampled`或`unavailable`覆盖；较新的`complete`允许更新。
- [ ] 运行`.\.venv\Scripts\python.exe -m pytest tests/test_llm_daily.py -q`确认新测试失败。
- [ ] 在每日upsert中按`unavailable < sampled < complete`比较质量；低质量结果保留已有行。
- [ ] 再次运行测试，确认幂等和既有NewAPI、DeepSeek、gateway测试通过。

### Task 2: 增加精确昨日采集

**Files:**
- Modify: `backend/app/llm_usage.py`
- Modify: `backend/app/llm_usage_collector.py`
- Modify: `backend/app/main.py`
- Test: `backend/tests/test_llm_usage.py`
- Test: `backend/tests/test_llm_daily.py`

- [ ] 写失败测试：`Asia/Shanghai`目标日期转换为正确Unix起止时间；NewAPI历史查询使用该区间；DeepSeek只落目标日期。
- [ ] 增加可选目标日期参数，普通轮询保持当前行为，昨日校准传入明确日期。
- [ ] 新增`collect_llm_usage_daily_once(target_date)`，逐来源隔离异常，不处理`openai_gateway`。
- [ ] APScheduler注册每小时第15分钟任务，使用配置时区的昨天；`max_instances=1`且`coalesce=True`。
- [ ] 运行`tests/test_llm_usage.py`和`tests/test_llm_daily.py`。

### Task 3: 活动接口只读每日表

**Files:**
- Modify: `backend/app/routes.py`
- Test: `backend/tests/test_llm_usage_routes.py`

- [ ] 写失败测试：调用活动接口时不调用`ensure_daily_rollups`或`rebuild_daily_rollups`。
- [ ] 删除活动请求路径的自动重建，只执行`daily_usage_query`。
- [ ] 无每日行时返回空活动数据和现有rollup状态，不回退到快照聚合。
- [ ] 运行活动接口与完整路由测试。

### Task 4: 请求取消和短期缓存

**Files:**
- Modify: `frontend/src/api.js`
- Modify: `frontend/src/api.test.js`
- Modify: `frontend/src/components/LlmUsageView.jsx`
- Modify: `frontend/src/components/LlmUsageView.test.jsx`

- [ ] 写失败测试：API透传`signal`；快速切换时旧响应不提交；相同活动键合并请求；时间范围变化不刷新活动。
- [ ] `getJson`和LLM API函数接受`{signal}`。
- [ ] 主数据缓存`range＋source`30秒，活动缓存`year＋source`60秒；缓存进行中的Promise。
- [ ] 每个effect创建AbortController，清理时终止请求；忽略`AbortError`。
- [ ] 手动刷新清除当前缓存并强制重新请求。
- [ ] 运行`src/api.test.js`和`LlmUsageView.test.jsx`。

### Task 5: 页面与图表拆包

**Files:**
- Modify: `frontend/src/App.jsx`
- Modify: `frontend/src/App.test.jsx`
- Modify: `frontend/src/components/LlmUsageView.jsx`

- [ ] 写失败测试：未进入LLM或Settings时对应页面模块不挂载，进入后通过Suspense渲染。
- [ ] 使用`React.lazy`加载`LlmUsageView`和`SettingsView`。
- [ ] 将ECharts完整导入替换为`echarts/core`及实际使用的Line、Bar、Pie、Grid、Tooltip、Legend、DataZoom、CanvasRenderer。
- [ ] 运行前端全量测试和`npm run build`，比较构建分包。

### Task 6: 全量验证

**Files:**
- Verify: `backend/tests/`
- Verify: `frontend/src/`

- [ ] 运行后端全量pytest。
- [ ] 运行前端全量Vitest和生产构建。
- [ ] 运行`git diff --check`并确认没有`.env`、数据库或构建产物。
- [ ] 汇总实际测试数、构建包体和剩余风险。
