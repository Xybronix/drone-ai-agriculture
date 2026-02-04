"""
Database configuration and models.
Uses SQLAlchemy with async support for SQLite/PostgreSQL.
"""

import os
from datetime import datetime
from typing import AsyncGenerator
from sqlalchemy import Column, String, Float, DateTime, Boolean, Text, Integer, JSON
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import declarative_base
from api.config import get_settings

settings = get_settings()

# Create async engine
engine = create_async_engine(
    settings.database_url,
    echo=settings.debug,
    future=True
)
# Create async session factory
async_session_factory = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False
)

# Base class for models
Base = declarative_base()

class Analysis(Base):
    """Database model for analysis results."""
    __tablename__ = "analyses"

    id = Column(String(36), primary_key=True)
    timestamp = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    processing_time_ms = Column(Float, nullable=False)

    # Drone info
    drone_id = Column(String(50), index=True)
    field_id = Column(String(50), index=True)

    # Location
    latitude = Column(Float)
    longitude = Column(Float)
    altitude = Column(Float)

    # Plant detection
    plant_detected = Column(Boolean, nullable=False)
    plant_confidence = Column(Float)

    # Species
    species = Column(String(50), index=True)
    species_confidence = Column(Float)

    # Growth stage
    growth_stage = Column(String(50), index=True)
    growth_stage_confidence = Column(Float)

    # Health
    health_status = Column(String(50), index=True)
    health_confidence = Column(Float)
    disease_type = Column(String(50))
    severity = Column(String(20))

    # Storage
    image_path = Column(String(500))
    image_url = Column(String(500))
    thumbnail_url = Column(String(500))

    # Recommendations (stored as JSON)
    recommendations = Column(JSON)

    # Notes
    notes = Column(Text)

    # User tracking
    user_id = Column(Integer, index=True, nullable=True)
    guest_identifier = Column(String(100), index=True, nullable=True)
    backend_used = Column(String(20), default="local")

class Drone(Base):
    """Database model for registered drones."""
    __tablename__ = "drones"

    id = Column(String(50), primary_key=True)
    name = Column(String(100), nullable=False)
    model = Column(String(100))
    firmware_version = Column(String(50))
    registered_at = Column(DateTime, default=datetime.utcnow)
    last_seen = Column(DateTime)
    status = Column(String(20), default="offline")
    api_key = Column(String(100), unique=True)

class User(Base):
    """Database model for users."""
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String(50), unique=True, nullable=False)
    email = Column(String(100), unique=True)
    hashed_password = Column(String(255), nullable=False)
    is_active = Column(Boolean, default=True)
    is_admin = Column(Boolean, default=False)
    is_super_admin = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    last_login = Column(DateTime)

class Field(Base):
    """Database model for agricultural fields."""
    __tablename__ = "fields"

    id = Column(String(50), primary_key=True)
    name = Column(String(100), nullable=False)
    description = Column(Text)
    area_hectares = Column(Float)
    crop_type = Column(String(50))
    planting_date = Column(DateTime)
    expected_harvest = Column(DateTime)
    owner_id = Column(Integer)  # Reference to users

    # Boundary as GeoJSON (simplified for SQLite)
    boundary_geojson = Column(JSON)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """
    Dependency for getting async database session.
    
    Usage:
        @app.get("/endpoint")
        async def endpoint(session: AsyncSession = Depends(get_session)):
            ...
    """
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()

async def init_database():
    """Initialize database tables."""
    # Create data directory if it doesn't exist
    data_dir = os.path.dirname(settings.database_url.replace("sqlite+aiosqlite:///", ""))
    if data_dir and not os.path.exists(data_dir):
        os.makedirs(data_dir, exist_ok=True)

    # Create all tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

async def create_super_admin():
    """Create default super admin if not exists."""
    import bcrypt
    
    async with async_session_factory() as session:
        # Check if super admin exists
        result = await session.execute(
            select(User).where(User.username == "superadmin")
        )
        existing = result.scalar_one_or_none()
        
        if not existing:
            # Hash password directly with bcrypt
            password = "SuperAdmin2026!".encode('utf-8')
            hashed = bcrypt.hashpw(password, bcrypt.gensalt()).decode('utf-8')
            
            super_admin = User(
                username="superadmin",
                email="admin@droneai.local",
                hashed_password=hashed,
                is_active=True,
                is_admin=True,
                is_super_admin=True
            )
            session.add(super_admin)
            await session.commit()
            return True
        return False

async def close_database():
    """Close database connections."""
    await engine.dispose()