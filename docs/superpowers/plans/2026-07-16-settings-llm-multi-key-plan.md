# Settings多API Key配置实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将LLM多Key配置完整迁移到Settings，并把供应商、Key和操作层级做得清晰可扫描。

**Architecture:** 新建`LlmProviderSettings`负责读取、分组和保存LLM来源，`SettingsView`只负责页面编排和普通运行参数。现有`/api/llm/usage/config`继续作为单Key读写接口，LLM看板删除配置状态，只消费采集结果。

**Tech Stack:** React 18、Vite 8、Vitest、Testing Library、FastAPI现有配置接口、CSS响应式布局。

---

## 文件结构

- 新建`frontend/src/components/LlmProviderSettings.jsx`：供应商分组、Key列表、新增/编辑表单及保存状态。
- 新建`frontend/src/components/LlmProviderSettings.test.jsx`：验证多Key分组、新增和编辑行为。
- 新建`frontend/src/components/LlmUsageView.test.jsx`：验证LLM看板不再承担配置职责。
- 新建`frontend/src/test/setup.js`：Testing Library清理和DOM断言初始化。
- 修改`frontend/src/components/SettingsView.jsx`：挂载LLM供应商区域，清理旧固定密钥配置。
- 修改`frontend/src/components/LlmUsageView.jsx`：移除配置表单、配置状态条和添加Key操作。
- 修改`frontend/src/styles.css`：建立清晰的供应商、Key、编辑表单和窄屏层级。
- 修改`frontend/vite.config.js`、`frontend/package.json`、`frontend/package-lock.json`：增加前端测试环境和命令。

### Task 1: 建立前端组件测试环境

**Files:**
- Create: `frontend/src/test/setup.js`
- Modify: `frontend/vite.config.js`
- Modify: `frontend/package.json`
- Modify: `frontend/package-lock.json`

- [ ] **Step 1: 安装测试依赖**

Run: `npm install --save-dev vitest jsdom @testing-library/react @testing-library/jest-dom`

Expected: `package.json`出现四个开发依赖，安装过程无安全漏洞。

- [ ] **Step 2: 配置Vitest**

在`vite.config.js`的配置对象中加入：

```js
test: {
  environment: 'jsdom',
  setupFiles: './src/test/setup.js',
  clearMocks: true,
},
```

创建`src/test/setup.js`：

```js
import '@testing-library/jest-dom/vitest'
import { cleanup } from '@testing-library/react'
import { afterEach } from 'vitest'

afterEach(cleanup)
```

在`package.json`中加入：

```json
"test": "vitest run"
```

- [ ] **Step 3: 验证测试运行器**

Run: `npm test -- --passWithNoTests`

Expected: PASS，无测试文件时正常退出。

### Task 2: 先用失败测试固定Settings多Key行为

**Files:**
- Create: `frontend/src/components/LlmProviderSettings.test.jsx`
- Create: `frontend/src/components/LlmProviderSettings.jsx`

- [ ] **Step 1: 写供应商分组失败测试**

测试模拟`fetchLlmConfig`返回同一`provider_id`下两个来源：

```jsx
const sources = [
  { source_id: 'deepseek-main', provider_id: 'deepseek', provider_name: 'DeepSeek', display_name: '主Key', source_type: 'deepseek_balance', has_api_key: true },
  { source_id: 'deepseek-backup', provider_id: 'deepseek', provider_name: 'DeepSeek', display_name: '备用Key', source_type: 'deepseek_balance', has_api_key: true },
]

render(<LlmProviderSettings />)
expect(await screen.findByText('DeepSeek')).toBeVisible()
expect(screen.getByText('2个Key')).toBeVisible()
expect(screen.getByText('主Key')).toBeVisible()
expect(screen.getByText('备用Key')).toBeVisible()
```

- [ ] **Step 2: 运行测试确认RED**

Run: `npm test -- LlmProviderSettings.test.jsx`

Expected: FAIL，因为组件尚未实现供应商和Key列表。

- [ ] **Step 3: 写新增Key失败测试**

点击DeepSeek供应商的“添加Key”，填写`backup-2`和“备用Key 2”，保存后断言：

```jsx
expect(saveLlmConfig).toHaveBeenCalledWith(expect.objectContaining({
  provider_id: 'deepseek',
  provider_name: 'DeepSeek',
  source_id: 'deepseek-backup-2',
  display_name: '备用Key 2',
}))
```

- [ ] **Step 4: 写编辑Key失败测试**

点击“主Key”的“编辑”，断言供应商ID和保存ID不可修改、密钥输入为空且占位符为“留空则保留原密钥”。

- [ ] **Step 5: 运行测试确认新增与编辑均为RED**

Run: `npm test -- LlmProviderSettings.test.jsx`

Expected: 三项行为测试都因缺少实现而失败。

### Task 3: 实现Settings供应商配置区

**Files:**
- Modify: `frontend/src/components/LlmProviderSettings.jsx`
- Modify: `frontend/src/components/SettingsView.jsx`

- [ ] **Step 1: 实现分组与表单状态**

组件使用`fetchLlmConfig`读取配置，并按`provider_id`归组：

```js
function groupConfigs(items = []) {
  const groups = new Map()
  for (const item of items) {
    const providerId = item.provider_id || item.source_id
    const providerName = item.provider_name || item.display_name || providerId
    if (!groups.has(providerId)) {
      groups.set(providerId, { provider_id: providerId, provider_name: providerName, items: [] })
    }
    groups.get(providerId).items.push(item)
  }
  return Array.from(groups.values())
}
```

新增供应商、供应商内新增Key和编辑Key共用表单。编辑时保留原`source_id`，密钥字段始终初始化为空。

- [ ] **Step 2: 实现保存载荷**

新增模式通过规范化后的供应商ID和Key ID生成`source_id`；编辑模式沿用原ID：

```js
const payload = {
  provider_id: normalizedProviderId,
  provider_name: form.provider_name.trim() || normalizedProviderId,
  source_id: form.original_source_id || `${normalizedProviderId}-${normalizedKeyId}`,
  display_name: form.display_name.trim() || normalizedKeyId,
  source_type: form.source_type,
  base_url: form.source_type === 'newapi_admin' ? form.base_url.trim() : '',
  api_key: form.source_type === 'deepseek_balance' ? form.api_key.trim() : '',
  access_token: form.source_type === 'newapi_admin' ? form.access_token.trim() : '',
  user_id: form.source_type === 'newapi_admin' ? form.user_id.trim() || '1' : '',
}
```

保存成功后关闭表单并重新调用`fetchLlmConfig`，失败时保留表单并显示错误。

- [ ] **Step 3: 集成Settings并移除旧LLM密钥字段**

`SettingsView`顶部依次渲染运行配置标题、`<LlmProviderSettings />`和普通配置网格。删除旧`PULSEBOARD_LLM_USAGE_SOURCES`输入，以及固定的DeepSeek和Academic密钥输入，避免重复入口；保留`PULSEBOARD_LLM_USAGE_INTERVAL_SECONDS`。

- [ ] **Step 4: 运行组件测试确认GREEN**

Run: `npm test -- LlmProviderSettings.test.jsx`

Expected: PASS，两个Key归在同一供应商下，新增和编辑行为均正确。

### Task 4: 清理LLM看板配置职责

**Files:**
- Create: `frontend/src/components/LlmUsageView.test.jsx`
- Modify: `frontend/src/components/LlmUsageView.jsx`

- [ ] **Step 1: 写失败测试**

模拟ECharts和所有LLM数据接口，渲染`LlmUsageView`并断言：

```jsx
expect(screen.queryByRole('button', { name: '添加API Key' })).not.toBeInTheDocument()
expect(screen.queryByText('保存ID')).not.toBeInTheDocument()
expect(screen.getByRole('button', { name: '手动刷新' })).toBeVisible()
```

测试先因现有“添加API Key”按钮仍存在而失败。

- [ ] **Step 2: 运行测试确认RED**

Run: `npm test -- LlmUsageView.test.jsx`

Expected: FAIL，找到“添加API Key”按钮。

- [ ] **Step 3: 删除看板配置状态**

从`LlmUsageView`移除`fetchLlmConfig`、`saveLlmConfig`、`configs`、`showConfig`、`form`、保存方法、配置表单和`configured-strip`。来源筛选直接使用采集结果分组，供应商卡删除“添加Key”回调，只保留展开和筛选。

- [ ] **Step 4: 运行测试确认GREEN**

Run: `npm test -- LlmUsageView.test.jsx`

Expected: PASS，看板只保留监控与刷新操作。

### Task 5: 提升Settings信息清晰度

**Files:**
- Modify: `frontend/src/styles.css`

- [ ] **Step 1: 建立页面层级**

新增`.llm-settings-panel`、`.provider-settings-row`、`.provider-key-row`和`.llm-key-editor`样式。供应商区占满宽度，供应商标题16px/700，字段标签和Key正文至少14px，保存ID至少13px；操作按钮使用现有绿色高光，编辑使用低强调边框按钮。

- [ ] **Step 2: 调整普通配置字号**

将`.settings-fields span`从12px提高到14px，输入框高度从38px提高到42px；分区标题保持清晰实色，不增加解释性小字。

- [ ] **Step 3: 完善主题与响应式**

浅色主题为新区域提供可辨认的背景层级和边框；在`max-width: 860px`下将供应商元信息、Key行和表单操作改为单列，在375px宽度不横向溢出。

- [ ] **Step 4: 运行全部前端测试和构建**

Run: `npm test`

Expected: 全部测试PASS。

Run: `npm run build`

Expected: Vite构建成功；允许保留现有ECharts大包体积警告。

### Task 6: 全量验证与提交

**Files:**
- Verify: `backend/tests`
- Verify: `frontend/src`

- [ ] **Step 1: 运行后端回归测试**

Run: `backend/.venv/Scripts/python.exe -m pytest -q backend/tests`

Expected: 所有后端测试PASS，密钥仍不回显。

- [ ] **Step 2: 浏览器验证**

启动后端与前端，检查桌面宽度和375px宽度：同一供应商显示两个Key；新增/编辑表单不遮挡；深色和浅色主题文字对比清晰；LLM页无配置入口。

- [ ] **Step 3: 检查差异并提交**

Run: `git diff --check`

Expected: 无空白错误。

```bash
git add frontend docs/superpowers/plans/2026-07-16-settings-llm-multi-key-plan.md
git commit -m "feat: manage multiple LLM keys in Settings"
```
