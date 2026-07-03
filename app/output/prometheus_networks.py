"""
output/prometheus_networks.py
------------------------------
Prometheus-Netzwerk-Output-Modul für den VM-Metadaten-Exporter.

Schreibt VM-Netzwerk-Zuordnungen im Prometheus Textfile Collector Format.
Pro VM und Netzwerk wird eine eigene Zeitreihe ausgegeben. Dieses Format
ermöglicht in Grafana die Filterung nach Netzwerk, Host und VM-Name.

Beispielausgabe::

    # HELP vm_network_attachment Network attachment for a VM or container
    # TYPE vm_network_attachment gauge
    vm_network_attachment{uid="...",name="web-01",source_type="vmware",
        host="esx-01",network="frontend"} 1
    vm_network_attachment{uid="...",name="web-01",source_type="vmware",
        host="esx-01",network="backend"} 1

Verwendung via CLI::

    python main.py --source vmware --output prometheus-networks

Prometheus-Konfiguration::

    scrape_configs:
      - job_name: 'vm_networks'
        static_configs:
          - targets: ['localhost:9100']
"""

import sys
from typing import IO, List, Optional

from sources.base import VM

_METRIC_NAME = "vm_network_attachment"
_METRIC_HELP = "Network attachment for a VM or container. One time series per VM+network pair."


def _escape_label_value(value: str) -> str:
    """Escape characters forbidden inside Prometheus label values.

    Per the exposition format spec, backslashes, double-quotes and
    newlines must be escaped.

    Args:
        value: Raw label value string.

    Returns:
        Escaped string safe for inclusion in ``label="value"`` pairs.
    """
    value = value.replace("\\", "\\\\")
    value = value.replace('"', '\\"')
    value = value.replace("\n", "\\n")
    return value


def _build_label_string(vm: VM, network: str) -> str:
    """Build a Prometheus label set string for a VM+network pair.

    Args:
        vm: :class:`~sources.base.VM` instance.
        network: Network name for this time series.

    Returns:
        A string like ``{uid="...",name="...",network="..."}`` ready
        for inclusion in a Prometheus exposition line.
    """
    pairs = [
        f'uid="{_escape_label_value(vm.uid)}"',
        f'name="{_escape_label_value(vm.name)}"',
        f'source_type="{_escape_label_value(vm.source_type)}"',
        f'host="{_escape_label_value(vm.host)}"',
        f'network="{_escape_label_value(network)}"',
    ]
    return "{" + ",".join(pairs) + "}"


def write_prometheus_networks(
    vms: List[VM],
    file: Optional[IO[str]] = None,
) -> None:
    """Write VM network attachments in Prometheus exposition format.

    Emits one ``vm_network_attachment`` gauge time series per VM+network
    pair with a value of 1. VMs without networks are skipped. The output
    is compatible with the Prometheus Textfile Collector and direct HTTP
    scraping.

    Args:
        vms: List of :class:`~sources.base.VM` instances to emit metrics for.
        file: Output file object. If None, writes to stdout.
    """
    out = file or sys.stdout

    out.write(f"# HELP {_METRIC_NAME} {_METRIC_HELP}\n")
    out.write(f"# TYPE {_METRIC_NAME} gauge\n")

    for vm in vms:
        networks = [n.strip() for n in vm.networks.split(",") if n.strip()]
        for network in networks:
            labels = _build_label_string(vm, network)
            out.write(f"{_METRIC_NAME}{labels} 1\n")

    out.write("\n")
