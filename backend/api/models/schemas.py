"""
Pydantic schemas for GenOS API
"""

from pydantic import BaseModel, Field, validator
from typing import Optional, Dict, Any, List
from datetime import datetime
from enum import Enum

# Enums
class EnvironmentStatus(str, Enum):
    REQUESTED = "requested"
    PROVISIONING = "provisioning"
    RUNNING = "running"
    SUSPENDED = "suspended"
    TERMINATED = "terminated"
    ERROR = "error"

class NetworkMode(str, Enum):
    ISOLATED = "isolated"
    LIMITED = "limited"
    FULL = "full"

class ClientType(str, Enum):
    WEB = "web"
    ANDROID = "android"
    IOS = "ios"

# Base schemas
class BaseSchema(BaseModel):
    class Config:
        from_attributes = True

# User schemas
class UserBase(BaseSchema):
    username: str = Field(..., min_length=3, max_length=50)
    email: str = Field(..., regex=r'^[^@]+@[^@]+\.[^@]+$')

class UserCreate(UserBase):
    password: str = Field(..., min_length=8)

class UserUpdate(BaseSchema):
    username: Optional[str] = Field(None, min_length=3, max_length=50)
    email: Optional[str] = Field(None, regex=r'^[^@]+@[^@]+\.[^@]+$')
    is_active: Optional[bool] = None

class User(UserBase):
    id: int
    is_active: bool
    is_admin: bool
    created_at: datetime
    updated_at: Optional[datetime] = None

# Environment specification schemas
class EnvironmentSpec(BaseSchema):
    base_os: str = Field(..., description="Base operating system (e.g., 'ubuntu_20.04', 'fedora_38')")
    apps: List[str] = Field(default=[], description="List of applications to install")
    network_mode: NetworkMode = Field(default=NetworkMode.ISOLATED, description="Network access mode")
    memory_mb: int = Field(default=2048, ge=512, le=16384, description="Memory allocation in MB")
    cpu_cores: int = Field(default=2, ge=1, le=8, description="Number of CPU cores")
    disk_gb: int = Field(default=20, ge=10, le=100, description="Disk space in GB")
    gpu_enabled: bool = Field(default=False, description="Enable GPU acceleration")
    custom_config: Optional[Dict[str, Any]] = Field(default=None, description="Custom configuration options")

class EnvironmentRequest(BaseSchema):
    name: str = Field(..., min_length=1, max_length=100)
    description: Optional[str] = Field(None, max_length=500)
    specification: EnvironmentSpec
    auto_start: bool = Field(default=True, description="Automatically start the environment after creation")

class EnvironmentUpdate(BaseSchema):
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    description: Optional[str] = Field(None, max_length=500)
    status: Optional[EnvironmentStatus] = None

class Environment(BaseSchema):
    id: int
    user_id: int
    name: str
    description: Optional[str]
    specification: EnvironmentSpec
    status: EnvironmentStatus
    vm_id: Optional[str]
    streaming_port: Optional[int]
    streaming_url: Optional[str]
    created_at: datetime
    updated_at: Optional[datetime]
    terminated_at: Optional[datetime]

# Natural Language Processing schemas
class NLPCommand(BaseSchema):
    command: str = Field(..., min_length=1, max_length=1000, description="Natural language command")
    context: Optional[Dict[str, Any]] = Field(default=None, description="Additional context for parsing")

class NLPResponse(BaseSchema):
    command: str
    specification: EnvironmentSpec
    confidence: float = Field(..., ge=0.0, le=1.0, description="Confidence score of the parsing")
    alternatives: Optional[List[EnvironmentSpec]] = Field(default=None, description="Alternative interpretations")
    warnings: Optional[List[str]] = Field(default=None, description="Parsing warnings")

# Streaming schemas
class StreamingConnection(BaseSchema):
    environment_id: int
    protocol: str = Field(default="spice", description="Streaming protocol (spice, rdp)")
    quality: str = Field(default="auto", description="Stream quality (low, medium, high, auto)")
    client_type: ClientType

class StreamingSession(BaseSchema):
    id: int
    environment_id: int
    user_id: int
    client_type: ClientType
    client_info: Optional[Dict[str, Any]]
    started_at: datetime
    ended_at: Optional[datetime]
    is_active: bool

# Authentication schemas
class Token(BaseSchema):
    access_token: str
    token_type: str = "bearer"
    expires_in: int

class TokenData(BaseSchema):
    username: Optional[str] = None

class LoginRequest(BaseSchema):
    username: str
    password: str

# Monitoring schemas
class SystemMetrics(BaseSchema):
    cpu_usage: float = Field(..., ge=0.0, le=100.0)
    memory_usage: float = Field(..., ge=0.0, le=100.0)
    disk_usage: float = Field(..., ge=0.0, le=100.0)
    active_environments: int = Field(..., ge=0)
    total_users: int = Field(..., ge=0)
    uptime_seconds: int = Field(..., ge=0)

class EnvironmentMetrics(BaseSchema):
    environment_id: int
    cpu_usage: float = Field(..., ge=0.0, le=100.0)
    memory_usage: float = Field(..., ge=0.0, le=100.0)
    network_rx_bytes: int = Field(..., ge=0)
    network_tx_bytes: int = Field(..., ge=0)
    disk_read_bytes: int = Field(..., ge=0)
    disk_write_bytes: int = Field(..., ge=0)
    timestamp: datetime

# Error schemas
class ErrorResponse(BaseSchema):
    error: str
    detail: Optional[str] = None
    code: Optional[str] = None

# Health check schemas
class HealthCheck(BaseSchema):
    status: str
    version: str
    components: Dict[str, str]
    timestamp: datetime = Field(default_factory=datetime.utcnow)

