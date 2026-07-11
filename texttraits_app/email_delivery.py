from __future__ import annotations

import json
import logging
import os
import smtplib
import ssl
import urllib.error
import urllib.parse
import urllib.request
from email.message import EmailMessage
from runtime_config import env_int
from typing import Any

import certifi


class EmailDeliveryError(RuntimeError):
    pass


def provider_name() -> str:
    return os.getenv("TEXTTRAITS_EMAIL_PROVIDER", "").strip().lower()


def configured() -> bool:
    provider = provider_name()
    if provider == "smtp":
        return bool(os.getenv("TEXTTRAITS_SMTP_HOST") and from_email())
    if provider == "sendgrid":
        return bool(os.getenv("TEXTTRAITS_SENDGRID_API_KEY") and from_email())
    return provider == "console"


def from_email() -> str:
    return os.getenv("TEXTTRAITS_FROM_EMAIL", os.getenv("TEXTTRAITS_SMTP_FROM", "")).strip()


def status() -> dict[str, Any]:
    provider = provider_name() or "not_configured"
    return {
        "provider": provider,
        "configured": configured(),
        "from_email": from_email() if configured() else "",
    }


def send_account_email(to_email: str, subject: str, text_body: str, html_body: str | None = None) -> dict[str, Any]:
    provider = provider_name()
    if not configured():
        logging.info("Email delivery skipped; provider is not configured.")
        return {"sent": False, "provider": provider or "not_configured"}
    if provider == "console":
        logging.info("console_email to=%s subject=%s body_redacted=true", to_email, subject)
        return {"sent": True, "provider": provider}
    if provider == "smtp":
        send_smtp(to_email, subject, text_body, html_body)
        return {"sent": True, "provider": provider}
    if provider == "sendgrid":
        send_sendgrid(to_email, subject, text_body, html_body)
        return {"sent": True, "provider": provider}
    raise EmailDeliveryError(f"Unsupported email provider: {provider}")


def send_smtp(to_email: str, subject: str, text_body: str, html_body: str | None = None) -> None:
    host = os.getenv("TEXTTRAITS_SMTP_HOST", "").strip()
    port = env_int("TEXTTRAITS_SMTP_PORT", 587, minimum=1, maximum=65535)
    username = os.getenv("TEXTTRAITS_SMTP_USERNAME", "").strip()
    password = os.getenv("TEXTTRAITS_SMTP_PASSWORD", "")
    use_tls = os.getenv("TEXTTRAITS_SMTP_TLS", "true").strip().lower() in {"1", "true", "yes", "on"}
    if not host:
        raise EmailDeliveryError("TEXTTRAITS_SMTP_HOST is required for SMTP delivery.")

    message = EmailMessage()
    message["From"] = from_email()
    message["To"] = to_email
    message["Subject"] = subject
    message.set_content(text_body)
    if html_body:
        message.add_alternative(html_body, subtype="html")

    context = smtp_ssl_context()
    with smtplib.SMTP(host, port, timeout=20) as smtp:
        if use_tls:
            smtp.starttls(context=context)
        if username or password:
            smtp.login(username, password)
        smtp.send_message(message)


def smtp_ssl_context() -> ssl.SSLContext:
    return ssl.create_default_context(cafile=certifi.where())


def send_sendgrid(to_email: str, subject: str, text_body: str, html_body: str | None = None) -> None:
    api_key = os.getenv("TEXTTRAITS_SENDGRID_API_KEY", "")
    sendgrid_url = "https://api.sendgrid.com/v3/mail/send"
    parsed = urllib.parse.urlparse(sendgrid_url)
    if parsed.scheme != "https" or not parsed.netloc:
        raise EmailDeliveryError("SendGrid delivery requires an HTTPS API endpoint.")
    payload: dict[str, Any] = {
        "personalizations": [{"to": [{"email": to_email}]}],
        "from": {"email": from_email()},
        "subject": subject,
        "content": [{"type": "text/plain", "value": text_body}],
    }
    if html_body:
        payload["content"].append({"type": "text/html", "value": html_body})
    request = urllib.request.Request(
        sendgrid_url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:  # nosec B310
            if response.status >= 300:
                raise EmailDeliveryError(f"SendGrid returned status {response.status}.")
    except urllib.error.HTTPError as error:
        raise EmailDeliveryError(f"SendGrid rejected email with status {error.code}.") from error
