import os
from datetime import timedelta


def _get_bool(name, default=False):
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {'1', 'true', 'yes', 'on'}


def _get_list(name, default=''):
    raw_value = os.environ.get(name, default)
    return [item.strip().rstrip('/') for item in raw_value.split(',') if item.strip()]

class Config:
    """Base configuration"""
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'dev-key-change-in-production'
    SESSION_COOKIE_SECURE = True
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'
    PERMANENT_SESSION_LIFETIME = timedelta(days=7)
    SEND_FILE_MAX_AGE_DEFAULT = 31536000  # 1 year for static files
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16MB max request size
    COMPRESS_MIMETYPES = [
        'text/html',
        'text/css',
        'text/xml',
        'application/json',
        'application/javascript',
        'text/javascript'
    ]
    COMPRESS_LEVEL = 6
    COMPRESS_MIN_SIZE = 500
    CACHE_TYPE = 'SimpleCache'
    CACHE_DEFAULT_TIMEOUT = 30
    RATELIMIT_HEADERS_ENABLED = True
    API_BASE_URL = os.environ.get('API_BASE_URL', '')
    CALENDAR_BOOKING_URL = os.environ.get('CALENDAR_BOOKING_URL', '')
    ALLOWED_CORS_ORIGINS = _get_list(
        'ALLOWED_CORS_ORIGINS',
        'https://vistawavepro.com,https://www.vistawavepro.com'
    )
    FORMSPREE_STAFFING_ENDPOINT = os.environ.get('FORMSPREE_STAFFING_ENDPOINT', '')
    FORMSPREE_APPLY_ENDPOINT = os.environ.get('FORMSPREE_APPLY_ENDPOINT', '')
    CRISP_WEBSITE_ID = os.environ.get('CRISP_WEBSITE_ID', '')
    SMTP_HOST = os.environ.get('SMTP_HOST', 'smtp.gmail.com')
    SMTP_PORT = int(os.environ.get('SMTP_PORT', '587'))
    SMTP_USERNAME = os.environ.get('SMTP_USERNAME', '')
    SMTP_PASSWORD = os.environ.get('SMTP_PASSWORD', '')
    SMTP_FROM_EMAIL = os.environ.get('SMTP_FROM_EMAIL', SMTP_USERNAME or 'no-reply@vistawavepro.com')
    SMTP_USE_TLS = _get_bool('SMTP_USE_TLS', True)
    SMTP_USE_SSL = _get_bool('SMTP_USE_SSL', False)
    SMTP_TIMEOUT_SECONDS = int(os.environ.get('SMTP_TIMEOUT_SECONDS', '20'))
    NOTIFICATION_TO_EMAILS = _get_list('NOTIFICATION_TO_EMAILS', 'kiran@vistawave.com')
    RESUME_STORAGE_BACKEND = os.environ.get('RESUME_STORAGE_BACKEND', 'local').strip().lower()
    RESUME_UPLOAD_DIR = os.environ.get('RESUME_UPLOAD_DIR', 'storage/resumes')
    RESUME_MAX_BYTES = int(os.environ.get('RESUME_MAX_BYTES', str(5 * 1024 * 1024)))
    AWS_ACCESS_KEY_ID = os.environ.get('AWS_ACCESS_KEY_ID', '')
    AWS_SECRET_ACCESS_KEY = os.environ.get('AWS_SECRET_ACCESS_KEY', '')
    S3_BUCKET_NAME = os.environ.get('S3_BUCKET_NAME', '')
    S3_REGION = os.environ.get('S3_REGION', '')
    S3_PUBLIC_BASE_URL = os.environ.get('S3_PUBLIC_BASE_URL', '')
    S3_SERVER_SIDE_ENCRYPTION = os.environ.get('S3_SERVER_SIDE_ENCRYPTION', '')


class DevelopmentConfig(Config):
    """Development configuration"""
    DEBUG = True
    TESTING = False
    SESSION_COOKIE_SECURE = False


class ProductionConfig(Config):
    """Production configuration"""
    DEBUG = False
    TESTING = False
    SESSION_COOKIE_SECURE = True


class TestingConfig(Config):
    """Testing configuration"""
    DEBUG = True
    TESTING = True
    SESSION_COOKIE_SECURE = False


config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'testing': TestingConfig,
    'default': DevelopmentConfig
}
