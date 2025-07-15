"""
Streaming Gateway for GenOS
Manages real-time GUI streaming using SPICE and RDP protocols
"""

import asyncio
import json
import uuid
import websockets
import subprocess
from typing import Dict, List, Optional, Any, Set
from pathlib import Path
from enum import Enum
import logging
import socket
import struct
import ssl

from ..api.models.schemas import ClientType
from ..api.core.config import settings
from ..api.core.logging import get_logger

logger = get_logger(__name__)

class StreamingProtocol(Enum):
    """Supported streaming protocols"""
    SPICE = "spice"
    RDP = "rdp"
    VNC = "vnc"
    WEBRTC = "webrtc"

class StreamQuality(Enum):
    """Stream quality levels"""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    AUTO = "auto"

class ConnectionState(Enum):
    """Connection states"""
    CONNECTING = "connecting"
    CONNECTED = "connected"
    STREAMING = "streaming"
    DISCONNECTED = "disconnected"
    ERROR = "error"

class StreamingConnection:
    """Represents a streaming connection to an environment"""
    
    def __init__(self, connection_id: str, env_id: str, user_id: int, client_type: ClientType):
        self.connection_id = connection_id
        self.env_id = env_id
        self.user_id = user_id
        self.client_type = client_type
        self.protocol = StreamingProtocol.SPICE
        self.quality = StreamQuality.AUTO
        self.state = ConnectionState.CONNECTING
        self.websocket = None
        self.spice_process = None
        self.rdp_process = None
        self.created_at = asyncio.get_event_loop().time()
        self.last_activity = asyncio.get_event_loop().time()
        self.bandwidth_usage = 0
        self.frame_rate = 30
        self.resolution = (1920, 1080)
        self.compression_level = 6
        self.metadata = {}

class StreamingGateway:
    """Main streaming gateway for managing GUI streams"""
    
    def __init__(self):
        self.connections: Dict[str, StreamingConnection] = {}
        self.environment_connections: Dict[str, Set[str]] = {}  # env_id -> connection_ids
        self.websocket_server = None
        self.spice_servers: Dict[str, subprocess.Popen] = {}
        self.rdp_servers: Dict[str, subprocess.Popen] = {}
        self.running = False
        self.port_pool = list(range(5900, 6000))  # VNC/SPICE port range
        self.allocated_ports: Dict[str, int] = {}
    
    async def start(self):
        """Start the streaming gateway"""
        logger.info("Starting streaming gateway")
        self.running = True
        
        # Start WebSocket server for client connections
        await self._start_websocket_server()
        
        # Initialize streaming protocols
        await self._initialize_spice()
        await self._initialize_rdp()
        
        # Start monitoring tasks
        asyncio.create_task(self._monitor_connections())
        asyncio.create_task(self._cleanup_inactive_connections())
        
        logger.info("Streaming gateway started")
    
    async def stop(self):
        """Stop the streaming gateway"""
        logger.info("Stopping streaming gateway")
        self.running = False
        
        # Close all connections
        for connection_id in list(self.connections.keys()):
            await self.disconnect_client(connection_id)
        
        # Stop WebSocket server
        if self.websocket_server:
            self.websocket_server.close()
            await self.websocket_server.wait_closed()
        
        # Stop all streaming servers
        await self._stop_all_servers()
        
        logger.info("Streaming gateway stopped")
    
    async def create_connection(self, env_id: str, user_id: int, client_type: ClientType, 
                              protocol: StreamingProtocol = StreamingProtocol.SPICE,
                              quality: StreamQuality = StreamQuality.AUTO) -> str:
        """Create a new streaming connection"""
        connection_id = f"conn-{uuid.uuid4().hex[:8]}"
        
        logger.info(f"Creating streaming connection {connection_id} for environment {env_id}")
        
        connection = StreamingConnection(connection_id, env_id, user_id, client_type)
        connection.protocol = protocol
        connection.quality = quality
        
        # Determine optimal settings based on client type and quality
        await self._optimize_connection_settings(connection)
        
        # Store connection
        self.connections[connection_id] = connection
        
        # Track environment connections
        if env_id not in self.environment_connections:
            self.environment_connections[env_id] = set()
        self.environment_connections[env_id].add(connection_id)
        
        # Start streaming server for the environment if not already running
        await self._ensure_streaming_server(env_id, protocol)
        
        logger.info(f"Streaming connection {connection_id} created")
        return connection_id
    
    async def connect_websocket(self, connection_id: str, websocket) -> bool:
        """Connect a WebSocket to a streaming connection"""
        if connection_id not in self.connections:
            logger.error(f"Connection {connection_id} not found")
            return False
        
        connection = self.connections[connection_id]
        connection.websocket = websocket
        connection.state = ConnectionState.CONNECTED
        
        logger.info(f"WebSocket connected to {connection_id}")
        
        # Start streaming
        await self._start_streaming(connection)
        
        return True
    
    async def disconnect_client(self, connection_id: str) -> bool:
        """Disconnect a client"""
        if connection_id not in self.connections:
            return False
        
        connection = self.connections[connection_id]
        
        logger.info(f"Disconnecting client {connection_id}")
        
        # Close WebSocket
        if connection.websocket:
            try:
                await connection.websocket.close()
            except:
                pass
        
        # Update state
        connection.state = ConnectionState.DISCONNECTED
        
        # Remove from environment tracking
        if connection.env_id in self.environment_connections:
            self.environment_connections[connection.env_id].discard(connection_id)
            
            # Stop streaming server if no more connections
            if not self.environment_connections[connection.env_id]:
                await self._stop_streaming_server(connection.env_id)
                del self.environment_connections[connection.env_id]
        
        # Remove connection
        del self.connections[connection_id]
        
        logger.info(f"Client {connection_id} disconnected")
        return True
    
    async def handle_input_event(self, connection_id: str, event: Dict[str, Any]) -> bool:
        """Handle input event from client"""
        if connection_id not in self.connections:
            return False
        
        connection = self.connections[connection_id]
        connection.last_activity = asyncio.get_event_loop().time()
        
        # Forward input to appropriate streaming server
        if connection.protocol == StreamingProtocol.SPICE:
            await self._handle_spice_input(connection, event)
        elif connection.protocol == StreamingProtocol.RDP:
            await self._handle_rdp_input(connection, event)
        elif connection.protocol == StreamingProtocol.VNC:
            await self._handle_vnc_input(connection, event)
        
        return True
    
    async def get_connection_info(self, connection_id: str) -> Optional[Dict[str, Any]]:
        """Get connection information"""
        if connection_id not in self.connections:
            return None
        
        connection = self.connections[connection_id]
        
        return {
            "connection_id": connection_id,
            "env_id": connection.env_id,
            "user_id": connection.user_id,
            "client_type": connection.client_type.value,
            "protocol": connection.protocol.value,
            "quality": connection.quality.value,
            "state": connection.state.value,
            "resolution": connection.resolution,
            "frame_rate": connection.frame_rate,
            "bandwidth_usage": connection.bandwidth_usage,
            "created_at": connection.created_at,
            "last_activity": connection.last_activity
        }
    
    async def update_quality(self, connection_id: str, quality: StreamQuality) -> bool:
        """Update streaming quality for a connection"""
        if connection_id not in self.connections:
            return False
        
        connection = self.connections[connection_id]
        old_quality = connection.quality
        connection.quality = quality
        
        # Apply new quality settings
        await self._optimize_connection_settings(connection)
        await self._apply_quality_settings(connection)
        
        logger.info(f"Updated quality for {connection_id} from {old_quality.value} to {quality.value}")
        return True
    
    async def _start_websocket_server(self):
        """Start WebSocket server for client connections"""
        async def handle_websocket(websocket, path):
            try:
                # Extract connection ID from path
                connection_id = path.strip('/')
                
                if not await self.connect_websocket(connection_id, websocket):
                    await websocket.close(code=4004, reason="Invalid connection ID")
                    return
                
                # Handle messages
                async for message in websocket:
                    try:
                        data = json.loads(message)
                        await self._handle_websocket_message(connection_id, data)
                    except json.JSONDecodeError:
                        logger.warning(f"Invalid JSON from {connection_id}: {message}")
                    except Exception as e:
                        logger.error(f"Error handling message from {connection_id}: {str(e)}")
                
            except websockets.exceptions.ConnectionClosed:
                logger.info(f"WebSocket connection closed for {connection_id}")
            except Exception as e:
                logger.error(f"WebSocket error: {str(e)}")
            finally:
                if 'connection_id' in locals():
                    await self.disconnect_client(connection_id)
        
        # Start WebSocket server
        self.websocket_server = await websockets.serve(
            handle_websocket,
            "0.0.0.0",
            8765,  # WebSocket port
            ping_interval=20,
            ping_timeout=10
        )
        
        logger.info("WebSocket server started on port 8765")
    
    async def _handle_websocket_message(self, connection_id: str, data: Dict[str, Any]):
        """Handle WebSocket message from client"""
        message_type = data.get("type")
        
        if message_type == "input":
            await self.handle_input_event(connection_id, data)
        elif message_type == "quality_change":
            quality = StreamQuality(data.get("quality", "auto"))
            await self.update_quality(connection_id, quality)
        elif message_type == "ping":
            # Send pong response
            connection = self.connections.get(connection_id)
            if connection and connection.websocket:
                await connection.websocket.send(json.dumps({"type": "pong"}))
        elif message_type == "resolution_change":
            await self._handle_resolution_change(connection_id, data)
    
    async def _optimize_connection_settings(self, connection: StreamingConnection):
        """Optimize connection settings based on client type and quality"""
        # Mobile optimizations
        if connection.client_type in [ClientType.ANDROID, ClientType.IOS]:
            connection.resolution = (1280, 720)  # Lower resolution for mobile
            connection.frame_rate = 24  # Lower frame rate
            connection.compression_level = 8  # Higher compression
        
        # Quality-based optimizations
        if connection.quality == StreamQuality.LOW:
            connection.resolution = (1024, 768)
            connection.frame_rate = 15
            connection.compression_level = 9
        elif connection.quality == StreamQuality.MEDIUM:
            connection.resolution = (1280, 720)
            connection.frame_rate = 24
            connection.compression_level = 6
        elif connection.quality == StreamQuality.HIGH:
            connection.resolution = (1920, 1080)
            connection.frame_rate = 30
            connection.compression_level = 3
        # AUTO quality will be determined dynamically based on bandwidth
    
    async def _ensure_streaming_server(self, env_id: str, protocol: StreamingProtocol):
        """Ensure streaming server is running for environment"""
        server_key = f"{env_id}-{protocol.value}"
        
        if protocol == StreamingProtocol.SPICE:
            if server_key not in self.spice_servers:
                await self._start_spice_server(env_id)
        elif protocol == StreamingProtocol.RDP:
            if server_key not in self.rdp_servers:
                await self._start_rdp_server(env_id)
    
    async def _start_spice_server(self, env_id: str):
        """Start SPICE server for environment"""
        logger.info(f"Starting SPICE server for environment {env_id}")
        
        # Allocate port
        port = self._allocate_port(env_id)
        
        # SPICE server command
        cmd = [
            "spice-server",
            "--port", str(port),
            "--addr", "0.0.0.0",
            "--disable-ticketing",
            "--streaming-video", "all",
            "--jpeg-wan-compression", "auto",
            "--zlib-glz-wan-compression", "auto"
        ]
        
        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            server_key = f"{env_id}-spice"
            self.spice_servers[server_key] = process
            
            logger.info(f"SPICE server started for {env_id} on port {port}")
            
        except Exception as e:
            logger.error(f"Failed to start SPICE server for {env_id}: {str(e)}")
            self._release_port(env_id)
            raise
    
    async def _start_rdp_server(self, env_id: str):
        """Start RDP server for environment"""
        logger.info(f"Starting RDP server for environment {env_id}")
        
        # Allocate port
        port = self._allocate_port(env_id)
        
        # RDP server command (using xrdp)
        cmd = [
            "xrdp",
            "--port", str(port),
            "--nodaemon"
        ]
        
        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            server_key = f"{env_id}-rdp"
            self.rdp_servers[server_key] = process
            
            logger.info(f"RDP server started for {env_id} on port {port}")
            
        except Exception as e:
            logger.error(f"Failed to start RDP server for {env_id}: {str(e)}")
            self._release_port(env_id)
            raise
    
    async def _start_streaming(self, connection: StreamingConnection):
        """Start streaming for a connection"""
        logger.info(f"Starting streaming for connection {connection.connection_id}")
        
        connection.state = ConnectionState.STREAMING
        
        # Start streaming task based on protocol
        if connection.protocol == StreamingProtocol.SPICE:
            asyncio.create_task(self._stream_spice(connection))
        elif connection.protocol == StreamingProtocol.RDP:
            asyncio.create_task(self._stream_rdp(connection))
        elif connection.protocol == StreamingProtocol.VNC:
            asyncio.create_task(self._stream_vnc(connection))
        elif connection.protocol == StreamingProtocol.WEBRTC:
            asyncio.create_task(self._stream_webrtc(connection))
    
    async def _stream_spice(self, connection: StreamingConnection):
        """Stream SPICE protocol data"""
        logger.info(f"Starting SPICE streaming for {connection.connection_id}")
        
        try:
            # Connect to SPICE server
            port = self.allocated_ports.get(connection.env_id)
            if not port:
                raise RuntimeError("No SPICE server port allocated")
            
            # Simulate SPICE streaming (in real implementation, connect to actual SPICE server)
            frame_count = 0
            while connection.state == ConnectionState.STREAMING and connection.websocket:
                # Simulate frame data
                frame_data = {
                    "type": "frame",
                    "protocol": "spice",
                    "frame_id": frame_count,
                    "timestamp": asyncio.get_event_loop().time(),
                    "resolution": connection.resolution,
                    "data": f"spice_frame_data_{frame_count}",  # Base64 encoded frame data
                    "compression": connection.compression_level
                }
                
                try:
                    await connection.websocket.send(json.dumps(frame_data))
                    connection.bandwidth_usage += len(json.dumps(frame_data))
                except websockets.exceptions.ConnectionClosed:
                    break
                
                frame_count += 1
                await asyncio.sleep(1.0 / connection.frame_rate)
                
        except Exception as e:
            logger.error(f"SPICE streaming error for {connection.connection_id}: {str(e)}")
            connection.state = ConnectionState.ERROR
    
    async def _stream_rdp(self, connection: StreamingConnection):
        """Stream RDP protocol data"""
        logger.info(f"Starting RDP streaming for {connection.connection_id}")
        
        # Similar implementation to SPICE but for RDP
        # In real implementation, this would connect to RDP server and relay data
        pass
    
    async def _stream_vnc(self, connection: StreamingConnection):
        """Stream VNC protocol data"""
        logger.info(f"Starting VNC streaming for {connection.connection_id}")
        
        # VNC streaming implementation
        pass
    
    async def _stream_webrtc(self, connection: StreamingConnection):
        """Stream WebRTC data"""
        logger.info(f"Starting WebRTC streaming for {connection.connection_id}")
        
        # WebRTC streaming implementation
        pass
    
    def _allocate_port(self, env_id: str) -> int:
        """Allocate a port for streaming server"""
        for port in self.port_pool:
            if port not in self.allocated_ports.values():
                self.allocated_ports[env_id] = port
                return port
        
        raise RuntimeError("No available ports for streaming")
    
    def _release_port(self, env_id: str):
        """Release allocated port"""
        if env_id in self.allocated_ports:
            del self.allocated_ports[env_id]
    
    async def _initialize_spice(self):
        """Initialize SPICE protocol support"""
        logger.info("Initializing SPICE protocol support")
        # Check if SPICE tools are available
        # In real implementation, verify spice-server installation
    
    async def _initialize_rdp(self):
        """Initialize RDP protocol support"""
        logger.info("Initializing RDP protocol support")
        # Check if RDP tools are available
        # In real implementation, verify xrdp installation
    
    async def _monitor_connections(self):
        """Monitor connection health and performance"""
        while self.running:
            try:
                current_time = asyncio.get_event_loop().time()
                
                for connection in self.connections.values():
                    # Check for inactive connections
                    if current_time - connection.last_activity > 300:  # 5 minutes
                        logger.warning(f"Connection {connection.connection_id} inactive")
                    
                    # Monitor bandwidth and adjust quality if needed
                    if connection.quality == StreamQuality.AUTO:
                        await self._auto_adjust_quality(connection)
                
                await asyncio.sleep(30)  # Check every 30 seconds
                
            except Exception as e:
                logger.error(f"Connection monitoring error: {str(e)}")
                await asyncio.sleep(30)
    
    async def _cleanup_inactive_connections(self):
        """Cleanup inactive connections"""
        while self.running:
            try:
                current_time = asyncio.get_event_loop().time()
                inactive_connections = []
                
                for connection_id, connection in self.connections.items():
                    # Mark connections inactive after 10 minutes
                    if current_time - connection.last_activity > 600:
                        inactive_connections.append(connection_id)
                
                # Disconnect inactive connections
                for connection_id in inactive_connections:
                    logger.info(f"Cleaning up inactive connection {connection_id}")
                    await self.disconnect_client(connection_id)
                
                await asyncio.sleep(60)  # Check every minute
                
            except Exception as e:
                logger.error(f"Cleanup error: {str(e)}")
                await asyncio.sleep(60)
    
    async def _auto_adjust_quality(self, connection: StreamingConnection):
        """Automatically adjust quality based on performance"""
        # Simple bandwidth-based quality adjustment
        if connection.bandwidth_usage > 10000000:  # 10MB/s
            if connection.quality != StreamQuality.LOW:
                connection.quality = StreamQuality.LOW
                await self._apply_quality_settings(connection)
        elif connection.bandwidth_usage < 1000000:  # 1MB/s
            if connection.quality != StreamQuality.HIGH:
                connection.quality = StreamQuality.HIGH
                await self._apply_quality_settings(connection)
    
    async def _apply_quality_settings(self, connection: StreamingConnection):
        """Apply quality settings to active connection"""
        await self._optimize_connection_settings(connection)
        
        # Send quality update to client
        if connection.websocket:
            quality_update = {
                "type": "quality_update",
                "quality": connection.quality.value,
                "resolution": connection.resolution,
                "frame_rate": connection.frame_rate,
                "compression": connection.compression_level
            }
            
            try:
                await connection.websocket.send(json.dumps(quality_update))
            except:
                pass
    
    async def _handle_spice_input(self, connection: StreamingConnection, event: Dict[str, Any]):
        """Handle SPICE input events"""
        # Forward input to SPICE server
        logger.debug(f"SPICE input from {connection.connection_id}: {event}")
    
    async def _handle_rdp_input(self, connection: StreamingConnection, event: Dict[str, Any]):
        """Handle RDP input events"""
        # Forward input to RDP server
        logger.debug(f"RDP input from {connection.connection_id}: {event}")
    
    async def _handle_vnc_input(self, connection: StreamingConnection, event: Dict[str, Any]):
        """Handle VNC input events"""
        # Forward input to VNC server
        logger.debug(f"VNC input from {connection.connection_id}: {event}")
    
    async def _handle_resolution_change(self, connection_id: str, data: Dict[str, Any]):
        """Handle resolution change request"""
        if connection_id not in self.connections:
            return
        
        connection = self.connections[connection_id]
        new_resolution = data.get("resolution", connection.resolution)
        
        if isinstance(new_resolution, list) and len(new_resolution) == 2:
            connection.resolution = tuple(new_resolution)
            logger.info(f"Resolution changed for {connection_id}: {connection.resolution}")
    
    async def _stop_streaming_server(self, env_id: str):
        """Stop streaming server for environment"""
        logger.info(f"Stopping streaming servers for environment {env_id}")
        
        # Stop SPICE server
        spice_key = f"{env_id}-spice"
        if spice_key in self.spice_servers:
            process = self.spice_servers[spice_key]
            process.terminate()
            try:
                await asyncio.wait_for(process.wait(), timeout=5)
            except asyncio.TimeoutError:
                process.kill()
            del self.spice_servers[spice_key]
        
        # Stop RDP server
        rdp_key = f"{env_id}-rdp"
        if rdp_key in self.rdp_servers:
            process = self.rdp_servers[rdp_key]
            process.terminate()
            try:
                await asyncio.wait_for(process.wait(), timeout=5)
            except asyncio.TimeoutError:
                process.kill()
            del self.rdp_servers[rdp_key]
        
        # Release port
        self._release_port(env_id)
    
    async def _stop_all_servers(self):
        """Stop all streaming servers"""
        logger.info("Stopping all streaming servers")
        
        # Stop all SPICE servers
        for process in self.spice_servers.values():
            process.terminate()
        
        # Stop all RDP servers
        for process in self.rdp_servers.values():
            process.terminate()
        
        # Wait for processes to terminate
        await asyncio.sleep(2)
        
        # Force kill if necessary
        for process in list(self.spice_servers.values()) + list(self.rdp_servers.values()):
            if process.poll() is None:
                process.kill()
        
        self.spice_servers.clear()
        self.rdp_servers.clear()
        self.allocated_ports.clear()

# Global streaming gateway instance
streaming_gateway = StreamingGateway()

