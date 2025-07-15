"""
Orchestration Engine for GenOS
Manages the lifecycle of virtualized environments
"""

import asyncio
import uuid
import json
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
from enum import Enum
import logging

from ..api.models.schemas import EnvironmentSpec, EnvironmentStatus
from ..runtime.vm_manager import VMManager
from ..runtime.container_manager import ContainerManager
from ..security.sandbox import SecuritySandbox
from ..api.core.logging import get_logger

logger = get_logger(__name__)

class ProvisioningStrategy(Enum):
    """Provisioning strategy for environments"""
    VM_ONLY = "vm_only"
    CONTAINER_ONLY = "container_only"
    HYBRID = "hybrid"
    AUTO = "auto"

class ResourcePool:
    """Manages available system resources"""
    
    def __init__(self):
        self.max_cpu_cores = 16
        self.max_memory_mb = 32768
        self.max_disk_gb = 1000
        self.allocated_cpu = 0
        self.allocated_memory = 0
        self.allocated_disk = 0
        self.active_environments: Dict[str, Dict] = {}
    
    def can_allocate(self, cpu: int, memory: int, disk: int) -> bool:
        """Check if resources can be allocated"""
        return (
            self.allocated_cpu + cpu <= self.max_cpu_cores and
            self.allocated_memory + memory <= self.max_memory_mb and
            self.allocated_disk + disk <= self.max_disk_gb
        )
    
    def allocate(self, env_id: str, cpu: int, memory: int, disk: int) -> bool:
        """Allocate resources for an environment"""
        if self.can_allocate(cpu, memory, disk):
            self.allocated_cpu += cpu
            self.allocated_memory += memory
            self.allocated_disk += disk
            self.active_environments[env_id] = {
                "cpu": cpu,
                "memory": memory,
                "disk": disk,
                "allocated_at": datetime.utcnow()
            }
            logger.info(f"Allocated resources for {env_id}: {cpu}CPU, {memory}MB, {disk}GB")
            return True
        return False
    
    def deallocate(self, env_id: str) -> bool:
        """Deallocate resources for an environment"""
        if env_id in self.active_environments:
            resources = self.active_environments[env_id]
            self.allocated_cpu -= resources["cpu"]
            self.allocated_memory -= resources["memory"]
            self.allocated_disk -= resources["disk"]
            del self.active_environments[env_id]
            logger.info(f"Deallocated resources for {env_id}")
            return True
        return False
    
    def get_utilization(self) -> Dict[str, float]:
        """Get current resource utilization"""
        return {
            "cpu_percent": (self.allocated_cpu / self.max_cpu_cores) * 100,
            "memory_percent": (self.allocated_memory / self.max_memory_mb) * 100,
            "disk_percent": (self.allocated_disk / self.max_disk_gb) * 100
        }

class OrchestrationEngine:
    """Main orchestration engine for managing environments"""
    
    def __init__(self):
        self.vm_manager = VMManager()
        self.container_manager = ContainerManager()
        self.security_sandbox = SecuritySandbox()
        self.resource_pool = ResourcePool()
        self.environments: Dict[str, Dict] = {}
        self.provisioning_queue: asyncio.Queue = asyncio.Queue()
        self.worker_tasks: List[asyncio.Task] = []
        self.running = False
    
    async def start(self):
        """Start the orchestration engine"""
        logger.info("Starting orchestration engine")
        self.running = True
        
        # Initialize components
        await self.vm_manager.initialize()
        await self.container_manager.initialize()
        await self.security_sandbox.initialize()
        
        # Start worker tasks
        for i in range(3):  # 3 worker tasks for parallel provisioning
            task = asyncio.create_task(self._provisioning_worker(f"worker-{i}"))
            self.worker_tasks.append(task)
        
        logger.info("Orchestration engine started")
    
    async def stop(self):
        """Stop the orchestration engine"""
        logger.info("Stopping orchestration engine")
        self.running = False
        
        # Cancel worker tasks
        for task in self.worker_tasks:
            task.cancel()
        
        # Wait for tasks to complete
        await asyncio.gather(*self.worker_tasks, return_exceptions=True)
        
        # Cleanup components
        await self.vm_manager.cleanup()
        await self.container_manager.cleanup()
        
        logger.info("Orchestration engine stopped")
    
    async def create_environment(self, env_id: str, spec: EnvironmentSpec, user_id: int) -> Dict[str, Any]:
        """Create a new environment"""
        logger.info(f"Creating environment {env_id} for user {user_id}")
        
        # Determine provisioning strategy
        strategy = self._determine_strategy(spec)
        
        # Create environment record
        environment = {
            "id": env_id,
            "user_id": user_id,
            "specification": spec.dict(),
            "strategy": strategy,
            "status": EnvironmentStatus.REQUESTED,
            "created_at": datetime.utcnow(),
            "vm_id": None,
            "container_id": None,
            "streaming_port": None,
            "metadata": {}
        }
        
        self.environments[env_id] = environment
        
        # Add to provisioning queue
        await self.provisioning_queue.put({
            "action": "provision",
            "env_id": env_id
        })
        
        logger.info(f"Environment {env_id} queued for provisioning")
        return environment
    
    async def start_environment(self, env_id: str) -> bool:
        """Start an environment"""
        if env_id not in self.environments:
            logger.error(f"Environment {env_id} not found")
            return False
        
        environment = self.environments[env_id]
        
        if environment["status"] != EnvironmentStatus.SUSPENDED:
            logger.error(f"Cannot start environment {env_id} in status {environment['status']}")
            return False
        
        # Add to provisioning queue
        await self.provisioning_queue.put({
            "action": "start",
            "env_id": env_id
        })
        
        return True
    
    async def stop_environment(self, env_id: str) -> bool:
        """Stop an environment"""
        if env_id not in self.environments:
            logger.error(f"Environment {env_id} not found")
            return False
        
        environment = self.environments[env_id]
        
        if environment["status"] != EnvironmentStatus.RUNNING:
            logger.error(f"Cannot stop environment {env_id} in status {environment['status']}")
            return False
        
        # Add to provisioning queue
        await self.provisioning_queue.put({
            "action": "stop",
            "env_id": env_id
        })
        
        return True
    
    async def terminate_environment(self, env_id: str) -> bool:
        """Terminate an environment"""
        if env_id not in self.environments:
            logger.error(f"Environment {env_id} not found")
            return False
        
        # Add to provisioning queue
        await self.provisioning_queue.put({
            "action": "terminate",
            "env_id": env_id
        })
        
        return True
    
    async def get_environment_status(self, env_id: str) -> Optional[Dict[str, Any]]:
        """Get environment status"""
        if env_id in self.environments:
            return self.environments[env_id].copy()
        return None
    
    async def list_environments(self, user_id: Optional[int] = None) -> List[Dict[str, Any]]:
        """List environments, optionally filtered by user"""
        environments = []
        for env in self.environments.values():
            if user_id is None or env["user_id"] == user_id:
                environments.append(env.copy())
        return environments
    
    def _determine_strategy(self, spec: EnvironmentSpec) -> ProvisioningStrategy:
        """Determine the best provisioning strategy for a specification"""
        # Simple heuristics for strategy selection
        
        # If GPU is required, use VM
        if spec.gpu_enabled:
            return ProvisioningStrategy.VM_ONLY
        
        # If Windows or macOS, use VM
        if "windows" in spec.base_os.lower() or "macos" in spec.base_os.lower():
            return ProvisioningStrategy.VM_ONLY
        
        # If high resource requirements, use VM
        if spec.memory_mb > 4096 or spec.cpu_cores > 4:
            return ProvisioningStrategy.VM_ONLY
        
        # If only simple apps, use container
        simple_apps = ["firefox", "chrome", "terminal", "python", "nodejs"]
        if all(app in simple_apps for app in spec.apps):
            return ProvisioningStrategy.CONTAINER_ONLY
        
        # Default to VM for full OS experience
        return ProvisioningStrategy.VM_ONLY
    
    async def _provisioning_worker(self, worker_id: str):
        """Worker task for processing provisioning queue"""
        logger.info(f"Provisioning worker {worker_id} started")
        
        while self.running:
            try:
                # Get next task from queue
                task = await asyncio.wait_for(
                    self.provisioning_queue.get(),
                    timeout=1.0
                )
                
                env_id = task["env_id"]
                action = task["action"]
                
                logger.info(f"Worker {worker_id} processing {action} for environment {env_id}")
                
                if action == "provision":
                    await self._provision_environment(env_id)
                elif action == "start":
                    await self._start_environment(env_id)
                elif action == "stop":
                    await self._stop_environment(env_id)
                elif action == "terminate":
                    await self._terminate_environment(env_id)
                
                # Mark task as done
                self.provisioning_queue.task_done()
                
            except asyncio.TimeoutError:
                # No tasks in queue, continue
                continue
            except Exception as e:
                logger.error(f"Worker {worker_id} error: {str(e)}")
                continue
        
        logger.info(f"Provisioning worker {worker_id} stopped")
    
    async def _provision_environment(self, env_id: str):
        """Provision a new environment"""
        environment = self.environments[env_id]
        spec = EnvironmentSpec(**environment["specification"])
        
        try:
            # Update status
            environment["status"] = EnvironmentStatus.PROVISIONING
            
            # Check resource availability
            if not self.resource_pool.can_allocate(spec.cpu_cores, spec.memory_mb, spec.disk_gb):
                logger.error(f"Insufficient resources for environment {env_id}")
                environment["status"] = EnvironmentStatus.ERROR
                environment["metadata"]["error"] = "Insufficient resources"
                return
            
            # Allocate resources
            self.resource_pool.allocate(env_id, spec.cpu_cores, spec.memory_mb, spec.disk_gb)
            
            # Apply security policies
            security_config = await self.security_sandbox.create_security_config(spec)
            environment["metadata"]["security_config"] = security_config
            
            # Provision based on strategy
            if environment["strategy"] == ProvisioningStrategy.VM_ONLY:
                vm_id = await self.vm_manager.create_vm(env_id, spec, security_config)
                environment["vm_id"] = vm_id
                
                # Start VM
                await self.vm_manager.start_vm(vm_id)
                
                # Get streaming port
                streaming_port = await self.vm_manager.get_streaming_port(vm_id)
                environment["streaming_port"] = streaming_port
                
            elif environment["strategy"] == ProvisioningStrategy.CONTAINER_ONLY:
                container_id = await self.container_manager.create_container(env_id, spec, security_config)
                environment["container_id"] = container_id
                
                # Start container
                await self.container_manager.start_container(container_id)
                
                # Get streaming port (for X11 forwarding)
                streaming_port = await self.container_manager.get_streaming_port(container_id)
                environment["streaming_port"] = streaming_port
            
            # Update status
            environment["status"] = EnvironmentStatus.RUNNING
            environment["started_at"] = datetime.utcnow()
            
            logger.info(f"Environment {env_id} provisioned successfully")
            
        except Exception as e:
            logger.error(f"Failed to provision environment {env_id}: {str(e)}")
            environment["status"] = EnvironmentStatus.ERROR
            environment["metadata"]["error"] = str(e)
            
            # Cleanup resources
            self.resource_pool.deallocate(env_id)
    
    async def _start_environment(self, env_id: str):
        """Start a suspended environment"""
        environment = self.environments[env_id]
        
        try:
            environment["status"] = EnvironmentStatus.PROVISIONING
            
            if environment["vm_id"]:
                await self.vm_manager.start_vm(environment["vm_id"])
            elif environment["container_id"]:
                await self.container_manager.start_container(environment["container_id"])
            
            environment["status"] = EnvironmentStatus.RUNNING
            environment["started_at"] = datetime.utcnow()
            
            logger.info(f"Environment {env_id} started successfully")
            
        except Exception as e:
            logger.error(f"Failed to start environment {env_id}: {str(e)}")
            environment["status"] = EnvironmentStatus.ERROR
            environment["metadata"]["error"] = str(e)
    
    async def _stop_environment(self, env_id: str):
        """Stop a running environment"""
        environment = self.environments[env_id]
        
        try:
            if environment["vm_id"]:
                await self.vm_manager.stop_vm(environment["vm_id"])
            elif environment["container_id"]:
                await self.container_manager.stop_container(environment["container_id"])
            
            environment["status"] = EnvironmentStatus.SUSPENDED
            environment["stopped_at"] = datetime.utcnow()
            
            logger.info(f"Environment {env_id} stopped successfully")
            
        except Exception as e:
            logger.error(f"Failed to stop environment {env_id}: {str(e)}")
            environment["status"] = EnvironmentStatus.ERROR
            environment["metadata"]["error"] = str(e)
    
    async def _terminate_environment(self, env_id: str):
        """Terminate an environment"""
        environment = self.environments[env_id]
        
        try:
            if environment["vm_id"]:
                await self.vm_manager.destroy_vm(environment["vm_id"])
            elif environment["container_id"]:
                await self.container_manager.destroy_container(environment["container_id"])
            
            # Deallocate resources
            self.resource_pool.deallocate(env_id)
            
            environment["status"] = EnvironmentStatus.TERMINATED
            environment["terminated_at"] = datetime.utcnow()
            
            logger.info(f"Environment {env_id} terminated successfully")
            
        except Exception as e:
            logger.error(f"Failed to terminate environment {env_id}: {str(e)}")
            environment["status"] = EnvironmentStatus.ERROR
            environment["metadata"]["error"] = str(e)

# Global orchestration engine instance
orchestration_engine = OrchestrationEngine()

