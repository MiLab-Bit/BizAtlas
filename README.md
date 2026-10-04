# 商舆 BizAtlas · 让企业风险研判像聊天一样简单

> **上传一份财报，或问一句「这家公司稳吗」——商舆在几秒内给出五维风险研判、可溯源结论与一页报告。**
> 一个**数据 + 规则 + 计算**驱动的金融分析 Agent，专为 to-B 金融场景而生：**结论可解释、过程可溯源、关键数字绝不靠大模型编造。**

---

## 在线部署 / Live Deployment

| 环境 | 地址 |
|---|---|
| API 服务 | http://bizatlas.sy-realm.ltd |
| Swagger 文档 | http://bizatlas.sy-realm.ltd/docs |

> FastAPI 后端，部署于阿里云 ECS，经 Nginx 反代，DNS 走 Cloudflare（DNS-only 直连）。
> 编排底座：Temporal（[temporal.sy-realm.ltd](http://temporal.sy-realm.ltd) 可视化 Workflow 执行）。



## 商舆能帮你解决什么

金融分析师每天在做三件事：读资料、算风险、写报告。商舆把这三条流水线自动化：

- **读资料** —— PDF / Excel / CSV / TXT 一键解析，自动抽取财务三表与关键指标，建本地知识库。
- **算风险** —— 22+ 条可解释规则 + 五维评分内核，输出 GREEN → BLACK 五级风险等级与一票否决判定。
- **写报告** —— 一句话结论 + 五维雷达 + 担保链图谱 + 信用评估 Word/PDF，人工确认即出稿。

你不需要懂风控模型，只要**会问问题**。

## ✨ 主打功能

| 功能 | 一句话说明 |
| --- | --- |
| 🔍 **一键风险研判** | `POST /v1/analyze`：上传或指定企业 → 规则命中 → 五维评分 → 风险等级，全程秒级返回 |
| 🧮 **五维评分内核** | 财务 30% · 经营 25% · 行业 15% · 舆情 15% · 关联 15%，GREEN–BLACK 五级 + 一票否决 |
| 📐 **可解释规则引擎** | YAML 规则库 22+ 条；支持**自然语言加规则**（`/v1/rules/from-nl`），先入 pilot 后转正 |
| 🕸️ **担保链知识图谱** | AntV G6 可视化实控人 / 担保 / 关联企业网络，关联风险一目了然 |
| 📚 **本地 RAG 副驾** | `/v1/chat` 基于上传资料的引用溯源问答；「加规则：…」自动分流建规则 |
| 📝 **信用评估报告** | 一页摘要 + 完整信用评估报告，导出 Markdown / Word / PDF |
| 🧪 **压力测试与归因** | 行业下行 / 大客户流失情景推演，五维评分归因到具体指标与规则命中 |
| 🔄 **三级数据降级** | 实时 → 缓存 → 估算，单源故障不中断分析，每字段标注 `tier / source / confidence` |
| ✅ **贷前尽调流程** | 清单 → 研判 → 报告 → 人工确认提交，AI 出草稿、人不确认不动作 |
| 📱 **微信小程序** | 移动端随身查阅风险研判（appid `wx18d6236028c29ea9`，上传脚本已就绪） |

## 🛡️ 为什么是商舆，而不是又一个聊天机器人

1. **计算确定性** —— 关键数字与评分强制走确定性规则计算，LLM 只做解析与润色；润色若混入未登记数字，Gate 直接拒绝并回退模板。**不编数字。**
2. **处处可溯源** —— 每条结论都输出「数据 → 计算 → 结论」链路，报告首段固定为「一句话结论 + 风险等级」。
3. **人在回路** —— AI 出草稿与建议，外部动作（提交、导出）必须人工确认；NL 新规则先入 pilot，人工确认才转正计分。
4. **降级不阻塞** —— 数据 / 服务不可用时继续跑，明确标注降级层级，分析绝不因单字段缺失而中断。

## ⚙️ 技术架构一览

```
上传资料 / 对话指令
        ↓
编排层（意图识别 → 任务图 → 人在回路闸门）
        ↓
资料理解 → 规则匹配 → 风险研判 → 投研整理 → 流程辅助
        ↓
数据层（多源获取 · 三级降级 · 六维质检 · SQLite · RAG）
```

全栈 Python（FastAPI + React 19 工作台），详情见 [技术架构文档](docs/ARCHITECTURE.md)。

## 🧭 文档地图

| 文档 | 内容 |
| --- | --- |
| [`PRD.md`](docs/PRD.md) | 产品需求文档 |
| [`ARCHITECTURE.md`](docs/ARCHITECTURE.md) | 技术架构 |
| [`RULES.md`](docs/RULES.md) | 规则引擎设计 |
| [`HANDOVER.md`](docs/HANDOVER.md) | 交接文档 |

## 🏁 快速开始

```bash
git clone https://github.com/MiLab-Bit/BizAtlas.git
cd BizAtlas
python -m venv venv && source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -e ".[dev]"

# 启动 API
uvicorn apps.api.app.main:app --reload --port 8000

# 启动前端
cd apps/web && npm install && npm run dev
```

## 📊 当前状态

| 项 | 状态 |
|---|---|
| API + 规则 / 风险闭环 | ✅ |
| React 工作台（雷达 / 图谱 / 副驾） | ✅ |
| 信用报告 Word / PDF 导出 | ✅ |
| NL 加规则 / 本地 RAG / 担保链 KG | ✅ |
| 压力测试 / 多源冲突 / 五维归因 | ✅ |
| 微信小程序（已上传 v1.0.1，待配域名白名单） | ✅ |
| CI/CD（GitHub Actions，覆盖率 ≥ 75%） | ✅ 绿 |

---

*产品名 商舆 · 工程代号 BizAtlas · 文档对齐 PRD v1.0*

## 本轮新增能力（2026-09-01）

承接《竞品扫描与产品路线》，三级优先级（P0 进门门槛 / P1 差异化加深 / P2 规模化前置）已落地：

| 能力 | 层级 | 说明 |
|---|---|---|
| PD/LGD 模型校准 | P0 | 启发式得分叠加违约概率/损失校准，AUC/KS 可评估、标签可回灌 |
| 审计中间件 | P0 | 敏感 API 调用全量写入 append-only 审计日志 |
| 私有化一键部署 | P0 | `deploy/privatize.sh` 生成强随机密钥、强制开启鉴权、幂等可重跑 |
| 征信 / 票据 OCR 数据源 | P0 | 真实数据源接线，未配置优雅降级 |
| 担保链传染推导 | P1 | 担保图谱违约穿透，量化关联违约敞口 |
| 可解释溯源报告 | P1 | 指标溯源到规则文件 / PDF 页码 / 法条 |
| 效果度量埋点 | P2 | 分析师决策反馈采集（RaaS 前置） |
| 开放 API / MCP 骨架 | P2 | JSON-RPC MCP server + Prometheus 指标端点 |

详见 `HANDOVER.md` 的「产品优化路线执行记录」段。

---

## Temporal 编排接入（2026-10）

BizAtlas 的多 Agent 研判管线（RiskAnalysis）和尽调流程（DueDiligence）已接入 **Temporal Server v1.27** 进行编排，实现工作流持久化、自动重试、状态查询和人在回路审批。

### 架构

```
FastAPI (:8000) → Temporal Client → Temporal Server (:7233)
                                          │
                                   namespace: bizatlas
                                          │
                              Worker (独立进程, systemd 管理)
                              ├── RiskAnalysisWorkflow（五维风险研判）
                              └── DueDiligenceWorkflow（尽调流程）
                                   └── 12 个同步 Activity
```

### 代码结构

```
packages/bizatlas/temporal/
├── common.py           # 跨边界数据结构
├── activities.py       # 12 个同步 Activity（线程池执行）
├── worker.py           # Worker 启动器（SandboxedWorkflowRunner + ThreadPool）
├── client.py           # Temporal Client 工厂
└── workflows/
    ├── risk_analysis.py   # 五维风险研判管线
    └── due_diligence.py   # 尽调工作流
```

### 设计原则

- **Workflow 只做确定性编排**：顺序 / 分支 / 等待信号，所有会变的操作落到 Activity
- **Activity 一律同步 def**：线程池执行，不阻塞事件循环
- **Sandbox passthrough**：bizatlas.* 领域模块设为沙箱直通
- **跨边界数据用 dict/dataclass**：不使用 pydantic 模型直传

### 配置

```bash
# .env（不入 git）
BIZATLAS_TEMPORAL_ENABLED=true
TEMPORAL_ADDRESS=127.0.0.1:7233
TEMPORAL_NAMESPACE=bizatlas
TEMPORAL_TASK_QUEUE=bizatlas-task-queue
```
