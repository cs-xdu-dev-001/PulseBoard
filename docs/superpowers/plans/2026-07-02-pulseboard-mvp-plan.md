# PulseBoard MVP 实施计划

## 目标

完成 GPU 监控 MVP：采集实验室 GPU API，写入 MySQL，提供后端接口，并渲染 GPU 优先的暗色看板。

## 主要任务

1. 初始化后端、前端、配置文件和本地脚本。
2. 建立 SQLAlchemy 模型和 Alembic 迁移。
3. 实现 GPU 数据解析、状态判断和历史保存。
4. 实现当前看板和历史曲线 API。
5. 实现 React 前端、GPU 卡片、机器卡片和图表。
6. 运行后端测试和前端构建。

## 验证

- `pytest`
- `npm run build`
