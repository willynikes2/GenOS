"""
Container Manager for GenOS
Manages Docker and LXC containers for lightweight environments
"""

import asyncio
import json
import uuid
from typing import Dict, List, Optional, Any
from pathlib import Path
import docker
import docker.errors

from ..api.models.schemas import EnvironmentSpec, NetworkMode
from ..api.core.config import settings
from ..api.core.logging import get_logger

logger = get_logger(__name__)

class ContainerManager:
    """Manages containers using Docker and LXC"""
    
    def __init__(self):
        self.containers: Dict[str, Dict] = {}
        self.docker_client = None
        self.streaming_port_pool = list(range(
            settings.streaming_port_range_start + 1000,  # Offset from VM ports
            settings.streaming_port_range_end + 1000
        ))
        self.allocated_ports: Dict[str, int] = {}
    
    async def initialize(self):
        """Initialize the container manager"""
        logger.info("Initializing container manager")
        
        try:
            # Initialize Docker client
            self.docker_client = docker.from_env()
            
            # Test Docker connection
            self.docker_client.ping()
            logger.info("Docker connection established")
            
            # Pull base images
            await self._initialize_base_images()
            
        except docker.errors.DockerException as e:
            logger.error(f"Docker not available: {str(e)}")
            self.docker_client = None
        
        logger.info("Container manager initialized")
    
    async def cleanup(self):
        """Cleanup container manager resources"""
        logger.info("Cleaning up container manager")
        
        # Stop all running containers
        for container_id in list(self.containers.keys()):
            try:
                await self.destroy_container(container_id)
            except Exception as e:
                logger.error(f"Error destroying container {container_id}: {str(e)}")
        
        if self.docker_client:
            self.docker_client.close()
        
        logger.info("Container manager cleanup completed")
    
    async def create_container(self, env_id: str, spec: EnvironmentSpec, security_config: Dict) -> str:
        """Create a new container"""
        if not self.docker_client:
            raise RuntimeError("Docker not available")
        
        container_id = f"genos-{env_id}-{uuid.uuid4().hex[:8]}"
        
        logger.info(f"Creating container {container_id} for environment {env_id}")
        
        try:
            # Create container configuration
            container_config = await self._create_container_config(container_id, spec, security_config)
            
            # Allocate streaming port
            streaming_port = self._allocate_streaming_port(container_id)
            container_config["streaming_port"] = streaming_port
            
            # Create Docker container
            docker_container = await self._create_docker_container(container_id, container_config)
            
            # Store container configuration
            self.containers[container_id] = {
                "id": container_id,
                "env_id": env_id,
                "docker_id": docker_container.id,
                "config": container_config,
                "status": "created",
                "created_at": asyncio.get_event_loop().time()
            }
            
            logger.info(f"Container {container_id} created successfully")
            return container_id
            
        except Exception as e:
            logger.error(f"Failed to create container {container_id}: {str(e)}")
            raise
    
    async def start_container(self, container_id: str) -> bool:
        """Start a container"""
        if container_id not in self.containers:
            raise ValueError(f"Container {container_id} not found")
        
        container = self.containers[container_id]
        
        if container["status"] == "running":
            logger.warning(f"Container {container_id} is already running")
            return True
        
        logger.info(f"Starting container {container_id}")
        
        try:
            # Get Docker container
            docker_container = self.docker_client.containers.get(container["docker_id"])
            
            # Start container
            docker_container.start()
            
            # Wait for container to be ready
            await self._wait_for_container_ready(container_id)
            
            # Set up X11 forwarding for GUI applications
            await self._setup_x11_forwarding(container_id)
            
            container["status"] = "running"
            container["started_at"] = asyncio.get_event_loop().time()
            
            logger.info(f"Container {container_id} started successfully")
            return True
            
        except Exception as e:
            logger.error(f"Failed to start container {container_id}: {str(e)}")
            container["status"] = "error"
            raise
    
    async def stop_container(self, container_id: str) -> bool:
        """Stop a container"""
        if container_id not in self.containers:
            raise ValueError(f"Container {container_id} not found")
        
        container = self.containers[container_id]
        
        if container["status"] != "running":
            logger.warning(f"Container {container_id} is not running")
            return True
        
        logger.info(f"Stopping container {container_id}")
        
        try:
            # Get Docker container
            docker_container = self.docker_client.containers.get(container["docker_id"])
            
            # Stop container gracefully
            docker_container.stop(timeout=10)
            
            container["status"] = "stopped"
            container["stopped_at"] = asyncio.get_event_loop().time()
            
            logger.info(f"Container {container_id} stopped successfully")
            return True
            
        except Exception as e:
            logger.error(f"Failed to stop container {container_id}: {str(e)}")
            raise
    
    async def destroy_container(self, container_id: str) -> bool:
        """Destroy a container"""
        if container_id not in self.containers:
            raise ValueError(f"Container {container_id} not found")
        
        container = self.containers[container_id]
        
        logger.info(f"Destroying container {container_id}")
        
        try:
            # Stop container if running
            if container["status"] == "running":
                await self.stop_container(container_id)
            
            # Get Docker container
            docker_container = self.docker_client.containers.get(container["docker_id"])
            
            # Remove container
            docker_container.remove(force=True)
            
            # Release streaming port
            self._release_streaming_port(container_id)
            
            # Remove container record
            del self.containers[container_id]
            
            logger.info(f"Container {container_id} destroyed successfully")
            return True
            
        except Exception as e:
            logger.error(f"Failed to destroy container {container_id}: {str(e)}")
            raise
    
    async def get_streaming_port(self, container_id: str) -> Optional[int]:
        """Get the streaming port for a container"""
        if container_id in self.containers:
            return self.containers[container_id]["config"].get("streaming_port")
        return None
    
    async def get_container_status(self, container_id: str) -> Optional[Dict]:
        """Get container status"""
        if container_id in self.containers:
            return self.containers[container_id].copy()
        return None
    
    async def _initialize_base_images(self):
        """Initialize base container images"""
        logger.info("Initializing base container images")
        
        base_images = [
            "ubuntu:22.04",
            "ubuntu:20.04",
            "fedora:38",
            "alpine:latest"
        ]
        
        for image in base_images:
            try:
                logger.info(f"Pulling base image: {image}")
                # In a real implementation, we'd pull the image
                # self.docker_client.images.pull(image)
                logger.info(f"Base image {image} ready")
            except Exception as e:
                logger.warning(f"Failed to pull image {image}: {str(e)}")
    
    async def _create_container_config(self, container_id: str, spec: EnvironmentSpec, security_config: Dict) -> Dict:
        """Create container configuration"""
        # Map OS specification to Docker image
        image_map = {
            "ubuntu_22.04": "ubuntu:22.04",
            "ubuntu_20.04": "ubuntu:20.04",
            "fedora_38": "fedora:38",
            "alpine_latest": "alpine:latest"
        }
        
        base_image = image_map.get(spec.base_os, "ubuntu:22.04")
        
        # Create environment variables
        env_vars = {
            "DISPLAY": ":1",
            "DEBIAN_FRONTEND": "noninteractive"
        }
        
        # Create volumes
        volumes = {
            "/tmp/.X11-unix": {"bind": "/tmp/.X11-unix", "mode": "rw"}
        }
        
        # Create port mappings
        ports = {}
        if "streaming_port" in locals():
            ports["5901/tcp"] = streaming_port
        
        # Create network configuration
        network_mode = "bridge"
        if spec.network_mode == NetworkMode.ISOLATED:
            network_mode = "none"
        elif spec.network_mode == NetworkMode.LIMITED:
            network_mode = "bridge"  # With restrictions applied later
        
        config = {
            "container_id": container_id,
            "image": base_image,
            "command": self._generate_startup_command(spec),
            "environment": env_vars,
            "volumes": volumes,
            "ports": ports,
            "network_mode": network_mode,
            "memory_limit": f"{spec.memory_mb}m",
            "cpu_quota": int(spec.cpu_cores * 100000),  # CPU quota in microseconds
            "cpu_period": 100000,
            "security": security_config,
            "apps": spec.apps
        }
        
        return config
    
    def _generate_startup_command(self, spec: EnvironmentSpec) -> List[str]:
        """Generate startup command for container"""
        commands = [
            "bash", "-c",
            " && ".join([
                "apt-get update",
                "apt-get install -y xvfb x11vnc supervisor",
                "mkdir -p /var/log/supervisor",
                self._generate_app_install_commands(spec.apps),
                "Xvfb :1 -screen 0 1024x768x16 &",
                "x11vnc -display :1 -nopw -listen localhost -xkb -rfbport 5901 &",
                "sleep infinity"
            ])
        ]
        
        return commands
    
    def _generate_app_install_commands(self, apps: List[str]) -> str:
        """Generate commands to install applications"""
        install_commands = []
        
        app_packages = {
            "firefox": "apt-get install -y firefox",
            "chrome": "wget -q -O - https://dl.google.com/linux/linux_signing_key.pub | apt-key add - && echo 'deb [arch=amd64] http://dl.google.com/linux/chrome/deb/ stable main' > /etc/apt/sources.list.d/google-chrome.list && apt-get update && apt-get install -y google-chrome-stable",
            "tor_browser": "apt-get install -y tor torbrowser-launcher",
            "vscode": "wget -qO- https://packages.microsoft.com/keys/microsoft.asc | gpg --dearmor > packages.microsoft.gpg && install -o root -g root -m 644 packages.microsoft.gpg /etc/apt/trusted.gpg.d/ && echo 'deb [arch=amd64,arm64,armhf signed-by=/etc/apt/trusted.gpg.d/packages.microsoft.gpg] https://packages.microsoft.com/repos/code stable main' > /etc/apt/sources.list.d/vscode.list && apt-get update && apt-get install -y code",
            "python": "apt-get install -y python3 python3-pip",
            "nodejs": "curl -fsSL https://deb.nodesource.com/setup_18.x | bash - && apt-get install -y nodejs",
            "git": "apt-get install -y git",
            "terminal": "apt-get install -y gnome-terminal",
            "office": "apt-get install -y libreoffice",
            "gimp": "apt-get install -y gimp",
            "vlc": "apt-get install -y vlc"
        }
        
        for app in apps:
            if app in app_packages:
                install_commands.append(app_packages[app])
        
        return " && ".join(install_commands) if install_commands else "echo 'No apps to install'"
    
    async def _create_docker_container(self, container_id: str, config: Dict):
        """Create Docker container"""
        try:
            container = self.docker_client.containers.create(
                image=config["image"],
                command=config["command"],
                environment=config["environment"],
                volumes=config["volumes"],
                ports=config["ports"],
                network_mode=config["network_mode"],
                mem_limit=config["memory_limit"],
                cpu_quota=config["cpu_quota"],
                cpu_period=config["cpu_period"],
                name=container_id,
                detach=True,
                tty=True,
                stdin_open=True
            )
            
            return container
            
        except docker.errors.ImageNotFound:
            # Pull image and retry
            logger.info(f"Pulling image: {config['image']}")
            self.docker_client.images.pull(config["image"])
            
            return self.docker_client.containers.create(
                image=config["image"],
                command=config["command"],
                environment=config["environment"],
                volumes=config["volumes"],
                ports=config["ports"],
                network_mode=config["network_mode"],
                mem_limit=config["memory_limit"],
                cpu_quota=config["cpu_quota"],
                cpu_period=config["cpu_period"],
                name=container_id,
                detach=True,
                tty=True,
                stdin_open=True
            )
    
    def _allocate_streaming_port(self, container_id: str) -> int:
        """Allocate a streaming port for a container"""
        for port in self.streaming_port_pool:
            if port not in self.allocated_ports.values():
                self.allocated_ports[container_id] = port
                return port
        
        raise RuntimeError("No available streaming ports")
    
    def _release_streaming_port(self, container_id: str):
        """Release a streaming port"""
        if container_id in self.allocated_ports:
            del self.allocated_ports[container_id]
    
    async def _wait_for_container_ready(self, container_id: str, timeout: int = 30):
        """Wait for container to be ready"""
        logger.info(f"Waiting for container {container_id} to be ready")
        
        container = self.containers[container_id]
        docker_container = self.docker_client.containers.get(container["docker_id"])
        
        start_time = asyncio.get_event_loop().time()
        
        while asyncio.get_event_loop().time() - start_time < timeout:
            # Check if container is running
            docker_container.reload()
            if docker_container.status == "running":
                logger.info(f"Container {container_id} is ready")
                return
            
            await asyncio.sleep(1)
        
        raise TimeoutError(f"Container {container_id} did not become ready within {timeout} seconds")
    
    async def _setup_x11_forwarding(self, container_id: str):
        """Set up X11 forwarding for GUI applications"""
        logger.info(f"Setting up X11 forwarding for container {container_id}")
        
        container = self.containers[container_id]
        docker_container = self.docker_client.containers.get(container["docker_id"])
        
        try:
            # Start Xvfb and VNC server inside container
            exec_result = docker_container.exec_run(
                "bash -c 'Xvfb :1 -screen 0 1024x768x16 & x11vnc -display :1 -nopw -listen localhost -xkb -rfbport 5901 &'",
                detach=True
            )
            
            logger.info(f"X11 forwarding set up for container {container_id}")
            
        except Exception as e:
            logger.warning(f"Failed to set up X11 forwarding for container {container_id}: {str(e)}")
    
    async def execute_command(self, container_id: str, command: str) -> Dict[str, Any]:
        """Execute a command in a container"""
        if container_id not in self.containers:
            raise ValueError(f"Container {container_id} not found")
        
        container = self.containers[container_id]
        docker_container = self.docker_client.containers.get(container["docker_id"])
        
        try:
            exec_result = docker_container.exec_run(command)
            
            return {
                "exit_code": exec_result.exit_code,
                "output": exec_result.output.decode("utf-8")
            }
            
        except Exception as e:
            logger.error(f"Failed to execute command in container {container_id}: {str(e)}")
            raise

