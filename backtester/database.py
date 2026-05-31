"""
Database setup and session management using SQLAlchemy.
SQLite is used as the default backend (zero-config, file-based).
"""
import logging
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, DeclarativeBase
from config import DATABASE_URL

logger = logging.getLogger(__name__)

# ── Engine ────────────────────────────────────────────────────────────────────
engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},  # needed for SQLite + FastAPI
    echo=False,
)

# Enable WAL mode for better concurrent read performance
@event.listens_for(engine, "connect")
def set_sqlite_pragma(dbapi_conn, _):
    cursor = dbapi_conn.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()

# ── Session factory ───────────────────────────────────────────────────────────
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# ── Declarative base ──────────────────────────────────────────────────────────
class Base(DeclarativeBase):
    pass

# ── Dependency for FastAPI ────────────────────────────────────────────────────
def get_db():
    """Yield a database session; close it when the request is done."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def init_db():
    """Create all tables if they don't already exist."""
    import models  # noqa: F401 – ensure models are registered with Base
    Base.metadata.create_all(bind=engine)
    logger.info("✅ Database tables created / verified")
