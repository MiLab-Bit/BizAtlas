# 12 · 前端架构（雷达落地）

> 选型依据：完整雷达清单 [`reference/frontend-research-radar.md`](./reference/frontend-research-radar.md) + 本地镜像 `c:\Dev\frontend-radar`。  
> 产品 IA：PRD `04_信息架构与交互`。  
> 系统边界：[`02-architecture.md`](./02-architecture.md) · API：[`06-api-contracts.md`](./06-api-contracts.md)。

**结论先行：** BizAtlas 前端按「研究工作台 + 对话副驾」建模，**React + Vite 为正式 UI**；不走 Streamlit 主路径（见 ADR-005）。状态按雷达原则分层——**不按页面功能平铺堆库**。

---

## 1. 产品形态 → 空间模型

商舆不是城市漫游/2.5D，也不是可随意拼装的万能 Dashboard。MVP 空间模型只有两种：

| 空间 | 库 | 用途 |
|---|---|---|
| **Split Pane** | `react-resizable-panels` | 主工作区 ‖ 对话副驾；企业空间 ‖ 溯源抽屉 |
| **内容分区** | 路由 + Tabs | 工作台 / 企业空间 / 规则 / 报告 / 流程 |

**Hold：** Docking Tree（Dockview/FlexLayout）、Dashboard Grid（RGL）——分析师工作台不需要 IDE 级窗格森林；指标卡用固定信息架构，不用可拖拽仪表盘。

```
┌──────────────────────────────────────────────────────────────┐
│ App Shell · 商舆 · 模式角标(snapshot/hybrid) · 快捷命令 ⌘K   │
├─────────────────────────────────────────────┬────────────────┤
│ Main（路由页面）                             │ Copilot Panel  │
│  工作台 | 企业空间 | 规则 | 报告 | 流程      │  对话 · 任务   │
│  ┌──────────────┬─────────────────────────┐ │  进度 · 确认  │
│  │ 结论/雷达     │ 明细 · 命中 · 指标表     │ │                │
│  └──────────────┴─────────────────────────┘ │                │
│         ↕ SourceDrawer（引用 / 页码）         │                │
└─────────────────────────────────────────────┴────────────────┘
```

---

## 2. 分层（按状态所有权）

```
┌─────────────────────────────────────────────────────────────┐
│ App Shell                                                    │
│  tokens · 路由 · ⌘K · 降级角标 · HumanConfirm modal           │
└─────────────────────────────────────────────────────────────┘
┌──────────────┬──────────────────┬──────────────┬────────────┐
│ Workbench    │ Company Space    │ Rules/Report │ Copilot    │
│ 列表·快捷    │ 资料·风险·图谱   │ 规则·报告    │ 对话·意图  │
└──────┬───────┴────────┬─────────┴──────┬───────┴─────┬──────┘
       │                │                │             │
  Zustand UI      AnalyzeFSM(XState)  局部表单态    Chat UI 态
       │                │
       └──── TanStack Query（companies / risk / rules / tasks）────┘
                        │
                   Zod Envelope（packages/contracts 对等 TS）
                        │
                   HTTP ──► apps/api  /v1/*
```

### 所有权硬边界

| 状态 | 归属 | 禁止 |
|---|---|---|
| 服务端实体（企业、风险、规则、报告） | TanStack Query 缓存 | 镜像进 Zustand「第二真相」 |
| 分析任务阶段 | XState `AnalyzeFSM` | 用散落 `useState` 布尔旗汤 |
| 面板开合、选中 citation、主题偏好 | Zustand | 塞进 Query |
| ECharts / G6 / Flow 内部 viewport | 组件本地 / 库内部 | 同步进全局 Store |
| 表单（NL 规则草稿、上传元数据） | React Hook Form | 每键击打进全局 |

---

## 3. AnalyzeFSM（XState）

主路径状态机（对齐流水线 S0–S5）：

```
idle → uploading → parsing → enriching → matching → scoring → ready
         ↘──────────────────────────────────────────→ degraded
任何阶段 ─→ failed
ready → exporting → done
ready → awaiting_human（导出/激活规则前）
```

| 状态 | 允许 UI |
|---|---|
| idle | 上传、选案例、提问 |
| uploading / parsing | 进度条；禁重复提交 |
| matching / scoring | 骨架 + 阶段文案 |
| ready | 结论先行、雷达、命中、生成报告 |
| awaiting_human | 确认闸门（ADR-001/人在回路） |
| degraded | 展示 `_tier` 混比与缺失维度 |
| failed | 可读错误 + Excel 兜底入口 |

**雷达图相机/缩放、图谱 pan 不属于 FSM context。**

流程辅助另建轻量 `DueDiligenceFSM`（清单 → 研判 → 报告），可嵌套调用 AnalyzeFSM。

---

## 4. 雷达 Adopt / Trial / Hold

### 4.1 Adopt（MVP 直接用）

| 层 | 库 | 本地镜像 | BizAtlas 用法 |
|---|---|---|---|
| 校验 | Zod | `colinhacks__zod` | `AnalyzeResponse` / `RiskResult` 入口 `parse` |
| 服务端态 | TanStack Query | `TanStack__query` | 列表、最新风险、任务轮询、mutation |
| UI 态 | Zustand | `pmndrs__zustand` | drawer、copilotOpen、选中 citation |
| 阶段机 | XState | `statelyai__xstate` | AnalyzeFSM / DueDiligenceFSM |
| 分栏 | react-resizable-panels | `bvaughn__react-resizable-panels` | 主区‖副驾；详情‖溯源 |
| UI 原语 | Radix + 薄封装 | `radix-ui__primitives` | Dialog/Tabs/Dropdown；样式自管 |
| 样式 | Tailwind + CVA + merge | `tailwindlabs__tailwindcss` 等 | token 驱动；避免整包 AntD 皮肤 |
| 图标 | Lucide | `lucide-icons__lucide` | 一致线性图标 |
| 命令面板 | cmdk | `pacocoursey__cmdk` | 「分析风险 / 生成报告 / 加规则」 |
| 上传 | react-dropzone | `react-dropzone__react-dropzone` | 财报拖拽；进度走 API task |
| 表单 | React Hook Form | `react-hook-form__react-hook-form` | NL 规则、企业创建 |
| 表格 | TanStack Table | `TanStack__table` | 指标表、命中清单、规则库 |
| 图表 | Apache ECharts | `apache__echarts` | 五维雷达、趋势、行业对比条 |
| 动效 | Motion | （清单 3.2；npm） | 仅 2–3 处：等级徽章、面板、列表入场 |
| 客户端搜 | Fuse.js | `krisk__Fuse` | 规则名/企业名本地滤 |

### 4.2 Trial（P1，接口先留）

| 库 | 镜像 | 用法 |
|---|---|---|
| AntV G6 | `antvis__G6` | 知识图谱 / 担保链（只读探索） |
| xyflow | `xyflow__xyflow` | 贷前流程图可视化（非企业关系网） |
| assistant-ui | `assistant-ui__assistant-ui` | 若自研 Chat 成本高，再换标准 AI Chat 壳 |
| Uppy | `transloadit__uppy` | 大文件/断点续传 |
| TanStack Virtual | `TanStack__virtual` | 规则/命中过长列表 |
| ELK.js + Comlink | `kieler__elkjs` · `GoogleChromeLabs__comlink` | 大图布局进 Worker |
| Tiptap / Milkdown | 清单 1.5 | 报告叙述段轻编辑（数字插槽只读） |

### 4.3 Hold（明确不用）

| 库 | 原因 |
|---|---|
| R3F / Three / Drei | 非空间漫游产品；线程预算留给表+图 |
| Dockview / FlexLayout / RGL | 空间模型过重 |
| Ant Design / Mantine 全量 | 与自建 token 冲突；可用单点子组件但默认不引入整包 |
| AG Grid / Glide Data Grid | MVP 表格密度不够格上 Canvas Grid |
| Lightweight Charts | 不是行情终端；财务趋势用 ECharts |
| Yjs / Liveblocks | 暂无多人协作 |
| tsParticles / 重 GPU 特效 | 金融可信感优先，禁装饰粒子 |
| Streamlit 作主 UI | 见 ADR-005 |
| tRPC | 后端是 FastAPI/Python，契约走 OpenAPI + Zod |

---

## 5. `apps/web` 目录

```
apps/web/
  package.json
  vite.config.ts
  index.html
  src/
    app/
      providers.tsx          # QueryClient, 主题
      router.tsx
      shell/                 # AppShell, SplitLayout, CommandPalette
    features/
      workbench/             # 最近企业、待办、快捷入口
      company/
        documents/           # 上传、解析状态、资料树
        metrics/             # 指标卡 + Table
        risk/                # 结论、雷达、命中、等级徽章
        graph/               # P1 G6
        sources/             # SourceDrawer 溯源
      rules/                 # 列表、NL 新增、pilot/activate
      report/                # 预览、导出确认
      workflow/              # 贷前向导
      analyze/               # machine.ts, selectors, useAnalyze
      copilot/               # ChatPanel, intent chips
    shared/
      ui/                    # Button, Badge(Grade), Panel...
      lib/api.ts             # fetch + Zod parse
      lib/query-keys.ts
      styles/tokens.css      # 品牌色 / 等级色 / 字体
    pages/                   # 薄路由页，拼 features
```

依赖方向：

```
pages → features → shared
features/analyze 可被 company/risk、copilot、workflow 订阅
web ↛ Python packages；只依赖 HTTP + 可选 packages/contracts 的 JSON Schema/TS 导出
```

---

## 6. 视觉与交互约束（商舆）

- **品牌优先**：壳层左上「商舆」为强识别；工作台首屏不是通用后台统计墙。
- **结论先行**：风险页首屏 = 一句话结论 + 等级徽章 + 雷达；明细下钻。
- **等级色**：GREEN / YELLOW / ORANGE / RED / BLACK 用 token，禁止彩虹装饰。
- **降级可见**：顶栏或摘要区固定 `L1/L2/L3` 比例芯片。
- **动效预算**：Motion ≤ 3 处意图动画；图谱交互不叠加页面级滚动劫持（Hold Lenis）。
- **字体**：选用有辨识度的中文+西文配对（文档实现时写入 `tokens.css`），避免 Inter/系统默认堆叠。
- **反模式**：紫渐变 AI 风、粒子背景、首屏堆指标卡片墙。

---

## 7. 渲染与线程预算

| 工作 | 线程 |
|---|---|
| 路由 / FSM / Query / 表单 | 主线程 |
| ECharts 雷达与趋势 | 主线程；按需 `dispose`，禁隐藏页空转 |
| G6 图谱（P1） | 主线程；节点 > 阈值则简化或 Worker+ELK |
| 聊天流式 token | 主线程；节流 setState |
| PDF 原文预览 | iframe / 独立层；勿与图谱同帧重布局 |

降级：WebGL 不可用时图谱改邻接列表 + Mermaid；图表改静态 SVG 快照（fixtures 预渲染可答辩）。

---

## 8. 与 API / 人在回路

- 所有写操作经 `shared/lib/api.ts`；响应必须 Zod 校验。
- `export` / `activate rule` / 流程提交：UI 只发 `confirm=true`，弹窗文案展示将落库的数字摘要（防误触）。
- Copilot 不执行本地算分；只调用 `/v1/chat` 或 `/v1/analyze`。
- 任务进度：`GET /v1/analyze/{task_id}` 由 Query `refetchInterval` 驱动，FSM 听 Query 数据转移。

---

## 9. 本地研读路径（优先打开）

```
c:\Dev\frontend-radar\colinhacks__zod
c:\Dev\frontend-radar\TanStack__query
c:\Dev\frontend-radar\pmndrs__zustand
c:\Dev\frontend-radar\statelyai__xstate
c:\Dev\frontend-radar\bvaughn__react-resizable-panels
c:\Dev\frontend-radar\radix-ui__primitives
c:\Dev\frontend-radar\apache__echarts
c:\Dev\frontend-radar\TanStack__table
c:\Dev\frontend-radar\react-dropzone__react-dropzone
c:\Dev\frontend-radar\pacocoursey__cmdk
c:\Dev\frontend-radar\antvis__G6                 # P1
c:\Dev\frontend-radar\xyflow__xyflow             # P1 流程
c:\Dev\frontend-radar\assistant-ui__assistant-ui # Trial 对话壳
```

完整清单副本：[`reference/frontend-research-radar.md`](./reference/frontend-research-radar.md)

---

## 10. 采用前检查（雷达原文落地）

1. **状态所有权**：ECharts option / G6 graph 不进 Zustand。  
2. **渲染管线**：主路径 DOM+SVG/Canvas（ECharts）；图谱 WebGL 可降级。  
3. **输入模型**：上传用 dropzone；规则排序若需要再用 dnd-kit（非 P0）。  
4. **空间模型**：只 Split Pane + 路由，不混 Dock/Grid。  
5. **执行位置**：算分/规则在服务端；浏览器只展示与确认。  
6. **线程预算**：见 §7。  
7. **授权**：优先 MIT/Apache；上生产前复核各库 license。  
8. **退出成本**：领域数据在 API Schema，不绑死助手 UI 框架。

---

*下一步：ADR-005 确认后，W1 可并行脚手架 `apps/web`（Vite）与 `apps/api`。*
