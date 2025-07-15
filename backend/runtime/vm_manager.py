"""
VM Manager for GenOS
Manages KVM/QEMU virtual machines and Firecracker microVMs
"""

import asyncio
import subprocess
import json
import os
import uuid
from typing import Dict, List, Optional, Any
from pathlib import Path
import xml.etree.ElementTree as ET

from ..api.models.schemas import EnvironmentSpec, NetworkMode
from ..api.core.config import settings
from ..api.core.logging import get_logger

logger = get_logger(__name__)

class VMManager:
    """Manages virtual machines using KVM/QEMU and Firecracker"""
    
    def __init__(self):
        self.vms: Dict[str, Dict] = {}
        self.base_images_path = Path(settings.vm_images_path)
        self.vm_storage_path = Path(settings.vm_storage_path)
        self.streaming_port_pool = list(range(
            settings.streaming_port_range_start,
            settings.streaming_port_range_end + 1
        ))
        self.allocated_ports: Dict[str, int] = {}
    
    async def initialize(self):
        """Initialize the VM manager"""
        logger.info("Initializing VM manager")
        
        # Create directories
        self.base_images_path.mkdir(parents=True, exist_ok=True)
        self.vm_storage_path.mkdir(parents=True, exist_ok=True)
        
        # Check KVM availability
        if not await self._check_kvm_support():
            logger.warning("KVM support not available, VMs will run in emulation mode")
        
        # Check QEMU availability
        if not await self._check_qemu_availability():
            logger.error("QEMU not available, VM functionality will be limited")
        
        # Initialize base images
        await self._initialize_base_images()
        
        logger.info("VM manager initialized")
    
    async def cleanup(self):
        """Cleanup VM manager resources"""
        logger.info("Cleaning up VM manager")
        
        # Stop all running VMs
        for vm_id in list(self.vms.keys()):
            try:
                await self.destroy_vm(vm_id)
            except Exception as e:
                logger.error(f"Error destroying VM {vm_id}: {str(e)}")
        
        logger.info("VM manager cleanup completed")
    
    async def create_vm(self, env_id: str, spec: EnvironmentSpec, security_config: Dict) -> str:
        """Create a new virtual machine"""
        vm_id = f"genos-{env_id}-{uuid.uuid4().hex[:8]}"
        
        logger.info(f"Creating VM {vm_id} for environment {env_id}")
        
        try:
            # Determine VM type based on requirements
            if spec.memory_mb <= 512 and spec.cpu_cores <= 2:
                vm_type = "firecracker"
            else:
                vm_type = "qemu"
            
            # Create VM configuration
            vm_config = await self._create_vm_config(vm_id, spec, security_config, vm_type)
            
            # Create VM disk image
            disk_path = await self._create_vm_disk(vm_id, spec)
            vm_config["disk_path"] = str(disk_path)
            
            # Allocate streaming port
            streaming_port = self._allocate_streaming_port(vm_id)
            vm_config["streaming_port"] = streaming_port
            
            # Store VM configuration
            self.vms[vm_id] = {
                "id": vm_id,
                "env_id": env_id,
                "type": vm_type,
                "config": vm_config,
                "status": "created",
                "pid": None,
                "created_at": asyncio.get_event_loop().time()
            }
            
            logger.info(f"VM {vm_id} created successfully")
            return vm_id
            
        except Exception as e:
            logger.error(f"Failed to create VM {vm_id}: {str(e)}")
            raise
    
    async def start_vm(self, vm_id: str) -> bool:
        """Start a virtual machine"""
        if vm_id not in self.vms:
            raise ValueError(f"VM {vm_id} not found")
        
        vm = self.vms[vm_id]
        
        if vm["status"] == "running":
            logger.warning(f"VM {vm_id} is already running")
            return True
        
        logger.info(f"Starting VM {vm_id}")
        
        try:
            if vm["type"] == "firecracker":
                pid = await self._start_firecracker_vm(vm_id, vm["config"])
            else:
                pid = await self._start_qemu_vm(vm_id, vm["config"])
            
            vm["pid"] = pid
            vm["status"] = "running"
            vm["started_at"] = asyncio.get_event_loop().time()
            
            # Wait for VM to be ready
            await self._wait_for_vm_ready(vm_id)
            
            logger.info(f"VM {vm_id} started successfully with PID {pid}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to start VM {vm_id}: {str(e)}")
            vm["status"] = "error"
            raise
    
    async def stop_vm(self, vm_id: str) -> bool:
        """Stop a virtual machine"""
        if vm_id not in self.vms:
            raise ValueError(f"VM {vm_id} not found")
        
        vm = self.vms[vm_id]
        
        if vm["status"] != "running":
            logger.warning(f"VM {vm_id} is not running")
            return True
        
        logger.info(f"Stopping VM {vm_id}")
        
        try:
            # Send shutdown signal
            if vm["pid"]:
                process = await asyncio.create_subprocess_exec(
                    "kill", "-TERM", str(vm["pid"]),
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                await process.wait()
                
                # Wait for graceful shutdown
                await asyncio.sleep(5)
                
                # Force kill if still running
                try:
                    process = await asyncio.create_subprocess_exec(
                        "kill", "-KILL", str(vm["pid"]),
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.PIPE
                    )
                    await process.wait()
                except:
                    pass  # Process might already be dead
            
            vm["status"] = "stopped"
            vm["pid"] = None
            vm["stopped_at"] = asyncio.get_event_loop().time()
            
            logger.info(f"VM {vm_id} stopped successfully")
            return True
            
        except Exception as e:
            logger.error(f"Failed to stop VM {vm_id}: {str(e)}")
            raise
    
    async def destroy_vm(self, vm_id: str) -> bool:
        """Destroy a virtual machine"""
        if vm_id not in self.vms:
            raise ValueError(f"VM {vm_id} not found")
        
        vm = self.vms[vm_id]
        
        logger.info(f"Destroying VM {vm_id}")
        
        try:
            # Stop VM if running
            if vm["status"] == "running":
                await self.stop_vm(vm_id)
            
            # Remove disk image
            disk_path = Path(vm["config"]["disk_path"])
            if disk_path.exists():
                disk_path.unlink()
            
            # Release streaming port
            self._release_streaming_port(vm_id)
            
            # Remove VM record
            del self.vms[vm_id]
            
            logger.info(f"VM {vm_id} destroyed successfully")
            return True
            
        except Exception as e:
            logger.error(f"Failed to destroy VM {vm_id}: {str(e)}")
            raise
    
    async def get_streaming_port(self, vm_id: str) -> Optional[int]:
        """Get the streaming port for a VM"""
        if vm_id in self.vms:
            return self.vms[vm_id]["config"].get("streaming_port")
        return None
    
    async def get_vm_status(self, vm_id: str) -> Optional[Dict]:
        """Get VM status"""
        if vm_id in self.vms:
            return self.vms[vm_id].copy()
        return None
    
    async def _check_kvm_support(self) -> bool:
        """Check if KVM is available"""
        try:
            process = await asyncio.create_subprocess_exec(
                "test", "-r", "/dev/kvm",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            return_code = await process.wait()
            return return_code == 0
        except:
            return False
    
    async def _check_qemu_availability(self) -> bool:
        """Check if QEMU is available"""
        try:
            process = await asyncio.create_subprocess_exec(
                "qemu-system-x86_64", "--version",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            return_code = await process.wait()
            return return_code == 0
        except:
            return False
    
    async def _initialize_base_images(self):
        """Initialize base VM images"""
        logger.info("Initializing base VM images")
        
        # Define base images
        base_images = {
            "ubuntu_22.04": {
                "url": "https://cloud-images.ubuntu.com/focal/current/focal-server-cloudimg-amd64.img",
                "filename": "ubuntu-22.04-server-cloudimg-amd64.img"
            },
            "ubuntu_20.04": {
                "url": "https://cloud-images.ubuntu.com/focal/current/focal-server-cloudimg-amd64.img",
                "filename": "ubuntu-20.04-server-cloudimg-amd64.img"
            },
            "fedora_38": {
                "url": "https://download.fedoraproject.org/pub/fedora/linux/releases/38/Cloud/x86_64/images/Fedora-Cloud-Base-38-1.6.x86_64.qcow2",
                "filename": "fedora-38-cloud-base.qcow2"
            }
        }
        
        # Download missing images (in a real implementation)
        for os_name, image_info in base_images.items():
            image_path = self.base_images_path / image_info["filename"]
            if not image_path.exists():
                logger.info(f"Base image for {os_name} not found, would download from {image_info['url']}")
                # In a real implementation, download the image
                # For now, create a placeholder
                image_path.touch()
    
    async def _create_vm_config(self, vm_id: str, spec: EnvironmentSpec, security_config: Dict, vm_type: str) -> Dict:
        """Create VM configuration"""
        config = {
            "vm_id": vm_id,
            "type": vm_type,
            "memory_mb": spec.memory_mb,
            "cpu_cores": spec.cpu_cores,
            "disk_gb": spec.disk_gb,
            "base_os": spec.base_os,
            "apps": spec.apps,
            "network_mode": spec.network_mode,
            "gpu_enabled": spec.gpu_enabled,
            "security": security_config
        }
        
        # Add type-specific configuration
        if vm_type == "firecracker":
            config.update({
                "kernel_path": "/usr/lib/firecracker/vmlinux",
                "rootfs_path": None,  # Will be set when disk is created
                "socket_path": f"/tmp/firecracker-{vm_id}.socket"
            })
        else:
            config.update({
                "machine_type": "q35",
                "accel": "kvm" if await self._check_kvm_support() else "tcg",
                "display": "spice-app,gl=on" if spec.gpu_enabled else "spice-app"
            })
        
        return config
    
    async def _create_vm_disk(self, vm_id: str, spec: EnvironmentSpec) -> Path:
        """Create VM disk image"""
        # Determine base image
        base_image_map = {
            "ubuntu_22.04": "ubuntu-22.04-server-cloudimg-amd64.img",
            "ubuntu_20.04": "ubuntu-20.04-server-cloudimg-amd64.img",
            "fedora_38": "fedora-38-cloud-base.qcow2"
        }
        
        base_image_name = base_image_map.get(spec.base_os, "ubuntu-22.04-server-cloudimg-amd64.img")
        base_image_path = self.base_images_path / base_image_name
        
        # Create VM-specific disk
        vm_disk_path = self.vm_storage_path / f"{vm_id}.qcow2"
        
        # Create copy-on-write disk from base image
        process = await asyncio.create_subprocess_exec(
            "qemu-img", "create", "-f", "qcow2",
            "-b", str(base_image_path),
            "-F", "qcow2",
            str(vm_disk_path),
            f"{spec.disk_gb}G",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        
        stdout, stderr = await process.communicate()
        
        if process.returncode != 0:
            logger.error(f"Failed to create VM disk: {stderr.decode()}")
            raise RuntimeError(f"Failed to create VM disk: {stderr.decode()}")
        
        logger.info(f"Created VM disk: {vm_disk_path}")
        return vm_disk_path
    
    def _allocate_streaming_port(self, vm_id: str) -> int:
        """Allocate a streaming port for a VM"""
        for port in self.streaming_port_pool:
            if port not in self.allocated_ports.values():
                self.allocated_ports[vm_id] = port
                return port
        
        raise RuntimeError("No available streaming ports")
    
    def _release_streaming_port(self, vm_id: str):
        """Release a streaming port"""
        if vm_id in self.allocated_ports:
            del self.allocated_ports[vm_id]
    
    async def _start_qemu_vm(self, vm_id: str, config: Dict) -> int:
        """Start a QEMU VM"""
        cmd = [
            "qemu-system-x86_64",
            "-machine", config["machine_type"],
            "-accel", config["accel"],
            "-m", str(config["memory_mb"]),
            "-smp", str(config["cpu_cores"]),
            "-drive", f"file={config['disk_path']},format=qcow2,if=virtio",
            "-netdev", "user,id=net0",
            "-device", "virtio-net-pci,netdev=net0",
            "-spice", f"port={config['streaming_port']},addr=0.0.0.0,disable-ticketing",
            "-display", "spice-app",
            "-daemonize",
            "-pidfile", f"/tmp/{vm_id}.pid"
        ]
        
        # Add GPU support if enabled
        if config.get("gpu_enabled"):
            cmd.extend(["-vga", "virtio-gpu-gl"])
        
        logger.info(f"Starting QEMU VM with command: {' '.join(cmd)}")
        
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        
        stdout, stderr = await process.communicate()
        
        if process.returncode != 0:
            logger.error(f"Failed to start QEMU VM: {stderr.decode()}")
            raise RuntimeError(f"Failed to start QEMU VM: {stderr.decode()}")
        
        # Read PID from pidfile
        try:
            with open(f"/tmp/{vm_id}.pid", "r") as f:
                pid = int(f.read().strip())
            return pid
        except:
            raise RuntimeError("Failed to get VM PID")
    
    async def _start_firecracker_vm(self, vm_id: str, config: Dict) -> int:
        """Start a Firecracker microVM"""
        # Create Firecracker configuration
        fc_config = {
            "boot-source": {
                "kernel_image_path": config["kernel_path"],
                "boot_args": "console=ttyS0 reboot=k panic=1 pci=off"
            },
            "drives": [
                {
                    "drive_id": "rootfs",
                    "path_on_host": config["disk_path"],
                    "is_root_device": True,
                    "is_read_only": False
                }
            ],
            "machine-config": {
                "vcpu_count": config["cpu_cores"],
                "mem_size_mib": config["memory_mb"]
            },
            "network-interfaces": [
                {
                    "iface_id": "eth0",
                    "guest_mac": "AA:FC:00:00:00:01",
                    "host_dev_name": "tap0"
                }
            ]
        }
        
        # Write configuration file
        config_path = f"/tmp/{vm_id}-config.json"
        with open(config_path, "w") as f:
            json.dump(fc_config, f, indent=2)
        
        # Start Firecracker
        cmd = [
            "firecracker",
            "--api-sock", config["socket_path"],
            "--config-file", config_path
        ]
        
        logger.info(f"Starting Firecracker VM with command: {' '.join(cmd)}")
        
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        
        # Firecracker runs in foreground, so we need to handle it differently
        # In a real implementation, we'd use the API socket to control it
        
        return process.pid
    
    async def _wait_for_vm_ready(self, vm_id: str, timeout: int = 60):
        """Wait for VM to be ready"""
        logger.info(f"Waiting for VM {vm_id} to be ready")
        
        start_time = asyncio.get_event_loop().time()
        
        while asyncio.get_event_loop().time() - start_time < timeout:
            # In a real implementation, we'd check if the VM is responding
            # For now, just wait a bit
            await asyncio.sleep(2)
            
            # Check if VM process is still running
            vm = self.vms[vm_id]
            if vm["pid"]:
                try:
                    process = await asyncio.create_subprocess_exec(
                        "kill", "-0", str(vm["pid"]),
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.PIPE
                    )
                    return_code = await process.wait()
                    if return_code == 0:
                        logger.info(f"VM {vm_id} is ready")
                        return
                except:
                    pass
            
            await asyncio.sleep(3)
        
        raise TimeoutError(f"VM {vm_id} did not become ready within {timeout} seconds")

