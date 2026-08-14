import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { KeyRound, Plus, Trash2, Eye, EyeOff, CheckCircle2, XCircle } from "lucide-react";
import {
  listProviderPresets,
  listModelProviders,
  testModelProvider,
  createModelProvider,
  deleteModelProvider,
  type ModelProvider,
  type ProviderPreset,
} from "@/shared/lib/api";
import {
  Button,
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
  Input,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/shared/ui";

export function ModelConfigPage() {
  const qc = useQueryClient();
  const [preset, setPreset] = useState<ProviderPreset | null>(null);
  const [name, setName] = useState("");
  const [apiKey, setApiKey] = useState("");
  const [baseUrl, setBaseUrl] = useState("");
  const [model, setModel] = useState("");
  const [showKey, setShowKey] = useState(false);
  const [testResult, setTestResult] = useState<
    { ok: boolean; kind: "success" | "timeout" | "fail"; msg: string } | null
  >(null);
  const [saveErr, setSaveErr] = useState<string | null>(null);

  const { data: presets = [] } = useQuery({
    queryKey: ["providerPresets"],
    queryFn: listProviderPresets,
  });
  const { data: providers = [], isLoading } = useQuery({
    queryKey: ["modelProviders"],
    queryFn: listModelProviders,
  });

  const testMut = useMutation({
    mutationFn: () =>
      testModelProvider({
        provider: preset?.provider ?? "custom",
        apiKey,
        baseUrl: baseUrl || undefined,
        model: model || undefined,
      }),
    onSuccess: (r) =>
      setTestResult(
        r.ok
          ? { ok: true, kind: "success", msg: `连通成功（${r.latency_ms ?? "?"}ms）` }
          : (r.error ?? "").includes("超时")
            ? { ok: false, kind: "timeout", msg: r.error ?? "未知错误" }
            : { ok: false, kind: "fail", msg: r.error ?? "未知错误" },
      ),
    onError: (e) =>
      setTestResult({ ok: false, kind: "fail", msg: e instanceof Error ? e.message : "测试失败" }),
  });

  const createMut = useMutation({
    mutationFn: () =>
      createModelProvider({
        name: name.trim(),
        provider: preset?.provider ?? "custom",
        apiKey,
        baseUrl: baseUrl || undefined,
        model: model || undefined,
      }),
    onSuccess: () => {
      setName("");
      setApiKey("");
      setTestResult(null);
      setSaveErr(null);
      qc.invalidateQueries({ queryKey: ["modelProviders"] });
    },
    onError: (e) => setSaveErr(e instanceof Error ? e.message : "保存失败，请重试"),
  });

  const deleteMut = useMutation({
    mutationFn: (id: string) => deleteModelProvider(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["modelProviders"] }),
  });

  function applyPreset(p: ProviderPreset) {
    setPreset(p);
    setBaseUrl(p.baseUrl);
    setModel(p.defaultModel);
    if (!name) setName(p.label);
  }

  const statusLabel: Record<string, string> = {
    active: "有效",
    unverified: "未验证",
    error: "验证失败",
  };

  return (
    <div className="mx-auto max-w-4xl px-5 py-8">
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <KeyRound size={18} /> 模型配置
          </CardTitle>
          <CardDescription>
            配置你自己的大模型供应商密钥，BizAtlas 会用它来生成分析。密钥加密存储，仅你可见。
          </CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col gap-5">
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <label className="flex flex-col gap-1 text-sm">
              供应商
              <select
                className="rounded-md border border-input bg-background px-3 py-2 text-sm"
                value={preset?.provider ?? ""}
                onChange={(e) => {
                  const p = presets.find((x) => x.provider === e.target.value) ?? null;
                  if (p) applyPreset(p);
                }}
              >
                <option value="" disabled>
                  请选择供应商…
                </option>
                {presets.map((p) => (
                  <option key={p.provider} value={p.provider}>
                    {p.label}
                  </option>
                ))}
              </select>
            </label>
            <label className="flex flex-col gap-1 text-sm">
              名称（便于识别）
              <Input
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="例如：我的 OpenAI"
              />
            </label>
            <label className="flex flex-col gap-1 text-sm sm:col-span-2">
              API Key
              <div className="relative">
                <Input
                  type={showKey ? "text" : "password"}
                  value={apiKey}
                  onChange={(e) => setApiKey(e.target.value)}
                  placeholder="sk-... / 你的供应商密钥"
                  className="pr-16"
                />
                <Button
                  type="button"
                  size="sm"
                  variant="ghost"
                  className="absolute right-1 top-1"
                  onClick={() => setShowKey((s) => !s)}
                >
                  {showKey ? <EyeOff size={14} /> : <Eye size={14} />}
                  {showKey ? "隐藏" : "显示"}
                </Button>
              </div>
            </label>
            <label className="flex flex-col gap-1 text-sm">
              Base URL（OpenAI 兼容）
              <Input
                value={baseUrl}
                onChange={(e) => setBaseUrl(e.target.value)}
                placeholder="留空则使用供应商默认地址"
              />
            </label>
            <label className="flex flex-col gap-1 text-sm">
              模型
              <Input
                value={model}
                onChange={(e) => setModel(e.target.value)}
                placeholder="例如：gpt-4o-mini"
              />
            </label>
          </div>

          <div className="flex flex-wrap items-center gap-3">
            <Button
              variant="outline"
              disabled={!apiKey.trim() || testMut.isPending}
              onClick={() => testMut.mutate()}
            >
              {testMut.isPending ? "测试中…" : "测试连通性"}
            </Button>
            {testResult && (
              <span
                className={`inline-flex items-center gap-1 text-sm ${
                  testResult.kind === "success"
                    ? "text-emerald-600"
                    : testResult.kind === "timeout"
                      ? "text-amber-600"
                      : "text-red-600"
                }`}
              >
                {testResult.kind === "success" ? <CheckCircle2 size={15} /> : <XCircle size={15} />}
                {testResult.kind === "timeout"
                  ? `连接超时：${testResult.msg}（请检查网络或 Base URL 后重试）`
                  : testResult.msg}
              </span>
            )}
            <Button
              disabled={!preset || !name.trim() || !apiKey.trim() || createMut.isPending}
              onClick={() => createMut.mutate()}
            >
              <Plus size={15} /> {createMut.isPending ? "保存中…" : "保存配置"}
            </Button>
          </div>
          {saveErr && (
            <p className="text-sm text-red-600">保存失败：{saveErr}（可重试）</p>
          )}

          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>名称</TableHead>
                <TableHead>供应商</TableHead>
                <TableHead>模型</TableHead>
                <TableHead>状态</TableHead>
                <TableHead className="text-right">操作</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {isLoading && (
                <TableRow>
                  <TableCell colSpan={5} className="text-center text-muted-foreground">
                    加载中…
                  </TableCell>
                </TableRow>
              )}
              {!isLoading && providers.length === 0 && (
                <TableRow>
                  <TableCell colSpan={5} className="text-center text-muted-foreground">
                    尚无模型配置，添加一个开始使用你自己的大模型吧。
                  </TableCell>
                </TableRow>
              )}
              {providers.map((p: ModelProvider) => (
                <TableRow key={p.id}>
                  <TableCell className="font-medium">{p.name}</TableCell>
                  <TableCell>{p.provider}</TableCell>
                  <TableCell className="text-xs text-muted-foreground">{p.model ?? "—"}</TableCell>
                  <TableCell>
                    <span
                      className={
                        p.status === "active"
                          ? "text-emerald-600"
                          : p.status === "error"
                          ? "text-red-600"
                          : "text-muted-foreground"
                      }
                    >
                      {statusLabel[p.status] ?? p.status}
                    </span>
                  </TableCell>
                  <TableCell className="text-right">
                    <Button
                      size="sm"
                      variant="outline"
                      disabled={deleteMut.isPending}
                      onClick={() => {
                        if (window.confirm(`确定删除模型配置「${p.name}」？`)) {
                          deleteMut.mutate(p.id);
                        }
                      }}
                    >
                      <Trash2 size={14} />
                    </Button>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </CardContent>
      </Card>
    </div>
  );
}
