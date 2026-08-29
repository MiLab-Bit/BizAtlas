import { PageHeader, Card, CardContent, CardHeader, CardTitle } from "@/shared/ui";

const pipeline: Array<[string, string, string]> = [
  ["S0", "意图识别", "用户话术/按钮意图 → Intent（analyze_risk / gen_report / add_rule / ask）。"],
  ["S1", "资料理解", "文件/URL → MetricPack + chunks + 可选 KG 草案。"],
  ["S2", "数据补全", "补全外部字段、质检、冲突列表。"],
  ["S3", "规则匹配", "MetricPack + RuleSet → RuleHits（含 severity、explain）。"],
  ["S4", "风险评分", "MetricPack + RuleHits → 五维、总分、等级、否决。"],
  ["S5", "报告装配", "RiskResult + 模板 → ReportDraft + 一页摘要。"],
];

const dataPoints: Array<[string, string]> = [
  ["多源接入", "财务（PDF/Excel + 可选 Tushare/AKShare）、工商、司法、舆情、行业对标；AKShare 已实现（默认关闭）。"],
  ["三级降级", "L1 实时 → L2 缓存（SQLite）→ L3 估算（标注低置信度）；字段带 tier/source/as_of/confidence，单字段 L3 不中断分析。"],
  ["六维质检", "完整性·准确性·及时性·一致性·充足性·可用性追溯（缺引用数字不得进报告正文）。"],
  ["本地 RAG + KG", "文档切片检索做引用溯源；实体-关系图谱（G6）支撑关联与担保链推演。"],
  ["SQLite 持久化", "companies/documents/financial_metrics/entities_relations/rules/risk_scores/reports 等表。"],
  ["多源冲突归因", "冲突进列表；五维评分归因到指标与规则命中；支持压力测试情景。"],
];

const principles: string[] = [
  "能力与领域分离——算法内核通用，规则/模板外置可配置。",
  "可解释优先——每条结论输出「数据 → 计算 → 结论」链路。",
  "人在回路——AI 出草稿，人不确认不触发外部动作。",
  "降级不阻塞——数据/服务不可用继续跑，明确标注 _tier。",
  "关键数字可溯源——指标与评分强制走规则计算，LLM 不编数字。",
];

export function EngineeringPage() {
  return (
    <main className="mx-auto w-full max-w-6xl space-y-8 px-5 py-8">
      <PageHeader
        brand="BizAtlas · 工程能力"
        title="商舆：企业经营与风险研判 Agent"
        description="数据 + 规则 + 计算，可解释、可降级、人在回路。下面是我们对 Agent 工程与数据工程的真实落地——不调黑箱、不编数字。"
      />

      <section className="space-y-3">
        <h2 className="text-xl font-semibold text-foreground">一、对 Agent 技术的理解</h2>
        <p className="text-sm leading-relaxed text-muted-foreground">
          我们把「分析师读资料 → 算风险 → 写报告」拆成一条可编排、可解释、可降级的流水线，而不是把问题丢给一个大模型。
        </p>
        <div className="grid gap-3 sm:grid-cols-2">
          {pipeline.map(([s, name, desc]) => (
            <Card key={s}>
              <CardHeader>
                <CardTitle className="flex items-center gap-2 text-base">
                  <span className="rounded-md bg-secondary px-2 py-0.5 text-xs font-mono text-muted-foreground">{s}</span>
                  {name}
                </CardTitle>
              </CardHeader>
              <CardContent className="text-sm text-muted-foreground">{desc}</CardContent>
            </Card>
          ))}
        </div>
        <ul className="list-disc space-y-1 pl-5 text-sm text-muted-foreground">
          <li>意图驱动任务图：五类意图（分析风险 / 生成报告 / 文档问答 / NL 加规则 / 贷前尽调），未知意图先澄清。</li>
          <li>人在回路：AI 出草稿与建议，人不确认不触发外部动作；NL 规则先入 pilot，确认后才计分。</li>
          <li>LLM 定位克制：只做解析辅助与文案润色；润色含未登记数字则 Gate 拒绝并回退模板句。</li>
        </ul>
      </section>

      <section className="space-y-3">
        <h2 className="text-xl font-semibold text-foreground">二、数据工程能力</h2>
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {dataPoints.map(([title, desc]) => (
            <Card key={title}>
              <CardHeader>
                <CardTitle className="text-base">{title}</CardTitle>
              </CardHeader>
              <CardContent className="text-sm text-muted-foreground">{desc}</CardContent>
            </Card>
          ))}
        </div>
      </section>

      <section className="space-y-3">
        <h2 className="text-xl font-semibold text-foreground">三、风险研判内核</h2>
        <p className="text-sm leading-relaxed text-muted-foreground">
          五维评分：财务 30% · 经营 25% · 行业 15% · 舆情 15% · 关联 15%。GREEN–BLACK 五级（0–100），叠加「失信被执行 / 破产重整 / 严重造假迹象」一票否决 → BLACK。每条结论输出「数据 → 计算 → 结论」溯源链路。
        </p>
      </section>

      <section className="space-y-3">
        <h2 className="text-xl font-semibold text-foreground">四、工程原则（不可砍）</h2>
        <ul className="list-disc space-y-1 pl-5 text-sm text-muted-foreground">
          {principles.map((p) => (
            <li key={p}>{p}</li>
          ))}
        </ul>
      </section>

      <section className="space-y-3">
        <h2 className="text-xl font-semibold text-foreground">五、已交付且可演示</h2>
        <p className="text-sm leading-relaxed text-muted-foreground">
          API + 规则/风险闭环 · React 工作台（雷达/图谱/副驾）· 三套演示案例（健康/风险/违约）· Word/PDF 导出与信用评估报告 · NL 加规则 · 本地 RAG · 担保链 KG（G6）· 压力测试 · 多源冲突 · 五维归因 · 行业对标 · 规则中心 / 报告中心独立页 · AKShare Provider（默认关闭）。
        </p>
        <p className="text-xs text-muted-foreground">技术栈：React + Vite · FastAPI · SQLite · YAML 规则库 · 本地 RAG / 知识图谱（G6）· 确定性规则引擎 + LLM 辅助。</p>
      </section>
    </main>
  );
}
