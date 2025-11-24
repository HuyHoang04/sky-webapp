"""
Database configuration and session management for PostgreSQL/Supabase

Copyright (c) 2025 HuyHoang04
Licensed under MIT License - see LICENSE file for details
"""

import os
from sqlalchemy import create_engine, event
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, scoped_session
from sqlalchemy.pool import Pool
from contextlib import contextmanager
import logging
from urllib.parse import urlparse, parse_qs, urlencode, urlunparse

logger = logging.getLogger(__name__)

# Database configuration from environment variables
DATABASE_URL = os.getenv('DATABASE_URL')

if not DATABASE_URL:
    raise ValueError("DATABASE_URL environment variable is not set. Please create a .env file with your database connection string.")

# Clean Supabase connection string (remove pgbouncer parameter if present)
def clean_database_url(url: str) -> str:
    """
    Remove unsupported parameters from database URL
    Supabase adds ?pgbouncer=true which psycopg2 doesn't understand
    """
    try:
        parsed = urlparse(url)
        
        # Parse query parameters
        query_params = parse_qs(parsed.query)
        
        # Remove pgbouncer parameter
        if 'pgbouncer' in query_params:
            del query_params['pgbouncer']
            logger.info("Removed 'pgbouncer' parameter from connection string")
        
        # Rebuild query string
        new_query = urlencode(query_params, doseq=True)
        
        # Rebuild URL
        new_parsed = parsed._replace(query=new_query)
        return urlunparse(new_parsed)
    except Exception as e:
        logger.warning(f"Could not parse DATABASE_URL: {e}, using as-is")
        return url

DATABASE_URL = clean_database_url(DATABASE_URL)

# Create engine with connection pooling
engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,  # Verify connections before using
    pool_size=10,        # Number of connections to maintain
    max_overflow=20,     # Maximum overflow connections
    pool_recycle=3600,   # Recycle connections after 1 hour
    echo=False           # Set to True for SQL debugging
)

# Add listener to log connection events (useful for debugging)
@event.listens_for(Pool, "connect")
def receive_connect(dbapi_conn, connection_record):
    logger.debug("Database connection established")

@event.listens_for(Pool, "checkout")
def receive_checkout(dbapi_conn, connection_record, connection_proxy):
    logger.debug("Database connection checked out from pool")

# Create session factory
SessionLocal = scoped_session(sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
    expire_on_commit=False
))

# Base class for declarative models
Base = declarative_base()

def init_db():
    """
    Initialize database tables
    Creates all tables defined in models
    """
    try:
        # Import all models to ensure they are registered
        from model.mission_model import Mission, Waypoint, Route, Order
        from model.voice_model import VoiceRecord
        from model.capture_model import CaptureRecord
        
        # Create all tables
        Base.metadata.create_all(bind=engine)
        logger.info("✓ Database tables created/verified successfully")
        return True
        
    except Exception as e:
        logger.error(f"✗ Error creating database tables: {e}")
        return False

def drop_all_tables():
    """
    Drop all tables (use with caution!)
    Mainly for development/testing
    """
    try:
        Base.metadata.drop_all(bind=engine)
        logger.warning("All database tables dropped")
    except Exception as e:
        logger.error(f"Error dropping tables: {e}")
        raise

@contextmanager
def get_db():
    """
    Context manager for database sessions
    Automatically handles commit/rollback and cleanup
    
    Usage:
        with get_db() as db:
            mission = db.query(Mission).first()
            # ... do work ...
        # Automatically commits and closes
    """
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception as e:
        db.rollback()
        logger.error(f"Database transaction error: {e}")
        raise
    finally:
        db.close()

def get_db_session():
    """
    Get database session for dependency injection
    Used primarily with Flask request context
    
    Usage:
        db = next(get_db_session())
        try:
            # ... do work ...
            db.commit()
        except:
            db.rollback()
        finally:
            db.close()
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def check_db_connection():
    """
    Check if database connection is working
    Returns True if connection successful, False otherwise
    """
    try:
        from sqlalchemy import text
        with get_db() as db:
            db.execute(text("SELECT 1"))
        logger.info("✓ Database connection verified")
        return True
    except Exception as e:
        logger.error(f"✗ Database connection failed: {e}")
        return False
