# BizAtlas × Temporal 编排底座

> 分层重构：以 Temporal 作为长任务 / 有状态流程的底座，FastAPI 退化为 HTTP 网关。
> 默认开关关闭（`BIZATLAS_TEMPORAL_ENABLED=false`），关闭时全应用行为与原先完全一致。

## 1. 为什么是 Temporal

BizAtlas 有两类流程天然契合 Temporal：

| 流程 | 原实现 | Temporal 带来的收益 |
|---|---|---|
| 多 Agent 研判管线（`run_analysis_pipeline` / SSE） | 同步串行 + 后台线程 | 可持久化、可重试、可观测；每步 Activity 独立超时/重试/心跳；崩溃可恢复 |
| 贷前尽调状态机（`workflow/due_diligence.py`） | 手写 SQLite 状态机 | 状态即事件溯源；`advance`/`review` 为显式 Update；审计轨迹 = Temporal 事件历史；人在回路硬门禁 |

核心约束（Temporal 铁律）：**Workflow 代码必须确定性**。因此所有"会变"的操作
（LLM 调用、RAG 检索、SQLite 读写、报告导出）一律落到 Activity，Workflow 只做
顺序编排、分支、等待信号、维护内存状态。

## 2. 架构

```
                         ┌─────────────────────────────┐
  HTTP 客户端 ─────────► │ FastAPI (apps/api)          │
   /v1/analyze/pipeline  │  - 开关关闭：走原同步路径    │
   /v1/workflows/*       │  - 开关开启：调用 Temporal  │
                         │    start / query / update   │
                         └──────────────┬──────────────┘
                                        │ gRPC (temporalio client)
                                        ▼
                         ┌─────────────────────────────┐
                         │ Temporal Cluster             │
                         │  - RiskAnalysisWorkflow      │
                         │  - DueDiligenceWorkflow      │
                         └──────────────┬──────────────┘
                                        │ 派发任务到任务队列
                                        ▼
                         ┌─────────────────────────────┐
                         │ Worker (bizatlas-worker)     │
                         │  注册 Workflow + Activities   │
                         │  Activities → 领域函数        │
                         │   (run_analyze / agents / …)  │
                         └─────────────────────────────┘
```

- **FastAPI**（`apps/api/app/main.py`）：仅在 6 个路由上按开关分支；关闭时零改动。
  新增 `GET /v1/analyze/pipeline/{workflow_id}` 查询管线状态。
- **Gateway**（`apps/api/app/temporal_gateway.py`）：HTTP ↔ Temporal 翻译层，
  所有 `temporalio` 引用懒导入，确保离线/未装 temporalio 时不污染既有测试。
- **包**（`packages/bizatlas/temporal/`）：
  - `client.py` 懒连接 + 缓存
  - `common.py` 跨边界 dataclass（`RiskAnalysisInput` / `DueDiligenceInput`）
  - `activities.py` 领域函数 → `@activity.defn`
  - `workflows/risk_analysis.py` 多 Agent 管线（Query：`get_progress`/`get_status`/`get_result`）
  - `workflows/due_diligence.py` 贷前尽调（Update：`advance`/`review`；Query：`get_snapshot`）
  - `worker.py` Worker 启动器
- **SQLite 仍作系统记录**（companies / metrics / users / 报告 / 工作流镜像）。
  Temporal 是事件溯源日志，不适合做"列表所有进行中工作流"扫描；贷前尽调每次变更
  通过 `dd_mirror` Activity 写回 `workflows` 表，列表查询走镜像，单一实例详情走 Query。

## 3. 本地运行（Dev Server）

```bash
# 0) 装可选依赖
pip install "temporalio>=1.6.0"

# 1) 起 Temporal Dev Server（需 temporal CLI）
#    macOS/homebrew: brew install temporal
#    或用 docker: docker run -p 7233:7233 -p 8080:8080 temporalio/auto-setup
temporal server start-dev

# 2) 起 Worker（独立进程）
python scripts/run_worker.py
#   或：bizatlas-worker

# 3) 起 API（打开 Temporal 开关）
export BIZATLAS_TEMPORAL_ENABLED=true
export TEMPORAL_ADDRESS=localhost:7233
export TEMPORAL_NAMESPACE=default
export TEMPORAL_TASK_QUEUE=bizatlas-task-queue
uvicorn apps.api.launcher:app --port 8000
```

或用 Docker Compose 一把起（`deploy/docker-compose.temporal.yml`，含 Temporal + API + Worker）。

## 4. 接口变化

开启 Temporal 后：

- `POST /v1/analyze/pipeline`：不再同步返回完整结果，而是立即返回
  `{"workflow_id": "...", "status": "running"}`。
  客户端轮询 `GET /v1/analyze/pipeline/{workflow_id}`，或订阅
  `GET /v1/analyze/pipeline/stream?company_id=...`（SSE，行为与原来一致）。
- `POST /v1/workflows/due-diligence`：启动 `DueDiligenceWorkflow`，返回快照。
- `POST /v1/workflows/{id}/advance` 与 `/review`：走 Temporal Update，返回值不变。
- `GET /v1/workflows/{id}`：优先走 Temporal Query；Workflow 已结束（submit 后）则回退 SQLite 镜像。

关闭 Temporal 时，上述接口全部回退到原有同步实现，契约不变。

## 5. 测试

```bash
# 单元测试（无需 Temporal server，离线可跑）：
#   - create_due_diligence 形状 / 纯状态逻辑
#   - Activity 封装（需 temporalio；未装则整文件 skip）
pytest tests/test_temporal.py

# 端到端（需 Temporal server 在 localhost:7233）：
TEMPORAL_SERVER=1 pytest tests/test_temporal.py -k integration
```

## 6. 生产注意事项

- 用 Temporal Cloud 或自建集群（PostgreSQL/Cassandra 后端）替代 Dev Server。
- 命名空间：Dev Server 默认 `default`；自建可 `temporal namespace create bizatlas` 并改 `TEMPORAL_NAMESPACE`。
- Worker 应多副本部署（同任务队列）以实现高可用；Activity 幂等（评分/导出带 company 维度，重复执行安全）。
- 镜像固化 `temporalio`（见 docker-compose.temporal.yml 顶部说明）。

## 7. 本地端到端验证（已实测通过）

环境：Windows + Python 3.13 + `temporalio 1.33.0` + `temporal` CLI 1.9.1（Dev Server 1.32.0）。

```bash
# 1) 起本地集群
temporal server start-dev --ip 127.0.0.1 --port 7233      # gRPC 7233 / UI 8233

# 2) 起 Worker（独立进程；会自动 init_db() 建 SQLite schema）
export PYTHONPATH="$PWD/packages;$PWD/apps"
export BIZATLAS_TEMPORAL_ENABLED=true
python scripts/run_worker.py

# 3) 跑两条真实工作流
python scripts/e2e_risk_analysis.py      # RiskAnalysisWorkflow
python scripts/e2e_due_diligence.py      # DueDiligenceWorkflow（含人在回路）
```

实测结果：

- `RiskAnalysisWorkflow`（company_id=`risky`）→ `Completed`，`pipeline_mode=deterministic`、`metrics_count=17`，返回含 `agents/risk/rules_hit/graph/narrative/onepager/trace` 的完整研判。
- `DueDiligenceWorkflow`（fixture=`risky`）→ 全流程 `Completed`：
  `checklist(ready) → analyze(grade=BLACK) → report(requires_review) → review(approve) → submit(exported)`，
  最终导出 `exports/rp-*.md`，审计轨迹落在 `history` + Temporal 事件历史。

### 实测中修复的问题（已合入）

1. **沙箱校验**：`bizatlas.*` 域模块导入期有非确定性副作用（如 `Path.resolve`），Worker 里对沙箱设 `passthrough_modules={"bizatlas"}`。
2. **超时类型**：Activity 的 `start_to_close_timeout` 必须是 `timedelta`（原写成 int，SDK 报 `Fail to convert to Duration`）。
3. **管线模式汇总**：`collect_agent_mode(*results: AgentResult)` 期望 `AgentResult`；Workflow 内改为对 `AgentMode` 列表直接聚合。
4. **Worker 建表**：Worker 是独立进程、不经过 FastAPI 启动钩子，`_run()` 里显式 `init_db()`（否则 Activity 读表报 `no such table: companies`）。
5. **Update 初始化竞态**：客户端启动后立刻 `advance` 时，Update 可能在 `run()` 完成初始化前到达；`advance`/`review` 加 `wait_condition(company_id is not None)`。
6. **Update 与终态竞速**：`submit` 使 Workflow 完成时，Update 回值可能丢失（`AcceptedUpdateCompletedWorkflow`）；网关与示例客户端在 `action=="submit"` 时改取 `handle.result()`。
7. **Update 入参风格**：`WorkflowHandle.execute_update` 只接受单个 `arg` 或 `args=[...]`，不支持关键字参数，网关已改用 `args=[...]`。
