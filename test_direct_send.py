#!/usr/bin/env python3
"""Test SMTP email sending using app config."""

import sys
sys.path.insert(0, '/Users/kiranreddy/Documents/vistawave')

from app import create_app, send_notification_email

app = create_app()

print("Testing SMTP Configuration...")
print(f"SMTP_HOST: {app.config['SMTP_HOST']}")
print(f"SMTP_USERNAME: {app.config['SMTP_USERNAME']}")
print(f"SMTP_FROM_EMAIL: {app.config['SMTP_FROM_EMAIL']}")
print(f"NOTIFICATION_TO_EMAILS: {app.config['NOTIFICATION_TO_EMAILS']}")
print()

print("Sending test email...")
try:
    send_notification_email(
        app,
        subject='TEST: Direct Email from vistawave App',
        body='This is a test email to verify SMTP configuration.\n\nIf you received this, the email system is working correctly.',
        reply_to='test@example.com',
        attachments=None
    )
    print("✓ Email sent successfully!")
except Exception as e:
    print(f"✗ Error: {type(e).__name__}: {e}")
    import traceback
    traceback.print_exc()
