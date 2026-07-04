"""Docker source module.

Fetches VM metadata from a Docker daemon reachable via TCP.
Uses only Python standard library (urllib, json).
"""

import sys
import json
import ssl
import urllib.error
import urllib.request
from typing import Any

from sources.base import BaseSource, VM, _sanitize_label, parse_annotation


class DockerSource(BaseSource):
    """Fetch container metadata from a Docker TCP endpoint.

    Args:
        host: Base URL of the Docker daemon, e.g. ``http://hostname:2375``.
        no_verify_ssl: If ``True``, TLS certificate verification is disabled.
    """

    def __init__(self, host: str, no_verify_ssl: bool = False, quiet: bool = False) -> None:
        """Initialise the DockerSource.

        Args:
            host: Base URL of the Docker daemon.
            no_verify_ssl: Disable TLS certificate verification when ``True``.
        """
        super().__init__(host, quiet=quiet)
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

    def _host_info(self) -> tuple[str, int]:
        """Return the Docker daemon's reported hostname and CPU count.

        Returns:
            Tuple of (``Name``, ``NCPU``) from ``/info``, or
            ``("unknown", 0)`` on error.
        """
        try:
            info = self._get("/info")
            return str(info.get("Name", "unknown")), int(info.get("NCPU", 0))
        except Exception as exc:  # pylint: disable=broad-except
            print(f"[DockerSource] Could not fetch /info: {exc}", file=sys.stderr)
            return "unknown", 0

#     def _host_name(self) -> str:
#         """Return the Docker daemon's reported hostname.
# 
#         Returns:
#             The ``Name`` field from ``/info``, or ``"unknown"`` on error.
#         """
#         try:
#             info = self._get("/info")
#             return str(info.get("Name", "unknown"))
#         except Exception as exc:  # pylint: disable=broad-except
#             print(f"[DockerSource] Could not fetch /info: {exc}", file=sys.stderr)
#             return "unknown"

    def _container_stats(self, container_id: str) -> tuple:
        """Fetch RAM usage in MB and CPU percent for a container.

        CPU percent is normalised to whole threads: 100 percent equals one
        fully used thread, so a host with 8 threads tops out at 800 percent.
        This matches the semantics of ``docker stats``.

        Returns:
            Tuple (ram_mb, cpu_percent).
        """
        try:
            stats = self._get(f"/containers/{container_id}/stats?stream=false")
            mem = stats.get("memory_stats", {})
            usage = mem.get("usage", 0)
            cache = mem.get("stats", {}).get("cache", 0)
            ram_mb = max(0, (usage - cache)) // (1024 * 1024)

            cpu = stats.get("cpu_stats", {})
            precpu = stats.get("precpu_stats", {})
            cpu_delta = (cpu.get("cpu_usage", {}).get("total_usage", 0)
                         - precpu.get("cpu_usage", {}).get("total_usage", 0))
            system_delta = (cpu.get("system_cpu_usage", 0)
                            - precpu.get("system_cpu_usage", 0))
            num_cpus = (cpu.get("online_cpus")
                        or len(cpu.get("cpu_usage", {}).get("percpu_usage") or [])
                        or 1)


            # if cpu_delta <= 0 or system_delta <= 0:
            #     print(
            #         f"[DockerSource] DEBUG {container_id[:12]}: "
            #         f"cpu_delta={cpu_delta} system_delta={system_delta} "
            #         f"num_cpus={num_cpus} "
            #         f"pre_total={precpu.get('cpu_usage', {}).get('total_usage', 'MISSING')} "
            #         f"cur_total={cpu.get('cpu_usage', {}).get('total_usage', 'MISSING')} "
            #         f"pre_sys={precpu.get('system_cpu_usage', 'MISSING')}",
            #         file=sys.stderr,
            #     )

            if system_delta > 0 and cpu_delta >= 0:
                cpu_percent = round((cpu_delta / system_delta) * num_cpus * 100.0, 2)
            else:
                cpu_percent = 0.0

            return ram_mb, cpu_percent
        except Exception as exc:  # pylint: disable=broad-except
            print(f"[DockerSource] Could not fetch stats for {container_id}: {exc}",
                  file=sys.stderr)
            return 0, 0.0

 #   def _container_stats(self, container_id: str) -> tuple:
 #       """Fetch RAM usage in MB and CPU percent for a container.
 #   
 #       Returns:
 #           Tuple (ram_mb, cpu_percent).
 #       """
 #       try:
 #           stats = self._get(f"/containers/{container_id}/stats?stream=false")
 #           mem = stats.get("memory_stats", {})
 #           usage = mem.get("usage", 0)
 #           cache = mem.get("stats", {}).get("cache", 0)
 #           ram_mb = max(0, (usage - cache)) // (1024 * 1024)
 #   
 #           cpu = stats.get("cpu_stats", {})
 #           precpu = stats.get("precpu_stats", {})
 #           cpu_delta = (cpu.get("cpu_usage", {}).get("total_usage", 0)
 #                        - precpu.get("cpu_usage", {}).get("total_usage", 0))
 #           system_delta = (cpu.get("system_cpu_usage", 0)
 #                           - precpu.get("system_cpu_usage", 0))
 #           num_cpus = len(cpu.get("cpu_usage", {}).get("percpu_usage", [1]))
 #           if system_delta > 0:
 #               cpu_percent = round((cpu_delta / system_delta) * num_cpus * 100.0, 1)
 #           else:
 #               cpu_percent = 0.0
 #   
 #           return ram_mb, cpu_percent
 #       except Exception as exc:  # pylint: disable=broad-except
 #           print(f"[DockerSource] Could not fetch stats for {container_id}: {exc}", file=sys.stderr)
 #           return 0, 0.0

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def _container_to_record(self, cid: str, host_name: str, host_ncpu: int) -> VM:
        """Convert a Docker container ID to a :class:`~sources.base.VM`.

        Args:
            cid: Docker container ID.
            host_name: Pre-fetched Docker daemon hostname.
            host_ncpu: Number of CPU threads of the Docker host (0 if unknown).

        Returns:
            Populated :class:`~sources.base.VM` instance.
        """

        # /containers/<container ID>/json delivers all configuration setting. But no runtime data.
        details = self._get(f"/containers/{cid}/json")
        name = _sanitize_label(details.get("Name", "").lstrip("/"))
        # uid: hostname + container name. The name alone is not unique
        # if the same container name runs on multiple Docker hosts.
        uid = _sanitize_label(f"{host_name}__{name}")
        
        # nano = details.get("HostConfig", {}).get("NanoCpus", 0)
        # cpus = int(nano / 1_000_000_000) if nano else -1
        nano = details.get("HostConfig", {}).get("NanoCpus", 0)
        if nano:
            cpus = nano / 1_000_000_000  # float, z.B. 0.5 oder 1.5
        elif host_ncpu > 0:
            cpus = float(host_ncpu)  # kein Limit: Obergrenze = alle Host-Threads
        else:
            cpus = -1.0  # /info fehlgeschlagen, keine Abschätzung möglich

        ram_mb, cpu_percent = self._container_stats(cid)
        nets = list(details.get("NetworkSettings", {}).get("Networks", {}).keys())
        mounts = details.get("Mounts", [])
        volumes = ",".join(
            _sanitize_label(m.get("Destination", ""))
            for m in mounts if m.get("Destination")
        )
        volumes_count = len(mounts)

        labels = details.get("Config", {}).get("Labels", {}) or {}
        raw_annotation = labels.get("host-inventory.annotation", "")
        migration_fields, free_text = parse_annotation(raw_annotation)

        return VM(
            uid=uid,
            name=name,
            host=host_name,
            state=details.get("State", {}).get("Status", "unknown"),
            cpus=cpus,
            cpu_usage_mhz=0,
            cpu_usage_percent=cpu_percent,
            ram_mb=ram_mb,
            networks=",".join(_sanitize_label(n) for n in nets),
            volumes=volumes,
            source_type="docker",
            volumes_count=volumes_count,
            volumes_capacity_total_gb=-1,
            info_annotation=_sanitize_label(free_text),
            **migration_fields,
        )

    def fetch_vms(self) -> list[VM]:
        """Fetch metadata for all running containers.

        Returns:
            A list of :class:`~sources.base.VM` instances, one per running container.
        """
        import time
        self._log(f"connecting to {self.host}")
        t0 = time.monotonic()
        host_name, host_ncpu = self._host_info()
        vms: list[VM] = []

        try:
            containers = self._get("/containers/json")
        except Exception as exc:  # pylint: disable=broad-except
            print(f"[DockerSource] Could not list containers: {exc}", file=sys.stderr)
            return vms

        for container in containers:
            try:
                vms.append(self._container_to_record(container["Id"], host_name, host_ncpu))
            except Exception as exc:  # pylint: disable=broad-except
                print(f"[DockerSource] Skipping container {container.get('Id', '?')}: {exc}", file=sys.stderr)

        duration = time.monotonic() - t0
        self._log(f"collected {len(vms)} containers in {duration:.3f}s")
        return vms

