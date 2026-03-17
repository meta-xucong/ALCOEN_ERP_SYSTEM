"""
ALCOEN ERP - WSGI Entry Point for Production
"""
import os

from app import create_app

# Get environment configuration
config_name = os.environ.get('FLASK_ENV', 'production')

# Create application instance
application = create_app(config_name)

# For Gunicorn compatibility
app = application

if __name__ == '__main__':
    app.run()
