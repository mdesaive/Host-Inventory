"""Base module for VM metadata sources.

Defines the shared VM dataclass and the abstract base class for all sources.
"""

import re
from abc import ABC, abstractmethod
from dataclasses import dataclass

def _sanitize_label(value: str) -> str:
    """Remove characters that are illegal in CSV and Prometheus label values.

    Args:
        value: Raw string to sanitize.

    Returns:
        Sanitised string with problematic characters replaced by underscores.
    """
    return re.sub(r'[\\"\n\r\u2028\u2029,;\'|]', "_", value)


@dataclass
class VM:
    """Flat representation of a virtual machine or container.

    Attributes:
        source_type: Is it Docker or VMWare resource.
        host: Hostname of the node or ESXi host.
        name: Name of the container or VM.
        cpus: CPU count; -1 means unlimited (Docker with no CPU limit).
        ram_mb: RAM in MB; provisioned (VMware) or current usage (Docker).
        volumes: Comma-separated list of mount paths (Docker) or
                 name:sizeGB pairs (VMware).
        volumes_count: Number of volumes attached/mounted.
        volumes_capacity_total_gb: For VMWare total of volume sizes,
                                   for Docker: -1.
        networks: Comma-separated list of network names.
    """

    uid: str
    source_type: str
    host: str
    name: str
    state: str
    cpus: int
    cpu_usage_mhz: int       # VMware: overallCpuUsage, Docker: 0
    cpu_usage_percent: float # Docker: CPU%, VMware: 0.0
    ram_mb: int
    volumes_count: int
    volumes_capacity_total_gb: int
    volumes: str
    networks: str

class BaseSource(ABC):
    """Abstract base class for VM metadata sources.

    All concrete sources must implement :meth:`fetch_vms`.
    """

    @abstractmethod
    def fetch_vms(self) -> list[VM]:
        """Fetch VM metadata from the source.

        Returns:
            A list of :class:`VM` instances.
        """
