"""SMTP 发信（邮箱验证 / 密码找回）。零外部依赖，sender 可注入便于测试。

- EmailSender：真实 SMTP 发送（465 SSL 默认；587 设 smtp_use_ssl=false 走 STARTTLS）。
- ConsoleEmailSender：捕获到内存，供测试与开发态（smtp_enabled=false）使用，不发真实邮件。
- default_sender()：按配置返回真实 sender 或 None（未启用/未配置时不发信，仅生成 token）。

说明：smtplib 走原生 socket，不经过 HTTP(S) 代理（与 LLM 直连不同，无需绕过 Clash）。
"""

from __future__ import annotations

import smtplib
import ssl
from email.message import EmailMessage
from typing import Optional

from bizatlas.config import get_settings

VERIFY_EMAIL_SUBJECT = "请验证您的邮箱 - BizAtlas"
RESET_PASSWORD_SUBJECT = "重置您的密码 - BizAtlas"


class EmailSender:
    """真实 SMTP 发信（smtplib 直连，不经过 HTTP 代理）。"""

    def __init__(
        self,
        host: str,
        port: int,
        username: str,
        password: str,
        frm: str,
        use_ssl: bool = True,
        timeout: int = 15,
    ) -> None:
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.frm = frm
        self.use_ssl = use_ssl
        self.timeout = timeout

    def send(self, to: str, subject: str, html: str) -> None:
        msg = EmailMessage()
        msg["Subject"] = subject
        msg["From"] = self.frm
        msg["To"] = to
        msg.set_content("请使用支持 HTML 的邮件客户端查看此邮件。")
        msg.add_alternative(html, subtype="html")
        if self.use_ssl:
            with smtplib.SMTP_SSL(
                self.host, self.port, timeout=self.timeout,
                context=ssl.create_default_context(),
            ) as smtp:
                smtp.login(self.username, self.password)
                smtp.send_message(msg)
        else:
            with smtplib.SMTP(self.host, self.port, timeout=self.timeout) as smtp:
                smtp.starttls(context=ssl.create_default_context())
                smtp.login(self.username, self.password)
                smtp.send_message(msg)


class ConsoleEmailSender:
    """捕获发信到内存（测试 / 开发态无 SMTP 时使用），不触网。"""

    def __init__(self) -> None:
        self.sent: list[dict] = []

    def send(self, to: str, subject: str, html: str) -> None:
        self.sent.append({"to": to, "subject": subject, "html": html})

    def last_token(self) -> Optional[str]:
        """从最近一封邮件 HTML 中提取 ?token= 参数（测试用）。"""
        import re

        if not self.sent:
            return None
        m = re.search(r"token=([A-Za-z0-9_\-]+)", self.sent[-1]["html"])
        return m.group(1) if m else None

    def clear(self) -> None:
        self.sent.clear()


def default_sender() -> Optional[EmailSender]:
    """按配置构造真实 sender；未启用或配置不全返回 None（端点仅生成 token 不发信）。"""
    s = get_settings()
    if not (s.smtp_enabled and s.smtp_host and s.smtp_username and s.smtp_password):
        return None
    return EmailSender(
        host=s.smtp_host,
        port=s.smtp_port,
        username=s.smtp_username,
        password=s.smtp_password,
        frm=s.smtp_from or s.smtp_username,
        use_ssl=s.smtp_use_ssl,
    )


def verification_link(token: str, base_url: str) -> str:
    return f"{base_url.rstrip('/')}/verify-email?token={token}"


def reset_link(token: str, base_url: str) -> str:
    return f"{base_url.rstrip('/')}/reset-password?token={token}"


def build_verification_email(link: str) -> tuple[str, str]:
    subject = VERIFY_EMAIL_SUBJECT
    html = (
        "<html><body>"
        "<p>您好，</p>"
        "<p>欢迎注册 BizAtlas。请点击下面的按钮验证您的邮箱地址（链接 1 小时内有效）：</p>"
        f'<p><a href="{link}">验证邮箱</a></p>'
        f"<p>或复制链接到浏览器：<br/>{link}</p>"
        "<p>若非本人操作，请忽略此邮件。</p>"
        "</body></html>"
    )
    return subject, html


def build_password_reset_email(link: str) -> tuple[str, str]:
    subject = RESET_PASSWORD_SUBJECT
    html = (
        "<html><body>"
        "<p>您好，</p>"
        "<p>我们收到了您的密码重置请求。请点击下面的链接设置新密码（链接 1 小时内有效）：</p>"
        f'<p><a href="{link}">重置密码</a></p>'
        f"<p>或复制链接到浏览器：<br/>{link}</p>"
        "<p>若非本人操作，请忽略此邮件，账号安全不受影响。</p>"
        "</body></html>"
    )
    return subject, html
