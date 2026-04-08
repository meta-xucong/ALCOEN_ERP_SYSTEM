"""Tests for email config fallback behavior."""

from __future__ import annotations

import smtplib

from app.models import SystemSetting
from app.services.email_service import EmailService


def test_send_email_falls_back_to_db_settings(app, monkeypatch):
    """When MAIL_* config is empty, EmailService should use DB system settings."""
    calls = {}

    class DummySMTP:
        def __init__(self, host, port, timeout=None):
            calls["host"] = host
            calls["port"] = port
            calls["timeout"] = timeout

        def login(self, username, password):
            calls["login"] = (username, password)

        def sendmail(self, sender, to_email, message):
            calls["sendmail"] = (sender, to_email)
            calls["message_len"] = len(message)

        def quit(self):
            calls["quit"] = True

    monkeypatch.setattr(smtplib, "SMTP_SSL", DummySMTP)

    with app.app_context():
        # Ensure app-level MAIL_* is empty and fallback is required.
        from flask import current_app
        current_app.config["MAIL_USERNAME"] = ""
        current_app.config["MAIL_PASSWORD"] = ""
        current_app.config["MAIL_DEFAULT_SENDER"] = ("ERP系统", "")

        SystemSetting.set_email_config(
            {
                "server": "smtp.exmail.qq.com",
                "port": 465,
                "use_ssl": True,
                "username": "office@alcochrom.com",
                "password": "db-secret-pass",
                "sender_name": "ALCOEN ERP系统",
            }
        )

        ok, err = EmailService.send_email(
            "receiver@example.com",
            "fallback test",
            "<p>ok</p>",
        )

    assert ok is True
    assert err is None
    assert calls["host"] == "smtp.exmail.qq.com"
    assert calls["port"] == 465
    assert calls["login"] == ("office@alcochrom.com", "db-secret-pass")
    assert calls["sendmail"] == ("office@alcochrom.com", "receiver@example.com")
    assert calls["quit"] is True


def test_send_email_reports_unconfigured_without_db_or_env(app):
    """If both env config and DB credentials are empty, report unconfigured."""
    with app.app_context():
        SystemSetting.set("mail_username", "")
        SystemSetting.set("mail_password", "")

        from flask import current_app
        current_app.config["MAIL_USERNAME"] = ""
        current_app.config["MAIL_PASSWORD"] = ""

        ok, err = EmailService.send_email("receiver@example.com", "x", "<p>x</p>")

    assert ok is False
    assert "未配置" in err
