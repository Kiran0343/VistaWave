#!/usr/bin/env python3
"""
Comprehensive test: Start app, submit a job application, monitor logs for email send.
"""

import time
import zipfile
import threading
import requests
from pathlib import Path
from app import create_app

print("\n" + "=" * 70)
print("VISTAWAVE APPLICATION SUBMISSION TEST")
print("=" * 70 + "\n")

# Create app and prepare to redirect logs to display
port = 5006
app = create_app()

# Start app in background thread
def run_server():
    print("[SERVER] Starting Flask app on port", port)
    app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False)

server_thread = threading.Thread(target=run_server, daemon=False)
server_thread.start()

# Wait for app to start
print("[TEST] Waiting for server to start...")
for i in range(60):
    try:
        r = requests.get(f'http://127.0.0.1:{port}/health', timeout=1)
        if r.status_code == 200:
            print("[✓] Server is ready\n")
            break
    except Exception:
        time.sleep(0.2)
else:
    print("[✗] Server failed to start")
    exit(1)

# Create a test DOCX resume
print("[TEST] Creating test DOCX resume...")
resume_path = Path('/tmp/test_resume_submit.docx')
with zipfile.ZipFile(resume_path, 'w') as z:
    z.writestr('[Content_Types].xml', '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
</Types>''')
    z.writestr('_rels/.rels', '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
</Relationships>''')
    z.writestr('word/document.xml', '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>Professional Resume - Test Applicant</w:t></w:r></w:p></w:body></w:document>''')

print(f"[✓] Resume created: {resume_path}\n")

# Show configuration
print("[CONFIG] SMTP Settings:")
print(f"  Host: {app.config['SMTP_HOST']}")
print(f"  Port: {app.config['SMTP_PORT']}")
print(f"  Username: {app.config['SMTP_USERNAME']}")
print(f"  From: {app.config['SMTP_FROM_EMAIL']}")
print(f"  To: {app.config['NOTIFICATION_TO_EMAILS']}")
print()

# Submit the application
print("[TEST] Submitting application to /api/v1/apply-detailed...")
with resume_path.open('rb') as f:
    response = requests.post(
        f'http://127.0.0.1:{port}/api/v1/apply-detailed',
        files={'resume': ('test_resume.docx', f, 'application/vnd.openxmlformats-officedocument.wordprocessingml.document')},
        data={
            'first_name': 'John',
            'last_name': 'TestApplicant',
            'phone_number': '+1-555-123-4567',
            'email': 'john.test@example.com',
            'position': 'Technical Project Manager',
            'id_passport_acknowledged': 'true',
        },
        timeout=30,
    )

print(f"[RESPONSE] HTTP {response.status_code}")
print(f"[BODY] {response.json()}")
print()

# Wait for background email thread to complete
print("[TEST] Waiting 8 seconds for background email thread to complete...")
for i in range(8):
    print(f"  {8 - i}...", end=" ", flush=True)
    time.sleep(1)
print("\n")

print("=" * 70)
print("TEST COMPLETE")
print("=" * 70)
print("\nStatus: Check your email for the application submission!")
print("If no email received, check the app logs above for errors.\n")
