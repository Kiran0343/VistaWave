import os
import json
import logging
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
        return render_template(
            'index.html',
            formspree_staffing_endpoint=app.config.get('FORMSPREE_STAFFING_ENDPOINT', ''),
            formspree_apply_endpoint=app.config.get('FORMSPREE_APPLY_ENDPOINT', '')
        )
    
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
    """Generate staffing metrics for API and SSE consumers."""
    started_at = app.config['STARTED_AT_UTC']
    uptime_minutes = max(
        1,
        int((datetime.now(timezone.utc) - started_at).total_seconds() // 60)
    )

    active_requisitions = len(app.extensions['job_postings'])
    qualified_candidates = 412
    data = {
        'generated_at': datetime.now(timezone.utc).isoformat(),
        'uptime_minutes': uptime_minutes,
        'fill_rate': 94,
        'submission_to_interview_days': 3.8,
        'active_client_requisitions': active_requisitions,
        'qualified_candidates': qualified_candidates,
        'offer_acceptance_rate': 89,
        'time_to_fill_days': 16,
        'recommendations': [
            'Prioritize roles with immediate delivery dependencies first.',
            'Use blended contract-to-hire strategy for hard-to-fill niches.',
            'Standardize interview scorecards to improve match quality.'
        ]
    }
    return data


def build_talent_pool_snapshot():
    """Create talent pool summary."""
    return {
        'generated_at': datetime.now(timezone.utc).isoformat(),
        'categories': [
            {'technology': 'Python', 'available': 84, 'avg_experience_years': 6},
            {'technology': 'Java', 'available': 63, 'avg_experience_years': 7},
            {'technology': 'React', 'available': 58, 'avg_experience_years': 5},
            {'technology': 'Node.js', 'available': 49, 'avg_experience_years': 5},
            {'technology': 'AWS', 'available': 72, 'avg_experience_years': 7},
            {'technology': 'Kubernetes', 'available': 44, 'avg_experience_years': 6},
            {'technology': 'DevOps', 'available': 53, 'avg_experience_years': 7},
            {'technology': 'Data Engineering', 'available': 46, 'avg_experience_years': 6},
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
