# Settings 页面实施计划

## 目标

增加轻量 Settings 页面，用于个人环境下直接修改 PulseBoard 的 `.env` 配置。

## 主要任务

1. 后端增加 `/api/settings`，支持读取配置和保存允许修改的字段。
2. 密钥字段只返回是否已配置，不回显真实值。
3. 前端增加 `Settings` 顶部 Tab。
4. Settings 页面按 General、GPU、VPS、LLM、Secrets 分组。
5. 保存后写入 `.env` 并清理后端 settings cache。

## 验证

- 后端测试
- 前端构建
- 手动访问 `/api/settings`，确认不泄露密钥
