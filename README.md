# 商舆 BizAtlas · 让企业风险研判像聊天一样简单

> **上传一份财报，或问一句「这家公司稳吗」——商舆在几秒内给出五维风险研判、可溯源结论与一页报告。**
> 一个**数据 + 规则 + 计算**驱动的金融分析 Agent，专为 to-B 金融场景而生：**结论可解释、过程可溯源、关键数字绝不靠大模型编造。**

**▶ 立即体验：[https://bizatlas.sy-realm.ltd](https://bizatlas.sy-realm.ltd)**

---

## 使用方式

1. 打开 **[bizatlas.sy-realm.ltd](https://bizatlas.sy-realm.ltd)**，注册并登录
2. **两条入口，选一个**：
   - **上传资料**：PDF / Excel / CSV / TXT 一键解析，自动抽取财务三表与关键指标，建本地知识库
   - **直接提问**：问一句「这家公司稳吗」，从公开信息 + 已上传资料中研判
3. 得到五维风险研判：风险等级（GREEN → BLACK 五级）+ 五维雷达 + 担保链图谱 + 一句话结论
4. 追问、加规则、跑压力测试；确认无误后**导出信用评估报告**（Markdown / Word / PDF）
5. 移动端可走微信小程序，随身查阅

> 人在回路：AI 出草稿与建议，外部动作（提交、导出）必须人工确认——**人不确认，不动作**。

---

## 品牌与产品能力

金融分析师每天在做三件事：读资料、算风险、写报告。商舆把这三条流水线自动化：

| 功能 | 一句话说明 |
| --- | --- |
| 🔍 **一键风险研判** | 上传或指定企业 → 规则命中 → 五维评分 → 风险等级，全程秒级返回 |
| 🧮 **五维评分内核** | 财务 30% · 经营 25% · 行业 15% · 舆情 15% · 关联 15%，GREEN–BLACK 五级 + 一票否决 |
| 📐 **可解释规则引擎** | YAML 规则库 22+ 条；支持**自然语言加规则**，先入 pilot 后转正 |
| 🕸️ **担保链知识图谱** | 实控人 / 担保 / 关联企业网络可视化，关联风险一目了然 |
| 📚 **本地 RAG 副驾** | 基于上传资料的引用溯源问答；「加规则：…」自动分流建规则 |
| 📝 **信用评估报告** | 一页摘要 + 完整报告，导出 Markdown / Word / PDF |
| 🧪 **压力测试与归因** | 行业下行 / 大客户流失情景推演，评分归因到具体指标与规则命中 |
| 🔄 **三级数据降级** | 实时 → 缓存 → 估算，单源故障不中断分析，每字段标注 `tier / source / confidence` |
| ✅ **贷前尽调流程** | 清单 → 研判 → 报告 → 人工确认提交 |

### 为什么是商舆，而不是又一个聊天机器人

1. **计算确定性**——关键数字与评分强制走确定性规则计算，LLM 只做解析与润色；润色若混入未登记数字，Gate 直接拒绝并回退模板。**不编数字。**
2. **处处可溯源**——每条结论都输出「数据 → 计算 → 结论」链路，报告首段固定为「一句话结论 + 风险等级」。
3. **人在回路**——AI 出草稿与建议，外部动作必须人工确认；NL 新规则先入 pilot，人工确认才转正计分。
4. **降级不阻塞**——数据 / 服务不可用时继续跑，明确标注降级层级，分析绝不因单字段缺失而中断。

---

## 技术与特色

| 层 | 选型 |
| --- | --- |
| 前端 | React 19 · Vite 8 · TypeScript 5.9 · Tailwind CSS 4 · React Router 7 · TanStack Query 5 · Zustand 5 |
| UI 基座 | Radix UI 原语 + CVA + clsx + tailwind-merge（shadcn 模式，源码分发、代码归自己） |
| 可视化 | ECharts 5（五维雷达/混合图表）+ React Flow（担保链图谱）+ 可拖拽分栏面板 |
| 后端 | FastAPI · Pydantic v2 · PDF/Excel/Word 解析 · Fernet 加密 |
|  Schema 校验 | Zod |

**工程特色**：

- **混合图表才上 ECharts，单一轻图表用轻库**——五维雷达是雷达图 + 柱图 + 表格混合，ECharts 是对的选择；图谱走 React Flow 而非自研
- **服务端状态与 UI 状态分离**：报告/任务归 TanStack Query，面板折叠/筛选器归 Zustand
- **依赖分组打包**：vendor 按 react / charts / graph / radix / misc 分组，缓存粒度到库一级
- **pnpm monorepo**：apps/api + apps/web + apps/miniprogram，Web + 微信小程序双端共享契约

---

## 业务建模：把风险研判写成可审计的决策系统

商舆的核心对象不是“一段 AI 回答”，而是 **企业、指标、证据、规则命中、风险结果、授信建议与尽调工作流**。财务数据与外部事件先映射为 `MetricValue`、`Evidence` 与 `RuleHit`，再通过 `risk/score.py` 的五维评分、否决与缺失数据策略形成 `RiskResult`；`credit/decision.py` 将评级进一步转为授信准入建议；`workflow/due_diligence.py` 管理清单和人工复核。

**为什么这样设计：** 风险事实、模型推断和最终业务决策拥有不同的责任与证据要求。评分口径由 `ScoringSnapshot` 保存；数据不足为 `UNRATED`，而不是误判为 GREEN；新规则可处于 `pilot`，不立即参与正式计分。业务上的“未知不等于安全”因此成为可检查的程序行为。

**源码入口：** [领域契约](packages/bizatlas/contracts/models.py) · [规则引擎](packages/bizatlas/rules/engine.py) · [风险评分](packages/bizatlas/risk/score.py) · [授信建议](packages/bizatlas/credit/decision.py) · [尽调流程](packages/bizatlas/workflow/due_diligence.py)。

## 工程完成度与验证边界

- **已在仓库中实现：** Pydantic 领域契约、YAML 规则匹配、风险评分与融合逻辑、证据引用、尽调状态、API、Web 和小程序代码；`tests/` 有规则风控、授信、数据摄取、数字真实性门禁、RBAC、工作流、Temporal 和黄金回归测试。
- **可复核的工程配置：** [GitHub Actions CI](.github/workflows/ci.yml) 与项目内测试。存在测试和 CI 配置不等于最新提交全部通过，实际状态应以对应 commit 的运行记录为准。
- **尚需独立验证：** 真实金融数据的完整性与授权、评分预测校准、真实业务中的人工审批效果、生产级可用性与跨系统端到端验收。授信结果是辅助决策建议，不是自动放款承诺。


---

© 商舆 BizAtlas · MiLab-Bit
