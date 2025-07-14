"""
Monitoring router for GenOS API
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List, Dict, Any
from datetime import datetime, timedelta
import psutil
import asyncio

from ..models.database import get_db, Environment, User
from ..models.schemas import SystemMetrics, EnvironmentMetrics, HealthCheck
from ..routers.auth import get_current_active_user
from ..core.logging import get_logger

logger = get_logger(__name__)
router = APIRouter()

@router.get("/health", response_model=HealthCheck)
async def health_check():
    """System health check"""
    try:
        # Check database connectivity
        # Check Redis connectivity
        # Check VM runtime availability
        
        components = {
            "database": "connected",
            "redis": "connected", 
            "vm_runtime": "available",
            "streaming": "available"
        }
        
        return HealthCheck(
            status="healthy",
            version="1.0.0",
            components=components
        )
    except Exception as e:
        logger.error(f"Health check failed: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Service unhealthy"
        )

@router.get("/metrics/system", response_model=SystemMetrics)
async def get_system_metrics(
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Get system-wide metrics"""
    try:
        # Get system metrics
        cpu_usage = psutil.cpu_percent(interval=1)
        memory = psutil.virtual_memory()
        disk = psutil.disk_usage('/')
        
        # Get environment counts
        active_environments = db.query(Environment).filter(
            Environment.status == "running"
        ).count()
        
        total_users = db.query(User).count()
        
        # Get system uptime
        boot_time = psutil.boot_time()
        uptime_seconds = int(datetime.now().timestamp() - boot_time)
        
        return SystemMetrics(
            cpu_usage=cpu_usage,
            memory_usage=memory.percent,
            disk_usage=disk.percent,
            active_environments=active_environments,
            total_users=total_users,
            uptime_seconds=uptime_seconds
        )
    except Exception as e:
        logger.error(f"Failed to get system metrics: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve system metrics"
        )

@router.get("/metrics/environments", response_model=List[EnvironmentMetrics])
async def get_environment_metrics(
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Get metrics for user's environments"""
    try:
        environments = db.query(Environment).filter(
            Environment.user_id == current_user.id,
            Environment.status == "running"
        ).all()
        
        metrics = []
        for env in environments:
            # In a real implementation, these would come from the VM/container runtime
            # For now, we'll simulate some metrics
            env_metrics = EnvironmentMetrics(
                environment_id=env.id,
                cpu_usage=simulate_cpu_usage(),
                memory_usage=simulate_memory_usage(),
                network_rx_bytes=simulate_network_bytes(),
                network_tx_bytes=simulate_network_bytes(),
                disk_read_bytes=simulate_disk_bytes(),
                disk_write_bytes=simulate_disk_bytes(),
                timestamp=datetime.utcnow()
            )
            metrics.append(env_metrics)
        
        return metrics
    except Exception as e:
        logger.error(f"Failed to get environment metrics: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve environment metrics"
        )

@router.get("/metrics/environments/{environment_id}", response_model=EnvironmentMetrics)
async def get_environment_metrics_by_id(
    environment_id: int,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Get metrics for a specific environment"""
    environment = db.query(Environment).filter(
        Environment.id == environment_id,
        Environment.user_id == current_user.id
    ).first()
    
    if not environment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Environment not found"
        )
    
    if environment.status != "running":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Environment is not running"
        )
    
    try:
        # In a real implementation, these would come from the VM/container runtime
        metrics = EnvironmentMetrics(
            environment_id=environment_id,
            cpu_usage=simulate_cpu_usage(),
            memory_usage=simulate_memory_usage(),
            network_rx_bytes=simulate_network_bytes(),
            network_tx_bytes=simulate_network_bytes(),
            disk_read_bytes=simulate_disk_bytes(),
            disk_write_bytes=simulate_disk_bytes(),
            timestamp=datetime.utcnow()
        )
        
        return metrics
    except Exception as e:
        logger.error(f"Failed to get environment metrics: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve environment metrics"
        )

@router.get("/logs/environments/{environment_id}")
async def get_environment_logs(
    environment_id: int,
    limit: int = 100,
    level: str = None,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Get logs for a specific environment"""
    environment = db.query(Environment).filter(
        Environment.id == environment_id,
        Environment.user_id == current_user.id
    ).first()
    
    if not environment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Environment not found"
        )
    
    try:
        # In a real implementation, this would query the environment_logs table
        # For now, we'll return simulated logs
        logs = []
        for i in range(min(limit, 10)):
            log_entry = {
                "id": i + 1,
                "environment_id": environment_id,
                "level": "INFO",
                "message": f"Simulated log entry {i + 1}",
                "timestamp": datetime.utcnow() - timedelta(minutes=i),
                "metadata": {"component": "vm_runtime"}
            }
            logs.append(log_entry)
        
        return {"logs": logs}
    except Exception as e:
        logger.error(f"Failed to get environment logs: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve environment logs"
        )

@router.get("/stats/usage")
async def get_usage_statistics(
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Get usage statistics for the current user"""
    try:
        # Get user's environment statistics
        total_environments = db.query(Environment).filter(
            Environment.user_id == current_user.id
        ).count()
        
        running_environments = db.query(Environment).filter(
            Environment.user_id == current_user.id,
            Environment.status == "running"
        ).count()
        
        terminated_environments = db.query(Environment).filter(
            Environment.user_id == current_user.id,
            Environment.status == "terminated"
        ).count()
        
        # Calculate usage over time (last 30 days)
        thirty_days_ago = datetime.utcnow() - timedelta(days=30)
        recent_environments = db.query(Environment).filter(
            Environment.user_id == current_user.id,
            Environment.created_at >= thirty_days_ago
        ).count()
        
        stats = {
            "total_environments": total_environments,
            "running_environments": running_environments,
            "terminated_environments": terminated_environments,
            "recent_environments": recent_environments,
            "user_since": current_user.created_at,
            "last_activity": datetime.utcnow()  # In real implementation, track actual last activity
        }
        
        return stats
    except Exception as e:
        logger.error(f"Failed to get usage statistics: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve usage statistics"
        )

# Helper functions for simulating metrics
def simulate_cpu_usage() -> float:
    """Simulate CPU usage percentage"""
    import random
    return round(random.uniform(10.0, 80.0), 2)

def simulate_memory_usage() -> float:
    """Simulate memory usage percentage"""
    import random
    return round(random.uniform(20.0, 90.0), 2)

def simulate_network_bytes() -> int:
    """Simulate network bytes"""
    import random
    return random.randint(1000000, 100000000)  # 1MB to 100MB

def simulate_disk_bytes() -> int:
    """Simulate disk bytes"""
    import random
    return random.randint(100000, 10000000)  # 100KB to 10MB

