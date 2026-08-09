import { useState } from "react";
import type { FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { Button, Card, CardContent, CardHeader, CardTitle } from "@/shared/ui";
import { login, register } from "@/shared/lib/auth";

export function LoginPage() {
  const navigate = useNavigate();
  const [mode, setMode] = useState<"login" | "register">("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [nickname, setNickname] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setError("");
    setBusy(true);
    try {
      if (mode === "login") {
        await login(email.trim(), password);
      } else {
        await register(email.trim(), password, nickname.trim() || undefined);
      }
      navigate("/");
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="mx-auto flex min-h-[70vh] max-w-sm flex-col justify-center px-4">
      <Card>
        <CardHeader>
          <CardTitle className="text-xl">
            {mode === "login" ? "登录商舆" : "注册商舆账号"}
          </CardTitle>
          <p className="text-sm text-muted-foreground">
            企业风险研判平台 · 仅支持邮箱登录
          </p>
        </CardHeader>
        <CardContent>
          <form onSubmit={submit} className="flex flex-col gap-3">
            <label className="flex flex-col gap-1 text-sm">
              邮箱
              <input
                type="email"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="you@example.com"
                className="rounded-md border border-border bg-background px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-ring"
              />
            </label>
            {mode === "register" && (
              <label className="flex flex-col gap-1 text-sm">
                昵称（可选）
                <input
                  value={nickname}
                  onChange={(e) => setNickname(e.target.value)}
                  placeholder="分析师 A"
                  className="rounded-md border border-border bg-background px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-ring"
                />
              </label>
            )}
            <label className="flex flex-col gap-1 text-sm">
              密码
              <input
                type="password"
                required
                minLength={8}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="至少 8 位"
                className="rounded-md border border-border bg-background px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-ring"
              />
            </label>
            {error && <p className="text-sm text-destructive">{error}</p>}
            <Button type="submit" disabled={busy} className="mt-1">
              {busy ? "处理中…" : mode === "login" ? "登录" : "注册并登录"}
            </Button>
          </form>
          <button
            type="button"
            onClick={() => {
              setMode(mode === "login" ? "register" : "login");
              setError("");
            }}
            className="mt-3 text-sm text-muted-foreground underline-offset-4 hover:underline"
          >
            {mode === "login" ? "没有账号？去注册" : "已有账号？去登录"}
          </button>
        </CardContent>
      </Card>
    </div>
  );
}
