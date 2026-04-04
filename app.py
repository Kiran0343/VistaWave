import os
import json
import logging
import smtplib
import time
from pathlib import Path
from uuid import uuid4
from datetime import datetime, timezone
from collections import deque
from logging.handlers import RotatingFileHandler
from email.message import EmailMessage
from flask import Flask, render_template, jsonify, request, Response, stream_with_context
from flask_caching import Cache
from flask_compress import Compress
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from pydantic import BaseModel, EmailStr, Field, ValidationError
from werkzeug.exceptions import HTTPException
from werkzeug.utils import secure_filename
from config import config
from blog_posts import BLOG_POSTS


limiter = Limiter(key_func=get_remote_address, storage_uri='memory://')
cache = Cache()
compress = Compress()


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
    linkedin_url: str = Field(min_length=5, max_length=500)
    message: str = Field(min_length=10, max_length=2000)


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


def build_resume_filename(applicant_name, original_filename):
    safe_name = secure_filename(applicant_name) or 'applicant'
    extension = Path(original_filename).suffix.lower() or '.pdf'
    timestamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    return f'{timestamp}-{uuid4().hex[:10]}-{safe_name}{extension}'


def validate_resume_upload(uploaded_file):
    if uploaded_file is None or not uploaded_file.filename:
        raise ValueError('Resume PDF is required')

    extension = Path(uploaded_file.filename).suffix.lower()
    if extension != '.pdf':
        raise ValueError('Resume must be a PDF file')

    content_type = (uploaded_file.mimetype or '').lower()
    if content_type and content_type not in {'application/pdf', 'application/x-pdf'}:
        raise ValueError('Resume must be uploaded as a PDF')


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


def store_resume(app, uploaded_file, applicant_name):
    validate_resume_upload(uploaded_file)

    file_bytes = uploaded_file.read()
    if len(file_bytes) > app.config['RESUME_MAX_BYTES']:
        raise ValueError('Resume exceeds the maximum allowed size')

    uploaded_file.stream.seek(0)
    filename = build_resume_filename(applicant_name, uploaded_file.filename)
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


def format_email_body(title, rows):
    lines = [title, '']
    for label, value in rows:
        lines.append(f'{label}: {value}')
    return '\n'.join(lines)


def send_notification_email(app, subject, body, reply_to=None):
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

def create_app(config_name=None):
    """Application factory function"""
    if config_name is None:
        config_name = os.environ.get('FLASK_ENV', 'development')
    
    app = Flask(__name__)
    app.config.from_object(config[config_name])

    # Track startup metadata for live metrics.
    app.config['STARTED_AT_UTC'] = datetime.now(timezone.utc)
    app.extensions['staffing_inquiries'] = deque(maxlen=250)
    app.extensions['job_applications'] = deque(maxlen=500)
    app.extensions['job_postings'] = generate_sample_jobs()

    init_extensions(app)
    
    # Setup logging
    setup_logging(app)
    
    # Register error handlers
    register_error_handlers(app)
    
    # Security headers middleware
    @app.after_request
    def set_security_headers(response):
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
            "script-src 'self' https://client.crisp.chat; "
            "connect-src 'self' https://*.crisp.chat wss://*.crisp.chat; "
            "frame-src 'self' https://*.crisp.chat;"
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
        return {
            'crisp_website_id': app.config.get('CRISP_WEBSITE_ID', '').strip(),
            'api_base_url': app.config.get('API_BASE_URL', '').rstrip('/'),
            'calendar_booking_url': app.config.get('CALENDAR_BOOKING_URL', '').strip(),
        }
    
    # Routes
    @app.route('/')
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
    def blog():
        """Blog listing page"""
        return render_template('blog.html', posts=BLOG_POSTS)

    @app.route('/jobs')
    @limiter.limit('120 per minute')
    def jobs():
        """Jobs board page"""
        return render_template(
            'jobs.html',
            formspree_apply_endpoint=app.config.get('FORMSPREE_APPLY_ENDPOINT', ''),
        )

    @app.route('/privacy')
    @limiter.limit('120 per minute')
    def privacy():
        """Privacy policy page."""
        return render_template('privacy.html')

    @app.route('/terms')
    @limiter.limit('120 per minute')
    def terms():
        """Terms of use page."""
        return render_template('terms.html')

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
        return render_template(
            'thank_you.html',
            page_title='Application Received | vistawave',
            eyebrow='Application Submitted',
            heading='Your application has been received.',
            lead='Our team will review your background and reach out if there is a fit with current or upcoming roles.',
            next_steps=[
                'Your application and resume are now in review.',
                'Qualified candidates are typically contacted within a few business days.',
                'If you prefer a faster conversation, you can use the calendar link below.'
            ],
            primary_cta_label='Book an Intro Call',
            secondary_cta_label='Explore Open Roles'
        )

    @app.route('/blog/<slug>')
    @limiter.limit('120 per minute')
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

    register_api_routes(app)
    
    return app


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
            'title': 'Senior Python Backend Engineer',
            'company': 'Vistawave Client - FinTech',
            'location': 'Dallas, TX (Hybrid)',
            'type': 'Contract-to-Hire',
            'experience_required': '5+',
            'skills': ['Python', 'FastAPI', 'AWS', 'PostgreSQL'],
            'salary_range': '$135k-$165k',
            'posted_date': '2026-03-26',
            'description': 'Build high-throughput backend services for payments workflows.'
        },
        {
            'id': 'job_002',
            'title': 'Senior React Frontend Engineer',
            'company': 'Vistawave Client - HealthTech',
            'location': 'Austin, TX (Remote)',
            'type': 'Direct Hire',
            'experience_required': '4+',
            'skills': ['React', 'TypeScript', 'Next.js', 'GraphQL'],
            'salary_range': '$125k-$150k',
            'posted_date': '2026-03-27',
            'description': 'Lead UI architecture for clinical workflow applications.'
        },
        {
            'id': 'job_003',
            'title': 'Cloud DevOps Engineer',
            'company': 'Vistawave Client - SaaS Platform',
            'location': 'Remote (US)',
            'type': 'Direct Hire',
            'experience_required': '6+',
            'skills': ['Kubernetes', 'Terraform', 'AWS', 'CI/CD'],
            'salary_range': '$140k-$175k',
            'posted_date': '2026-03-24',
            'description': 'Own platform reliability, deployment automation, and observability.'
        },
        {
            'id': 'job_004',
            'title': 'Senior Data Engineer',
            'company': 'Vistawave Client - Retail Analytics',
            'location': 'Chicago, IL (Hybrid)',
            'type': 'Contract-to-Hire',
            'experience_required': '4+',
            'skills': ['Python', 'Spark', 'Snowflake', 'dbt', 'Airflow'],
            'salary_range': '$130k-$158k',
            'posted_date': '2026-03-25',
            'description': 'Build enterprise data pipelines and modern analytics foundation.'
        },
        {
            'id': 'job_005',
            'title': 'QA Automation Engineer',
            'company': 'Vistawave Client - E-commerce',
            'location': 'Seattle, WA (Remote)',
            'type': 'Contract',
            'experience_required': '3+',
            'skills': ['Selenium', 'Python', 'Jest', 'Playwright'],
            'salary_range': '$95k-$125k',
            'posted_date': '2026-03-28',
            'description': 'Expand end-to-end test automation for omnichannel checkout.'
        },
        {
            'id': 'job_006',
            'title': 'Machine Learning Engineer',
            'company': 'Vistawave Client - Logistics AI',
            'location': 'Atlanta, GA (Hybrid)',
            'type': 'Direct Hire',
            'experience_required': '5+',
            'skills': ['Python', 'PyTorch', 'MLOps', 'AWS'],
            'salary_range': '$150k-$185k',
            'posted_date': '2026-03-29',
            'description': 'Deploy demand forecasting and route optimization ML models.'
        },
        {
            'id': 'job_007',
            'title': 'Salesforce Developer',
            'company': 'Vistawave Client - Professional Services',
            'location': 'Remote (US)',
            'type': 'Contract',
            'experience_required': '4+',
            'skills': ['Salesforce', 'Apex', 'LWC', 'Integration APIs'],
            'salary_range': '$105k-$135k',
            'posted_date': '2026-03-27',
            'description': 'Implement CRM workflows and quote-to-cash automations.'
        },
        {
            'id': 'job_008',
            'title': 'Cybersecurity Analyst',
            'company': 'Vistawave Client - Insurance',
            'location': 'Phoenix, AZ (Hybrid)',
            'type': 'Contract-to-Hire',
            'experience_required': '4+',
            'skills': ['SIEM', 'SOC', 'Threat Modeling', 'Incident Response'],
            'salary_range': '$115k-$145k',
            'posted_date': '2026-03-29',
            'description': 'Strengthen SOC operations and response playbooks.'
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
        def event_stream():
            for _ in range(20):
                payload = json.dumps(build_live_metrics(app))
                yield f'event: metrics\ndata: {payload}\n\n'
                time.sleep(3)

        headers = {
            'Content-Type': 'text/event-stream',
            'Cache-Control': 'no-cache',
            'X-Accel-Buffering': 'no'
        }
        return Response(stream_with_context(event_stream()), headers=headers)

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
            send_notification_email(
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
            }), 502

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
            resume_meta = store_resume(app, resume_file, application.name)
        except ValueError as exc:
            return jsonify({
                'status': 'error',
                'message': str(exc)
            }), 400
        except ValidationError as exc:
            return jsonify({
                'status': 'error',
                'message': 'Invalid application',
                'errors': exc.errors()
            }), 400

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
            send_notification_email(
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
            }), 502

        app.logger.info(
            'New job application from %s (%s) for %s',
            application.name,
            application.email,
            application.position
        )

        return jsonify({
            'status': 'accepted',
            'message': 'Application submitted successfully',
            'application_id': application_record['id']
        }), 202


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
    app_instance = create_app()
    app_instance.run(debug=True, host='0.0.0.0', port=5001)
