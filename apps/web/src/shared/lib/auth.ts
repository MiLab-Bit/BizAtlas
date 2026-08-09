import { z } from "zod";
import { getEnvelope } from "./api";

const AuthUserSchema = z.object({
  user_id: z.string(),
  email: z.string(),
  nickname: z.string().nullable().optional(),
  avatar_url: z.string().nullable().optional(),
  status: z.string(),
  role: z.string(),
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

export async function register(
  email: string,
  password: string,
  nickname?: string,
): Promise<AuthUser> {
  await getEnvelope("/v1/auth/register", z.object({ user: AuthUserSchema }), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password, nickname: nickname || undefined }),
  });
  // 注册成功后自动登录，复用同一套令牌存储
  return login(email, password);
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
