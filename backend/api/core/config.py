"""
Configuration management for GenOS Backend
"""

from pydantic_settings import BaseSettings
from typing import Optional
import os

class Settings(BaseSettings):
    """Application settings"""
    
    # API Configuration
    api_title: str = "GenOS API"
    api_version: str = "1.0.0"
    debug: bool = False
    
    # Database Configuration
    database_url: str = "postgresql://genos:genos@localhost/genos"
    database_pool_size: int = 10
    database_max_overflow: int = 20
    
    # Redis Configuration
    redis_url: str = "redis://localhost:6379"
    redis_db: int = 0
    
    # Security Configuration
    secret_key: str = "your-secret-key-change-in-production"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    
    # VM Runtime Configuration
    vm_storage_path: str = "/var/lib/genos/vms"
    vm_images_path: str = "/var/lib/genos/images"
    max_concurrent_vms: int = 10
    default_vm_memory: int = 2048  # MB
    default_vm_cpu: int = 2
    
    # Streaming Configuration
    streaming_host: str = "0.0.0.0"
    streaming_port_range_start: int = 5900
    streaming_port_range_end: int = 5999
    
    # NLP Configuration
    nlp_model_path: str = "en_core_web_sm"
    nlp_cache_size: int = 1000
    
    # Monitoring Configuration
    metrics_enabled: bool = True
    metrics_port: int = 9090
    log_level: str = "INFO"
    
    # Security Sandbox Configuration
    enable_network_isolation: bool = True
    enable_filesystem_isolation: bool = True
    enable_capability_restrictions: bool = True
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"

# Global settings instance
settings = Settings()

