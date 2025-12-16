import sys
from sqlalchemy import create_engine
from django.conf import settings
from django.db import connection

# A simple check to see if we are running tests (e.g., 'manage.py test')
IS_RUNNING_TESTS = 'test' in sys.argv

def get_django_connection():
    """Returns the underlying psycopg2 connection from Django."""
    # Ensure the connection is established/active
    connection.ensure_connection() 
    return connection.connection

def create_configured_engine():
    if IS_RUNNING_TESTS:
        # --- Engine for Django Tests ---
        # This uses the connection created and managed by Django's test runner,
        # ensuring it points to the temporary test database.
        print("Creating SQLAlchemy engine using Django's test connection.")
        return create_engine(
            "postgresql+psycopg2://",  # DSN is ignored when 'creator' is used
            creator=get_django_connection,
            # poolclass=None is often recommended when using an external connection manager
            poolclass=None, 
            echo=False
        )
    else:
        # --- Engine for Standard Application Use (Outside of Tests) ---
        # This uses the connection settings directly and manages its own connection pool.
        print("Creating SQLAlchemy engine using direct settings connection.")
        db_settings = settings.DATABASES['default']
        return create_engine(
            f"postgresql+psycopg2://{db_settings['USER']}:{db_settings['PASSWORD']}@"
            f"{db_settings['HOST']}:{db_settings['PORT']}/"
            f"{db_settings['NAME']}", 
            echo=False
        )

# Use this function to initialize your engine
engine = create_configured_engine()