"""Shared pytest fixtures for all tests."""

import os
import sys
import pytest

# Set environment BEFORE imports
os.environ['REDIS_URL'] = 'memory://'
os.environ['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
os.environ['SKIP_INIT_DEFAULT_DATA'] = 'true'

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app, init_default_data
from ext import db


@pytest.fixture
def app_context():
    """Create fresh app context for each test."""
    app = create_app('development')
    app.config['TESTING'] = True
    app.config['WTF_CSRF_ENABLED'] = False
    
    with app.app_context():
        db.drop_all()
        db.create_all()
        init_default_data()
        yield app
        db.drop_all()


@pytest.fixture
def client(app_context):
    """Return test client."""
    return app_context.test_client()