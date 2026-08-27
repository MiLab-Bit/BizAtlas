import { useState } from "react";
import type { FormEvent } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { Button, Card, CardContent, CardHeader, CardTitle } from "@/shared/ui";
import { requestPasswordReset, resetPassword } from "@/shared/lib/api";

export function ForgotPasswordPage() {
  const [params] = useSearchParams();
  const token = params.get("token") ?? "";
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [info, setInfo] = useState("");

  async function submitRequest(e: FormEvent) {
    e.preventDefault();
    setError("");
    setInfo("");
    setBusy(true);
    try {
      await requestPasswordReset(email.trim());
      setInfo("如果该邮箱已注册，重置邮件已发送，请查收并设置新密码。");
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  async function submitReset(e: FormEvent) {
    e.preventDefault();
    setError("");
    setInfo("");
    setBusy(true);
    try {
      await resetPassword(token, password);
      setInfo("密码已重置，即将跳转到登录页…");
      window.setTimeout(() => navigate("/login"), 1200);
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
          <CardTitle className="text-xl">{token ? "设置新密码" : "找回密码"}</CardTitle>
          <p className="text-sm text-muted-foreground">
            {token
              ? "请输入新的登录密码（至少 8 位）"
              : "输入注册邮箱，我们将发送密码重置链接"}
          </p>
        </CardHeader>
        <CardContent>
          {token ? (
            <form onSubmit={submitReset} className="flex flex-col gap-3">
              <label className="flex flex-col gap-1 text-sm">
                新密码
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
              {info && <p className="text-sm text-foreground">{info}</p>}
              <Button type="submit" disabled={busy} className="mt-1">
                {busy ? "处理中…" : "重置密码"}
              </Button>
            </form>
          ) : (
            <form onSubmit={submitRequest} className="flex flex-col gap-3">
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
              {error && <p className="text-sm text-destructive">{error}</p>}
              {info && <p className="text-sm text-foreground">{info}</p>}
              <Button type="submit" disabled={busy} className="mt-1">
                {busy ? "处理中…" : "发送重置邮件"}
              </Button>
            </form>
          )}
          <Link
            to="/login"
            className="mt-3 block text-sm text-muted-foreground underline-offset-4 hover:underline"
          >
            返回登录
          </Link>
        </CardContent>
      </Card>
    </div>
  );
}
