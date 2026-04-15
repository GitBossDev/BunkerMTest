"""
Entrega de notificaciones externas para alertas del monitor.

Soporta dos canales opcionales:
1) Email via SMTP


Todo se controla por variables de entorno para no acoplar secretos al código.
"""
from __future__ import annotations

import logging
import os
import smtplib
import threading
from email.message import EmailMessage
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


def _as_bool(value: Optional[str], default: bool = False) -> bool:
	if value is None:
		return default
	return value.strip().lower() in {"1", "true", "yes", "on"}


def _csv(value: Optional[str]) -> List[str]:
	if not value:
		return []
	return [item.strip() for item in value.split(",") if item.strip()]


def _build_subject(alert: Dict[str, object]) -> str:
	severity = str(alert.get("severity", "high")).upper()
	title = str(alert.get("title", "Broker Alert"))
	return f"[BunkerM][{severity}] {title}"


def _build_message(alert: Dict[str, object]) -> str:
	return (
		"BunkerM detected an active alert\n\n"
		f"Type: {alert.get('type', '')}\n"
		f"Severity: {alert.get('severity', '')}\n"
		f"Title: {alert.get('title', '')}\n"
		f"Description: {alert.get('description', '')}\n"
		f"Impact: {alert.get('impact', '')}\n"
		f"Timestamp: {alert.get('timestamp', '')}\n"
		f"Alert ID: {alert.get('id', '')}\n"
	)


def _send_email(alert: Dict[str, object]) -> None:
	recipients = _csv(os.getenv("ALERT_NOTIFY_EMAIL_TO"))
	if not recipients:
		logger.debug("Alert notification skipped: no recipients configured")
		return

	smtp_host = os.getenv("ALERT_NOTIFY_SMTP_HOST", "")
	if not smtp_host:
		logger.warning("Alert email enabled but ALERT_NOTIFY_SMTP_HOST is empty")
		return

	smtp_port = int(os.getenv("ALERT_NOTIFY_SMTP_PORT", "587"))
	smtp_user = os.getenv("ALERT_NOTIFY_SMTP_USERNAME")
	smtp_pass = os.getenv("ALERT_NOTIFY_SMTP_PASSWORD")
	smtp_starttls = _as_bool(os.getenv("ALERT_NOTIFY_SMTP_STARTTLS"), default=True)
	smtp_ssl = _as_bool(os.getenv("ALERT_NOTIFY_SMTP_SSL"), default=False)

	sender = os.getenv("ALERT_NOTIFY_EMAIL_FROM") or smtp_user or "bunkerm-alerts@localhost"

	msg = EmailMessage()
	msg["Subject"] = _build_subject(alert)
	msg["From"] = sender
	msg["To"] = ", ".join(recipients)
	msg.set_content(_build_message(alert))

	if smtp_ssl:
		with smtplib.SMTP_SSL(smtp_host, smtp_port, timeout=15) as smtp:
			if smtp_user and smtp_pass:
				smtp.login(smtp_user, smtp_pass)
			smtp.send_message(msg)
		logger.info("Alert email sent to %s recipient(s)", len(recipients))
		return

	with smtplib.SMTP(smtp_host, smtp_port, timeout=15) as smtp:
		if smtp_starttls:
			smtp.starttls()
		if smtp_user and smtp_pass:
			smtp.login(smtp_user, smtp_pass)
		smtp.send_message(msg)
	logger.info("Alert email sent to %s recipient(s)", len(recipients))

def _send_all(alert: Dict[str, object]) -> None:
	email_enabled = _as_bool(os.getenv("ALERT_NOTIFY_EMAIL_ENABLED"), default=True)

	if email_enabled:
		try:
			_send_email(alert)
		except Exception as exc:
			logger.error("Failed to send alert email notification: %s", exc)
	else:
		logger.debug("Alert email notification disabled by config")


def notify_alert_raised(alert: Dict[str, object]) -> None:
	"""
	Envía notificaciones externas para una alerta recién activada.
	Nunca bloquea al motor de alertas.
	"""
	if not _as_bool(os.getenv("ALERT_NOTIFY_ENABLED"), default=False):
		return

	t = threading.Thread(target=_send_all, args=(dict(alert),), daemon=True)
	t.start()
