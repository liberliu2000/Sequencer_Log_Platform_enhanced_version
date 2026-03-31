from __future__ import annotations

import logging
import smtplib
from email.message import EmailMessage

from app.core.settings import get_settings


logger = logging.getLogger(__name__)


class EmailDeliveryError(RuntimeError):
    pass


class EmailService:
    def __init__(self) -> None:
        self.settings = get_settings()

    def send_verification_code(self, *, recipient: str, username: str, code: str, expires_minutes: int) -> None:
        subject = "Sequencer Log Platform 邮箱验证码"
        body = (
            f"您好，{username}：\n\n"
            f"您的验证码是：{code}\n"
            f"有效期：{expires_minutes} 分钟。\n"
            "如果这不是您的操作，请忽略此邮件。\n"
        )
        self.send_mail(recipient=recipient, subject=subject, body=body)

    def send_mail(self, *, recipient: str, subject: str, body: str) -> None:
        if self.settings.mail_delivery_mode == "console":
            logger.info("console_email recipient=%s subject=%s body=%s", recipient, subject, body)
            return

        if not self.settings.smtp_host:
            raise EmailDeliveryError("SMTP_HOST 未配置，无法发送邮件。")

        message = EmailMessage()
        message["Subject"] = subject
        message["From"] = f"{self.settings.smtp_from_name} <{self.settings.smtp_from_email}>"
        message["To"] = recipient
        message.set_content(body)

        try:
            if self.settings.smtp_use_ssl:
                server = smtplib.SMTP_SSL(self.settings.smtp_host, self.settings.smtp_port, timeout=15)
            else:
                server = smtplib.SMTP(self.settings.smtp_host, self.settings.smtp_port, timeout=15)
            with server:
                if self.settings.smtp_use_tls and not self.settings.smtp_use_ssl:
                    server.starttls()
                if self.settings.smtp_username:
                    server.login(self.settings.smtp_username, self.settings.smtp_password)
                server.send_message(message)
        except Exception as exc:
            raise EmailDeliveryError(f"邮件发送失败: {exc}") from exc
