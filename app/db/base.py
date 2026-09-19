"""
SQLAlchemy engine + session factory.

`Base` is defined with zero dependency on the DB driver, so importing
`app.models` (and therefore configuring the ORM mappers) never requires
pyodbc to be installed - only actually connecting does. The engine itself
is built lazily on first use via `get_engine()`, so unit tests can import
every model, build their own SQLite engine, and never touch SQL Server.
"""
from functools import lru_cache

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.core.config import get_settings


class Base(DeclarativeBase):
    pass


@lru_cache
def get_engine():
    settings = get_settings()
    return create_engine(
        settings.sqlalchemy_database_uri,
        pool_pre_ping=True,
        pool_size=10,
        max_overflow=20,
        future=True,
    )


@lru_cache
def get_session_factory():
    return sessionmaker(bind=get_engine(), autoflush=False, autocommit=False, future=True)


def get_db():
    """FastAPI dependency: yields a DB session, always closed after the request."""
    SessionLocal = get_session_factory()
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
