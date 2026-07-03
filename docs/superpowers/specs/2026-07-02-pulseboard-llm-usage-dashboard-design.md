# PulseBoard LLM 用量看板设计

## 目标

先不做 LLM 代理和请求追踪，只做账户余额、用量统计、费用估算和模型分布展示。

## 数据源

第一版支持两类来源：

- `deepseek_balance`：DeepSeek 官方余额接口。
- `newapi_admin`：OpenAI 兼容中转站或 New API 管理接口。

## 配置示例

```env
PULSEBOARD_LLM_USAGE_SOURCES=academic,deepseek

PULSEBOARD_LLM_ACADEMIC_TYPE=newapi_admin
PULSEBOARD_LLM_ACADEMIC_DISPLAY_NAME=Academic Gateway
PULSEBOARD_LLM_ACADEMIC_BASE_URL=https://YOUR_NEW_API_DOMAIN
PULSEBOARD_LLM_ACADEMIC_ACCESS_TOKEN=
PULSEBOARD_LLM_ACADEMIC_USER_ID=1

PULSEBOARD_LLM_DEEPSEEK_TYPE=deepseek_balance
PULSEBOARD_LLM_DEEPSEEK_DISPLAY_NAME=DeepSeek
PULSEBOARD_LLM_DEEPSEEK_API_KEY=
```

密钥只存 `.env`，接口只返回是否已配置。

## 存储

新增两类数据：

- `llm_usage_sources`：每个来源的当前状态和余额。
- `llm_usage_snapshots`：周期性统计快照，用于趋势图。

## 前端

LLM 页面展示：

- 来源卡片
- 今日 / 24h / 7d 区间切换
- 估算费用
- 请求数
- 余额
- 按模型拆分的面积图
- 模型费用表

## 安全

- 不回显 API Key、访问令牌或 Authorization Header。
- 不保存 prompt/response。
- 不在日志中打印完整密钥。
