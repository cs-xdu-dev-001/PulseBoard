# LLM每日用量汇总 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 用每日Token汇总替换LLM月度活动的重复快照计算，并修正DeepSeek余额展示、NewAPI每日口径和供应商切换性能。

**Architecture:** 新增`llm_usage_daily`表保存按Key、日期、模型的汇总；采集时对NewAPI/DeepSeek采用“最新周期结果覆盖”，网关采用事件累加。新增活动接口只查询每日表，长范围统计优先查询每日表；前端缓存活动数据并把活动图色阶改为Token分位蓝色。

**Tech Stack:** FastAPI、SQLAlchemy、Alembic、MySQL、React、Vitest、pytest。

---

### Task 1: 新增每日汇总模型和迁移

**Files:**
- Modify: `backend/app/models.py`
- Create: `backend/alembic/versions/20260721_0005_llm_usage_daily.py`
- Test: `backend/tests/test_llm_daily.py`

- [ ] **Step 1: 写表结构测试**

在`backend/tests/test_llm_daily.py`添加测试，使用现有测试数据库fixture，断言`LlmUsageDaily`能插入并按`source_id＋usage_date＋model`唯一约束冲突；断言`token_count`允许为空、`data_quality`默认值为`unavailable`。

- [ ] **Step 2: 运行测试确认失败**

运行：`pytest backend/tests/test_llm_daily.py -q`

预期：因`LlmUsageDaily`尚未定义而失败。

- [ ] **Step 3: 添加SQLAlchemy模型**

在`backend/app/models.py`导入`Date`、`Boolean`、`UniqueConstraint`，新增：

```python
class LlmUsageDaily(Base):
    __tablename__ = "llm_usage_daily"
    __table_args__ = (
        UniqueConstraint("source_id", "usage_date", "model", name="uq_llm_usage_daily_source_date_model"),
        Index("ix_llm_usage_daily_source_date", "source_id", "usage_date"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("llm_usage_sources.id"), nullable=False, index=True)
    usage_date: Mapped[date] = mapped_column(Date, nullable=False)
    model: Mapped[str] = mapped_column(String(200), nullable=False)
    request_count: Mapped[float | None] = mapped_column(Float)
    token_count: Mapped[float | None] = mapped_column(Float)
    input_tokens: Mapped[float | None] = mapped_column(Float)
    output_tokens: Mapped[float | None] = mapped_column(Float)
    estimated_amount: Mapped[float | None] = mapped_column(Float)
    estimated_cost_usd: Mapped[float | None] = mapped_column(Float)
    currency: Mapped[str | None] = mapped_column(String(16))
    token_complete: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    data_quality: Mapped[str] = mapped_column(String(16), default="unavailable", nullable=False)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)
```

在文件顶部补充`from datetime import date`。

- [ ] **Step 4: 添加Alembic迁移**

迁移创建同名表、外键、唯一约束和两个索引；`downgrade()`删除表。迁移`down_revision`使用当前最新迁移`20260718_0004`。

- [ ] **Step 5: 运行测试确认通过**

运行：`pytest backend/tests/test_llm_daily.py -q`

预期：测试通过。

- [ ] **Step 6: 提交**

运行：`git add backend/app/models.py backend/alembic/versions/20260721_0005_llm_usage_daily.py backend/tests/test_llm_daily.py && git commit -m "feat: add llm daily usage table"`

### Task 2: 实现每日汇总生成、回填和清理

**Files:**
- Create: `backend/app/llm_daily.py`
- Modify: `backend/app/llm_usage_collector.py`
- Modify: `backend/app/routes.py`
- Modify: `backend/app/config.py`
- Modify: `backend/app/main.py`
- Modify: `backend/tests/test_llm_daily.py`

- [ ] **Step 1: 写NewAPI和DeepSeek回填测试**

测试构造同一Key同一天的两份NewAPI快照：第一份有较小桶，第二份有完整桶；调用回填后只保留第二份的每日值。再构造DeepSeek平台快照中的两个官方日期桶，断言生成两个日期的`__total__`行。断言没有输入/输出Token的NewAPI桶不计入Token。

- [ ] **Step 2: 运行测试确认失败**

运行：`pytest backend/tests/test_llm_daily.py::test_rebuild_daily_rollups_uses_latest_newapi_snapshot -q`以及`pytest backend/tests/test_llm_daily.py::test_rebuild_daily_rollups_reads_deepseek_daily_buckets -q`

预期：因回填函数不存在而失败。

- [ ] **Step 3: 添加统一汇总函数**

在`backend/app/llm_daily.py`实现以下公开函数：

```python
def upsert_daily_from_result(db, result, collected_at, lab_timezone, *, replace=True) -> None:
    """将一次采集结果覆盖或累加到本地日期的每日行。"""

def rebuild_daily_rollups(db, lab_timezone, now, snapshot_retention_days=30, daily_retention_days=365) -> None:
    """从快照按来源和日期选择最新结果，幂等重建每日表。"""

def cleanup_daily_rollups(db, now, snapshot_retention_days=30, daily_retention_days=365) -> None:
    """删除过期快照和每日汇总。"""

def daily_usage_query(db, start_date, end_date, source_id, configured_source_ids) -> list[dict]:
    """按来源筛选并返回日期范围内的每日模型行。"""
```

实现细节：

- 用`ZoneInfo(lab_timezone)`把采集时间和官方桶时间转换成本地`date`。
- NewAPI优先写`__total__`行，使用周期统计的请求数、Token和`quota`金额；模型行使用可信日志桶，缺输入/输出Token时标为`sampled`。
- DeepSeek读取`raw_summary["deepseek_platform"]["daily"]`，每个日期写`__total__`行，金额币种使用平台返回的币种。
- 网关将同日同模型快照累加；NewAPI和DeepSeek同日同Key同模型使用最新结果覆盖。
- `rebuild_daily_rollups`先清理每日表，再按来源分组读取快照：NewAPI每个本地日期取最新快照，DeepSeek取最新平台快照中的全部官方日期桶，网关读取全部快照累加。
- 用事务提交，重复调用结果一致。

- [ ] **Step 4: 在持久化链路接入汇总**

修改`persist_result()`增加`lab_timezone="Asia/Shanghai"`参数，在写入`LlmUsageSnapshot`后调用`upsert_daily_from_result()`。采集任务传入`settings.lab_timezone`；网关代理传入`get_settings().lab_timezone`。

- [ ] **Step 5: 添加配置和清理任务**

在`Settings`添加`llm_daily_retention_days: int = 365`。每日采集任务在提交结果后调用`cleanup_daily_rollups()`，同时删除超过`retention_days`的`LlmUsageSnapshot`，删除超过`llm_daily_retention_days`的`LlmUsageDaily`。

- [ ] **Step 6: 添加首次回填保护**

在每日活动接口调用`ensure_daily_rollups()`：当每日表为空时执行一次`rebuild_daily_rollups()`；使用模块级锁防止并发请求重复回填。回填失败回滚并返回明确的降级字段，不使用旧的重复快照聚合结果。

- [ ] **Step 7: 运行测试确认通过**

运行：`pytest backend/tests/test_llm_daily.py backend/tests/test_llm_usage.py -q`

预期：新增每日汇总测试和既有采集测试全部通过。

- [ ] **Step 8: 提交**

运行：`git add backend/app/llm_daily.py backend/app/llm_usage_collector.py backend/app/routes.py backend/app/config.py backend/app/main.py backend/tests/test_llm_daily.py && git commit -m "feat: build llm daily rollups"`

### Task 3: 新增活动接口并让长范围读取每日表

**Files:**
- Modify: `backend/app/routes.py`
- Modify: `backend/tests/test_llm_usage_routes.py`

- [ ] **Step 1: 写活动接口测试**

测试插入两天`LlmUsageDaily`数据，调用`GET /api/llm/usage/activity?year=2026&source=provider:academic`，断言返回365/366个日期、只包含筛选供应商、`active_days`和`peak_daily_tokens`正确；断言未知Token不被序列化为0。

- [ ] **Step 2: 运行测试确认失败**

运行：`pytest backend/tests/test_llm_usage_routes.py -k activity -q`

预期：因路由不存在而失败。

- [ ] **Step 3: 实现活动接口**

新增`GET /llm/usage/activity`：校验`year`在2000到2100，按本地日期范围查询每日表，合并`__total__`行，返回：

```json
{
  "year": 2026,
  "days": [{"date": "2026-07-21", "request_count": 12, "token_count": 3456, "has_data": true, "data_quality": "complete"}],
  "active_days": 1,
  "total_tokens": 3456,
  "peak_daily_tokens": 3456,
  "token_complete": true
}
```

未来日期返回`has_data:false`、`token_count:null`；没有Token的历史日期返回`has_data:true`、`token_count:null`。

- [ ] **Step 4: 长范围查询改读每日表**

`summary`、`series`、`models`在`7d`、`14d`、`29d`调用每日查询；`today`和`24h`保留细粒度快照。每日总行用于来源统计，模型行用于模型统计，禁止把`__total__`和模型行相加。

- [ ] **Step 5: 运行后端测试**

运行：`pytest backend/tests/test_llm_usage_routes.py backend/tests/test_llm_usage.py -q`

预期：全部通过。

- [ ] **Step 6: 提交**

运行：`git add backend/app/routes.py backend/tests/test_llm_usage_routes.py && git commit -m "feat: serve llm activity from daily usage"`

### Task 4: 前端活动图、余额展示和切换缓存

**Files:**
- Modify: `frontend/src/api.js`
- Modify: `frontend/src/components/LlmUsageView.jsx`
- Modify: `frontend/src/components/LlmUsageView.test.jsx`
- Modify: `frontend/src/styles.css`

- [ ] **Step 1: 写前端失败测试**

增加测试断言：初始加载调用`fetchLlmActivity(2026, '')`而不是`fetchLlmSeries('29d', '')`；供应商切换传递`provider:academic`；DeepSeek Key行不显示余额，EduModel Key行显示余额；活动数据使用`token_count`作为格子值。

- [ ] **Step 2: 运行测试确认失败**

运行：`npm test -- --run src/components/LlmUsageView.test.jsx`

预期：因`fetchLlmActivity`和新展示逻辑尚不存在而失败。

- [ ] **Step 3: 添加活动API客户端**

在`frontend/src/api.js`添加：

```javascript
export function fetchLlmActivity(year, source = '') {
  const query = new URLSearchParams({ year: String(year) })
  if (source) query.set('source', source)
  return request(`/api/llm/usage/activity?${query.toString()}`)
}
```

- [ ] **Step 4: 拆分活动加载并缓存**

`LlmUsageView`用`activity`状态和`useRef(new Map())`缓存`year＋source`；活动effect只调用`fetchLlmActivity`，卸载或筛选切换后忽略旧结果。删除固定`29d`活动请求。主视图来源列表只在首次加载和手动刷新时请求，供应商/Key切换只请求summary、series、models和活动数据。

- [ ] **Step 5: 修改活动图数据和分位色阶**

`ActivityHeatmap`接收`activity.days`，格子值使用Token：

```javascript
const tokenValues = days.filter((day) => day.has_data && day.token_count != null).map((day) => day.token_count)
const thresholds = quantileThresholds(tokenValues)
const level = day.token_count == null ? 0 : levelFromThresholds(day.token_count, thresholds)
```

悬浮提示显示日期、Token总量、请求数和`data_quality`；未知Token显示“Token不可用”。`activityLevel`不再用单个最大值比例。

- [ ] **Step 6: DeepSeek余额按供应商显示**

`ProviderCard`在Key行中对`source_type === 'deepseek_platform'`隐藏余额节点；其他类型保持原有`formatKeyBalance()`。供应商卡片继续使用去重后的`formatProviderBalance()`。

- [ ] **Step 7: 调整蓝色色阶和响应式提示**

保留现有暗色/亮色主题结构，把活动0到4级统一为浅蓝、天蓝、蓝、深蓝和高亮蓝；提示文案避免把未知Token写成0。保持全年横向滚动及自动定位今天，不增加自动播放。

- [ ] **Step 8: 运行前端测试和构建**

运行：`npm test -- --run src/components/LlmUsageView.test.jsx src/api.test.js`以及`npm run build`

预期：测试通过，构建通过；只允许已有的Vite chunk size warning。

- [ ] **Step 9: 提交**

运行：`git add frontend/src/api.js frontend/src/components/LlmUsageView.jsx frontend/src/components/LlmUsageView.test.jsx frontend/src/styles.css && git commit -m "feat: add token activity heatmap"`

### Task 5: 全量验证和本地运行

**Files:**
- Verify: `backend/tests/`, `frontend/src/`

- [ ] **Step 1: 运行后端全量测试**

运行：`pytest backend/tests -q`

预期：全部通过。

- [ ] **Step 2: 运行前端全量测试和构建**

运行：`npm test -- --run`以及`npm run build`

预期：全部通过，构建无错误。

- [ ] **Step 3: 本地迁移和接口冒烟测试**

在`backend`虚拟环境运行：`alembic upgrade head`，启动`uvicorn app.main:app --host 127.0.0.1 --port 8000`，请求：

`GET /api/llm/usage/activity?year=2026`

确认返回全年日期数组、活动数据不重复、未知Token不冒充0；确认`GET /api/llm/usage/series?range=29d`响应明显小于旧版。

- [ ] **Step 4: 查看最终差异**

运行：`git status --short`和`git log --oneline -8`，确认没有`.env`、数据库文件或构建产物被提交。

- [ ] **Step 5: 最终提交**

若前述步骤没有未提交修改，保留各任务提交；若测试修复产生修改，运行：`git add backend frontend docs && git commit -m "test: verify llm daily usage"`。
