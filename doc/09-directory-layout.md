# 09 · 代码目录规划

> ✅ README · doc · `.env.example` · `.gitignore` 已建  
> 下列为脚手架目标树（W1 起落地）

---

## 1. 目标树

```
BizAtlas/
├── README.md
├── .env.example
├── .gitignore
├── pyproject.toml                 # workspace / 共享工具配置
├── doc/                           # ✅ 工程文档
│   ├── README.md
│   ├── 01-product-scope.md
│   ├── 02-architecture.md
│   ├── 03-tech-stack.md
│   ├── 04-data-layer.md
│   ├── 05-agent-pipeline.md
│   ├── 06-api-contracts.md
│   ├── 09-directory-layout.md
│   ├── 10-milestones.md
│   └── adr/
├── apps/
│   ├── api/                       # FastAPI
│   │   └── app/
│   │       ├── main.py
│   │       ├── routes/
│   │       └── deps.py
│   └── web/                       # React + Vite（ADR-005）
│       └── src/                   # 见 12-frontend-architecture
├── packages/
│   ├── contracts/
│   ├── data/
│   ├── ingest/
│   ├── rag/
│   ├── kg/
│   ├── rules/
│   ├── risk/
│   ├── report/
│   ├── workflow/
│   └── orchestrator/
├── content/
│   ├── rules/                     # YAML 规则资产
│   │   └── seed_financial.yaml
│   ├── templates/                 # 报告模板定义
│   │   ├── risk_onepager.yaml
│   │   └── credit_assessment.yaml
│   ├── industry/                  # 行业参数 / 均值
│   └── fixtures/                  # 三案例演示包
│       ├── healthy/
│       ├── risky/
│       └── defaulted/
├── data/                          # 运行时 DB（gitignore）
├── uploads/
├── exports/
├── scripts/
│   ├── smoke_analyze.py
│   ├── seed_db.py
│   └── eval_extract_accuracy.py
└── tests/
    ├── test_rules_engine.py
    ├── test_risk_score.py
    └── fixtures/
```

---

## 2. 依赖方向（硬）

```
apps/web ──HTTP──► apps/api
apps/api ──► packages/orchestrator
orchestrator ──► ingest, rules, risk, report, workflow, data, rag, kg
report ──► contracts（RiskResult）
rules ↛ risk
web ↛ data providers / API keys
* ──► contracts
```

---

## 3. 与产品设计目录的关系

| 路径 | 角色 |
|---|---|
| `商舆漫游指南/00–10` | PRD 权威 |
| `商舆漫游指南/BizAtlas/` | 本工程 |
| Web3QuantMaster（若本机有） | 复用参考，不作为运行时 submodule 强依赖 |

---

## 4. 命名

- 产品对外：商舆 / BizAtlas
- 仓库与包前缀：`bizatlas`  
- Python 包名：`bizatlas_contracts` / `bizatlas_risk` … 或 `packages.*` 本地 editable

---

*下一步：[10-milestones.md](./10-milestones.md)*
