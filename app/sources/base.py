"""Base module for VM metadata sources.

Defines the shared VM dataclass and the abstract base class for all sources.
"""

import sys
import re
from datetime import datetime
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


_INVENTORY_BLOCK_PATTERN = re.compile(
    r"^\[INVENTORY:\s*(?P<body>[^\]]*)\]\s*\n?"
)
_KV_PATTERN = re.compile(r"^([a-z_]+)=(.+)$")

# Maps keys used in the [INVENTORY: ...] block to VM field names.
# By convention, keys are identical to VM field names and Prometheus
# label names (full symmetry from annotation to dashboard).
_INVENTORY_KEY_MAP: dict[str, str] = {
    # migration planning fields
    "migration_batch": "migration_batch",
    "migration_status": "migration_status",
    "migration_difficulty": "migration_difficulty",
    "migration_target": "migration_target",
    "migration_notes": "migration_notes",
    # general resource info fields
    "info_downtime_impact": "info_downtime_impact",
    "info_stakeholder": "info_stakeholder",
    "info_os_contact": "info_os_contact",
}

# Fields that should be parsed as int; default 0 if missing/invalid.
_INT_FIELDS = ("migration_difficulty", "info_downtime_impact")


def parse_annotation(raw: str) -> tuple[dict[str, object], str]:
    """Split a VM annotation into structured migration fields and free text.

    Recognises an optional leading block of the form::

    [INVENTORY: migration_batch=2; migration_status=planned; info_stakeholder=jdoe; ...]
    Everything after this block (or the entire annotation if no such block
    is present) is treated as free text. Other bracketed content that does
    not match this exact pattern (e.g. "[TODO] ...") is left untouched and
    stays part of the free text.

    Args:
        raw: Raw annotation string as read from vCenter (or a Docker label).

    Returns:
        Tuple of (parsed migration fields keyed by VM field name, free text).
    """
    if not raw:
        return {}, ""

    match = _INVENTORY_BLOCK_PATTERN.match(raw)
    if not match:
        return {}, raw.strip()

    body = match.group("body")
    free_text = raw[match.end():].strip()

    fields: dict[str, object] = {}
    for part in (p.strip() for p in body.split(";") if p.strip()):
        kv_match = _KV_PATTERN.match(part)
        if not kv_match:
            continue
        short_key, value = kv_match.group(1), kv_match.group(2).strip()
        field_name = _INVENTORY_KEY_MAP.get(short_key)
        if field_name is None:
            continue
        if field_name in _INT_FIELDS:
            try:
                fields[field_name] = int(value)
            except ValueError:
                fields[field_name] = 0
        else:
            fields[field_name] = value

    if not fields:
        return {}, raw.strip()

    return fields, free_text


@dataclass
class VM: # pylint: disable=too-many-instance-attributes
    """Flat representation of a virtual machine or container.

    Attributes:
        source_type: Is it Docker or VMWare resource.
        host: Hostname of the node or ESXi host.
        name: Name of the container or VM.
        cpus: CPU count (vCPUs for VMware, CPU limit for Docker; unlimited
    containers are estimated with the host's thread count).
    -1 means the value could not be determined.
        ram_mb: RAM in MB; provisioned (VMware) or current usage (Docker).
        volumes: Comma-separated list of mount paths (Docker) or
                 name:sizeGB pairs (VMware).
        volumes_count: Number of volumes attached/mounted.
        volumes_capacity_total_gb: For VMWare total of volume sizes,
                                   for Docker: -1.
        networks: Comma-separated list of network names.
        annotation: Free-text annotation (VMware notes field, minus any
                    structured [INVENTORY: ...] block). Empty for Docker
                    unless populated via a custom label.
        migration_batch: Migration phase/wave this VM is assigned to.
        migration_status: not_started / planned / in_progress / done.
        migration_difficulty: Estimated migration difficulty, 1-5.
        migration_downtime_impact: Impact of downtime during migration, 1-5.
        migration_stakeholder: Contact for coordinating downtime windows.
        migration_os_contact: Contact familiar with the guest OS internals.
        migration_target: Target host/cluster on Proxmox.
        migration_notes: Migration-specific notes, separate from annotation.
    """
    uid: str
    source_type: str
    host: str
    name: str
    state: str
    cpus: float
    cpu_usage_mhz: int       # VMware: overallCpuUsage, Docker: 0
    cpu_usage_percent: float  # Docker: CPU%, VMware: 0.0
    ram_mb: int
    volumes_count: int
    volumes_capacity_total_gb: int
    volumes: str
    networks: str
    info_annotation: str = ""
    migration_batch: str = ""
    migration_status: str = ""
    migration_difficulty: int = 0
    info_downtime_impact: int = 0
    info_stakeholder: str = ""
    info_os_contact: str = ""
    migration_target: str = ""
    migration_notes: str = ""


class BaseSource(ABC):
    """Abstract base class for VM metadata sources.

    All concrete sources must implement :meth:`fetch_vms`.
    """

    def __init__(self, host: str, quiet: bool = False) -> None:
        """Initialise the source.

        Args:
            host: Connection endpoint.
            quiet: If True, suppress all log output. Default False.
        """
        self.host = host
        self.quiet = quiet

    def _log(self, message: str) -> None:
        """Log a timestamped message prefixed with the source class name.

        Args:
            message: Message to log.
        """
        if not self.quiet:
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            print(f"{timestamp} [{self.__class__.__name__}] {message}", file=sys.stderr)

    @abstractmethod
    def fetch_vms(self) -> list[VM]:
        """Fetch VM metadata from the source.

        Returns:
            A list of :class:`VM` instances.
        """
