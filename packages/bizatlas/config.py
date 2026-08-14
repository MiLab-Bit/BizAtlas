from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    bizatlas_mode: str = "snapshot"
    bizatlas_db_path: str = str(ROOT / "data" / "bizatlas.sqlite")
    bizatlas_db_dsn: str = ""  # 留空用本地 SQLite；部署时填 postgresql://... 启用 PG 后端（需单独迁移脚本）
    bizatlas_upload_dir: str = str(ROOT / "uploads")
    bizatlas_export_dir: str = str(ROOT / "exports")
    bizatlas_providers_registry: str = str(ROOT / "content" / "providers" / "registry.yaml")
    bizatlas_rules_dir: str = str(ROOT / "content" / "rules")

    tushare_token: str = ""
    tianyancha_token: str = ""
    qichacha_token: str = ""  # 企查查开放平台 appkey
    qichacha_secret: str = ""  # 企查查开放平台 appsecret（签名用，与 appkey 成对）
    company_json_dir: str = str(ROOT / "content" / "fixtures" / "company_json")

    llm_provider: str = "openai_compatible"
    llm_api_base: str = ""
    llm_api_key: str = ""
    llm_model: str = "gpt-4o-mini"

    # 视觉解析分支（阶段 1）：默认关闭。开启后 PDF 解析会先做扫描件/印章/复杂表格
    # 检测；若检测到非纯文本版面且配置了 vision_backend，则走视觉抽取（带 bbox 坐标）。
    # 关闭或后端未配置时自动降级到纯文本解析，不影响现有逻辑。
    vision_enabled: bool = False
    vision_backend: str = ""  # vlm | ocr | ""（空=纯文本降级）
    vision_api_base: str = ""
    vision_api_key: str = ""
    vision_model: str = ""

    api_host: str = "127.0.0.1"
    api_port: int = 8000
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    # —— 阶段 3：企业化部署鉴权 ——
    # bizatlas_auth_disabled 默认 True：保持旧演示/前端无感（等价 ADMIN 放行）。
    # 生产部署：设 bizatlas_auth_disabled=false 并提供 bizatlas_auth_secret，
    # 端点即启用 RBAC。
    bizatlas_auth_disabled: bool = True
    bizatlas_auth_secret: str = ""

    # 一次性首管理员引导令牌：设非空时，/v1/admin/bootstrap 在系统无 admin 时可用。
    # 留空则该端点永久 401（禁用引导）。建议部署时生成一个强随机值。
    bizatlas_bootstrap_token: str = ""

    # —— 邮箱用户系统（身份基础设施）：令牌时效（秒）——
    # 访问令牌短时效（默认 15 分钟），刷新令牌长时效（默认 7 天）。
    bizatlas_token_access_ttl: int = 900
    bizatlas_token_refresh_ttl: int = 604800

    # —— 邮箱发信（SMTP）与邮箱验证/密码找回 ——
    # 复用 FastToken 的 QQ 邮箱授权码发信；smtp_enabled=false 时发信模块返回 None
    # （端点不发送，仅生成 token，便于离线/测试）。
    smtp_host: str = ""
    smtp_port: int = 465
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_from: str = ""
    smtp_use_ssl: bool = True  # 465→SSL；587→STARTTLS（设为 false）
    smtp_enabled: bool = False

    # 邮箱验证：开启后注册即置 email_verified=0 并发验证邮件，未验证账号登录被拦截。
    # 默认关闭以保持旧演示/测试无感（注册即视为已验证）。
    email_verification_enabled: bool = False
    email_base_url: str = "http://localhost:5173"  # 验证/重置链接的前端 base
    email_token_ttl: int = 3600  # 验证/重置 token 有效期（秒）

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def root(self) -> Path:
        return ROOT


@lru_cache
def get_settings() -> Settings:
    return Settings()
