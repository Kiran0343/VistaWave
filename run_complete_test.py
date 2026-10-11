#!/usr/bin/env python3
"""
Complete end-to-end test: start app, submit application, watch for email.
"""
import time
import zipfile
import subprocess
import requests
from pathlib import Path

print("\n" + "="*70)
print("VISTAWAVE APPLICATION SUBMISSION & EMAIL TEST")
print("="*70 + "\n")

# Kill any existing app on port 5003
subprocess.run("lsof -ti :5003 | xargs -r kill -9", shell=True, stderr=subprocess.DEVNULL)
time.sleep(1)

# Start app in background
print("[1] Starting Flask app on port 5003...")
proc = subprocess.Popen(
    ["python", "app.py"],
    cwd="/Users/kiranreddy/Documents/vistawave",
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE,
    text=True
)
time.sleep(3)

# Verify app started
print("[2] Verifying app is running...")
try:
    r = requests.get("http://127.0.0.1:5003/health", timeout=5)
    print(f"    ✓ Server ready (HTTP {r.status_code})\n")
except Exception as e:
    print(f"    ✗ Server not responding: {e}")
    exit(1)

# Create test DOCX
print("[3] Creating test DOCX resume...")
resume_path = Path('/tmp/test_app_resume.docx')
with zipfile.ZipFile(resume_path, 'w') as z:
    z.writestr('[Content_Types].xml', '''<?xml version="1.0"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
</Types>''')
    z.writestr('_rels/.rels', '''<?xml version="1.0"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
</Relationships>''')
    z.writestr('word/document.xml', '''<?xml version="1.0"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:body><w:p><w:r><w:t>Professional Resume - Complete Test</w:t></w:r></w:p></w:body>
</w:document>''')
print(f"    ✓ Resume created\n")

# Submit application
print("[4] Submitting application to /api/v1/apply-detailed...")
with resume_path.open('rb') as f:
    response = requests.post(
        "http://127.0.0.1:5003/api/v1/apply-detailed",
        files={'resume': ('test_resume.docx', f, 'application/vnd.openxmlformats-officedocument.wordprocessingml.document')},
        data={
            'first_name': 'James',
            'last_name': 'TestUser',
            'phone_number': '+1-800-555-0123',
            'email': 'james.testuser@example.com',
            'position': 'Full Stack Developer',
            'id_passport_acknowledged': 'true',
        },
        timeout=30,
    )

print(f"    HTTP Status: {response.status_code}")
print(f"    Response Body: {response.json()}\n")

if response.status_code != 202:
    print("    ✗ Application not accepted!")
    exit(1)

print("    ✓ Application accepted\n")

# Wait for background email
print("[5] Waiting 10 seconds for background email thread...")
for i in range(10):
    print(f"    {'.'*i} {10-i} seconds remaining", end="\r", flush=True)
    time.sleep(1)
print()

# Check app logs for email status
print("[6] Checking app logs...")
stdout, stderr = proc.communicate(timeout=1) if proc.poll() is None else (proc.stdout.read(), proc.stderr.read())
if stderr:
    print("    App STDERR:")
    for line in stderr.split('\n')[-10:]:
        if line:
            print(f"      {line}")

print()
print("="*70)
print("Test Complete!")
print("="*70)
print("\n✓ Application was submitted successfully.")
print("✓ Recruiter email should have been queued for sending.")
print("\nCheck your email for: recruiter@vistawavepro.com inbox")
print("Email should be from: kiranlk1989@gmail.com")
print("Subject: Application for Full Stack Developer - James TestUser")
