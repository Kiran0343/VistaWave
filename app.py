import os
import json
import logging
import smtplib
import time
import threading
import secrets
import calendar
import sqlite3
from pathlib import Path
from uuid import uuid4
from datetime import datetime, timedelta, timezone
from collections import deque
from logging.handlers import RotatingFileHandler
from email.message import EmailMessage
from urllib.parse import urlparse
from functools import wraps
from flask import Flask, render_template, jsonify, request, Response, redirect, url_for, g, session, flash
from flask_caching import Cache
from flask_compress import Compress
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from pydantic import BaseModel, EmailStr, Field, ValidationError, HttpUrl
from werkzeug.exceptions import HTTPException
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
from dotenv import load_dotenv

load_dotenv()

from config import config
from blog_posts import BLOG_POSTS


limiter = Limiter(key_func=get_remote_address, storage_uri='memory://')
cache = Cache()
compress = Compress()


def normalize_email(value):
    return (value or '').strip().lower()


def generate_passcode(length=6):
    return ''.join(secrets.choice('0123456789') for _ in range(length))


def coerce_hours_value(value):
    """Convert a timesheet input to a safe float between 0 and 24."""
    try:
        hours = float(value)
    except (TypeError, ValueError):
        return 0.0
    return round(max(0.0, min(hours, 24.0)), 2)


def auth_required(view_func):
    @wraps(view_func)
    def wrapper(*args, **kwargs):
        if not session.get('user_email'):
            flash('Please sign in to continue.', 'error')
            return redirect(url_for('auth_page', mode='login'))
        return view_func(*args, **kwargs)
    return wrapper


def get_user_records(app):
    with sqlite3.connect(app.config['SQLITE_DB_PATH']) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT id, name, email, password_hash, verified, verification_code,
                   verification_expires_at, reset_code, reset_expires_at,
                   title, department, phone, created_at
            FROM users
            """
        ).fetchall()
        records = {}
        for row in rows:
            records[row['email']] = {
                'id': row['id'],
                'name': row['name'],
                'email': row['email'],
                'password_hash': row['password_hash'],
                'verified': bool(row['verified']),
                'verification_code': row['verification_code'],
                'verification_expires_at': row['verification_expires_at'],
                'reset_code': row['reset_code'],
                'reset_expires_at': row['reset_expires_at'],
                'title': row['title'] or '',
                'department': row['department'] or '',
                'phone': row['phone'] or '',
                'created_at': row['created_at'],
            }
        return records


def get_timesheet_records(app):
    with sqlite3.connect(app.config['SQLITE_DB_PATH']) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT user_email, year, month, day, hours, submitted_at
            FROM timesheets
            """
        ).fetchall()
        records = {}
        for row in rows:
            email_records = records.setdefault(row['user_email'], {})
            year_records = email_records.setdefault(str(row['year']), {})
            month_records = year_records.setdefault(str(row['month']).zfill(2), {})
            month_records[str(row['day'])] = {
                'hours': float(row['hours']),
                'submitted_at': row['submitted_at'],
            }
        return records


def get_user_by_email(app, email):
    normalized_email = normalize_email(email)
    with sqlite3.connect(app.config['SQLITE_DB_PATH']) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            """
            SELECT id, name, email, password_hash, verified, verification_code,
                   verification_expires_at, reset_code, reset_expires_at,
                   title, department, phone, created_at
            FROM users
            WHERE email = ?
            """,
            (normalized_email,),
        ).fetchone()
        if not row:
            return None
        return {
            'id': row['id'],
            'name': row['name'],
            'email': row['email'],
            'password_hash': row['password_hash'],
            'verified': bool(row['verified']),
            'verification_code': row['verification_code'],
            'verification_expires_at': row['verification_expires_at'],
            'reset_code': row['reset_code'],
            'reset_expires_at': row['reset_expires_at'],
            'title': row['title'] or '',
            'department': row['department'] or '',
            'phone': row['phone'] or '',
            'created_at': row['created_at'],
        }


def get_sqlite_connection(app):
    conn = sqlite3.connect(app.config['SQLITE_DB_PATH'])
    conn.row_factory = sqlite3.Row
    return conn


def init_sqlite_db(app):
    create_directory_if_missing(str(Path(app.config['SQLITE_DB_PATH']).parent))
    with get_sqlite_connection(app) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                email TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                verified INTEGER NOT NULL DEFAULT 0,
                verification_code TEXT,
                verification_expires_at TEXT,
                reset_code TEXT,
                reset_expires_at TEXT,
                title TEXT,
                department TEXT,
                phone TEXT,
                created_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS timesheets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_email TEXT NOT NULL,
                year INTEGER NOT NULL,
                month INTEGER NOT NULL,
                day INTEGER NOT NULL,
                hours REAL NOT NULL,
                submitted_at TEXT NOT NULL,
                UNIQUE(user_email, year, month, day)
            )
            """
        )


def save_timesheet_day(app, user_email, year, month, day, hours, submitted_at):
    with get_sqlite_connection(app) as conn:
        conn.execute(
            """
            INSERT INTO timesheets (user_email, year, month, day, hours, submitted_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(user_email, year, month, day)
            DO UPDATE SET
                hours = excluded.hours,
                submitted_at = excluded.submitted_at
            """,
            (user_email, int(year), int(month), int(day), float(hours), submitted_at),
        )


def update_user_profile_record(app, email, name, title, department, phone):
    with get_sqlite_connection(app) as conn:
        conn.execute(
            """
            UPDATE users
            SET name = ?, title = ?, department = ?, phone = ?
            WHERE email = ?
            """,
            (name, title, department, phone, email),
        )


def get_monthly_timesheet_records(app, user_email, year, month):
    """Return stored timesheet rows for a given month."""
    with get_sqlite_connection(app) as conn:
        rows = conn.execute(
            """
            SELECT day, hours, submitted_at
            FROM timesheets
            WHERE user_email = ? AND year = ? AND month = ?
            ORDER BY day ASC
            """,
            (user_email, int(year), int(month)),
        ).fetchall()

    month_records = {}
    for row in rows:
        month_records[str(row['day'])] = {
            'hours': float(row['hours']),
            'submitted_at': row['submitted_at'],
        }
    return month_records


def get_timesheet_history(app, user_email, limit=18):
    with get_sqlite_connection(app) as conn:
        rows = conn.execute(
            """
            SELECT year, month, SUM(hours) AS total_hours, MAX(submitted_at) AS last_submitted_at
            FROM timesheets
            WHERE user_email = ?
            GROUP BY year, month
            ORDER BY year DESC, month DESC
            LIMIT ?
            """,
            (user_email, int(limit)),
        ).fetchall()

    history = []
    for row in rows:
        history.append(
            {
                'year': int(row['year']),
                'month': int(row['month']),
                'month_name': calendar.month_name[int(row['month'])],
                'total_hours': round(float(row['total_hours'] or 0.0), 2),
                'last_submitted_at': row['last_submitted_at'],
            }
        )
    return history


def store_user_verification_email(app, email, name, passcode):
    subject = 'Verify your vistawave account'
    body = (
        f"Hi {name},\n\n"
        f"Your account verification code is: {passcode}\n\n"
        "Enter this code on the verification page to activate your account.\n\n"
        "Regards,\n"
        "vistawave"
    )
    try:
        send_notification_email_async(
            app,
            subject=subject,
            body=body,
            reply_to=email,
        )
    except Exception:
        app.logger.warning('Verification email not sent for %s: %s', email, passcode)


def store_user_reset_email(app, email, passcode):
    subject = 'Your vistawave password reset code'
    body = (
        f"A password reset was requested for {email}.\n\n"
        f"Your one-time password is: {passcode}\n\n"
        "Use this code to set a new password and sign in again.\n\n"
        "Regards,\n"
        "vistawave"
    )
    try:
        send_notification_email_async(
            app,
            subject=subject,
            body=body,
            reply_to=email,
        )
    except Exception:
        app.logger.warning('Reset email not sent for %s: %s', email, passcode)


class StaffingInquiry(BaseModel):
    """Validated staffing request from hiring companies."""

    name: str = Field(min_length=2, max_length=120)
    work_email: EmailStr
    company: str = Field(min_length=2, max_length=120)
    area_of_interest: str = Field(min_length=2, max_length=160)
    technologies_involved: str = Field(min_length=2, max_length=1000)
    engagement_type: str = Field(min_length=2, max_length=80)
    team_size: str = Field(min_length=1, max_length=80)
    desired_timeline: str = Field(min_length=2, max_length=120)
    project_goals: str = Field(min_length=10, max_length=3000)


class JobApplication(BaseModel):
    """Validated job application from job seekers."""

    name: str = Field(min_length=2, max_length=120)
    email: EmailStr
    phone: str = Field(min_length=10, max_length=20)
    position: str = Field(min_length=2, max_length=160)
    linkedin_url: HttpUrl
    message: str = Field(min_length=10, max_length=2000)


class DetailedJobApplication(BaseModel):
    """Validated detailed application for recruiter follow-up."""

    first_name: str = Field(min_length=2, max_length=80)
    last_name: str = Field(min_length=2, max_length=80)
    phone_number: str = Field(min_length=10, max_length=20)
    email: EmailStr
    position: str = Field(min_length=2, max_length=160)
    linkedin_profile_url: HttpUrl
    id_passport_acknowledged: bool = Field(default=False)


def create_directory_if_missing(path_value):
    Path(path_value).mkdir(parents=True, exist_ok=True)


def get_request_origin():
    return request.headers.get('Origin', '').rstrip('/')


def get_allowed_origin(app):
    origin = get_request_origin()
    if origin and origin in app.config['ALLOWED_CORS_ORIGINS']:
        return origin
    return None


def add_cors_headers(response, app):
    origin = get_allowed_origin(app)
    if origin:
        response.headers['Access-Control-Allow-Origin'] = origin
        response.headers['Vary'] = 'Origin'
        response.headers['Access-Control-Allow-Methods'] = 'GET, POST, OPTIONS'
        response.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization'
    return response


def build_resume_filename(applicant_name, original_filename, role_name=''):
    safe_name = secure_filename(applicant_name) or 'applicant'
    safe_role = secure_filename(role_name) if role_name else ''
    extension = Path(original_filename).suffix.lower() or '.pdf'
    if safe_role:
        return f'{safe_name}-{safe_role}{extension}'
    return f'{safe_name}{extension}'


def validate_resume_upload(uploaded_file):
    if uploaded_file is None or not uploaded_file.filename:
        raise ValueError('DOCX file is required')

    extension = Path(uploaded_file.filename).suffix.lower()
    if extension != '.docx':
        raise ValueError('Only DOCX files are allowed')

    content_type = (uploaded_file.mimetype or '').lower()
    allowed_types = {
        'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
        'application/docx',
        'application/octet-stream'
    }
    if content_type and content_type not in allowed_types:
        raise ValueError('Only DOCX files are allowed')


def upload_resume_to_s3(app, storage_key, file_bytes, content_type):
    import importlib

    boto3 = importlib.import_module('boto3')

    client = boto3.client(
        's3',
        region_name=app.config['S3_REGION'],
        aws_access_key_id=app.config['AWS_ACCESS_KEY_ID'],
        aws_secret_access_key=app.config['AWS_SECRET_ACCESS_KEY']
    )
    extra_args = {
        'ContentType': content_type,
    }
    if app.config.get('S3_SERVER_SIDE_ENCRYPTION'):
        extra_args['ServerSideEncryption'] = app.config['S3_SERVER_SIDE_ENCRYPTION']

    client.put_object(
        Bucket=app.config['S3_BUCKET_NAME'],
        Key=storage_key,
        Body=file_bytes,
        **extra_args
    )

    public_base_url = app.config.get('S3_PUBLIC_BASE_URL', '').rstrip('/')
    if public_base_url:
        return f'{public_base_url}/{storage_key}'

    return f's3://{app.config["S3_BUCKET_NAME"]}/{storage_key}'


def store_resume(app, uploaded_file, applicant_name, role_name=''):
    validate_resume_upload(uploaded_file)

    file_bytes = uploaded_file.read()
    if len(file_bytes) > app.config['RESUME_MAX_BYTES']:
        raise ValueError('Resume exceeds the maximum allowed size')

    uploaded_file.stream.seek(0)
    filename = build_resume_filename(applicant_name, uploaded_file.filename, role_name)
    storage_key = f'resumes/{filename}'
    content_type = uploaded_file.mimetype or 'application/pdf'

    if app.config['RESUME_STORAGE_BACKEND'] == 's3':
        location = upload_resume_to_s3(app, storage_key, file_bytes, content_type)
        return {
            'filename': filename,
            'storage_backend': 's3',
            'storage_key': storage_key,
            'location': location,
            'content_type': content_type,
            'size_bytes': len(file_bytes)
        }

    create_directory_if_missing(app.config['RESUME_UPLOAD_DIR'])
    destination = Path(app.config['RESUME_UPLOAD_DIR']) / filename
    destination.write_bytes(file_bytes)
    return {
        'filename': filename,
        'storage_backend': 'local',
        'storage_key': str(destination),
        'location': str(destination),
        'content_type': content_type,
        'size_bytes': len(file_bytes)
    }


def get_attachment_bytes(file_storage):
    if file_storage is None:
        return None
    try:
        file_storage.stream.seek(0)
        return file_storage.read()
    except Exception:
        return None


def format_email_body(title, rows):
    lines = [title, '']
    for label, value in rows:
        lines.append(f'{label}: {value}')
    return '\n'.join(lines)


def send_notification_email(app, subject, body, reply_to=None, attachments=None):
    recipients = app.config['NOTIFICATION_TO_EMAILS']
    if not recipients:
        raise RuntimeError('Notification recipient email is not configured')

    message = EmailMessage()
    message['Subject'] = subject
    message['From'] = app.config['SMTP_FROM_EMAIL']
    message['To'] = ', '.join(recipients)
    if reply_to:
        message['Reply-To'] = reply_to
    message.set_content(body)

    if attachments:
        for filename, payload, mime_type in attachments:
            if payload is None:
                continue
            message.add_attachment(
                payload,
                maintype=mime_type.split('/')[0] if '/' in mime_type else 'application',
                subtype=mime_type.split('/')[-1] if '/' in mime_type else 'octet-stream',
                filename=filename
            )

    if app.config['SMTP_USE_SSL']:
        smtp_client = smtplib.SMTP_SSL(
            app.config['SMTP_HOST'],
            app.config['SMTP_PORT'],
            timeout=app.config['SMTP_TIMEOUT_SECONDS']
        )
    else:
        smtp_client = smtplib.SMTP(
            app.config['SMTP_HOST'],
            app.config['SMTP_PORT'],
            timeout=app.config['SMTP_TIMEOUT_SECONDS']
        )

    with smtp_client as server:
        server.ehlo()
        if app.config['SMTP_USE_TLS'] and not app.config['SMTP_USE_SSL']:
            server.starttls()
            server.ehlo()
        if app.config['SMTP_USERNAME']:
            server.login(app.config['SMTP_USERNAME'], app.config['SMTP_PASSWORD'])
        server.send_message(message)


def send_notification_email_async(app, subject, body, reply_to=None, attachments=None):
    def worker():
        try:
            send_notification_email(app, subject, body, reply_to=reply_to, attachments=attachments)
            app.logger.info('Background recruiter email sent successfully: %s', subject)
        except Exception as exc:
            app.logger.exception('Background recruiter email failed: %s', exc)

    thread = threading.Thread(target=worker, daemon=True)
    thread.start()
    return thread


def parse_job_application_form(form_data):
    payload = {
        'name': str(form_data.get('name') or '').strip(),
        'email': str(form_data.get('email') or '').strip(),
        'phone': str(form_data.get('phone') or '').strip(),
        'position': str(form_data.get('position') or '').strip(),
        'linkedin_url': str(form_data.get('linkedin_url') or '').strip(),
        'message': str(form_data.get('message') or '').strip(),
    }
    return JobApplication.model_validate(payload)


def parse_detailed_job_application_form(form_data):
    payload = {
        'first_name': str(form_data.get('first_name') or '').strip(),
        'last_name': str(form_data.get('last_name') or '').strip(),
        'phone_number': str(form_data.get('phone_number') or '').strip(),
        'email': str(form_data.get('email') or '').strip(),
        'position': str(form_data.get('position') or '').strip(),
        'linkedin_profile_url': str(form_data.get('linkedin_profile_url') or '').strip(),
        'id_passport_acknowledged': str(form_data.get('id_passport_acknowledged') or '').strip().lower() in {'1', 'true', 'yes', 'on'},
    }
    application = DetailedJobApplication.model_validate(payload)
    validate_linkedin_profile_format(str(application.linkedin_profile_url))
    return application


def validate_linkedin_profile_format(profile_url):
    parsed = urlparse(profile_url)
    host = parsed.netloc.lower()
    if parsed.scheme not in {'http', 'https'}:
        raise ValueError('LinkedIn profile URL must start with http:// or https://')
    if 'linkedin.com' not in host:
        raise ValueError('Please provide a valid LinkedIn profile URL.')


def create_app(config_name=None):
    """Application factory function"""
    if config_name is None:
        config_name = os.environ.get('FLASK_ENV', 'development')
    
    app = Flask(__name__)
    app.config.from_object(config[config_name])
    app.config['SQLITE_DB_PATH'] = os.environ.get(
        'SQLITE_DB_PATH',
        str(Path(app.root_path) / 'storage' / 'vistawave.db'),
    )

    # Track startup metadata for live metrics.
    app.config['STARTED_AT_UTC'] = datetime.now(timezone.utc)
    app.extensions['staffing_inquiries'] = deque(maxlen=250)
    app.extensions['job_applications'] = deque(maxlen=500)
    app.extensions['job_postings'] = generate_sample_jobs()
    init_sqlite_db(app)

    init_extensions(app)
    
    # Setup logging
    setup_logging(app)
    
    # Register error handlers
    register_error_handlers(app)
    
    # Security headers middleware
    @app.before_request
    def start_request_timer():
        g.request_started_at = time.perf_counter()

    @app.after_request
    def set_security_headers(response):
        elapsed_ms = None
        started_at = getattr(g, 'request_started_at', None)
        if started_at is not None:
            elapsed_ms = (time.perf_counter() - started_at) * 1000

        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['X-Frame-Options'] = 'SAMEORIGIN'
        response.headers['X-XSS-Protection'] = '1; mode=block'
        response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
        response.headers['Permissions-Policy'] = 'geolocation=(), microphone=(), camera=()'
        response.headers['Content-Security-Policy'] = (
            "default-src 'self'; "
            "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
            "font-src 'self' https://fonts.gstatic.com; "
            "img-src 'self' data: https://*.crisp.chat; "
            "script-src 'self' 'unsafe-inline' https://client.crisp.chat; "
            "connect-src 'self' https://*.crisp.chat wss://*.crisp.chat; "
            "frame-src 'self' https://*.crisp.chat;"
        )

        # Keep static assets cached briefly on clients/CDN for faster repeat loads.
        if request.path.startswith('/static/'):
            response.headers['Cache-Control'] = 'public, max-age=21600, stale-while-revalidate=300'

        is_html_get = (
            request.method == 'GET'
            and response.status_code == 200
            and response.mimetype == 'text/html'
        )

        # Signed-in HTML should never be served from shared/browser cache.
        if is_html_get and session.get('user_email'):
            response.headers['Cache-Control'] = 'private, no-store, max-age=0'

        # Cache public HTML pages briefly for faster repeat navigations.
        if (
            is_html_get
            and not session.get('user_email')
            and request.path in {
                '/', '/jobs', '/blog', '/privacy', '/terms', '/cookie-policy', '/sitemap'
            }
        ):
            response.headers['Cache-Control'] = 'public, max-age=120, stale-while-revalidate=60'
            response.headers['Vary'] = 'Cookie'

        if elapsed_ms is not None:
            response.headers['X-Response-Time-Ms'] = f'{elapsed_ms:.2f}'
            slow_ms_threshold = int(app.config.get('SLOW_REQUEST_LOG_THRESHOLD_MS', 600))
            if elapsed_ms >= slow_ms_threshold:
                app.logger.warning(
                    'Slow request detected: path=%s method=%s status=%s elapsed_ms=%.2f',
                    request.path,
                    request.method,
                    response.status_code,
                    elapsed_ms,
                )

        return add_cors_headers(response, app)

    @app.before_request
    def handle_preflight_requests():
        if request.method == 'OPTIONS':
            response = app.make_default_options_response()
            return add_cors_headers(response, app)
        return None

    @app.context_processor
    def inject_template_settings():
        """Inject global template settings."""
        user_email = session.get('user_email')
        user = get_user_by_email(app, user_email) if user_email else None
        user_name = (user or {}).get('name') or session.get('user_name') or 'Account'
        return {
            'crisp_website_id': app.config.get('CRISP_WEBSITE_ID', '').strip(),
            'api_base_url': app.config.get('API_BASE_URL', '').rstrip('/'),
            'calendar_booking_url': app.config.get('CALENDAR_BOOKING_URL', '').strip(),
            'is_authenticated': bool(user_email),
            'nav_user_name': user_name,
        }
    
    # Routes
    @app.route('/')
    @cache.cached(timeout=120, unless=lambda: bool(session.get('user_email')))
    def index():
        """Home page"""
        return render_template(
            'index.html',
            formspree_staffing_endpoint=app.config.get('FORMSPREE_STAFFING_ENDPOINT', ''),
            formspree_apply_endpoint=app.config.get('FORMSPREE_APPLY_ENDPOINT', ''),
            blog_posts=BLOG_POSTS
        )

    @app.route('/blog')
    @limiter.limit('120 per minute')
    @cache.cached(timeout=120, unless=lambda: bool(session.get('user_email')))
    def blog():
        """Blog listing page"""
        return render_template('blog.html', posts=BLOG_POSTS)

    @app.route('/jobs')
    @limiter.limit('120 per minute')
    @cache.cached(timeout=90, unless=lambda: bool(session.get('user_email')))
    def jobs():
        """Jobs board page"""
        return render_template(
            'jobs.html',
            formspree_apply_endpoint=app.config.get('FORMSPREE_APPLY_ENDPOINT', ''),
            jobs=app.extensions['job_postings'],
        )

    @app.route('/privacy')
    @limiter.limit('120 per minute')
    @cache.cached(timeout=600, unless=lambda: bool(session.get('user_email')))
    def privacy():
        """Privacy policy page."""
        return render_template('privacy.html')

    @app.route('/terms')
    @limiter.limit('120 per minute')
    @cache.cached(timeout=600, unless=lambda: bool(session.get('user_email')))
    def terms():
        """Terms of use page."""
        return render_template('terms.html')

    @app.route('/sitemap')
    @limiter.limit('120 per minute')
    @cache.cached(timeout=300, unless=lambda: bool(session.get('user_email')))
    def sitemap_page():
        """Human-readable sitemap page."""
        return render_template('sitemap.html')

    @app.route('/robots.txt')
    @limiter.limit('240 per minute')
    def robots_txt():
        """Robots directives including sitemap location for crawlers."""
        robots_body = '\n'.join([
            'User-agent: *',
            'Allow: /',
            f'Sitemap: {url_for("sitemap_xml", _external=True)}',
            ''
        ])
        return Response(robots_body, mimetype='text/plain')

    @app.route('/sitemap.xml')
    @limiter.limit('120 per minute')
    def sitemap_xml():
        """Machine-readable XML sitemap for search engines."""
        today = datetime.now(timezone.utc).date().isoformat()

        urls = [
            {
                'loc': url_for('index', _external=True),
                'changefreq': 'weekly',
                'priority': '1.0',
                'lastmod': today,
            },
            {
                'loc': url_for('jobs', _external=True),
                'changefreq': 'daily',
                'priority': '0.9',
                'lastmod': today,
            },
            {
                'loc': url_for('blog', _external=True),
                'changefreq': 'weekly',
                'priority': '0.8',
                'lastmod': today,
            },
            {
                'loc': url_for('privacy', _external=True),
                'changefreq': 'yearly',
                'priority': '0.4',
                'lastmod': today,
            },
            {
                'loc': url_for('terms', _external=True),
                'changefreq': 'yearly',
                'priority': '0.4',
                'lastmod': today,
            },
            {
                'loc': url_for('cookie_policy', _external=True),
                'changefreq': 'yearly',
                'priority': '0.4',
                'lastmod': today,
            },
            {
                'loc': url_for('sitemap_page', _external=True),
                'changefreq': 'monthly',
                'priority': '0.3',
                'lastmod': today,
            },
        ]

        for post in BLOG_POSTS:
            urls.append({
                'loc': url_for('blog_post', slug=post['slug'], _external=True),
                'changefreq': 'monthly',
                'priority': '0.7',
                'lastmod': post.get('published', today),
            })

        for job in app.extensions['job_postings']:
            urls.append({
                'loc': url_for('apply_for_job', job_id=job['id'], _external=True),
                'changefreq': 'weekly',
                'priority': '0.8',
                'lastmod': job.get('posted_date', today),
            })

        sitemap_xml_body = render_template('sitemap.xml', urls=urls)
        return Response(sitemap_xml_body, mimetype='application/xml')

    @app.route('/cookie-policy')
    @limiter.limit('120 per minute')
    @cache.cached(timeout=600, unless=lambda: bool(session.get('user_email')))
    def cookie_policy():
        """Cookie policy page."""
        return render_template('cookie_policy.html')

    @app.route('/thank-you/assessment')
    @limiter.limit('120 per minute')
    def thank_you_assessment():
        """Assessment thank-you page with next-step CTA."""
        return render_template(
            'thank_you.html',
            page_title='Assessment Request Received | vistawave',
            eyebrow='Thank You',
            heading='Your assessment request is in.',
            lead='We have your details and will follow up within one business day with a practical next-step recommendation.',
            next_steps=[
                'We review your current challenge, timeline, and delivery goals.',
                'You receive a tailored follow-up rather than a generic sales sequence.',
                'If you want to move faster, you can book time directly using the calendar link below.'
            ],
            primary_cta_label='Book a Strategy Call',
            secondary_cta_label='Back to Home'
        )

    @app.route('/thank-you/application')
    @limiter.limit('120 per minute')
    def thank_you_application():
        """Job application thank-you page with follow-up CTA."""
        role_name = request.args.get('role', '').strip() or 'this role'
        page_title = f'Application Received | {role_name}' if role_name else 'Application Received | vistawave'
        return render_template(
            'thank_you.html',
            page_title=page_title,
            eyebrow='Application Submitted',
            heading=f'Thank you for applying for {role_name}.',
            lead='Your resume and application details have been received successfully. Our recruiter will review your submission and contact you if there is a fit for this or a related opportunity.',
            next_steps=[
                'Your application and resume are now in our review queue.',
                'Our recruitment team evaluates submissions for fit and upcoming openings.',
                'If you would like to speak directly, you can book a quick intro call using the link below.'
            ],
            primary_cta_label='Book an Intro Call',
            secondary_cta_label='Explore Open Roles'
        )

    @app.route('/blog/<slug>')
    @limiter.limit('120 per minute')
    @cache.cached(timeout=300, unless=lambda: bool(session.get('user_email')))
    def blog_post(slug):
        """Individual blog post page"""
        post = next((p for p in BLOG_POSTS if p['slug'] == slug), None)
        if post is None:
            return render_template('404.html'), 404
        return render_template('blog_post.html', post=post)
    
    @app.route('/health')
    @limiter.limit('120 per minute')
    def health():
        """Health check endpoint for monitoring"""
        return {
            'status': 'healthy',
            'environment': config_name,
            'timestamp': datetime.now(timezone.utc).isoformat()
        }, 200

    @app.route('/warmup')
    @limiter.limit('240 per minute')
    def warmup():
        """Render warmup endpoint to keep app workers hot and dependencies loaded."""
        started = time.perf_counter()

        # Prime core in-memory computations commonly used by public routes.
        metrics_payload = build_live_metrics(app)
        talent_payload = build_talent_pool_snapshot()
        jobs_total = len(app.extensions['job_postings'])

        elapsed_ms = round((time.perf_counter() - started) * 1000, 2)
        return {
            'status': 'ok',
            'warmed': True,
            'jobs_total': jobs_total,
            'metrics_generated_at': metrics_payload.get('generated_at'),
            'talent_categories': len(talent_payload.get('categories', [])),
            'elapsed_ms': elapsed_ms,
            'timestamp': datetime.now(timezone.utc).isoformat(),
        }, 200

    register_api_routes(app)
    register_auth_routes(app)
    return app


def register_auth_routes(app):
    @app.route('/auth')
    @app.route('/signin')
    @app.route('/sign-in')
    @app.route('/login')
    def auth_page():
        action = request.args.get('mode', 'login')
        email = request.args.get('email', '')
        return render_template('auth.html', active_mode=action, email=email)

    @app.route('/signup')
    @app.route('/sign-up')
    @app.route('/register')
    def signup_page():
        return render_template('auth.html', active_mode='signup', email=request.args.get('email', ''))

    @app.route('/auth/register', methods=['POST'])
    @limiter.limit('20 per hour')
    def register_user():
        name = (request.form.get('name') or '').strip()
        email = normalize_email(request.form.get('email'))
        password = request.form.get('password') or ''

        if not name or len(name) < 2:
            flash('Please enter your full name.', 'error')
            return redirect(url_for('auth_page', mode='signup'))
        if not email or '@' not in email:
            flash('Please enter a valid email address.', 'error')
            return redirect(url_for('auth_page', mode='signup'))
        if len(password) < 6:
            flash('Password must be at least 6 characters long.', 'error')
            return redirect(url_for('auth_page', mode='signup'))

        existing_user = get_user_by_email(app, email)
        if existing_user:
            flash('An account with this email already exists. Please sign in.', 'error')
            return redirect(url_for('auth_page', mode='login'))

        passcode = generate_passcode()
        with get_sqlite_connection(app) as conn:
            conn.execute(
                """
                INSERT INTO users (
                    id, name, email, password_hash, verified,
                    verification_code, verification_expires_at,
                    reset_code, reset_expires_at, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(uuid4()),
                    name,
                    email,
                    generate_password_hash(password),
                    0,
                    passcode,
                    (datetime.now(timezone.utc) + timedelta(minutes=10)).isoformat(),
                    None,
                    None,
                    datetime.now(timezone.utc).isoformat(),
                ),
            )
        store_user_verification_email(app, email, name, passcode)
        flash('A verification code has been sent to your email. Enter it below to activate your account.', 'success')
        return redirect(url_for('auth_page', mode='verify', email=email))

    @app.route('/auth/verify', methods=['POST'])
    @limiter.limit('30 per hour')
    def verify_user():
        email = normalize_email(request.form.get('email'))
        code = (request.form.get('verification_code') or '').strip()
        user = get_user_by_email(app, email)

        if not user:
            flash('No account found for that email.', 'error')
            return redirect(url_for('auth_page', mode='verify', email=email))

        expires_at = user.get('verification_expires_at')
        if expires_at and datetime.fromisoformat(expires_at) < datetime.now(timezone.utc):
            flash('Your verification code has expired. Please sign up again.', 'error')
            return redirect(url_for('auth_page', mode='signup'))

        if user.get('verification_code') != code:
            flash('The verification code is incorrect.', 'error')
            return redirect(url_for('auth_page', mode='verify', email=email))

        with get_sqlite_connection(app) as conn:
            conn.execute(
                """
                UPDATE users
                SET verified = 1, verification_code = NULL, verification_expires_at = NULL
                WHERE email = ?
                """,
                (email,),
            )
        flash('Email verified successfully. You can now sign in.', 'success')
        return redirect(url_for('auth_page', mode='login', email=email))

    @app.route('/auth/login', methods=['POST'])
    @limiter.limit('30 per minute')
    def login_user():
        email = normalize_email(request.form.get('email'))
        password = request.form.get('password') or ''
        user = get_user_by_email(app, email)

        if not user or not check_password_hash(user['password_hash'], password):
            flash('Invalid email or password.', 'error')
            return redirect(url_for('auth_page', mode='login', email=email))

        if not user.get('verified'):
            flash('Please verify your account before logging in.', 'error')
            return redirect(url_for('auth_page', mode='verify', email=email))

        session['user_email'] = email
        session['user_name'] = user.get('name', 'Consultant')
        next_path = request.form.get('next') or url_for('timesheet_dashboard')
        return redirect(next_path)

    @app.route('/auth/logout')
    def logout_user():
        session.clear()
        flash('You have been signed out.', 'success')
        return redirect(url_for('auth_page', mode='login'))

    @app.route('/auth/request-reset', methods=['POST'])
    @limiter.limit('20 per hour')
    def request_password_reset():
        email = normalize_email(request.form.get('email'))
        user = get_user_by_email(app, email)

        if not user:
            flash('If an account exists for this email, a reset code has been sent.', 'success')
            return redirect(url_for('auth_page', mode='forgot'))

        passcode = generate_passcode()
        with get_sqlite_connection(app) as conn:
            conn.execute(
                """
                UPDATE users
                SET reset_code = ?, reset_expires_at = ?
                WHERE email = ?
                """,
                (passcode, (datetime.now(timezone.utc) + timedelta(minutes=10)).isoformat(), email),
            )
        store_user_reset_email(app, email, passcode)
        flash('A one-time password has been sent to your email.', 'success')
        return redirect(url_for('auth_page', mode='reset', email=email))

    @app.route('/auth/reset', methods=['POST'])
    @limiter.limit('20 per hour')
    def reset_password():
        email = normalize_email(request.form.get('email'))
        code = (request.form.get('reset_code') or '').strip()
        password = request.form.get('new_password') or ''
        user = get_user_by_email(app, email)

        if not user:
            flash('Account not found.', 'error')
            return redirect(url_for('auth_page', mode='forgot'))

        expires_at = user.get('reset_expires_at')
        if expires_at and datetime.fromisoformat(expires_at) < datetime.now(timezone.utc):
            flash('Your reset code has expired. Please request a new one.', 'error')
            return redirect(url_for('auth_page', mode='forgot'))

        if user.get('reset_code') != code:
            flash('The one-time password is incorrect.', 'error')
            return redirect(url_for('auth_page', mode='reset', email=email))

        if len(password) < 6:
            flash('Password must be at least 6 characters long.', 'error')
            return redirect(url_for('auth_page', mode='reset', email=email))

        with get_sqlite_connection(app) as conn:
            conn.execute(
                """
                UPDATE users
                SET password_hash = ?, reset_code = NULL, reset_expires_at = NULL
                WHERE email = ?
                """,
                (generate_password_hash(password), email),
            )
        flash('Your password has been updated successfully. Please sign in.', 'success')
        return redirect(url_for('auth_page', mode='login', email=email))

    @app.route('/portal')
    @auth_required
    def timesheet_dashboard():
        user_email = session.get('user_email')
        user = get_user_by_email(app, user_email)
        current_date = datetime.now(timezone.utc)
        selected_year = request.args.get('year', type=int) or current_date.year
        selected_month = request.args.get('month', type=int) or current_date.month
        selected_month = max(1, min(selected_month, 12))

        month_name = datetime(selected_year, selected_month, 1).strftime('%B')
        month_records = get_monthly_timesheet_records(app, user_email, selected_year, selected_month)
        days_in_month = calendar.monthrange(selected_year, selected_month)[1]

        daily_rows = []
        total_hours = 0.0
        for day in range(1, days_in_month + 1):
            day_record = month_records.get(str(day), {}) if isinstance(month_records, dict) else {}
            hours_value = day_record.get('hours', 0.0) if isinstance(day_record, dict) else 0.0
            try:
                hours_value = float(hours_value)
            except (TypeError, ValueError):
                hours_value = 0.0
            hours_value = round(max(0.0, min(hours_value, 24.0)), 2)
            total_hours += hours_value
            daily_rows.append({
                'day': day,
                'label': datetime(selected_year, selected_month, day).strftime('%a'),
                'hours': hours_value,
            })

        first_weekday = datetime(selected_year, selected_month, 1).weekday()  # Monday=0
        weeks = []
        current_week = []
        for _ in range(first_weekday):
            current_week.append(None)

        for row in daily_rows:
            current_week.append(row)
            if len(current_week) == 7:
                weeks.append(current_week)
                current_week = []

        if current_week:
            while len(current_week) < 7:
                current_week.append(None)
            weeks.append(current_week)

        week_options = []
        for idx, week in enumerate(weeks, start=1):
            day_values = [int(item['day']) for item in week if item]
            if day_values:
                label = f"Week {idx} ({min(day_values)}-{max(day_values)})"
            else:
                label = f"Week {idx}"
            week_options.append({'index': idx, 'label': label})

        selected_week = request.args.get('week', type=int)
        if selected_week and 1 <= selected_week <= len(weeks):
            active_week = selected_week
        elif selected_year == current_date.year and selected_month == current_date.month:
            today = current_date.day
            active_week = 1
            for idx, week in enumerate(weeks, start=1):
                if any(item and int(item['day']) == today for item in week):
                    active_week = idx
                    break
        else:
            active_week = 1

        timesheet_history = get_timesheet_history(app, user_email)

        return render_template(
            'portal.html',
            user=user,
            selected_year=selected_year,
            selected_month=selected_month,
            month_name=month_name,
            month_options=list(range(1, 13)),
            year_options=list(range(current_date.year - 2, current_date.year + 3)),
            daily_rows=daily_rows,
            weeks=weeks,
            week_options=week_options,
            active_week=active_week,
            timesheet_history=timesheet_history,
            total_hours=round(total_hours, 2),
        )

    @app.route('/portal/timesheet', methods=['POST'])
    @auth_required
    def submit_timesheet():
        user_email = session.get('user_email')
        current_date = datetime.now(timezone.utc)
        selected_year = int(request.form.get('selected_year') or current_date.year)
        selected_month = int(request.form.get('selected_month') or current_date.month)
        selected_month = max(1, min(selected_month, 12))
        days_in_month = calendar.monthrange(selected_year, selected_month)[1]
        saved_at = datetime.now(timezone.utc).isoformat()

        total_hours = 0.0
        with get_sqlite_connection(app) as conn:
            for day in range(1, days_in_month + 1):
                raw_value = request.form.get(f'hours_{selected_year}_{selected_month}_{day}')
                try:
                    hours = float(raw_value) if raw_value not in (None, '', 'NaN') else 0.0
                except (TypeError, ValueError):
                    hours = 0.0
                hours = round(max(0.0, min(hours, 24.0)), 2)
                total_hours += hours
                conn.execute(
                    """
                    INSERT INTO timesheets (user_email, year, month, day, hours, submitted_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    ON CONFLICT(user_email, year, month, day)
                    DO UPDATE SET
                        hours = excluded.hours,
                        submitted_at = excluded.submitted_at
                    """,
                    (user_email, selected_year, selected_month, day, hours, saved_at),
                )

        flash(
            f'Your timesheet for {datetime(selected_year, selected_month, 1).strftime("%B %Y")} has been saved successfully. Total: {total_hours:.2f} hours.',
            'success',
        )
        return redirect(url_for('timesheet_dashboard', year=selected_year, month=selected_month))

    @app.route('/portal/profile', methods=['POST'])
    @auth_required
    def update_profile():
        user_email = session.get('user_email')
        user = get_user_by_email(app, user_email)
        if not user:
            return redirect(url_for('auth_page', mode='login'))

        user_name = (request.form.get('name') or user['name']).strip() or user['name']
        user_title = (request.form.get('title') or '').strip()
        user_department = (request.form.get('department') or '').strip()
        user_phone = (request.form.get('phone') or '').strip()
        update_user_profile_record(app, user_email, user_name, user_title, user_department, user_phone)
        session['user_name'] = user_name
        flash('Profile updated successfully.', 'success')
        return redirect(url_for('timesheet_dashboard'))

    @app.route('/api/v1/auth/session')
    @limiter.limit('60 per minute')
    def auth_session_status():
        if not session.get('user_email'):
            return jsonify({'authenticated': False})
        return jsonify({'authenticated': True, 'email': session.get('user_email'), 'name': session.get('user_name')})
def setup_logging(app):
    """Configure logging"""
    if not app.debug and not app.testing:
        # Create logs directory if it doesn't exist
        if not os.path.exists('logs'):
            os.mkdir('logs')
        
        # File logger with rotation
        file_handler = RotatingFileHandler(
            'logs/vistawave.log',
            maxBytes=10485760,  # 10MB
            backupCount=10
        )
        file_handler.setFormatter(logging.Formatter(
            '%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]'
        ))
        file_handler.setLevel(logging.INFO)
        app.logger.addHandler(file_handler)
        
        app.logger.setLevel(logging.INFO)
        app.logger.info('vistawave startup')


def init_extensions(app):
    """Initialize production-grade Flask extensions."""
    limiter.init_app(app)
    cache.init_app(app)
    compress.init_app(app)


def generate_sample_jobs():
    """Create current open job postings."""
    jobs = [
        {
            'id': 'job_001',
            'title': 'Technical Project Manager',
            'company': 'State Project - WIC Program',
            'location': 'Remote (US)',
            'type': 'C2C',
            'experience_required': '8+ years',
            'skills': ['Project Planning', 'Stakeholder Management', 'Agile', 'Risk Management'],
            'posted_date': '2026-10-01',
            'start_date': 'October 2026 (Month 1)',
            'project_type': 'State Project',
            'description': 'Lead project delivery, milestones, and cross-functional coordination for a state government WIC initiative.'
        },
        {
            'id': 'job_002',
            'title': 'Full Stack Developer',
            'company': 'State Project - WIC Program',
            'location': 'Remote (US)',
            'type': 'C2C',
            'experience_required': '8+ years',
            'skills': ['JavaScript', 'Python', 'React', 'PostgreSQL'],
            'posted_date': '2026-10-01',
            'start_date': 'October 2026 (Month 1)',
            'project_type': 'State Project',
            'description': 'Build and maintain application features across frontend, backend, and data layers for a state program.'
        },
        {
            'id': 'job_003',
            'title': 'Entry-Level Software Developer',
            'company': 'State Project - WIC Program',
            'location': 'Remote (US)',
            'type': 'C2C',
            'experience_required': '0-2 years',
            'skills': ['HTML', 'CSS', 'JavaScript', 'Python'],
            'posted_date': '2026-10-01',
            'start_date': 'October 2026 (Month 1)',
            'project_type': 'State Project',
            'description': 'Support development work for new platform features and application enhancements on a state initiative.'
        },
        {
            'id': 'job_004',
            'title': 'QA Analyst',
            'company': 'State Project - WIC Program',
            'location': 'Remote (US)',
            'type': 'C2C',
            'experience_required': '8+ years',
            'skills': ['Manual Testing', 'Automation', 'SQL', 'Regression Testing'],
            'posted_date': '2026-10-01',
            'start_date': 'October 2026 (Month 1)',
            'project_type': 'State Project',
            'description': 'Validate requirements, test release quality, and support regression coverage for a state program.'
        },
        {
            'id': 'job_005',
            'title': 'Senior QA Analyst',
            'company': 'State Project - WIC Program',
            'location': 'Remote (US)',
            'type': 'C2C',
            'experience_required': '8+ years',
            'skills': ['QA Strategy', 'Automation', 'Test Planning', 'Defect Tracking'],
            'posted_date': '2026-10-01',
            'start_date': 'October 2026 (Month 1)',
            'project_type': 'State Project',
            'description': 'Lead quality assurance efforts and testing standards across a state-facing application delivery team.'
        },
        {
            'id': 'job_006',
            'title': 'Full Stack Developer',
            'company': 'State Project - WIC Program',
            'location': 'Remote (US)',
            'type': 'C2C',
            'experience_required': '8+ years',
            'skills': ['Java', 'JavaScript', 'Azure', 'API Development'],
            'posted_date': '2026-12-01',
            'start_date': 'December 2026 (Month 3)',
            'project_type': 'State Project',
            'description': 'Support additional engineering capacity for delivery milestones and modernization work on a state project.'
        },
        {
            'id': 'job_007',
            'title': 'Solution Architect',
            'company': 'State Project - WIC Program',
            'location': 'Remote (US)',
            'type': 'C2C',
            'experience_required': '8+ years',
            'skills': ['Cloud Architecture', 'Data Architecture', 'AWS', 'Azure'],
            'posted_date': '2026-12-01',
            'start_date': 'December 2026 (Month 3)',
            'project_type': 'State Project',
            'description': 'Design the target-state architecture and technical roadmap across cloud and data platforms for a state initiative.'
        },
        {
            'id': 'job_008',
            'title': 'QA Analyst',
            'company': 'State Project - WIC Program',
            'location': 'Remote (US)',
            'type': 'C2C',
            'experience_required': '8+ years',
            'skills': ['Test Cases', 'Automation', 'User Acceptance Testing', 'SQL'],
            'posted_date': '2026-12-01',
            'start_date': 'December 2026 (Month 3)',
            'project_type': 'State Project',
            'description': 'Support testing for release readiness, defect triage, and user acceptance validation on a state project.'
        },
        {
            'id': 'job_009',
            'title': 'PostgreSQL Developer',
            'company': 'State Project - WIC Program',
            'location': 'Remote (US)',
            'type': 'C2C',
            'experience_required': '8+ years',
            'skills': ['PostgreSQL', 'SQL', 'Performance Tuning', 'Data Migration'],
            'posted_date': '2027-01-01',
            'start_date': 'January 2027 (Month 4)',
            'project_type': 'State Project',
            'description': 'Support database optimization, migration, and PostgreSQL platform work for a state project.'
        }
    ]
    return jobs


def build_live_metrics(app):
    """Generate consulting metrics for API and SSE consumers."""
    started_at = app.config['STARTED_AT_UTC']
    uptime_minutes = max(
        1,
        int((datetime.now(timezone.utc) - started_at).total_seconds() // 60)
    )

    active_projects = len(app.extensions['job_postings'])
    data = {
        'generated_at': datetime.now(timezone.utc).isoformat(),
        'uptime_minutes': uptime_minutes,
        'fill_rate': 97,
        'submission_to_interview_days': 2.5,
        'active_client_requisitions': active_projects,
        'qualified_candidates': 85,
        'offer_acceptance_rate': 96,
        'time_to_fill_days': 14,
        'recommendations': [
            'Prioritize cloud migration projects with immediate business impact.',
            'Leverage data modernization to unlock analytics-driven decision making.',
            'Adopt a phased transformation approach for enterprise-scale changes.'
        ]
    }
    return data


def build_talent_pool_snapshot():
    """Create consulting capabilities summary."""
    return {
        'generated_at': datetime.now(timezone.utc).isoformat(),
        'categories': [
            {'technology': 'Cloud (AWS)', 'available': 24, 'avg_experience_years': 8},
            {'technology': 'Cloud (Azure)', 'available': 18, 'avg_experience_years': 7},
            {'technology': 'Data Engineering', 'available': 20, 'avg_experience_years': 7},
            {'technology': 'AI / Machine Learning', 'available': 14, 'avg_experience_years': 6},
            {'technology': 'Cybersecurity', 'available': 16, 'avg_experience_years': 9},
            {'technology': 'DevOps & SRE', 'available': 18, 'avg_experience_years': 7},
            {'technology': 'Digital Strategy', 'available': 12, 'avg_experience_years': 10},
            {'technology': 'Enterprise Architecture', 'available': 10, 'avg_experience_years': 12},
        ]
    }


def register_api_routes(app):
    """Register API routes for modern frontend integration."""

    @app.get('/api/v1/status')
    @limiter.limit('90 per minute')
    def api_status():
        return jsonify({
            'app': 'vistawave',
            'version': '2.0',
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'technologies': [
                'Flask 3',
                'Pydantic Validation',
                'SSE Realtime Streams',
                'Rate Limiting',
                'Response Caching',
                'HTTP Compression'
            ],
            'business_focus': 'IT Consulting - Cloud, Data, Strategy & Digital Transformation'
        })

    @app.get('/api/v1/metrics')
    @limiter.limit('60 per minute')
    @cache.cached(timeout=15)
    def api_metrics():
        return jsonify(build_live_metrics(app))

    @app.get('/api/v1/talent-pool')
    @limiter.limit('60 per minute')
    @cache.cached(timeout=20)
    def api_talent_pool():
        return jsonify(build_talent_pool_snapshot())

    @app.get('/api/v1/jobs')
    @limiter.limit('120 per minute')
    @cache.cached(timeout=30)
    def api_jobs():
        """Get all open job postings."""
        return jsonify({
            'generated_at': datetime.now(timezone.utc).isoformat(),
            'jobs': app.extensions['job_postings'],
            'total': len(app.extensions['job_postings'])
        })

    @app.get('/api/v1/jobs/<job_id>')
    @limiter.limit('120 per minute')
    @cache.cached(timeout=30)
    def api_job_detail(job_id):
        """Get specific job posting by ID."""
        for job in app.extensions['job_postings']:
            if job['id'] == job_id:
                return jsonify(job)
        return jsonify({'status': 'error', 'message': 'Job not found'}), 404

    @app.get('/api/v1/events')
    @limiter.limit('20 per minute')
    def api_events():
        payload = json.dumps(build_live_metrics(app))
        headers = {
            'Content-Type': 'text/event-stream',
            'Cache-Control': 'no-cache',
            'X-Accel-Buffering': 'no'
        }
        return Response(f'event: metrics\ndata: {payload}\n\n', headers=headers)

    @app.post('/api/v1/staffing-request')
    @limiter.limit('15 per hour')
    def api_staffing_request():
        """Accept contact and assessment request from consulting buyer."""
        payload = request.get_json(silent=True) or {}

        try:
            inquiry = StaffingInquiry.model_validate(payload)
        except ValidationError as exc:
            return jsonify({
                'status': 'error',
                'message': 'Invalid payload',
                'errors': exc.errors()
            }), 400

        inquiry_record = {
            'id': str(uuid4()),
            'name': inquiry.name,
            'work_email': inquiry.work_email,
            'company': inquiry.company,
            'area_of_interest': inquiry.area_of_interest,
            'technologies_involved': inquiry.technologies_involved,
            'engagement_type': inquiry.engagement_type,
            'team_size': inquiry.team_size,
            'desired_timeline': inquiry.desired_timeline,
            'project_goals': inquiry.project_goals,
            'created_at': datetime.now(timezone.utc).isoformat()
        }

        app.extensions['staffing_inquiries'].appendleft(inquiry_record)

        email_body = format_email_body('New Free IT Assessment Request', [
            ('Submitted At', inquiry_record['created_at']),
            ('Name', inquiry.name),
            ('Work Email', inquiry.work_email),
            ('Company', inquiry.company),
            ('Area of Interest', inquiry.area_of_interest),
            ('Technologies Involved', inquiry.technologies_involved),
            ('Engagement Type', inquiry.engagement_type),
            ('Team Size', inquiry.team_size),
            ('Desired Timeline', inquiry.desired_timeline),
            ('Project Goals', inquiry.project_goals),
        ])

        try:
            send_notification_email_async(
                app,
                subject=f'New IT Assessment Request - {inquiry.company}',
                body=email_body,
                reply_to=str(inquiry.work_email)
            )
        except Exception as exc:
            app.logger.exception('Failed to send staffing request email: %s', exc)
            return jsonify({
                'status': 'error',
                'message': 'Request saved but notification email failed'
            }, 502)

        app.logger.info(
            'New assessment request from %s (%s) for %s',
            inquiry.name,
            inquiry.work_email,
            inquiry.company
        )

        return jsonify({
            'status': 'accepted',
            'message': 'Assessment request submitted successfully',
            'request_id': inquiry_record['id']
        }), 202

    @app.route('/api/v1/apply', methods=['POST'])
    @limiter.limit('30 per hour')
    def api_job_apply():
        """Submit job application from job seeker with resume upload."""
        resume_file = request.files.get('resume')

        try:
            application = parse_job_application_form(request.form)
            resume_meta = store_resume(app, resume_file, application.name, application.position)
        except ValueError as exc:
            return jsonify({
                'status': 'error',
                'message': str(exc)
            }, 400)
        except ValidationError as exc:
            return jsonify({
                'status': 'error',
                'message': 'Invalid application',
                'errors': exc.errors()
            }, 400)

        application_record = {
            'id': str(uuid4()),
            'name': application.name,
            'email': application.email,
            'phone': application.phone,
            'position': application.position,
            'linkedin_url': application.linkedin_url,
            'message': application.message,
            'resume': resume_meta,
            'status': 'new',
            'created_at': datetime.now(timezone.utc).isoformat()
        }

        app.extensions['job_applications'].appendleft(application_record)

        email_body = format_email_body('New Career Application', [
            ('Submitted At', application_record['created_at']),
            ('Name', application.name),
            ('Email', application.email),
            ('Phone', application.phone),
            ('Position Applying For', application.position),
            ('LinkedIn URL', application.linkedin_url),
            ('Message', application.message),
            ('Resume Storage', resume_meta['storage_backend']),
            ('Resume Location', resume_meta['location']),
            ('Resume Filename', resume_meta['filename']),
            ('Resume Size (bytes)', resume_meta['size_bytes']),
        ])

        try:
            send_notification_email_async(
                app,
                subject=f'New Job Application - {application.position} - {application.name}',
                body=email_body,
                reply_to=str(application.email)
            )
        except Exception as exc:
            app.logger.exception('Failed to send application email: %s', exc)
            return jsonify({
                'status': 'error',
                'message': 'Application saved but notification email failed'
            }, 502)

        app.logger.info(
            'New job application from %s (%s) for %s',
            application.name,
            application.email,
            application.position
        )

        # For normal browser form posts, redirect to the thank-you page only after
        # the recruiter email has been sent successfully.
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.accept_mimetypes.best == 'application/json':
            return jsonify({
                'status': 'accepted',
                'message': 'Application submitted successfully.',
                'application_id': application_record['id']
            }), 202

        return redirect(url_for('thank_you_application', role=application.position))

    @app.route('/api/v1/detailed-apply', methods=['POST'])
    @app.route('/api/v1/apply-detailed', methods=['POST'])
    @limiter.limit('30 per hour')
    def api_detailed_job_apply():
        """Submit detailed job application from job seeker."""
        try:
            application = parse_detailed_job_application_form(request.form)
        except ValueError as exc:
            return jsonify({
                'status': 'error',
                'message': str(exc)
            }, 400)
        except ValidationError as exc:
            return jsonify({
                'status': 'error',
                'message': 'Invalid application',
                'errors': exc.errors()
            }, 400)

        application_record = {
            'id': str(uuid4()),
            'first_name': application.first_name,
            'last_name': application.last_name,
            'email': application.email,
            'phone_number': application.phone_number,
            'position': application.position,
            'linkedin_profile_url': str(application.linkedin_profile_url),
            'status': 'new',
            'created_at': datetime.now(timezone.utc).isoformat()
        }

        app.extensions['job_applications'].appendleft(application_record)

        email_body = format_email_body('New Detailed Job Application', [
            ('Submitted At', application_record['created_at']),
            ('First Name', application.first_name),
            ('Last Name', application.last_name),
            ('Email', application.email),
            ('Phone Number', application.phone_number),
            ('Position Applying For', application.position),
            ('LinkedIn Profile', application.linkedin_profile_url),
        ])

        try:
            send_notification_email_async(
                app,
                subject=f'New Detailed Job Application - {application.position} - {application.first_name} {application.last_name}',
                body=email_body,
                reply_to=str(application.email)
            )
        except Exception as exc:
            app.logger.exception('Failed to send detailed application email: %s', exc)
            return jsonify({
                'status': 'error',
                'message': 'Application saved but notification email failed'
            }, 502)

        app.logger.info(
            'New detailed job application from %s %s (%s) for %s',
            application.first_name,
            application.last_name,
            application.email,
            application.position
        )

        return jsonify({
            'status': 'accepted',
            'message': 'Application submitted successfully',
            'application_id': application_record['id']
        }), 202

    @app.route('/apply/<job_id>', methods=['GET'])
    def apply_for_job(job_id):
        """Display the job-specific detailed application page."""
        job = next((item for item in app.extensions['job_postings'] if item['id'] == job_id), None)
        if job is None:
            return render_template('404.html'), 404
        return render_template(
            'job_application.html',
            job=job,
            formspree_apply_endpoint=app.config.get('FORMSPREE_APPLY_ENDPOINT', '')
        )

    @app.route('/apply/<job_id>', methods=['POST'])
    @limiter.limit('30 per hour')
    def submit_job_application(job_id):
        """Submit the detailed application form via normal browser POST and redirect to success page."""
        job = next((item for item in app.extensions['job_postings'] if item['id'] == job_id), None)
        if job is None:
            return render_template('404.html', job=job), 404

        try:
            application = parse_detailed_job_application_form(request.form)
        except ValueError as exc:
            return render_template(
                'job_application.html',
                job=job,
                error=str(exc),
            ), 400
        except ValidationError as exc:
            return render_template(
                'job_application.html',
                job=job,
                error='Please complete all required fields correctly.',
                form_errors=exc.errors(),
            ), 400

        resume_file = request.files.get('resume')
        if resume_file is None or not resume_file.filename:
            return render_template(
                'job_application.html',
                job=job,
                error='Resume is required.',
            ), 400

        try:
            resume_meta = store_resume(app, resume_file, f"{application.first_name} {application.last_name}", application.position)
        except ValueError as exc:
            return render_template(
                'job_application.html',
                job=job,
                error=str(exc),
            ), 400

        app_record = {
            'id': str(uuid4()),
            'first_name': application.first_name,
            'last_name': application.last_name,
            'phone_number': application.phone_number,
            'email': application.email,
            'position': application.position,
            'linkedin_profile_url': str(application.linkedin_profile_url),
            'resume': resume_meta,
            'status': 'new',
            'created_at': datetime.now(timezone.utc).isoformat(),
            'id_passport_acknowledged': application.id_passport_acknowledged,
        }

        app.extensions['job_applications'].appendleft(app_record)

        email_body = format_email_body('New Detailed Job Application', [
            ('Submitted At', app_record['created_at']),
            ('First Name', application.first_name),
            ('Last Name', application.last_name),
            ('Phone Number', application.phone_number),
            ('Email', application.email),
            ('Position Applying For', application.position),
            ('LinkedIn Profile', application.linkedin_profile_url),
            ('Resume File', resume_meta['filename']),
            ('Resume Location', resume_meta['location']),
            ('ID / Passport Requirement Acknowledged', application.id_passport_acknowledged),
        ])

        resume_bytes = get_attachment_bytes(resume_file)
        attachments = [
            (
                resume_meta['filename'],
                resume_bytes or (
                    resume_meta['location'] and Path(resume_meta['location']).read_bytes() if resume_meta.get('storage_backend') == 'local' else None
                ),
                resume_meta['content_type'],
            ),
        ]

        send_notification_email_async(
            app,
            subject=f'Application for {application.position} - {application.first_name} {application.last_name}',
            body=email_body,
            reply_to=str(application.email),
            attachments=attachments,
        )

        return redirect(url_for('thank_you_application', role=application.position))


def register_error_handlers(app):
    """Register error handlers"""
    
    @app.errorhandler(404)
    def not_found_error(error):
        """Handle 404 errors"""
        app.logger.warning(f'404 error: {error}')
        return render_template('404.html'), 404
    
    @app.errorhandler(500)
    def internal_error(error):
        """Handle 500 errors"""
        app.logger.error(f'500 error: {error}')
        return render_template('500.html'), 500
    
    @app.errorhandler(400)
    def bad_request_error(error):
        """Handle 400 errors"""
        app.logger.warning(f'400 error: {error}')
        return render_template('400.html'), 400
    
    @app.errorhandler(Exception)
    def handle_exception(e):
        """Handle unexpected errors"""
        if isinstance(e, HTTPException):
            return e
        app.logger.error(f'Unhandled exception: {e}')
        return render_template('500.html'), 500

if __name__ == '__main__':
    app = create_app('development')
    app.debug = False
    preferred_port = int(os.environ.get('PORT', '5010'))
    fallback_ports = [5000, 5001, 5002, 5003, 5004, 5005, 5006, 5007, 5008, 5009, 5010]
    port_candidates = [preferred_port] + [port for port in fallback_ports if port != preferred_port]
    for candidate in port_candidates:
        try:
            app.run(host='0.0.0.0', port=candidate, debug=False, use_reloader=False)
            break
        except OSError:
            continue
    else:
        raise RuntimeError('No free port available for Flask app startup.')
