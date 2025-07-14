"""
Natural Language Processing service for GenOS
Converts natural language commands into structured environment specifications
"""

import spacy
import re
import asyncio
from typing import Dict, List, Optional, Tuple, Any
from ..models.schemas import EnvironmentSpec, NetworkMode, NLPResponse
from ..core.logging import get_logger

logger = get_logger(__name__)

class EnvironmentParser:
    """Natural language parser for environment specifications"""
    
    def __init__(self):
        self.nlp = None
        self._os_patterns = {
            'ubuntu': ['ubuntu', 'linux', 'debian'],
            'fedora': ['fedora', 'red hat', 'rhel'],
            'centos': ['centos', 'rocky'],
            'windows': ['windows', 'win10', 'win11'],
            'macos': ['macos', 'mac', 'osx']
        }
        
        self._app_patterns = {
            'tor_browser': ['tor', 'tor browser', 'anonymous browser'],
            'firefox': ['firefox', 'mozilla'],
            'chrome': ['chrome', 'chromium', 'google chrome'],
            'vscode': ['vscode', 'visual studio code', 'code editor'],
            'office': ['office', 'libreoffice', 'word', 'excel'],
            'gimp': ['gimp', 'image editor', 'photo editor'],
            'vlc': ['vlc', 'media player', 'video player'],
            'terminal': ['terminal', 'command line', 'shell'],
            'docker': ['docker', 'containers'],
            'python': ['python', 'python3'],
            'nodejs': ['nodejs', 'node', 'npm'],
            'git': ['git', 'version control']
        }
        
        self._network_patterns = {
            NetworkMode.ISOLATED: ['isolated', 'offline', 'no internet', 'air gapped'],
            NetworkMode.LIMITED: ['limited', 'restricted', 'filtered', 'vpn'],
            NetworkMode.FULL: ['full', 'unrestricted', 'open', 'normal']
        }
        
        self._resource_patterns = {
            'memory': r'(\d+)\s*(gb|mb|g|m)\s*(ram|memory)',
            'cpu': r'(\d+)\s*(core|cpu|processor)',
            'disk': r'(\d+)\s*(gb|tb|g|t)\s*(disk|storage|space)'
        }
    
    async def initialize(self):
        """Initialize the NLP model"""
        try:
            # Load spaCy model
            self.nlp = spacy.load("en_core_web_sm")
            logger.info("NLP model loaded successfully")
        except OSError:
            logger.warning("spaCy model not found, using basic parsing")
            self.nlp = None
    
    async def parse_command(self, command: str, context: Optional[Dict[str, Any]] = None) -> EnvironmentSpec:
        """
        Parse a natural language command into an environment specification
        
        Args:
            command: Natural language command
            context: Additional context for parsing
            
        Returns:
            EnvironmentSpec: Parsed environment specification
        """
        if not self.nlp:
            await self.initialize()
        
        logger.info(f"Parsing command: {command}")
        
        # Normalize command
        command_lower = command.lower().strip()
        
        # Extract components
        base_os = self._extract_os(command_lower)
        apps = self._extract_apps(command_lower)
        network_mode = self._extract_network_mode(command_lower)
        memory_mb, cpu_cores, disk_gb = self._extract_resources(command_lower)
        gpu_enabled = self._extract_gpu_requirement(command_lower)
        
        # Create specification
        spec = EnvironmentSpec(
            base_os=base_os,
            apps=apps,
            network_mode=network_mode,
            memory_mb=memory_mb,
            cpu_cores=cpu_cores,
            disk_gb=disk_gb,
            gpu_enabled=gpu_enabled
        )
        
        logger.info(f"Parsed specification: {spec.dict()}")
        return spec
    
    def _extract_os(self, command: str) -> str:
        """Extract operating system from command"""
        for os_name, patterns in self._os_patterns.items():
            for pattern in patterns:
                if pattern in command:
                    # Map to specific versions
                    if os_name == 'ubuntu':
                        if '22.04' in command or '22' in command:
                            return 'ubuntu_22.04'
                        elif '20.04' in command or '20' in command:
                            return 'ubuntu_20.04'
                        else:
                            return 'ubuntu_22.04'  # Default
                    elif os_name == 'fedora':
                        if '38' in command:
                            return 'fedora_38'
                        elif '37' in command:
                            return 'fedora_37'
                        else:
                            return 'fedora_38'  # Default
                    elif os_name == 'windows':
                        if '11' in command:
                            return 'windows_11'
                        elif '10' in command:
                            return 'windows_10'
                        else:
                            return 'windows_10'  # Default
                    else:
                        return f"{os_name}_latest"
        
        # Default to Ubuntu if no OS specified
        return 'ubuntu_22.04'
    
    def _extract_apps(self, command: str) -> List[str]:
        """Extract applications from command"""
        apps = []
        
        for app_name, patterns in self._app_patterns.items():
            for pattern in patterns:
                if pattern in command:
                    apps.append(app_name)
                    break
        
        # Remove duplicates while preserving order
        return list(dict.fromkeys(apps))
    
    def _extract_network_mode(self, command: str) -> NetworkMode:
        """Extract network mode from command"""
        for mode, patterns in self._network_patterns.items():
            for pattern in patterns:
                if pattern in command:
                    return mode
        
        # Check for security-related keywords
        security_keywords = ['secure', 'private', 'anonymous', 'vpn']
        if any(keyword in command for keyword in security_keywords):
            return NetworkMode.LIMITED
        
        # Default to isolated for security
        return NetworkMode.ISOLATED
    
    def _extract_resources(self, command: str) -> Tuple[int, int, int]:
        """Extract resource requirements from command"""
        memory_mb = 2048  # Default 2GB
        cpu_cores = 2     # Default 2 cores
        disk_gb = 20      # Default 20GB
        
        # Extract memory
        memory_match = re.search(self._resource_patterns['memory'], command, re.IGNORECASE)
        if memory_match:
            value = int(memory_match.group(1))
            unit = memory_match.group(2).lower()
            if unit in ['gb', 'g']:
                memory_mb = value * 1024
            elif unit in ['mb', 'm']:
                memory_mb = value
        
        # Extract CPU
        cpu_match = re.search(self._resource_patterns['cpu'], command, re.IGNORECASE)
        if cpu_match:
            cpu_cores = int(cpu_match.group(1))
        
        # Extract disk
        disk_match = re.search(self._resource_patterns['disk'], command, re.IGNORECASE)
        if disk_match:
            value = int(disk_match.group(1))
            unit = disk_match.group(2).lower()
            if unit in ['tb', 't']:
                disk_gb = value * 1024
            elif unit in ['gb', 'g']:
                disk_gb = value
        
        # Check for performance keywords
        if any(keyword in command for keyword in ['high performance', 'powerful', 'fast']):
            memory_mb = max(memory_mb, 4096)  # At least 4GB
            cpu_cores = max(cpu_cores, 4)    # At least 4 cores
        
        if any(keyword in command for keyword in ['light', 'minimal', 'basic']):
            memory_mb = min(memory_mb, 1024)  # At most 1GB
            cpu_cores = min(cpu_cores, 1)    # At most 1 core
        
        return memory_mb, cpu_cores, disk_gb
    
    def _extract_gpu_requirement(self, command: str) -> bool:
        """Extract GPU requirement from command"""
        gpu_keywords = ['gpu', 'graphics', 'gaming', 'ml', 'machine learning', 'ai', 'cuda']
        return any(keyword in command for keyword in gpu_keywords)
    
    async def get_suggestions(self, partial_command: str) -> List[str]:
        """Get command suggestions for autocomplete"""
        suggestions = [
            "I need a Linux environment with Tor browser for secure browsing",
            "Create a Ubuntu desktop with Firefox and VPN",
            "Launch isolated Windows 10 with Office suite",
            "Set up a development environment with Python and VS Code",
            "I want a high-performance Ubuntu with 8GB RAM for machine learning",
            "Create a minimal Fedora environment for testing",
            "Launch a secure browsing environment with no internet access",
            "Set up a Windows environment with 4 cores and 16GB RAM"
        ]
        
        # Filter suggestions based on partial command
        if partial_command:
            partial_lower = partial_command.lower()
            suggestions = [s for s in suggestions if partial_lower in s.lower()]
        
        return suggestions[:5]  # Return top 5 suggestions

