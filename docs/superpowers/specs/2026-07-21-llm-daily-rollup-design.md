# LLM每日用量汇总设计

日期：2026-07-21

## 目标

修正LLM统计中重复累加快照的问题，并让月度活动长期、快速、可解释地展示每日Token用量。

范围包括：

- DeepSeek供应商卡片只显示一次余额，Key明细保留状态和检查时间。
- EduModel维持现有供应商与Key展示方式。
- NewAPI每日请求、Token、金额按统计周期口径计算，禁止把累计快照当作每日增量。
- 月度活动固定展示当年1月到12月，色阶按每日Token总量划分。
- 每日汇总保留365天，原始LLM快照保留30天。
- 供应商和Key切换减少重复请求，并取消已经失效的慢请求。

## 官方统计参考

Codex公开的`account/usage/read`接口把统计拆成两部分：

- `summary`：累计Token、峰值日Token、连续使用天数等汇总指标。
- `dailyUsageBuckets`：`startDate`和`tokens`组成的每日桶。

PulseBoard本次只采用每日桶这一核心模式。不会伪造无法从供应商接口获得的连续天数或累计指标。

参考：[Codex App Server：Token usage](https://learn.chatgpt.com/docs/app-server#7-token-usage-chatgpt)

## 数据模型

新增`llm_usage_daily`表，每行代表一个来源Key、一个本地日期和一个模型：

- `source_id`：关联`llm_usage_sources.id`。
- `usage_date`：按`Settings.lab_timezone`转换后的本地日期。
- `model`：模型名；没有模型维度时使用`__total__`。
- `request_count`：当日请求数。
- `token_count`：当日Token总量，可为空。
- `input_tokens`、`output_tokens`：可为空。
- `estimated_amount`：供应商原始金额或额度单位。
- `estimated_cost_usd`：统一展示金额；DeepSeek官方金额另记录币种。
- `currency`：金额币种。
- `token_complete`：是否拥有完整Token口径。
- `data_quality`：`complete`、`sampled`或`unavailable`。
- `observed_at`：生成该日汇总时使用的最新采集时间。

唯一约束为`source_id＋usage_date＋model`，并为`source_id＋usage_date`建立查询索引。

## 汇总规则

### NewAPI

- 同一Key同一天只使用当天最新的周期统计快照，禁止累加多次采集结果。
- 金额优先取`/api/log/self/stat`当前周期`quota`，再换算为展示金额。
- 请求数和Token优先使用统计接口明确返回的周期字段。
- 统计接口没有完整Token时，只使用包含`input_tokens`或`output_tokens`的日志桶，并将`data_quality`标为`sampled`。
- 缺少输入/输出Token的旧日志桶不参与Token合计。

### DeepSeek官方平台

- 使用官方返回的每日桶按Key写入汇总表。
- 多个Key的用量仍按Key分别保存，供应商筛选时求和。
- 余额属于账户级信息：供应商卡片去重显示一次，Key列表不重复显示余额。

### 网关来源

- 每次真实请求是独立事件，按本地日期累加到每日汇总。
- 不参与定时平台采集。

## 历史回填与保留

迁移后首次读取活动数据时执行一次幂等回填：

- NewAPI按来源和日期选择最新快照后重建每日行。
- DeepSeek按最新平台快照中的官方每日桶重建每日行。
- 网关按已有请求快照按日累加。

回填不会把同一天的多个快照相加。原始快照超过30天后清理；每日汇总超过365天后清理。清理任务与现有定时采集任务同一进程执行，失败不影响当前采集。

## API与前端

新增每日活动接口，返回全年日期数组及汇总元数据：

`GET /api/llm/usage/activity?year=2026&source=provider:academic`

返回字段包括日期、Token、请求数、完整性和活跃天数。供应商或Key筛选继续复用现有`source`参数。

现有`today`和`24h`继续使用细粒度数据；`7d`、`14d`、`29d`和月度活动优先使用每日汇总，避免扫描大量快照。

月度活动的展示规则：

- 始终渲染当年1月1日至12月31日。
- 色阶只根据非零且Token可用的日期计算分位阈值，使用蓝色0到4级。
- 悬浮提示显示日期、Token总量、请求数和数据质量。
- Token不可用时显示“Token不可用”，不把未知值显示成0。

切换供应商或Key时：

- 活动数据按`year＋source`缓存。
- 取消旧的活动请求，避免切换页面后继续解析大响应。
- 主视图与活动接口分离，活动不再请求29d原始series。

## 错误处理

- 单个来源失败只标记该来源，不阻断其他来源的每日汇总。
- 数据库回填失败时接口返回明确的降级状态，不回退到重复累加的原始快照算法。
- Token不完整必须通过`data_quality`和页面提示暴露，禁止默默当作准确值。

## 测试

后端测试覆盖：

- 同一天多份NewAPI快照只生成一份每日数据。
- NewAPI周期`quota`优先于Key累计用量。
- 缺少输入/输出Token的日志不会计入Token总量。
- DeepSeek官方每日桶能按日期和Key写入，余额不参与Key余额叠加。
- 活动接口返回全年日期、正确筛选和数据质量字段。
- 每日汇总和原始快照清理边界。

前端测试覆盖：

- 活动图使用每日活动接口而不是29d series。
- 供应商切换和Key切换传递正确筛选值。
- DeepSeek Key行隐藏重复余额，EduModel Key行保持余额。
- Token色阶使用蓝色分位级别，未知Token不显示为0。

## 不在本次范围

- 不增加登录和告警。
- 不改LLM供应商配置格式或`.env`写入逻辑。
- 不保存每条请求的永久明细。
- 不实现Codex官方的连续使用天数等额外指标。
