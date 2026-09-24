import os


class Config:
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL', 'sqlite:///school.db')
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SECRET_KEY = os.environ.get('SECRET_KEY') or os.environ.get('APP_SECRET_KEY')
    if not SECRET_KEY:
        raise RuntimeError(
            'SECRET_KEY is required. Set SECRET_KEY or APP_SECRET_KEY in your environment before starting the app.'
        )
    LOGIN_MESSAGE = 'Please log in to access this page.'
    LOGIN_MESSAGE_CATEGORY = 'warning'
    HOST = os.environ.get('HOST', '127.0.0.1')
    PORT = int(os.environ.get('PORT', '5000'))


class DevelopmentConfig(Config):
    DEBUG = True
    HOST = os.environ.get('HOST', '127.0.0.1')


class ProductionConfig(Config):
    DEBUG = False
    HOST = os.environ.get('HOST', '127.0.0.1')
    PORT = int(os.environ.get('PORT', '8000'))


def get_config():
    env_name = os.environ.get('APP_ENV', 'development').lower()
    config_map = {
        'development': DevelopmentConfig,
        'production': ProductionConfig,
    }
    return config_map.get(env_name, DevelopmentConfig)
