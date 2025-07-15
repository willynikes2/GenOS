"""
GenOS Backend API
Main FastAPI application entry point
"""

from fastapi import FastAPI, HTTPException, Depends, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from contextlib import asynccontextmanager
import uvicorn
import os
from typing import Optional
import logging

from .routers import environments, auth, streaming, monitoring
from .models import database
from .core.config import settings
from .core.logging import setup_logging
from ..orchestration.engine import orchestration_engine

# Setup logging
setup_logging()
logger = logging.getLogger(__name__)

# Security
security = HTTPBearer()

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager"""
    # Startup
    logger.info("Starting GenOS Backend API")
    await database.connect()
    
    # Initialize orchestration engine
    logger.info("Starting orchestration engine")
    await orchestration_engine.start()
    
    yield
    
    # Shutdown
    logger.info("Shutting down GenOS Backend API")
    await orchestration_engine.stop()
    await database.disconnect()

# Create FastAPI app
app = FastAPI(
    title="GenOS API",
    description="Dynamic Virtualized Environment System API",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allow all origins for development
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(auth.router, prefix="/api/v1/auth", tags=["authentication"])
app.include_router(environments.router, prefix="/api/v1/environments", tags=["environments"])
app.include_router(streaming.router, prefix="/api/v1/streaming", tags=["streaming"])
app.include_router(monitoring.router, prefix="/api/v1/monitoring", tags=["monitoring"])

@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "message": "GenOS API",
        "version": "1.0.0",
        "status": "running"
    }

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    # Check orchestration engine status
    orchestration_status = "running" if orchestration_engine.running else "stopped"
    
    return {
        "status": "healthy",
        "version": "1.0.0",
        "components": {
            "database": "connected",
            "redis": "connected",
            "orchestration_engine": orchestration_status,
            "vm_runtime": "available"
        }
    }

@app.post("/api/v1/parse-command")
async def parse_natural_language_command(
    command: str,
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """
    Parse natural language command into environment specification
    
    Example commands:
    - "I need a Linux environment with Tor browser for secure browsing"
    - "Create a Ubuntu desktop with Firefox and VPN"
    - "Launch isolated Windows 10 with Office suite"
    """
    from .nlp.parser import EnvironmentParser
    
    try:
        parser = EnvironmentParser()
        specification = await parser.parse_command(command)
        
        return {
            "command": command,
            "specification": specification,
            "status": "parsed"
        }
    except Exception as e:
        logger.error(f"Failed to parse command: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to parse command: {str(e)}"
        )

@app.get("/api/v1/system/status")
async def get_system_status():
    """Get comprehensive system status"""
    try:
        # Get orchestration engine status
        orchestration_status = {
            "running": orchestration_engine.running,
            "active_environments": len(orchestration_engine.environments),
            "resource_utilization": orchestration_engine.resource_pool.get_utilization()
        }
        
        return {
            "system": "GenOS",
            "version": "1.0.0",
            "status": "operational",
            "orchestration": orchestration_status,
            "uptime": "running"  # TODO: Calculate actual uptime
        }
    except Exception as e:
        logger.error(f"Failed to get system status: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get system status"
        )

if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info"
    )

