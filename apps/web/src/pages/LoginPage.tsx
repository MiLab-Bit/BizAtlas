import { useState } from "react";
import type { FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import { Button, Card, CardContent, CardHeader, CardTitle } from "@/shared/ui";
import { login, register } from "@/shared/lib/auth";
import { requestVerification } from "@/shared/lib/api";

export function LoginPage() {
  const navigate = useNavigate();
  const [mode, setMode] = useState<"login" | "register">("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [nickname, setNickname] = useState("");
  const [error, setError] = useState("");
  const [info, setInfo] = useState("");
  const [needsVerify, setNeedsVerify] = useState(false);
  const [verifyAddr, setVerifyAddr] = useState("");
  const [busy, setBusy] = useState(false);

  function switchMode(next: "login" | "register") {
    setMode(next);
    setError("");
    setInfo("");
    setNeedsVerify(false);
  }

  async function resendVerification() {
    setError("");
    setBusy(true);
    try {
      await requestVerification(verifyAddr.trim());
      setInfo("验证邮件已重新发送，请查收（若邮箱已验证或不存在则静默忽略）。");
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  async function submit(e: FormEvent) {
    e.preventDefault();
    setError("");
    setInfo("");
    setNeedsVerify(false);
    setBusy(true);
    try {
      if (mode === "login") {
        await login(email.trim(), password);
        navigate("/");
      } else {
        const outcome = await register(email.trim(), password, nickname.trim() || undefined);
        if (outcome.status === "needs_verification") {
          setNeedsVerify(true);
          setVerifyAddr(outcome.email);
          setInfo("注册成功，请查收验证邮件以激活账户后再登录。");
        } else {
          navigate("/");
        }
      }
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      if (mode === "login" && /verif/i.test(msg)) {
        setNeedsVerify(true);
        setVerifyAddr(email.trim());
      }
      setError(msg);
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
            {info && <p className="text-sm text-foreground">{info}</p>}
            <Button type="submit" disabled={busy} className="mt-1">
              {busy ? "处理中…" : mode === "login" ? "登录" : "注册"}
            </Button>
          </form>

          {needsVerify && (
            <div className="mt-3 flex flex-col gap-2 rounded-md border border-border bg-accent/40 p-3">
              <p className="text-sm text-foreground">
                该邮箱尚未验证。请查收验证邮件并点击链接激活；若未收到：
              </p>
              <Button
                type="button"
                disabled={busy}
                onClick={resendVerification}
                className="w-full"
              >
                {busy ? "处理中…" : "重发验证邮件"}
              </Button>
            </div>
          )}

          <div className="mt-3 flex items-center justify-between text-sm">
            <button
              type="button"
              onClick={() => switchMode(mode === "login" ? "register" : "login")}
              className="text-muted-foreground underline-offset-4 hover:underline"
            >
              {mode === "login" ? "没有账号？去注册" : "已有账号？去登录"}
            </button>
            {mode === "login" && (
              <Link
                to="/forgot-password"
                className="text-muted-foreground underline-offset-4 hover:underline"
              >
                忘记密码？
              </Link>
            )}
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
