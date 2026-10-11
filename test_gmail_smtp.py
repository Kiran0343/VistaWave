#!/usr/bin/env python3
"""
Direct Gmail SMTP test to verify credentials and email delivery.
"""

import smtplib
import os
from email.message import EmailMessage
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

SMTP_HOST = os.getenv('SMTP_HOST', 'smtp.gmail.com')
SMTP_PORT = int(os.getenv('SMTP_PORT', '587'))
SMTP_USERNAME = os.getenv('SMTP_USERNAME')
SMTP_PASSWORD = os.getenv('SMTP_PASSWORD')
SMTP_FROM_EMAIL = os.getenv('SMTP_FROM_EMAIL')
NOTIFICATION_TO_EMAILS = [e.strip() for e in os.getenv('NOTIFICATION_TO_EMAILS', '').split(',') if e.strip()]

print("\n" + "=" * 70)
print("GMAIL SMTP DIRECT TEST")
print("=" * 70 + "\n")

print("[CONFIG]")
print(f"  SMTP Host: {SMTP_HOST}")
print(f"  SMTP Port: {SMTP_PORT}")
print(f"  Username: {SMTP_USERNAME}")
print(f"  From Email: {SMTP_FROM_EMAIL}")
print(f"  Recipients: {NOTIFICATION_TO_EMAILS}")
print()

# Validate configuration
if not SMTP_USERNAME or not SMTP_PASSWORD:
    print("[✗] SMTP credentials not configured in .env")
    exit(1)

if not NOTIFICATION_TO_EMAILS:
    print("[✗] NOTIFICATION_TO_EMAILS not configured in .env")
    exit(1)

print("[TEST] Testing SMTP connection...\n")

try:
    # Connect to SMTP server
    print("[1] Connecting to SMTP server...")
    smtp = smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=20)
    print("    ✓ Connection established\n")
    
    # Send EHLO
    print("[2] Sending EHLO...")
    smtp.ehlo()
    print("    ✓ EHLO successful\n")
    
    # Start TLS
    print("[3] Starting TLS...")
    smtp.starttls()
    print("    ✓ TLS started\n")
    
    # Login
    print("[4] Authenticating...")
    smtp.login(SMTP_USERNAME, SMTP_PASSWORD)
    print("    ✓ Authentication successful\n")
    
    # Create and send email
    print("[5] Creating email message...")
    msg = EmailMessage()
    msg['Subject'] = 'TEST: Job Application from vistawave App'
    msg['From'] = SMTP_FROM_EMAIL
    msg['To'] = ', '.join(NOTIFICATION_TO_EMAILS)
    msg['Reply-To'] = 'test.applicant@example.com'
    
    body = """New Detailed Job Application

Submitted At: 2026-10-11T10:30:00Z
First Name: Test
Last Name: Applicant
Phone Number: +1-555-123-4567
Email: test.applicant@example.com
Position Applying For: Technical Project Manager

This is a test email to verify SMTP configuration is working correctly.
If you receive this email, the vistawave application submission flow is functional."""
    
    msg.set_content(body)
    print("    ✓ Email message created\n")
    
    # Send email
    print("[6] Sending email...")
    smtp.send_message(msg)
    print("    ✓ Email sent successfully!\n")
    
    # Close connection
    print("[7] Closing SMTP connection...")
    smtp.quit()
    print("    ✓ Connection closed\n")
    
    print("=" * 70)
    print("✓ SUCCESS: Gmail SMTP is working correctly!")
    print("=" * 70)
    print(f"\nEmail was sent to: {', '.join(NOTIFICATION_TO_EMAILS)}")
    print("Check the recruiter inbox for the test email.\n")
    
except smtplib.SMTPAuthenticationError as e:
    print(f"\n[✗] AUTHENTICATION FAILED")
    print(f"    Error: {e}")
    print(f"\n    Check your Gmail App Password in .env file.")
    print(f"    Make sure 2FA is enabled on Gmail account.")
    exit(1)
    
except smtplib.SMTPException as e:
    print(f"\n[✗] SMTP ERROR: {type(e).__name__}")
    print(f"    {e}")
    exit(1)
    
except Exception as e:
    print(f"\n[✗] UNEXPECTED ERROR: {type(e).__name__}")
    print(f"    {e}")
    import traceback
    traceback.print_exc()
    exit(1)
