"""
Streaming router for GenOS API
Handles WebSocket connections and streaming management
"""

from fastapi import APIRouter, Depends, HTTPException, status, WebSocket, WebSocketDisconnect
from sqlalchemy.orm import Session
from typing import List, Optional, Dict, Any
import json
import asyncio

from ..models.database import get_db, Environment, User
from ..models.schemas import ClientType
from ..routers.auth import get_current_active_user, get_user_from_token
from ..core.logging import get_logger
from ...streaming.gateway import streaming_gateway, StreamingProtocol, StreamQuality

logger = get_logger(__name__)
router = APIRouter()

@router.post("/connections")
async def create_streaming_connection(
    env_id: int,
    client_type: ClientType = ClientType.WEB,
    protocol: StreamingProtocol = StreamingProtocol.SPICE,
    quality: StreamQuality = StreamQuality.AUTO,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Create a new streaming connection"""
    
    # Verify environment exists and belongs to user
    environment = db.query(Environment).filter(
        Environment.id == env_id,
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
            detail=f"Environment must be running to create streaming connection. Current status: {environment.status}"
        )
    
    try:
        # Create streaming connection
        connection_id = await streaming_gateway.create_connection(
            str(env_id),
            current_user.id,
            client_type,
            protocol,
            quality
        )
        
        logger.info(f"Streaming connection {connection_id} created for environment {env_id}")
        
        return {
            "connection_id": connection_id,
            "websocket_url": f"ws://localhost:8765/{connection_id}",
            "protocol": protocol.value,
            "quality": quality.value,
            "status": "created"
        }
        
    except Exception as e:
        logger.error(f"Failed to create streaming connection: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create streaming connection: {str(e)}"
        )

@router.get("/connections/{connection_id}")
async def get_connection_info(
    connection_id: str,
    current_user: User = Depends(get_current_active_user)
):
    """Get streaming connection information"""
    
    try:
        connection_info = await streaming_gateway.get_connection_info(connection_id)
        
        if not connection_info:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Connection not found"
            )
        
        # Verify user owns the connection
        if connection_info["user_id"] != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied"
            )
        
        return connection_info
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get connection info: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get connection info"
        )

@router.patch("/connections/{connection_id}/quality")
async def update_connection_quality(
    connection_id: str,
    quality: StreamQuality,
    current_user: User = Depends(get_current_active_user)
):
    """Update streaming quality for a connection"""
    
    try:
        # Verify connection exists and belongs to user
        connection_info = await streaming_gateway.get_connection_info(connection_id)
        
        if not connection_info:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Connection not found"
            )
        
        if connection_info["user_id"] != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied"
            )
        
        # Update quality
        success = await streaming_gateway.update_quality(connection_id, quality)
        
        if not success:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Failed to update quality"
            )
        
        return {"message": "Quality updated", "quality": quality.value}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update connection quality: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update quality"
        )

@router.delete("/connections/{connection_id}")
async def disconnect_streaming_connection(
    connection_id: str,
    current_user: User = Depends(get_current_active_user)
):
    """Disconnect a streaming connection"""
    
    try:
        # Verify connection exists and belongs to user
        connection_info = await streaming_gateway.get_connection_info(connection_id)
        
        if not connection_info:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Connection not found"
            )
        
        if connection_info["user_id"] != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied"
            )
        
        # Disconnect
        success = await streaming_gateway.disconnect_client(connection_id)
        
        if not success:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Failed to disconnect"
            )
        
        return {"message": "Connection disconnected"}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to disconnect connection: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to disconnect"
        )

@router.get("/protocols")
async def get_supported_protocols():
    """Get list of supported streaming protocols"""
    return {
        "protocols": [
            {
                "name": "SPICE",
                "value": "spice",
                "description": "Simple Protocol for Independent Computing Environments",
                "features": ["high_performance", "audio", "clipboard", "usb_redirection"],
                "recommended_for": ["linux", "desktop_applications"]
            },
            {
                "name": "RDP",
                "value": "rdp",
                "description": "Remote Desktop Protocol",
                "features": ["windows_native", "audio", "clipboard", "file_transfer"],
                "recommended_for": ["windows", "office_applications"]
            },
            {
                "name": "VNC",
                "value": "vnc",
                "description": "Virtual Network Computing",
                "features": ["cross_platform", "simple", "lightweight"],
                "recommended_for": ["basic_desktop", "troubleshooting"]
            },
            {
                "name": "WebRTC",
                "value": "webrtc",
                "description": "Web Real-Time Communication",
                "features": ["low_latency", "browser_native", "peer_to_peer"],
                "recommended_for": ["web_browsers", "real_time_interaction"]
            }
        ]
    }

@router.get("/quality-profiles")
async def get_quality_profiles():
    """Get available streaming quality profiles"""
    return {
        "profiles": [
            {
                "name": "Auto",
                "value": "auto",
                "description": "Automatically adjust quality based on network conditions",
                "resolution": "adaptive",
                "frame_rate": "adaptive",
                "compression": "adaptive"
            },
            {
                "name": "Low",
                "value": "low",
                "description": "Optimized for slow connections",
                "resolution": "1024x768",
                "frame_rate": "15fps",
                "compression": "high"
            },
            {
                "name": "Medium",
                "value": "medium",
                "description": "Balanced quality and performance",
                "resolution": "1280x720",
                "frame_rate": "24fps",
                "compression": "medium"
            },
            {
                "name": "High",
                "value": "high",
                "description": "Best quality for fast connections",
                "resolution": "1920x1080",
                "frame_rate": "30fps",
                "compression": "low"
            }
        ]
    }

@router.websocket("/ws/{connection_id}")
async def websocket_endpoint(websocket: WebSocket, connection_id: str):
    """WebSocket endpoint for streaming connections"""
    
    await websocket.accept()
    
    try:
        # Connect to streaming gateway
        success = await streaming_gateway.connect_websocket(connection_id, websocket)
        
        if not success:
            await websocket.close(code=4004, reason="Invalid connection ID")
            return
        
        logger.info(f"WebSocket connected for streaming connection {connection_id}")
        
        # Handle messages
        while True:
            try:
                # Receive message from client
                data = await websocket.receive_text()
                message = json.loads(data)
                
                # Handle different message types
                message_type = message.get("type")
                
                if message_type == "input":
                    # Forward input to streaming gateway
                    await streaming_gateway.handle_input_event(connection_id, message)
                
                elif message_type == "ping":
                    # Respond to ping
                    await websocket.send_text(json.dumps({"type": "pong"}))
                
                elif message_type == "quality_change":
                    # Handle quality change
                    quality = StreamQuality(message.get("quality", "auto"))
                    await streaming_gateway.update_quality(connection_id, quality)
                
                elif message_type == "resolution_change":
                    # Handle resolution change
                    # This would be forwarded to the streaming gateway
                    pass
                
                else:
                    logger.warning(f"Unknown message type: {message_type}")
                
            except json.JSONDecodeError:
                logger.warning(f"Invalid JSON received from {connection_id}")
            except Exception as e:
                logger.error(f"Error handling WebSocket message: {str(e)}")
                break
    
    except WebSocketDisconnect:
        logger.info(f"WebSocket disconnected for connection {connection_id}")
    except Exception as e:
        logger.error(f"WebSocket error for connection {connection_id}: {str(e)}")
    finally:
        # Clean up connection
        try:
            await streaming_gateway.disconnect_client(connection_id)
        except:
            pass

@router.get("/stats")
async def get_streaming_stats(
    current_user: User = Depends(get_current_active_user)
):
    """Get streaming statistics"""
    
    try:
        # Get user's active connections
        user_connections = []
        
        for connection_id, connection in streaming_gateway.connections.items():
            if connection.user_id == current_user.id:
                user_connections.append({
                    "connection_id": connection_id,
                    "env_id": connection.env_id,
                    "protocol": connection.protocol.value,
                    "quality": connection.quality.value,
                    "state": connection.state.value,
                    "bandwidth_usage": connection.bandwidth_usage,
                    "frame_rate": connection.frame_rate,
                    "resolution": connection.resolution,
                    "created_at": connection.created_at,
                    "last_activity": connection.last_activity
                })
        
        return {
            "user_id": current_user.id,
            "active_connections": len(user_connections),
            "connections": user_connections,
            "total_bandwidth": sum(conn["bandwidth_usage"] for conn in user_connections)
        }
        
    except Exception as e:
        logger.error(f"Failed to get streaming stats: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get streaming stats"
        )

@router.get("/health")
async def streaming_health_check():
    """Check streaming gateway health"""
    
    try:
        gateway_status = {
            "running": streaming_gateway.running,
            "active_connections": len(streaming_gateway.connections),
            "active_environments": len(streaming_gateway.environment_connections),
            "websocket_server": streaming_gateway.websocket_server is not None,
            "spice_servers": len(streaming_gateway.spice_servers),
            "rdp_servers": len(streaming_gateway.rdp_servers)
        }
        
        overall_status = "healthy" if gateway_status["running"] else "unhealthy"
        
        return {
            "status": overall_status,
            "gateway": gateway_status,
            "timestamp": asyncio.get_event_loop().time()
        }
        
    except Exception as e:
        logger.error(f"Failed to get streaming health: {str(e)}")
        return {
            "status": "error",
            "error": str(e),
            "timestamp": asyncio.get_event_loop().time()
        }

