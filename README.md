# vistawave Technology Staffing - Dual-Sided Platform

Modern, production-ready Flask application for a technology staffing firm with dual platforms for hiring companies and job seekers.

## Features

- ✨ Modern, responsive design with smooth animations
- 🔒 Security headers and best practices built-in
- 📊 Production-grade logging and error handling
- 🚀 WSGI-compatible for Gunicorn, uWSGI, and cloud platforms
- ⚙️ Environment-based configuration
- 📋 Health check endpoint for monitoring
- 🛡️ Security middleware with CSRF protection
- 📝 Comprehensive error pages
- ⚡ Realtime metrics streaming with Server-Sent Events (SSE)
- 🚦 API rate limiting and response caching for resilience
- ✅ Pydantic request validation for data quality
- 🗜️ Automatic HTTP compression for faster responses
- 👔 **Dual-sided platform**: Clients hire talent + Job seekers find opportunities
- 💼 Job board with filtering and smart matching
- 📝 Resume submission and candidate tracking

## Project Structure

```
vistawave/
├── app.py                  # Application factory
├── config.py              # Configuration management
├── wsgi.py                # WSGI entry point
├── gunicorn_config.py     # Gunicorn configuration
├── requirements.txt       # Python dependencies
├── Procfile               # Heroku/cloud deployment
├── .env.example           # Environment template
├── .gitignore             # Git ignore rules
├── templates/
│   ├── index.html         # Home page
│   ├── 404.html           # Not found page
│   ├── 400.html           # Bad request page
│   └── 500.html           # Server error page
├── static/
│   ├── styles.css         # CSS stylesheet
│   └── script.js          # JavaScript
└── logs/                  # Application logs (generated)
```

## Installation

### 1. Clone the Repository

```bash
git clone https://github.com/Kiran0343/VistaWave.git
cd VistaWave
```

### 2. Create Virtual Environment

```bash
python3 -m venv venv
source venv/bin/activate  # On macOS/Linux
# or
venv\Scripts\activate     # On Windows
```

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

### 4. Configure Environment

```bash
cp .env.example .env
# Edit .env and update SECRET_KEY and other variables
```

## Development

### Run Locally

```bash
FLASK_ENV=development python app.py
```

The application will be available at `http://localhost:5001`

### Debug Mode

Debug mode is enabled in development configuration. Changes to files will auto-reload.

## Production Deployment

### Using Gunicorn (Recommended)

```bash
pip install -r requirements.txt
gunicorn --config gunicorn_config.py wsgi:app
```

Or with custom workers:

```bash
gunicorn -w 4 -b 0.0.0.0:5000 wsgi:app
```

### Environment Variables

Set these in your production environment:

```bash
FLASK_ENV=production
SECRET_KEY=your-production-secret-key
API_BASE_URL=
CALENDAR_BOOKING_URL=
ALLOWED_CORS_ORIGINS=https://vistawavepro.com,https://www.vistawavepro.com
NOTIFICATION_TO_EMAILS=kiran@vistawave.com
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USERNAME=your-gmail-address@gmail.com
SMTP_PASSWORD=your-gmail-app-password
SMTP_FROM_EMAIL=your-gmail-address@gmail.com
SMTP_USE_TLS=true
SMTP_USE_SSL=false
RESUME_STORAGE_BACKEND=local
RESUME_UPLOAD_DIR=storage/resumes
RESUME_MAX_BYTES=5242880
AWS_ACCESS_KEY_ID=
AWS_SECRET_ACCESS_KEY=
S3_BUCKET_NAME=
S3_REGION=
S3_PUBLIC_BASE_URL=
CRISP_WEBSITE_ID=your_crisp_website_id
```

### Deployment Platforms

#### Heroku
```bash
heroku create your-app-name
git push heroku main
```

#### Docker

```dockerfile
FROM python:3.11-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .
EXPOSE 5000

CMD ["gunicorn", "--config", "gunicorn_config.py", "wsgi:app"]
```

Build and run:
```bash
docker build -t vistawave .
docker run -p 5000:5000 vistawave
```

#### AWS (Elastic Beanstalk)

```bash
eb init -p python-3.11 vistawave
eb create vistawave-env
eb deploy
```

#### DigitalOcean / Linode / VPS

1. SSH into server
2. Install Python 3.11, pip, virtualenv
3. Clone repo and follow Installation steps
4. Use Gunicorn with Supervisor or systemd for process management

**Example systemd service** (`/etc/systemd/system/vistawave.service`):

```ini
[Unit]
Description=VistWave Consulting Website
After=network.target

[Service]
User=www-data
WorkingDirectory=/home/user/vistawave
Environment="PATH=/home/user/vistawave/venv/bin"
Environment="FLASK_ENV=production"
Environment="SECRET_KEY=your-production-key"
ExecStart=/home/user/vistawave/venv/bin/gunicorn --config gunicorn_config.py wsgi:app

[Install]
WantedBy=multi-user.target
```

Start service:
```bash
sudo systemctl start vistawave
sudo systemctl enable vistawave
```

### Nginx Reverse Proxy

```nginx
server {
    listen 80;
    server_name yourdomain.com www.yourdomain.com;

    location / {
        proxy_pass http://127.0.0.1:5000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    location /static/ {
        alias /home/user/vistawave/static/;
        expires 1y;
    }
}
```

## Health Check

The application exposes a `/health` endpoint for monitoring:

```bash
curl http://localhost:5000/health
# Response: {"status":"healthy"}
```

## Advanced API Endpoints

The app now includes a comprehensive API layer for both companies and job seekers:

### For Hiring Companies

- `GET /api/v1/status` - service and stack status metadata
- `GET /api/v1/metrics` - cached staffing metrics payload (fill rate, time-to-fill, etc.)
- `GET /api/v1/talent-pool` - live technology talent availability snapshot
- `GET /api/v1/events` - realtime SSE stream for dashboard updates
- `POST /api/v1/staffing-request` - validated free IT assessment intake endpoint with email notification

Example staffing request:

```bash
curl -X POST http://localhost:5000/api/v1/staffing-request \
  -H "Content-Type: application/json" \
  -d '{
    "name":"Alex Rivera",
    "work_email":"alex@example.com",
    "company":"Northstar Labs",
    "area_of_interest":"Cloud modernization",
    "technologies_involved":"AWS, Terraform, Kubernetes",
    "engagement_type":"Project-Based Consulting",
    "team_size":"4 engineers",
    "desired_timeline":"2-4 weeks",
    "project_goals":"Build a modern platform foundation and improve delivery reliability."
  }'
```

### For Job Seekers

- `GET /api/v1/jobs` - browse all open job postings
- `GET /api/v1/jobs/<job_id>` - get specific job details
- `POST /api/v1/apply` - submit multipart job application with PDF resume storage and email notification

Example job application:

```bash
curl -X POST http://localhost:5000/api/v1/apply \
  -H "Accept: application/json" \
  -F "name=Jamie Chen" \
  -F "email=jamie@example.com" \
  -F "phone=+1 (555) 123-4567" \
  -F "position=Senior Python Backend Engineer" \
  -F "linkedin_url=https://linkedin.com/in/jamiechen" \
  -F "message=Experienced backend engineer interested in platform modernization work." \
  -F "resume=@/path/to/resume.pdf;type=application/pdf"
```

## Forms, Email, and Storage

### Contact / Free IT Assessment form

- Frontend submits JSON to `POST /api/v1/staffing-request`
- Backend validates the payload with Pydantic
- Backend sends an email notification to `kiran@vistawave.com` using SMTP

### Careers / Job Application form

- Frontend submits `multipart/form-data` to `POST /api/v1/apply`
- Backend validates applicant fields, enforces PDF-only resume uploads, and stores the file
- Backend emails applicant details plus the saved resume location

### Email delivery recommendation

- Gmail SMTP with an app password works for low-volume traffic and is already supported by the app
- For production reliability, prefer a transactional provider such as Postmark, Resend, SendGrid, or Amazon SES
- To switch providers later, keep the same SMTP environment variables and update only the provider credentials

### Resume storage recommendation

- `RESUME_STORAGE_BACKEND=local` stores PDFs under `storage/resumes`
- Local storage is acceptable for development only
- Render disks are ephemeral, so production should use `RESUME_STORAGE_BACKEND=s3`
- When S3 is enabled, configure `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `S3_BUCKET_NAME`, `S3_REGION`, and optionally `S3_PUBLIC_BASE_URL`

### Cross-origin setup

- Allowed origins are controlled by `ALLOWED_CORS_ORIGINS`
- The default value already allows `https://vistawavepro.com` and `https://www.vistawavepro.com`
- If your frontend calls the Render service directly, set `API_BASE_URL` to your Render backend origin

### Thank-you flow and calendar CTA

- Successful assessment submissions redirect to `/thank-you/assessment`
- Successful job applications redirect to `/thank-you/application`
- Set `CALENDAR_BOOKING_URL` to your Calendly, Microsoft Bookings, or other scheduling link to show a direct booking CTA on those pages
- If `CALENDAR_BOOKING_URL` is not set, the thank-you page falls back to an email CTA

## Security

- ✅ Security headers (X-Content-Type-Options, X-Frame-Options, etc.)
- ✅ HTTPS recommended for production (use SSL/TLS)
- ✅ Session cookies are HttpOnly and Secure in production
- ✅ CSRF protection with Flask defaults
- ✅ Proper error handling without exposing stack traces
- ✅ Request size limits (16MB max)

## Logging

Logs are stored in `logs/` directory with automatic rotation:
- **Application logs**: `logs/vistwave.log`
- **Access logs**: `logs/access.log` (when using Gunicorn)
- **Error logs**: `logs/error.log` (when using Gunicorn)

## Performance Optimization

- Static files cached for 1 year
- Gunicorn configured with 4 workers (adjust based on CPU cores)
- Connection pooling and keepalive enabled
- Gzip compression (enable in Nginx/reverse proxy)

## Monitoring & Maintenance

### Health Checks
Set up monitoring to check `/health` endpoint every 5 minutes

### Log Rotation
Logs automatically rotate at 10MB per file (keep 10 backups)

### Performance Metrics
Monitor these metrics:
- Response time
- Error rates
- CPU/Memory usage
- Log file size

## Updating Content

1. Edit template files in `templates/`
2. Update CSS in `static/styles.css`
3. Update JavaScript in `static/script.js`
4. Commit and push changes
5. Redeploy application

## Support

For issues or questions, contact: hello@vistwave.com

## License

© 2026 VistWave Consulting LLC. All rights reserved.
