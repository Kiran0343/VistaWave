#!/usr/bin/env python3
"""Direct SMTP test to verify email sending."""

import smtplib
from email.message import EmailMessage
import os
from dotenv import load_dotenv

load_dotenv()

SMTP_HOST = os.getenv('SMTP_HOST')
SMTP_PORT = int(os.getenv('SMTP_PORT', '587'))
SMTP_USERNAME = os.getenv('SMTP_USERNAME')
SMTP_PASSWORD = os.getenv('SMTP_PASSWORD')
SMTP_FROM_EMAIL = os.getenv('SMTP_FROM_EMAIL')
NOTIFICATION_TO_EMAILS = [e.strip() for e in os.getenv('NOTIFICATION_TO_EMAILS', '').split(',') if e.strip()]

print("Testing SMTP connection...")
print(f"  Host: {SMTP_HOST}")
print(f"  Port: {SMTP_PORT}")
print(f"  Username: {SMTP_USERNAME}")
print(f"  From: {SMTP_FROM_EMAIL}")
print(f"  To: {NOTIFICATION_TO_EMAILS}")
print()

try:
    smtp = smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=20)
    print("✓ SMTP connection established")
    
    smtp.ehlo()
    print("✓ EHLO sent")
    
    smtp.starttls()
    print("✓ TLS started")
    
    smtp.login(SMTP_USERNAME, SMTP_PASSWORD)
    print("✓ Login successful")
    
    # Create test email
    msg = EmailMessage()
    msg['Subject'] = 'TEST: Application from Test Applicant'
    msg['From'] = SMTP_FROM_EMAIL
    msg['To'] = ', '.join(NOTIFICATION_TO_EMAILS)
    msg.set_content('This is a test email from the vistawave app verification.\n\nIf you received this, SMTP is working correctly.')
    
    # Send
    smtp.send_message(msg)
    print("✓ Email sent successfully!")
    
    smtp.quit()
    print("✓ SMTP connection closed")
    print()
    print("SUCCESS: Email was sent to recruiter@vistawavepro.com")
    
except Exception as e:
    print(f"✗ Error: {type(e).__name__}: {e}")
    import traceback
    traceback.print_exc()
