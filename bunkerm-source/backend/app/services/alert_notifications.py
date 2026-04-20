"""
Entrega de notificaciones externas para alertas del monitor.
Email via SMTP.
"""
from __future__ import annotations

import logging
import os
import smtplib
import socket
import threading
import time
from email.message import EmailMessage
from typing import Dict, List, Optional

from services.alert_delivery_outbox import enqueue_alert_delivery_event

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


def _smtp_host_candidates(primary_host: str) -> List[str]:
	candidates = [primary_host]
	if primary_host == "smtp.gmail.com":
		candidates.append("smtp.googlemail.com")
	return candidates


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

	max_retries = 3
	smtp_hosts = _smtp_host_candidates(smtp_host)
	for host_index, current_host in enumerate(smtp_hosts, start=1):
		for attempt in range(1, max_retries + 1):
			try:
				if smtp_ssl:
					with smtplib.SMTP_SSL(current_host, smtp_port, timeout=15) as smtp:
						if smtp_user and smtp_pass:
							smtp.login(smtp_user, smtp_pass)
						smtp.send_message(msg)
				else:
					with smtplib.SMTP(current_host, smtp_port, timeout=15) as smtp:
						if smtp_starttls:
							smtp.starttls()
						if smtp_user and smtp_pass:
							smtp.login(smtp_user, smtp_pass)
						smtp.send_message(msg)

				logger.info(
					"Alert email sent successfully to %d recipient(s) via %s (attempt %d)",
					len(recipients), current_host, attempt
				)
				return

			except (socket.gaierror, socket.timeout, smtplib.SMTPServerDisconnected) as e:
				# Transient network/DNS errors: retry same host, then fallback to the next candidate.
				if attempt < max_retries:
					wait_secs = 2 ** (attempt - 1)  # 1s, 2s, 4s backoff
					logger.warning(
						"Alert email send failed via %s (attempt %d/%d, transient error): %s. "
						"Retrying in %ds...",
						current_host, attempt, max_retries, type(e).__name__, wait_secs
					)
					time.sleep(wait_secs)
				elif host_index < len(smtp_hosts):
					logger.warning(
						"Alert email host %s failed after %d attempts due to %s. Trying fallback host...",
						current_host, max_retries, type(e).__name__
					)
					break
				else:
					logger.error(
						"Alert email failed after %d attempts (DNS/network issue): %s host=%s port=%s",
						max_retries, e, current_host, smtp_port
					)
					raise

			except smtplib.SMTPAuthenticationError as e:
				# Auth failure: don't retry.
				logger.error(
					"Alert email authentication failed (invalid credentials?): %s user=%s",
					e, smtp_user
				)
				raise

			except Exception as e:
				# Other errors: don't retry.
				logger.error("Alert email failed (permanent error): %s", e)
				raise

def _send_all(alert: Dict[str, object]) -> None:
	email_enabled = _as_bool(os.getenv("ALERT_NOTIFY_EMAIL_ENABLED"), default=True)

	if email_enabled:
		try:
			_send_email(alert)
		except socket.gaierror as dns_err:
			# DNS failure: log prominently
			logger.critical(
				"ALERT EMAIL FAILED: DNS resolution error. Container network/DNS may be broken. "
				"Alert will NOT reach email. Error: %s", dns_err
			)
		except smtplib.SMTPAuthenticationError as auth_err:
			# Auth failure: configuration issue
			logger.critical(
				"ALERT EMAIL FAILED: SMTP authentication error. Check SMTP credentials. "
				"Alert will NOT reach email. Error: %s", auth_err
			)
		except Exception as exc:
			logger.error("Alert email notification failed: %s", exc)
	else:
		logger.debug("Alert email notification disabled by config")


def notify_alert_raised(alert: Dict[str, object]) -> None:
	"""
	Envía notificaciones externas para una alerta recién activada.
	Nunca bloquea al motor de alertas.
	"""
	if not _as_bool(os.getenv("ALERT_NOTIFY_ENABLED"), default=False):
		return

	try:
		enqueue_alert_delivery_event(alert)
	except Exception as exc:
		logger.error("Alert delivery outbox enqueue failed: %s", exc)

	if not _as_bool(os.getenv("ALERT_NOTIFY_INLINE_DELIVERY_ENABLED"), default=True):
		return

	t = threading.Thread(target=_send_all, args=(dict(alert),), daemon=True)
	t.start()
