"""
Streaming router for GenOS API
"""

from fastapi import APIRouter, Depends, HTTPException, status, WebSocket, WebSocketDisconnect
from sqlalchemy.orm import Session
from typing import List, Dict, Any
import json
import asyncio

from ..models.database import get_db, Environment, Session as SessionModel, User
from ..models.schemas import StreamingConnection, StreamingSession, ClientType
from ..routers.auth import get_current_active_user
from ..core.logging import get_logger

logger = get_logger(__name__)
router = APIRouter()

# Active WebSocket connections
active_connections: Dict[int, List[WebSocket]] = {}

class ConnectionManager:
    """Manage WebSocket connections for streaming"""
    
    def __init__(self):
        self.active_connections: Dict[int, List[WebSocket]] = {}
    
    async def connect(self, websocket: WebSocket, environment_id: int):
        """Accept a WebSocket connection"""
        await websocket.accept()
        if environment_id not in self.active_connections:
            self.active_connections[environment_id] = []
        self.active_connections[environment_id].append(websocket)
        logger.info(f"WebSocket connected for environment {environment_id}")
    
    def disconnect(self, websocket: WebSocket, environment_id: int):
        """Remove a WebSocket connection"""
        if environment_id in self.active_connections:
            if websocket in self.active_connections[environment_id]:
                self.active_connections[environment_id].remove(websocket)
            if not self.active_connections[environment_id]:
                del self.active_connections[environment_id]
        logger.info(f"WebSocket disconnected for environment {environment_id}")
    
    async def send_personal_message(self, message: str, websocket: WebSocket):
        """Send a message to a specific WebSocket"""
        await websocket.send_text(message)
    
    async def broadcast_to_environment(self, message: str, environment_id: int):
        """Broadcast a message to all connections for an environment"""
        if environment_id in self.active_connections:
            for connection in self.active_connections[environment_id]:
                try:
                    await connection.send_text(message)
                except:
                    # Remove dead connections
                    self.active_connections[environment_id].remove(connection)

manager = ConnectionManager()

@router.post("/{environment_id}/connect", response_model=Dict[str, Any])
async def create_streaming_connection(
    environment_id: int,
    connection_request: StreamingConnection,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Create a streaming connection to an environment"""
    # Verify environment exists and belongs to user
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
            detail=f"Environment is not running (status: {environment.status})"
        )
    
    # Create session record
    session = SessionModel(
        user_id=current_user.id,
        environment_id=environment_id,
        client_type=connection_request.client_type,
        client_info={"protocol": connection_request.protocol, "quality": connection_request.quality}
    )
    
    db.add(session)
    db.commit()
    db.refresh(session)
    
    # Generate connection info
    connection_info = {
        "session_id": session.id,
        "environment_id": environment_id,
        "streaming_url": environment.streaming_url or f"ws://localhost:8000/api/v1/streaming/{environment_id}/ws",
        "protocol": connection_request.protocol,
        "quality": connection_request.quality,
        "controls": {
            "keyboard": True,
            "mouse": True,
            "clipboard": True,
            "audio": True
        }
    }
    
    logger.info(f"Streaming connection created for environment {environment_id} by user {current_user.username}")
    
    return connection_info

@router.websocket("/{environment_id}/ws")
async def websocket_endpoint(websocket: WebSocket, environment_id: int):
    """WebSocket endpoint for streaming"""
    await manager.connect(websocket, environment_id)
    
    try:
        # Send initial connection message
        await manager.send_personal_message(
            json.dumps({
                "type": "connection",
                "status": "connected",
                "environment_id": environment_id
            }),
            websocket
        )
        
        # Start streaming simulation (in real implementation, this would connect to SPICE/RDP)
        asyncio.create_task(simulate_stream(websocket, environment_id))
        
        while True:
            # Receive messages from client (input events)
            data = await websocket.receive_text()
            message = json.loads(data)
            
            # Handle different message types
            if message.get("type") == "input":
                await handle_input_event(message, environment_id)
            elif message.get("type") == "control":
                await handle_control_command(message, environment_id)
            
    except WebSocketDisconnect:
        manager.disconnect(websocket, environment_id)
        logger.info(f"WebSocket disconnected for environment {environment_id}")

@router.get("/{environment_id}/sessions", response_model=List[StreamingSession])
async def list_streaming_sessions(
    environment_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """List active streaming sessions for an environment"""
    # Verify environment belongs to user
    environment = db.query(Environment).filter(
        Environment.id == environment_id,
        Environment.user_id == current_user.id
    ).first()
    
    if not environment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Environment not found"
        )
    
    sessions = db.query(SessionModel).filter(
        SessionModel.environment_id == environment_id,
        SessionModel.is_active == True
    ).all()
    
    return sessions

@router.delete("/{environment_id}/sessions/{session_id}")
async def terminate_streaming_session(
    environment_id: int,
    session_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Terminate a streaming session"""
    # Verify environment belongs to user
    environment = db.query(Environment).filter(
        Environment.id == environment_id,
        Environment.user_id == current_user.id
    ).first()
    
    if not environment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Environment not found"
        )
    
    session = db.query(SessionModel).filter(
        SessionModel.id == session_id,
        SessionModel.environment_id == environment_id
    ).first()
    
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session not found"
        )
    
    # Mark session as inactive
    session.is_active = False
    session.ended_at = datetime.utcnow()
    db.commit()
    
    # Disconnect WebSocket if active
    if environment_id in manager.active_connections:
        await manager.broadcast_to_environment(
            json.dumps({
                "type": "session_terminated",
                "session_id": session_id
            }),
            environment_id
        )
    
    logger.info(f"Streaming session {session_id} terminated for environment {environment_id}")
    
    return {"message": "Session terminated"}

# Helper functions
async def simulate_stream(websocket: WebSocket, environment_id: int):
    """Simulate streaming data (placeholder for real SPICE/RDP integration)"""
    frame_count = 0
    
    try:
        while True:
            # Simulate frame data
            frame_data = {
                "type": "frame",
                "frame_id": frame_count,
                "timestamp": asyncio.get_event_loop().time(),
                "data": f"simulated_frame_data_{frame_count}",
                "width": 1920,
                "height": 1080
            }
            
            await manager.send_personal_message(
                json.dumps(frame_data),
                websocket
            )
            
            frame_count += 1
            await asyncio.sleep(1/30)  # 30 FPS simulation
            
    except Exception as e:
        logger.error(f"Streaming simulation error: {str(e)}")

async def handle_input_event(message: Dict[str, Any], environment_id: int):
    """Handle input events from client"""
    input_type = message.get("input_type")
    
    if input_type == "keyboard":
        # Handle keyboard input
        key = message.get("key")
        action = message.get("action")  # press, release
        logger.debug(f"Keyboard input: {key} {action} for environment {environment_id}")
        
    elif input_type == "mouse":
        # Handle mouse input
        x = message.get("x")
        y = message.get("y")
        button = message.get("button")
        action = message.get("action")  # move, click, release
        logger.debug(f"Mouse input: {action} at ({x}, {y}) button {button} for environment {environment_id}")
        
    elif input_type == "touch":
        # Handle touch input (mobile)
        touches = message.get("touches", [])
        logger.debug(f"Touch input: {len(touches)} touches for environment {environment_id}")

async def handle_control_command(message: Dict[str, Any], environment_id: int):
    """Handle control commands from client"""
    command = message.get("command")
    
    if command == "disconnect":
        logger.info(f"Disconnect command received for environment {environment_id}")
    elif command == "quality_change":
        quality = message.get("quality")
        logger.info(f"Quality change to {quality} for environment {environment_id}")
    elif command == "fullscreen":
        fullscreen = message.get("enabled")
        logger.info(f"Fullscreen {'enabled' if fullscreen else 'disabled'} for environment {environment_id}")

