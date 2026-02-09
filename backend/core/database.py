from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker
import os
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://qauser:securepassword@postgres:5432/qadb")

# Create engine with optimized connection pooling
engine = create_engine(
    DATABASE_URL,
    echo=False,
    # Connection pool settings
    pool_pre_ping=True,           # Verify connections before using (prevents stale connections)
    pool_size=20,                 # Number of connections to keep in pool
    max_overflow=40,              # Additional connections above pool_size
    pool_recycle=3600,            # Recycle connections after 1 hour (prevents timeout issues)
    # Connection timeout
    connect_args={
        "connect_timeout": 10,    # Connection timeout in seconds
        "options": "-c statement_timeout=30000"  # 30 second query timeout
    }
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

def get_db():
    """Dependency for getting database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
