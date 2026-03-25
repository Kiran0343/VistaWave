# VistWave Consulting LLC - Website

Modern, production-ready Flask application for the VistWave consulting website.

## Features

- ✨ Modern, responsive design with smooth animations
- 🔒 Security headers and best practices built-in
- 📊 Production-grade logging and error handling
- 🚀 WSGI-compatible for Gunicorn, uWSGI, and cloud platforms
- ⚙️ Environment-based configuration
- 📋 Health check endpoint for monitoring
- 🛡️ Security middleware with CSRF protection
- 📝 Comprehensive error pages

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
