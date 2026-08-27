import { z } from "zod";
import { getEnvelope } from "./api";

const AuthUserSchema = z.object({
  user_id: z.string(),
  email: z.string(),
  nickname: z.string().nullable().optional(),
  avatar_url: z.string().nullable().optional(),
  status: z.string(),
  role: z.string(),
  email_verified: z.boolean().optional(),
  created_at: z.string().optional(),
});

const AuthResultSchema = z.object({
  access_token: z.string(),
  refresh_token: z.string(),
  token_type: z.string().optional(),
  expires_in: z.number().optional(),
  user: AuthUserSchema,
});

const MeSchema = z.object({
  user: AuthUserSchema.nullable(),
  anonymous: z.boolean().optional(),
  role: z.string(),
  scopes: z.array(z.string()),
});

export type AuthUser = z.output<typeof AuthUserSchema>;

const TOKEN_KEY = "bizatlas_access_token";
const REFRESH_KEY = "bizatlas_refresh_token";
const USER_KEY = "bizatlas_user";

export function getAccessToken(): string | null {
  return localStorage.getItem(TOKEN_KEY);
}

export function getStoredUser(): AuthUser | null {
  const raw = localStorage.getItem(USER_KEY);
  if (!raw) return null;
  try {
    return JSON.parse(raw) as AuthUser;
  } catch {
    return null;
  }
}

function persist(data: z.output<typeof AuthResultSchema>) {
  localStorage.setItem(TOKEN_KEY, data.access_token);
  localStorage.setItem(REFRESH_KEY, data.refresh_token);
  localStorage.setItem(USER_KEY, JSON.stringify(data.user));
}

export async function login(email: string, password: string): Promise<AuthUser> {
  const data = await getEnvelope("/v1/auth/login", AuthResultSchema, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password }),
  });
  persist(data);
  return data.user;
}

export type RegisterOutcome =
  | { status: "ok"; user: AuthUser }
  | { status: "needs_verification"; email: string; user: AuthUser };

export async function register(
  email: string,
  password: string,
  nickname?: string,
): Promise<RegisterOutcome> {
  const reg = await getEnvelope("/v1/auth/register", z.object({ user: AuthUserSchema }), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password, nickname: nickname || undefined }),
  });
  const user = reg.user;
  // 注册后若邮箱尚未验证，则不自动登录，交由前端引导去邮箱验证
  if (user.email_verified === false) {
    return { status: "needs_verification", email, user };
  }
  try {
    const data = await login(email, password);
    return { status: "ok", user: data };
  } catch {
    // 已验证却登录失败（极端情况）：仍以注册用户身份返回，前端可重试
    return { status: "ok", user };
  }
}

export async function fetchMe(): Promise<AuthUser | null> {
  try {
    const data = await getEnvelope("/v1/auth/me", MeSchema);
    if (data.anonymous || !data.user) return null;
    localStorage.setItem(USER_KEY, JSON.stringify(data.user));
    return data.user;
  } catch {
    return null;
  }
}

export function logout() {
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(REFRESH_KEY);
  localStorage.removeItem(USER_KEY);
}
