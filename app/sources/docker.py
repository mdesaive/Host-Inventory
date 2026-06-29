"""Docker source module.

Fetches VM metadata from a Docker daemon reachable via TCP.
Uses only Python standard library (urllib, json).
"""

import json
import ssl
import urllib.error
import urllib.request
from typing import Any

from sources.base import BaseSource, VM, _sanitize_label


class DockerSource(BaseSource):
    """Fetch container metadata from a Docker TCP endpoint.

    Args:
        host: Base URL of the Docker daemon, e.g. ``http://hostname:2375``.
        no_verify_ssl: If ``True``, TLS certificate verification is disabled.
    """

    def __init__(self, host: str, no_verify_ssl: bool = False) -> None:
        """Initialise the DockerSource.

        Args:
            host: Base URL of the Docker daemon.
            no_verify_ssl: Disable TLS certificate verification when ``True``.
        """
        self._host = host.rstrip("/")
        self._no_verify_ssl = no_verify_ssl

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get(self, path: str) -> Any:
        """Perform an HTTP GET request against the Docker API.

        Args:
            path: API path, e.g. ``/containers/json``.

        Returns:
            Parsed JSON response as a Python object.

        Raises:
            urllib.error.URLError: On network errors.
            json.JSONDecodeError: If the response body is not valid JSON.
        """
        url = f"{self._host}{path}"
        ctx: ssl.SSLContext | None = None
        if self._no_verify_ssl:
            ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
        with urllib.request.urlopen(url, context=ctx) as response:  # nosec
            return json.loads(response.read().decode())
            # json.loads creates dictionary from json. <3

    def _host_name(self) -> str:
        """Return the Docker daemon's reported hostname.

        Returns:
            The ``Name`` field from ``/info``, or ``"unknown"`` on error.
        """
        try:
            info = self._get("/info")
            return str(info.get("Name", "unknown"))
        except Exception as exc:  # pylint: disable=broad-except
            print(f"[DockerSource] Could not fetch /info: {exc}")
            return "unknown"

    def _container_ram_mb(self, container_id: str) -> int:
        """Fetch current RAM usage for a container in MB.
           
           Annotation: Queries expensive live data using the /stats endpoint.
                       If latency is relevant use /json endpoint and ram max
                       and ram reservation.
        Args:
            container_id: Container ID string.

        Returns:
            RAM usage in MB, or ``0`` on error.
        """
        try:
            stats = self._get(f"/containers/{container_id}/stats?stream=false")
            mem = stats.get("memory_stats", {})
            usage = mem.get("usage", 0)
            cache = mem.get("stats", {}).get("cache", 0)
            return max(0, (usage - cache)) // (1024 * 1024)
        except Exception as exc:  # pylint: disable=broad-except
            print(f"[DockerSource] Could not fetch stats for {container_id}: {exc}")
            return 0

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def _container_to_record(self, cid: str, host_name: str) -> VM:
        """Convert a Docker container ID to a :class:`~sources.base.VM`.

        Args:
            cid: Docker container ID.
            host_name: Pre-fetched Docker daemon hostname.

        Returns:
            Populated :class:`~sources.base.VM` instance.
        """

        # /containers/<container ID>/json delivers all configuration setting. But no runtime data.
        details = self._get(f"/containers/{cid}/json")
        name = _sanitize_label(details.get("Name", "").lstrip("/"))
        nano = details.get("HostConfig", {}).get("NanoCpus", 0)
        cpus = int(nano / 1_000_000_000) if nano else -1
        ram_mb = self._container_ram_mb(cid)
        nets = list(details.get("NetworkSettings", {}).get("Networks", {}).keys())
        mounts = details.get("Mounts", [])
        volumes = ",".join(
            _sanitize_label(m.get("Destination", ""))
            for m in mounts if m.get("Destination")
        )
        volumes_count = len(mounts)
        return VM(
            name=name,
            host=host_name,
            state=details.get("State", {}).get("Status", "unknown"),
            cpus=cpus,
            ram_mb=ram_mb,
            networks=",".join(_sanitize_label(n) for n in nets),
            volumes=volumes,
            source_type="docker",
            volumes_count=volumes_count,
            volumes_capacity_total_gb=-1,
        )

    def fetch_vms(self) -> list[VM]:
        """Fetch metadata for all running containers.

        Returns:
            A list of :class:`~sources.base.VM` instances, one per running container.
        """
        host_name = self._host_name()
        vms: list[VM] = []

        try:
            containers = self._get("/containers/json")
        except Exception as exc:  # pylint: disable=broad-except
            print(f"[DockerSource] Could not list containers: {exc}")
            return vms

        for container in containers:
            try:
                vms.append(self._container_to_record(container["Id"], host_name))
            except Exception as exc:  # pylint: disable=broad-except
                print(f"[DockerSource] Skipping container {container.get('Id', '?')}: {exc}")

        return vms
