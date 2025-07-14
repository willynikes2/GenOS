"""
Database models and connection management for GenOS
"""

from sqlalchemy import create_engine, MetaData, Table, Column, Integer, String, DateTime, Text, Boolean, JSON, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from sqlalchemy.sql import func
from databases import Database
import asyncio
from typing import Optional
from ..core.config import settings

# Database connection
database = Database(settings.database_url)
metadata = MetaData()

# SQLAlchemy setup
engine = create_engine(settings.database_url)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# Database Tables
users_table = Table(
    "users",
    metadata,
    Column("id", Integer, primary_key=True, index=True),
    Column("username", String(50), unique=True, index=True, nullable=False),
    Column("email", String(100), unique=True, index=True, nullable=False),
    Column("hashed_password", String(255), nullable=False),
    Column("is_active", Boolean, default=True),
    Column("is_admin", Boolean, default=False),
    Column("created_at", DateTime(timezone=True), server_default=func.now()),
    Column("updated_at", DateTime(timezone=True), onupdate=func.now()),
)

environments_table = Table(
    "environments",
    metadata,
    Column("id", Integer, primary_key=True, index=True),
    Column("user_id", Integer, ForeignKey("users.id"), nullable=False),
    Column("name", String(100), nullable=False),
    Column("description", Text),
    Column("specification", JSON, nullable=False),
    Column("status", String(20), default="requested"),  # requested, provisioning, running, suspended, terminated
    Column("vm_id", String(100)),
    Column("streaming_port", Integer),
    Column("streaming_url", String(255)),
    Column("created_at", DateTime(timezone=True), server_default=func.now()),
    Column("updated_at", DateTime(timezone=True), onupdate=func.now()),
    Column("terminated_at", DateTime(timezone=True)),
)

environment_logs_table = Table(
    "environment_logs",
    metadata,
    Column("id", Integer, primary_key=True, index=True),
    Column("environment_id", Integer, ForeignKey("environments.id"), nullable=False),
    Column("level", String(10), nullable=False),  # INFO, WARNING, ERROR
    Column("message", Text, nullable=False),
    Column("metadata", JSON),
    Column("created_at", DateTime(timezone=True), server_default=func.now()),
)

sessions_table = Table(
    "sessions",
    metadata,
    Column("id", Integer, primary_key=True, index=True),
    Column("user_id", Integer, ForeignKey("users.id"), nullable=False),
    Column("environment_id", Integer, ForeignKey("environments.id"), nullable=False),
    Column("client_type", String(20), nullable=False),  # web, android, ios
    Column("client_info", JSON),
    Column("started_at", DateTime(timezone=True), server_default=func.now()),
    Column("ended_at", DateTime(timezone=True)),
    Column("is_active", Boolean, default=True),
)

# SQLAlchemy Models
class User(Base):
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(50), unique=True, index=True, nullable=False)
    email = Column(String(100), unique=True, index=True, nullable=False)
    hashed_password = Column(String(255), nullable=False)
    is_active = Column(Boolean, default=True)
    is_admin = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

class Environment(Base):
    __tablename__ = "environments"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    name = Column(String(100), nullable=False)
    description = Column(Text)
    specification = Column(JSON, nullable=False)
    status = Column(String(20), default="requested")
    vm_id = Column(String(100))
    streaming_port = Column(Integer)
    streaming_url = Column(String(255))
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    terminated_at = Column(DateTime(timezone=True))

class EnvironmentLog(Base):
    __tablename__ = "environment_logs"
    
    id = Column(Integer, primary_key=True, index=True)
    environment_id = Column(Integer, ForeignKey("environments.id"), nullable=False)
    level = Column(String(10), nullable=False)
    message = Column(Text, nullable=False)
    metadata = Column(JSON)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

class Session(Base):
    __tablename__ = "sessions"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    environment_id = Column(Integer, ForeignKey("environments.id"), nullable=False)
    client_type = Column(String(20), nullable=False)
    client_info = Column(JSON)
    started_at = Column(DateTime(timezone=True), server_default=func.now())
    ended_at = Column(DateTime(timezone=True))
    is_active = Column(Boolean, default=True)

# Database connection management
async def connect():
    """Connect to the database"""
    await database.connect()

async def disconnect():
    """Disconnect from the database"""
    await database.disconnect()

def create_tables():
    """Create all tables"""
    metadata.create_all(bind=engine)

def get_db():
    """Get database session"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

