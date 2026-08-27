import { useEffect, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { Button, Card, CardContent, CardHeader, CardTitle } from "@/shared/ui";
import { verifyEmail } from "@/shared/lib/api";

export function VerifyEmailPage() {
  const [params] = useSearchParams();
  const token = params.get("token") ?? "";
  const navigate = useNavigate();
  const [state, setState] = useState<"loading" | "ok" | "error">("loading");
  const [error, setError] = useState("");

  useEffect(() => {
    if (!token) {
      setState("error");
      setError("链接缺少验证令牌");
      return;
    }
    verifyEmail(token)
      .then(() => setState("ok"))
      .catch((e) => {
        setState("error");
        setError(e instanceof Error ? e.message : String(e));
      });
  }, [token]);

  return (
    <div className="mx-auto flex min-h-[70vh] max-w-sm flex-col justify-center px-4">
      <Card>
        <CardHeader>
          <CardTitle className="text-xl">邮箱验证</CardTitle>
          <p className="text-sm text-muted-foreground">企业风险研判平台 · 邮箱账户激活</p>
        </CardHeader>
        <CardContent className="flex flex-col gap-4">
          {state === "loading" && (
            <p className="text-sm text-muted-foreground">正在验证，请稍候…</p>
          )}
          {state === "ok" && (
            <>
              <p className="text-sm text-foreground">
                邮箱验证成功，现在可以使用该邮箱登录了。
              </p>
              <Button className="w-full" onClick={() => navigate("/login")}>
                去登录
              </Button>
            </>
          )}
          {state === "error" && (
            <>
              <p className="text-sm text-destructive">
                {error || "验证失败，链接可能已过期或无效。"}
              </p>
              <Button className="w-full" onClick={() => navigate("/login")}>
                返回登录
              </Button>
            </>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
