import os
import json
import logging
import random
import time
from uuid import uuid4
from datetime import datetime, timezone
from collections import deque
from logging.handlers import RotatingFileHandler
from flask import Flask, render_template, jsonify, request, Response, stream_with_context
from flask_caching import Cache
from flask_compress import Compress
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from pydantic import BaseModel, EmailStr, Field, ValidationError
from werkzeug.exceptions import HTTPException
from config import config


limiter = Limiter(key_func=get_remote_address, storage_uri='memory://')
cache = Cache()
compress = Compress()


class StaffingInquiry(BaseModel):
    """Validated staffing request from hiring companies."""

    name: str = Field(min_length=2, max_length=120)
    email: EmailStr
    company: str = Field(min_length=2, max_length=120)
    role_title: str = Field(min_length=2, max_length=120)
    technologies: list[str] = Field(min_length=1, max_length=12)
    hiring_model: str = Field(min_length=2, max_length=80)
    positions: int = Field(ge=1, le=250)
    start_timeline: str = Field(min_length=2, max_length=80)
    goals: str = Field(min_length=10, max_length=3000)


class JobApplication(BaseModel):
    """Validated job application from job seekers."""

    full_name: str = Field(min_length=2, max_length=120)
    email: EmailStr
    phone: str = Field(min_length=10, max_length=20)
    current_title: str = Field(min_length=2, max_length=120)
    years_experience: int = Field(ge=0, le=60)
    skills: list[str] = Field(min_length=1, max_length=15)
    linkedin_url: str = Field(min_length=5, max_length=500)
    resume_summary: str = Field(min_length=20, max_length=2000)
    job_id: str = Field(min_length=1, max_length=50)

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
            "style-src 'self' https://fonts.googleapis.com; "
            "font-src 'self' https://fonts.gstatic.com; "
            "img-src 'self' data:; "
            "script-src 'self'; "
            "connect-src 'self';"
        )
        return response
    
    # Routes
    @app.route('/')
    def index():
        """Home page"""
        return render_template('index.html')
    
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
    """Create sample job postings for demonstration."""
    jobs = [
        {
            'id': 'job_001',
            'title': 'Senior Python Engineer',
            'company': 'TechCorp',
            'location': 'San Francisco, CA (Remote)',
            'type': 'Contract-to-Hire',
            'experience_required': '5+',
            'skills': ['Python', 'AWS', 'Docker', 'Kubernetes'],
            'salary_range': '$120k-$160k',
            'posted_date': '2026-03-22',
            'description': 'Build scalable financial data pipeline systems.'
        },
        {
            'id': 'job_002',
            'title': 'React Frontend Developer',
            'company': 'CreativeScape',
            'location': 'New York, NY',
            'type': 'Contract',
            'experience_required': '3+',
            'skills': ['React', 'TypeScript', 'TailwindCSS', 'Redux'],
            'salary_range': '$90k-$130k',
            'posted_date': '2026-03-25',
            'description': 'Lead frontend modernization of customer portal.'
        },
        {
            'id': 'job_003',
            'title': 'DevOps Specialist',
            'company': 'CloudWorks',
            'location': 'Austin, TX (Remote)',
            'type': 'Direct Hire',
            'experience_required': '6+',
            'skills': ['Kubernetes', 'Terraform', 'AWS', 'CI/CD'],
            'salary_range': '$130k-$170k',
            'posted_date': '2026-03-20',
            'description': 'Architect next-gen infrastructure platform.'
        },
        {
            'id': 'job_004',
            'title': 'Data Engineer',
            'company': 'AnalyticsHub',
            'location': 'Boston, MA',
            'type': 'Contract-to-Hire',
            'experience_required': '4+',
            'skills': ['Python', 'Spark', 'Snowflake', 'dbt'],
            'salary_range': '$110k-$150k',
            'posted_date': '2026-03-23',
            'description': 'Build modern data warehouse and ETL pipelines.'
        },
        {
            'id': 'job_005',
            'title': 'QA Automation Engineer',
            'company': 'TestFirst',
            'location': 'Seattle, WA (Remote)',
            'type': 'Contract',
            'experience_required': '3+',
            'skills': ['Selenium', 'Python', 'Jest', 'Playwright'],
            'salary_range': '$85k-$120k',
            'posted_date': '2026-03-24',
            'description': 'Lead automated testing strategy and implementation.'
        }
    ]
    return jobs


def build_live_metrics(app):
    """Generate dynamic staffing metrics for API and SSE consumers."""
    started_at = app.config['STARTED_AT_UTC']
    uptime_minutes = max(
        1,
        int((datetime.now(timezone.utc) - started_at).total_seconds() // 60)
    )

    active_clients = random.randint(30, 84)
    shortlisted_candidates = random.randint(180, 520)
    data = {
        'generated_at': datetime.now(timezone.utc).isoformat(),
        'uptime_minutes': uptime_minutes,
        'fill_rate': random.randint(86, 97),
        'submission_to_interview_days': round(random.uniform(2.1, 6.8), 1),
        'active_client_requisitions': active_clients,
        'qualified_candidates': shortlisted_candidates,
        'offer_acceptance_rate': random.randint(78, 96),
        'time_to_fill_days': random.randint(9, 24),
        'recommendations': [
            'Prioritize critical roles in cloud, data, and platform engineering.',
            'Bundle contract-to-hire pipelines to reduce time-to-fill variance.',
            'Use skill-based scorecards for faster shortlist approvals.'
        ]
    }
    return data


def build_talent_pool_snapshot():
    """Create a synthetic real-time technology talent pool summary."""
    return {
        'generated_at': datetime.now(timezone.utc).isoformat(),
        'categories': [
            {'technology': 'Python', 'available': random.randint(40, 95), 'avg_experience_years': 6},
            {'technology': 'Java', 'available': random.randint(35, 80), 'avg_experience_years': 7},
            {'technology': 'React', 'available': random.randint(28, 72), 'avg_experience_years': 5},
            {'technology': 'Node.js', 'available': random.randint(24, 64), 'avg_experience_years': 5},
            {'technology': 'AWS', 'available': random.randint(32, 88), 'avg_experience_years': 7},
            {'technology': 'Kubernetes', 'available': random.randint(22, 58), 'avg_experience_years': 6},
            {'technology': 'DevOps', 'available': random.randint(26, 68), 'avg_experience_years': 7},
            {'technology': 'Data Engineering', 'available': random.randint(20, 52), 'avg_experience_years': 6},
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
            'business_focus': 'Technology Staffing - Dual Platform (Clients & Job Seekers)'
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
        """Accept staffing request from hiring company."""
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
            'email': inquiry.email,
            'company': inquiry.company,
            'role_title': inquiry.role_title,
            'technologies': inquiry.technologies,
            'hiring_model': inquiry.hiring_model,
            'positions': inquiry.positions,
            'start_timeline': inquiry.start_timeline,
            'goals': inquiry.goals,
            'created_at': datetime.now(timezone.utc).isoformat()
        }

        app.extensions['staffing_inquiries'].appendleft(inquiry_record)
        app.logger.info(
            'New staffing request from %s (%s) for %s [%s]',
            inquiry.name,
            inquiry.email,
            inquiry.role_title,
            ','.join(inquiry.technologies)
        )

        return jsonify({
            'status': 'accepted',
            'message': 'Staffing request captured successfully',
            'request_id': inquiry_record['id']
        }), 202

    @app.post('/api/v1/apply')
    @limiter.limit('30 per hour')
    def api_job_apply():
        """Submit job application from job seeker."""
        payload = request.get_json(silent=True) or {}

        try:
            application = JobApplication.model_validate(payload)
        except ValidationError as exc:
            return jsonify({
                'status': 'error',
                'message': 'Invalid application',
                'errors': exc.errors()
            }), 400

        application_record = {
            'id': str(uuid4()),
            'full_name': application.full_name,
            'email': application.email,
            'phone': application.phone,
            'current_title': application.current_title,
            'years_experience': application.years_experience,
            'skills': application.skills,
            'linkedin_url': application.linkedin_url,
            'resume_summary': application.resume_summary,
            'job_id': application.job_id,
            'status': 'new',
            'created_at': datetime.now(timezone.utc).isoformat()
        }

        app.extensions['job_applications'].appendleft(application_record)
        app.logger.info(
            'New job application from %s (%s) for job %s',
            application.full_name,
            application.email,
            application.job_id
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
