"""
SMTP connectivity health check.
Validates that DNS and SMTP connection work before sending alerts.
Used by the backend to detect issues early.
"""
import socket
import smtplib
import os
import logging

logger = logging.getLogger(__name__)

def check_smtp_connectivity() -> dict:
	"""
	Check if SMTP is reachable from inside the container.
	Returns: {
		'healthy': bool,
		'dns_ok': bool,
		'smtp_ok': bool,
		'errors': list of error messages
	}
	"""
	errors = []
	dns_ok = False
	smtp_ok = False
	
	smtp_host = os.getenv("ALERT_NOTIFY_SMTP_HOST", "")
	smtp_port = int(os.getenv("ALERT_NOTIFY_SMTP_PORT", "587"))
	
	if not smtp_host:
		return {'healthy': False, 'dns_ok': False, 'smtp_ok': False, 'errors': ["ALERT_NOTIFY_SMTP_HOST not configured"]}
	
	# Test 1: DNS resolution
	try:
		ip = socket.gethostbyname(smtp_host)
		dns_ok = True
		logger.info(f"SMTP health check: DNS OK ({smtp_host} -> {ip})")
	except socket.gaierror as e:
		errors.append(f"DNS resolution failed for {smtp_host}: {e}")
		logger.warning(f"SMTP health check: DNS FAILED - {e}")
		return {'healthy': False, 'dns_ok': False, 'smtp_ok': False, 'errors': errors}
	
	# Test 2: SMTP connection (without TLS, just TCP)
	try:
		sock = socket.create_connection((smtp_host, smtp_port), timeout=5)
		sock.close()
		smtp_ok = True
		logger.info(f"SMTP health check: TCP connection OK ({smtp_host}:{smtp_port})")
	except (socket.timeout, socket.error) as e:
		errors.append(f"SMTP connection failed to {smtp_host}:{smtp_port}: {e}")
		logger.warning(f"SMTP health check: Connection FAILED - {e}")
	
	return {
		'healthy': dns_ok and smtp_ok,
		'dns_ok': dns_ok,
		'smtp_ok': smtp_ok,
		'errors': errors
	}

def wait_for_smtp_ready(max_attempts: int = 30, retry_delay: int = 2) -> bool:
	"""
	Block startup until SMTP is reachable.
	Prevents silent alert notification failures on startup.
	Used during container initialization.
	"""
	for attempt in range(1, max_attempts + 1):
		result = check_smtp_connectivity()
		if result['healthy']:
			logger.info(f"SMTP connectivity OK on attempt {attempt}/{max_attempts}")
			return True
		
		if attempt == 1:
			logger.warning(f"SMTP not ready yet. Waiting up to {max_attempts * retry_delay}s...")
		
		if attempt < max_attempts:
			logger.debug(f"SMTP check attempt {attempt}/{max_attempts}: {result['errors']}")
			import time
			time.sleep(retry_delay)
		else:
			logger.error(f"SMTP connectivity check failed after {max_attempts} attempts: {result['errors']}")
			return False
	
	return False
