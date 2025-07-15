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
from ...orchestration.engine import orchestration_engine

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
        # Create environment record in database
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
        
        # Create environment in orchestration engine
        if environment_request.auto_start:
            try:
                orchestration_env = await orchestration_engine.create_environment(
                    str(db_environment.id),
                    environment_request.specification,
                    current_user.id
                )
                
                # Update database with orchestration info
                db_environment.status = EnvironmentStatus.PROVISIONING
                db.commit()
                
            except Exception as e:
                logger.error(f"Failed to create environment in orchestration engine: {str(e)}")
                db_environment.status = EnvironmentStatus.ERROR
                db.commit()
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=f"Failed to provision environment: {str(e)}"
                )
        
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
    
    # Sync status with orchestration engine
    for env in environments:
        try:
            orchestration_status = await orchestration_engine.get_environment_status(str(env.id))
            if orchestration_status and orchestration_status["status"] != env.status:
                env.status = orchestration_status["status"]
                env.streaming_port = orchestration_status.get("streaming_port")
                db.commit()
        except Exception as e:
            logger.warning(f"Failed to sync status for environment {env.id}: {str(e)}")
    
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
    
    # Sync status with orchestration engine
    try:
        orchestration_status = await orchestration_engine.get_environment_status(str(environment_id))
        if orchestration_status:
            environment.status = orchestration_status["status"]
            environment.streaming_port = orchestration_status.get("streaming_port")
            if orchestration_status.get("streaming_port"):
                environment.streaming_url = f"ws://localhost:{orchestration_status['streaming_port']}"
            db.commit()
    except Exception as e:
        logger.warning(f"Failed to sync status for environment {environment_id}: {str(e)}")
    
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
    
    try:
        # Start environment in orchestration engine
        if environment.status == EnvironmentStatus.REQUESTED:
            # Create and start new environment
            from ..models.schemas import EnvironmentSpec
            spec = EnvironmentSpec(**environment.specification)
            await orchestration_engine.create_environment(
                str(environment_id),
                spec,
                current_user.id
            )
        else:
            # Start existing environment
            await orchestration_engine.start_environment(str(environment_id))
        
        # Update database status
        environment.status = EnvironmentStatus.PROVISIONING
        environment.updated_at = datetime.utcnow()
        db.commit()
        
        logger.info(f"Environment {environment_id} start requested by user {current_user.username}")
        
        return {"message": "Environment start initiated", "status": "provisioning"}
        
    except Exception as e:
        logger.error(f"Failed to start environment {environment_id}: {str(e)}")
        environment.status = EnvironmentStatus.ERROR
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to start environment: {str(e)}"
        )

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
    
    try:
        # Stop environment in orchestration engine
        await orchestration_engine.stop_environment(str(environment_id))
        
        # Update database status
        environment.status = EnvironmentStatus.SUSPENDED
        environment.updated_at = datetime.utcnow()
        db.commit()
        
        logger.info(f"Environment {environment_id} stop requested by user {current_user.username}")
        
        return {"message": "Environment stop initiated"}
        
    except Exception as e:
        logger.error(f"Failed to stop environment {environment_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to stop environment: {str(e)}"
        )

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
    
    try:
        # Terminate environment in orchestration engine
        await orchestration_engine.terminate_environment(str(environment_id))
        
        # Mark as terminated in database
        environment.status = EnvironmentStatus.TERMINATED
        environment.terminated_at = datetime.utcnow()
        environment.updated_at = datetime.utcnow()
        db.commit()
        
        logger.info(f"Environment {environment_id} deleted by user {current_user.username}")
        
        return {"message": "Environment deleted"}
        
    except Exception as e:
        logger.error(f"Failed to delete environment {environment_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete environment: {str(e)}"
        )

@router.get("/{environment_id}/status")
async def get_environment_detailed_status(
    environment_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Get detailed environment status including orchestration info"""
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
        # Get detailed status from orchestration engine
        orchestration_status = await orchestration_engine.get_environment_status(str(environment_id))
        
        detailed_status = {
            "environment_id": environment_id,
            "database_status": environment.status,
            "orchestration_status": orchestration_status,
            "created_at": environment.created_at,
            "updated_at": environment.updated_at
        }
        
        return detailed_status
        
    except Exception as e:
        logger.error(f"Failed to get detailed status for environment {environment_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get environment status: {str(e)}"
        )

