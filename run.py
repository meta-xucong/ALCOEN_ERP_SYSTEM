#!/usr/bin/env python
"""
ALCOEN ERP - Development Entry Point
"""
import os
import sys
import logging
from logging.handlers import RotatingFileHandler

# Add the current directory to path
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

# 配置日志
if not os.path.exists('logs'):
    os.makedirs('logs')
handler = RotatingFileHandler('logs/app.log', maxBytes=1000000, backupCount=5, encoding='utf-8')
handler.setLevel(logging.INFO)
formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
handler.setFormatter(formatter)
logging.getLogger().addHandler(handler)
logging.getLogger().setLevel(logging.INFO)

from app import create_app, db
from app.models import Company, Transaction, Statement, StatementItem

# Create app instance
app = create_app('development')

@app.shell_context_processor
def make_shell_context():
    """Shell context for Flask CLI"""
    return {
        'db': db,
        'Company': Company,
        'Transaction': Transaction,
        'Statement': Statement,
        'StatementItem': StatementItem
    }

if __name__ == '__main__':
    print("=" * 60)
    print("ALCOEN ERP v1.0 - Development Server")
    print("=" * 60)
    print(f"Access URL: http://localhost:5000")
    print(f"Debug Mode: {app.debug}")
    print("=" * 60)
    
    # Run the development server
    app.run(
        host='0.0.0.0',
        port=8080,
        debug=True,
        use_reloader=True
    )
