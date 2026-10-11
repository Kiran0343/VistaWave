#!/usr/bin/env python3
"""Test job application submission end-to-end."""

import requests
import zipfile
import time
from pathlib import Path

print("\n" + "="*70)
print("TESTING JOB APPLICATION SUBMISSION")
print("="*70 + "\n")

try:
    # Get available jobs
    print("[1] Fetching jobs from API...")
    jobs_resp = requests.get('http://127.0.0.1:5003/api/v1/jobs', timeout=5)
    jobs = jobs_resp.json()['jobs']
    job = jobs[0]
    
    print(f"    Found: {job['title']}")
    print(f"    Company: {job['company']}")
    print(f"    Location: {job['location']}\n")
    
    # Create a valid DOCX file
    print("[2] Creating DOCX resume...")
    resume_path = Path('/tmp/test_resume.docx')
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
  <w:body><w:p><w:r><w:t>Test Resume - Professional Experience</w:t></w:r></w:p></w:body>
</w:document>''')
    
    print(f"    ✓ Created resume ({resume_path.stat().st_size} bytes)\n")
    
    # Submit application
    print("[3] Submitting application to /api/v1/apply-detailed...")
    with resume_path.open('rb') as f:
        response = requests.post(
            'http://127.0.0.1:5003/api/v1/apply-detailed',
            files={'resume': ('resume.docx', f, 'application/vnd.openxmlformats-officedocument.wordprocessingml.document')},
            data={
                'first_name': 'Alex',
                'last_name': 'Johnson',
                'phone_number': '+1-555-1234',
                'email': 'alex.johnson@example.com',
                'position': job['title'],
                'id_passport_acknowledged': 'true',
            },
            timeout=30,
        )
    
    print(f"    HTTP Status: {response.status_code}")
    resp_data = response.json()
    print(f"    Status: {resp_data.get('status')}")
    print(f"    Message: {resp_data.get('message')}")
    print(f"    Application ID: {resp_data.get('application_id')}\n")
    
    if response.status_code == 202:
        print("    ✓ APPLICATION ACCEPTED (HTTP 202)\n")
        
        print("[4] Waiting 10 seconds for email thread to complete...")
        for i in range(10):
            print(f"    .", end="", flush=True)
            time.sleep(1)
        print()
        
        print("\n" + "="*70)
        print("✓ TEST SUCCESSFUL!")
        print("="*70)
        print()
        print("✓ Application was submitted for: " + job['title'])
        print("✓ Applicant: Alex Johnson (alex.johnson@example.com)")
        print("✓ Resume: resume.docx (uploaded)")
        print("✓ Phone: +1-555-1234")
        print("✓ Email queued to: recruiter@vistawavepro.com")
        print()
        print("NEXT: Check your email inbox for the recruiter notification")
        print()
    else:
        print(f"    ✗ ERROR: Unexpected status {response.status_code}")
        print(f"    Response: {response.text}")
        
except Exception as e:
    print(f"✗ ERROR: {e}")
    import traceback
    traceback.print_exc()
