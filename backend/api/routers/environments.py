"""
Environments router for GenOS API
"""

from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import datetime

from ..models.database import get_db, Environment, User
from ..models.schemas import (
    EnvironmentRequest, Environment as EnvironmentSchema, 
    EnvironmentUpdate, EnvironmentStatus, NLPCommand, NLPResponse
)
from ..routers.auth import get_current_active_user
from ..nlp.parser import EnvironmentParser
from ..core.logging import get_logger

logger = get_logger(__name__)
router = APIRouter()

# Global parser instance
parser = EnvironmentParser()

@router.post("/parse-command", response_model=NLPResponse)
async def parse_natural_language_command(
    nlp_command: NLPCommand,
    current_user: User = Depends(get_current_active_user)
):
    """
    Parse natural language command into environment specification
    
    Example commands:
    - "I need a Linux environment with Tor browser for secure browsing"
    - "Create a Ubuntu desktop with Firefox and VPN"
    - "Launch isolated Windows 10 with Office suite"
    """
    try:
        specification = await parser.parse_command(
            nlp_command.command, 
            nlp_command.context
        )
        
        logger.info(f"User {current_user.username} parsed command: {nlp_command.command}")
        
        return NLPResponse(
            command=nlp_command.command,
            specification=specification,
            confidence=0.85,  # TODO: Implement actual confidence scoring
            warnings=None
        )
    except Exception as e:
        logger.error(f"Failed to parse command: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to parse command: {str(e)}"
        )

@router.get("/suggestions")
async def get_command_suggestions(
    partial_command: Optional[str] = "",
    current_user: User = Depends(get_current_active_user)
):
    """Get command suggestions for autocomplete"""
    try:
        suggestions = await parser.get_suggestions(partial_command or "")
        return {"suggestions": suggestions}
    except Exception as e:
        logger.error(f"Failed to get suggestions: {str(e)}")
        return {"suggestions": []}

@router.post("/", response_model=EnvironmentSchema)
async def create_environment(
    environment_request: EnvironmentRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Create a new environment"""
    try:
        # Create environment record
        db_environment = Environment(
            user_id=current_user.id,
            name=environment_request.name,
            description=environment_request.description,
            specification=environment_request.specification.dict(),
            status=EnvironmentStatus.REQUESTED
        )
        
        db.add(db_environment)
        db.commit()
        db.refresh(db_environment)
        
        logger.info(f"Environment {db_environment.id} created for user {current_user.username}")
        
        # Start provisioning in background if auto_start is True
        if environment_request.auto_start:
            background_tasks.add_task(provision_environment, db_environment.id)
        
        return db_environment
        
    except Exception as e:
        logger.error(f"Failed to create environment: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create environment: {str(e)}"
        )

@router.get("/", response_model=List[EnvironmentSchema])
async def list_environments(
    skip: int = 0,
    limit: int = 100,
    status_filter: Optional[EnvironmentStatus] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """List user's environments"""
    query = db.query(Environment).filter(Environment.user_id == current_user.id)
    
    if status_filter:
        query = query.filter(Environment.status == status_filter)
    
    environments = query.offset(skip).limit(limit).all()
    return environments

@router.get("/{environment_id}", response_model=EnvironmentSchema)
async def get_environment(
    environment_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Get environment details"""
    environment = db.query(Environment).filter(
        Environment.id == environment_id,
        Environment.user_id == current_user.id
    ).first()
    
    if not environment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Environment not found"
        )
    
    return environment

@router.patch("/{environment_id}", response_model=EnvironmentSchema)
async def update_environment(
    environment_id: int,
    environment_update: EnvironmentUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Update environment"""
    environment = db.query(Environment).filter(
        Environment.id == environment_id,
        Environment.user_id == current_user.id
    ).first()
    
    if not environment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Environment not found"
        )
    
    # Update fields
    update_data = environment_update.dict(exclude_unset=True)
    for field, value in update_data.items():
        setattr(environment, field, value)
    
    environment.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(environment)
    
    logger.info(f"Environment {environment_id} updated by user {current_user.username}")
    
    return environment

@router.post("/{environment_id}/start")
async def start_environment(
    environment_id: int,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Start an environment"""
    environment = db.query(Environment).filter(
        Environment.id == environment_id,
        Environment.user_id == current_user.id
    ).first()
    
    if not environment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Environment not found"
        )
    
    if environment.status not in [EnvironmentStatus.REQUESTED, EnvironmentStatus.SUSPENDED]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot start environment in status: {environment.status}"
        )
    
    # Update status and start provisioning
    environment.status = EnvironmentStatus.PROVISIONING
    environment.updated_at = datetime.utcnow()
    db.commit()
    
    background_tasks.add_task(provision_environment, environment_id)
    
    logger.info(f"Environment {environment_id} start requested by user {current_user.username}")
    
    return {"message": "Environment start initiated", "status": "provisioning"}

@router.post("/{environment_id}/stop")
async def stop_environment(
    environment_id: int,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Stop an environment"""
    environment = db.query(Environment).filter(
        Environment.id == environment_id,
        Environment.user_id == current_user.id
    ).first()
    
    if not environment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Environment not found"
        )
    
    if environment.status != EnvironmentStatus.RUNNING:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot stop environment in status: {environment.status}"
        )
    
    background_tasks.add_task(stop_environment_task, environment_id)
    
    logger.info(f"Environment {environment_id} stop requested by user {current_user.username}")
    
    return {"message": "Environment stop initiated"}

@router.delete("/{environment_id}")
async def delete_environment(
    environment_id: int,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Delete an environment"""
    environment = db.query(Environment).filter(
        Environment.id == environment_id,
        Environment.user_id == current_user.id
    ).first()
    
    if not environment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Environment not found"
        )
    
    # Stop environment if running
    if environment.status == EnvironmentStatus.RUNNING:
        background_tasks.add_task(stop_environment_task, environment_id)
    
    # Mark as terminated
    environment.status = EnvironmentStatus.TERMINATED
    environment.terminated_at = datetime.utcnow()
    environment.updated_at = datetime.utcnow()
    db.commit()
    
    logger.info(f"Environment {environment_id} deleted by user {current_user.username}")
    
    return {"message": "Environment deleted"}

# Background tasks
async def provision_environment(environment_id: int):
    """Background task to provision an environment"""
    # TODO: Implement actual VM/container provisioning
    # This is a placeholder that simulates provisioning
    
    logger.info(f"Starting provisioning for environment {environment_id}")
    
    # Simulate provisioning delay
    import asyncio
    await asyncio.sleep(5)
    
    # Update environment status (in real implementation, this would be done by orchestration service)
    # For now, we'll just log the completion
    logger.info(f"Environment {environment_id} provisioning completed (simulated)")

async def stop_environment_task(environment_id: int):
    """Background task to stop an environment"""
    # TODO: Implement actual VM/container stopping
    
    logger.info(f"Stopping environment {environment_id}")
    
    # Simulate stop delay
    import asyncio
    await asyncio.sleep(2)
    
    logger.info(f"Environment {environment_id} stopped (simulated)")

