"""VMware source module.

Fetches VM metadata from a vCenter or vcsim instance using pyVmomi.
"""

import re
import ssl
from urllib.parse import urlparse

from pyVim.connect import Disconnect, SmartConnect
from pyVmomi import vim  # pylint: disable=no-name-in-module

from sources.base import BaseSource, VM


class VMwareSource(BaseSource):
    """Fetch VM metadata from a VMware vCenter or vcsim endpoint.

    Args:
        host: Full URL of the vCenter / vcsim, e.g. ``https://localhost:8989``.
        username: vCenter username.
        password: vCenter password.
        no_verify_ssl: If ``True``, TLS certificate verification is disabled.
    """

    def __init__(
        self,
        host: str,
        username: str = "user",
        password: str = "pass",
        no_verify_ssl: bool = False,
    ) -> None:
        """Initialise the VMwareSource.

        Args:
            host: vCenter / vcsim URL.
            username: Login username.
            password: Login password.
            no_verify_ssl: Disable TLS verification when ``True``.
        """
        parsed = urlparse(host)
        self._host = parsed.hostname or host
        self._port = parsed.port or 443
        self._username = username
        self._password = password
        self._no_verify_ssl = no_verify_ssl

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _ssl_context(self) -> ssl.SSLContext | None:
        """Build an SSL context for the connection.

        Returns:
            An unverified :class:`ssl.SSLContext` when verification is
            disabled, otherwise ``None`` (pyVmomi default).
        """
        if self._no_verify_ssl:
            ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
            return ctx
        return None

    @staticmethod
    def _disks_to_string(devices: list) -> str:
        """Convert a list of hardware devices to a disk label:size string.

        Only :class:`pyVmomi.vim.vm.device.VirtualDisk` objects are included.

        Args:
            devices: List of virtual hardware device objects.

        Returns:
            Comma-separated ``label:GBsizeGB`` pairs, e.g.
            ``"Hard disk 1:50GB,Hard disk 2:100GB"``.
        """
        parts: list[str] = []
        for device in devices:
            if isinstance(device, vim.vm.device.VirtualDisk):
                label = device.deviceInfo.label if device.deviceInfo else "disk"
                capacity_kb = device.capacityInKB or 0
                size_gb = round(capacity_kb / 1024 / 1024)
                parts.append(f"{label}:{size_gb}GB")
        return ",".join(parts)

    @staticmethod
    def _networks_to_string(networks: list) -> str:
        """Extract network names from a list of network objects.

        Args:
            networks: List of network managed objects.

        Returns:
            Comma-separated network names.
        """
        names: list[str] = []
        for net in networks:
            try:
                names.append(net.name)
            except Exception:  # pylint: disable=broad-except
                pass
        return ",".join(names)

    @staticmethod
    def _host_name(vm) -> str:  # type: ignore[no-untyped-def]
        """Resolve the ESXi host name for a VM.

        Args:
            vm: pyVmomi VirtualMachine managed object.

        Returns:
            The host's reported name, or ``"unknown"`` on error.
        """
        try:
            return str(vm.runtime.host.name)
        except Exception:  # pylint: disable=broad-except
            return "unknown"

    def _vm_to_record(self, vm) -> VM:  # type: ignore[no-untyped-def]
        """Convert a pyVmomi VirtualMachine object to a :class:`~sources.base.VM`.

        Args:
            vm: pyVmomi VirtualMachine managed object.

        Returns:
            Populated :class:`~sources.base.VM` instance.

        Raises:
            AttributeError: If required VM config attributes are missing.
        """
        cfg = vm.config
        if cfg is None:
            raise AttributeError("vm.config is None")
        devices = cfg.hardware.device or []
        disks = [d for d in devices if isinstance(d, vim.vm.device.VirtualDisk)]
        volumes_count = len(disks)
        volumes_capacity_total_gb = round(sum(d.capacityInKB for d in disks) / 1024 / 1024)
        return VM(
            name=cfg.name,
            host=self._host_name(vm),
            cpus=cfg.hardware.numCPU,
            ram_mb=cfg.hardware.memoryMB,
            networks=self._networks_to_string(vm.network or []),
            volumes=self._disks_to_string(cfg.hardware.device or []),
            source_type="vmware",
            volumes_count=volumes_count,
            volumes_capacity_total_gb=volumes_capacity_total_gb,
        )

    @staticmethod
    def _sanitize_label(value: str) -> str:
        """Remove characters that are illegal in Prometheus label values.

        Args:
            value: Raw label string.

        Returns:
            Sanitised string safe for Prometheus labels.
        """
        return re.sub(r'[\\"\n]', "_", value)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def fetch_vms(self) -> list[VM]:
        """Fetch metadata for all VMs visible to the connected vCenter.

        Returns:
            A list of :class:`~sources.base.VM` instances.
        """
        vms: list[VM] = []
        service_instance = None

        try:
            ctx = self._ssl_context()
            connect_kwargs: dict = {
                "host": self._host,
                "port": self._port,
                "user": self._username,
                "pwd": self._password,
            }
            if ctx is not None:
                connect_kwargs["sslContext"] = ctx

            service_instance = SmartConnect(**connect_kwargs)
            # VMWare API lets retrieve one inventory of content in "content".
            #   then with content.viewManager.CreateXXXView select details.
            content = service_instance.RetrieveContent()
            container_view = content.viewManager.CreateContainerView(
                content.rootFolder, [vim.VirtualMachine], True
            )

            for vm in container_view.view:
                try:
                    vms.append(self._vm_to_record(vm))
                except Exception as exc:  # pylint: disable=broad-except
                    print(f"[VMwareSource] Skipping VM: {exc}")

        except Exception as exc:  # pylint: disable=broad-except
            print(f"[VMwareSource] Connection error: {exc}")
        finally:
            if service_instance is not None:
                try:
                    Disconnect(service_instance)
                except Exception:  # pylint: disable=broad-except
                    pass

        return vms
