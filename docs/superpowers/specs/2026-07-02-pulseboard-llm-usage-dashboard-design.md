# PulseBoard MVP3：LLM 余额与用量看板设计

## 目标

先不做 LLM 网关代理和请求追踪，改为做一个类似 New API「模型调用分析」的 LLM 账户看板。PulseBoard 定时从 provider 或 New API 管理接口拉取数据，展示余额、可用状态、调用统计、token、费用和模型分布。

## 范围

MVP3 只做统计与余额展示，不接管调用链路。

暂不做：

- `/llm/{provider}/v1/...` 网关代理
- 单次请求 prompt/response 追踪
- Agent trace
- prompt 版本管理
- evaluation 数据集

## 数据源

第一版支持两类数据源：

```text
deepseek_balance
newapi_admin
```

### DeepSeek 官方余额

DeepSeek 使用官方余额接口：

```text
GET https://api.deepseek.com/user/balance
Authorization: Bearer <api_key>
```

记录内容：

- 是否可用
- 币种
- 总余额
- 赠送余额
- 充值余额
- 拉取时间
- 错误信息

### New API 管理统计

New API 使用系统访问令牌访问管理接口。

请求头：

```text
Authorization: bearer <access_token>
new-api-user: <user_id>
```

`new-api-user` 默认用 `1`，允许 `.env` 覆盖。

MVP3 优先接这些接口：

```text
GET /api/user/dashboard
GET /api/log/stat
GET /api/log/?p=0&page_size=100
GET /api/channel/
GET /api/channel/update_balance
```

如果你的 New API 版本接口字段和预期不同，后端要降级处理：

- 能解析什么就展示什么
- 解析不到的指标显示 `--`
- 保存原始错误摘要
- 不因为单个接口失败导致整个 LLM 页面不可用

## 配置

所有配置先放 `.env`，不做页面编辑。

示例：

```text
PULSEBOARD_LLM_USAGE_SOURCES=deepseek,academic

PULSEBOARD_LLM_DEEPSEEK_TYPE=deepseek_balance
PULSEBOARD_LLM_DEEPSEEK_DISPLAY_NAME=DeepSeek 官方
PULSEBOARD_LLM_DEEPSEEK_API_KEY=...

PULSEBOARD_LLM_ACADEMIC_TYPE=newapi_admin
PULSEBOARD_LLM_ACADEMIC_DISPLAY_NAME=Academic 中转站
PULSEBOARD_LLM_ACADEMIC_BASE_URL=https://academicedu.me
PULSEBOARD_LLM_ACADEMIC_ACCESS_TOKEN=...
PULSEBOARD_LLM_ACADEMIC_USER_ID=1
```

规则：

- Source ID 由你自定义。
- Source ID 允许小写字母、数字、`_`、`-`。
- 读取环境变量时，Source ID 会转大写，`-` 会转 `_`。
- `DISPLAY_NAME` 可为空；为空时页面显示 Source ID。
- `TYPE` 必填，第一版支持 `deepseek_balance` 和 `newapi_admin`。
- 敏感字段只存在 `.env`，不通过 API 返回给前端。

## 存储

新增两张表。

### `llm_usage_sources`

记录每个配置源的当前状态。

字段：

```text
id
source_id
display_name
source_type
status
last_checked_at
last_error
balance_currency
balance_total
balance_granted
balance_topped_up
quota_total
quota_used
quota_remaining
created_at
updated_at
```

`status`：

```text
online
degraded
offline
unknown
```

### `llm_usage_snapshots`

记录周期性统计快照，用于画趋势图。

字段：

```text
id
source_id
collected_at
range_key
request_count
token_count
quota_used
estimated_amount
rpm
tpm
success_rate
avg_latency_seconds
model_stats
raw_summary
```

`model_stats` 保存模型维度聚合，例如：

```json
[
  {
    "model": "deepseek-chat",
    "request_count": 120,
    "token_count": 500000,
    "amount": 3.2
  }
]
```

`raw_summary` 只保存统计摘要，不保存单次请求内容。

## 采集任务

后端新增定时任务：

```text
PULSEBOARD_LLM_USAGE_INTERVAL_SECONDS=300
```

默认每 5 分钟拉取一次。

采集逻辑：

1. 读取 `.env` 中的 source 列表。
2. 按 source type 调用对应接口。
3. 更新 `llm_usage_sources` 当前状态。
4. 写入 `llm_usage_snapshots`。
5. 单个 source 失败不影响其他 source。

## 前端

当前页面顶部改成 Tab：

```text
Infra
LLM
```

`Infra` 保留现有 GPU、VPS、实验室机器和历史曲线。

`LLM` 页面参考 New API 的统计布局，但使用 PulseBoard 暗色发光风格。

包含：

- Source 卡片：
  - 展示名
  - 类型
  - 状态
  - 余额
  - 可用额度
  - 最近采集时间
  - 错误摘要
- 总览卡片：
  - 总请求数
  - 总额度/总消费
  - 总 token
  - 平均 RPM
  - 平均 TPM
- 健康条：
  - 成功率
  - 平均延迟
  - 吞吐量
  - 高占比模型
- 消耗分布图：
  - 按日期聚合
  - 按模型堆叠
  - 支持今天 / 24h / 7d
- 模型调用分析：
  - 趋势
  - 调用次数分布
  - 调用次数排行

MVP3 不做用户统计页面，除非 New API 接口可以稳定返回用户维度聚合数据。

## 前端 API

新增：

```text
GET /api/llm/usage/sources
GET /api/llm/usage/summary?range=today|24h|7d&source=
GET /api/llm/usage/series?range=today|24h|7d&source=
GET /api/llm/usage/models?range=today|24h|7d&source=
POST /api/llm/usage/refresh
```

`refresh` 手动触发一次采集，方便你改 `.env` 或刚打开页面时立即刷新。

## 安全

- 不在前端返回 API key、访问令牌或 Authorization header。
- 不保存单次 prompt/response。
- 不在日志里打印完整 token。
- 访问令牌属于高权限凭证，建议后续换成只读或最小权限令牌；如果 New API 不支持只读，则只放在本机 `.env`。

## 错误处理

DeepSeek 余额接口失败：

- source 状态标记为 `offline` 或 `degraded`
- 保存 HTTP 状态码和错误摘要
- 前端显示余额不可用

New API 管理接口部分失败：

- 能解析的接口继续展示
- 失败的部分显示 `--`
- source 状态标记为 `degraded`

所有 source 均失败：

- LLM 页面显示错误摘要
- Infra 页面不受影响

## 非目标

- LLM 请求代理
- 单次请求追踪
- 用户权限系统
- New API 配置编辑
- 完整 New API 后台复刻
- prompt/response 存储
