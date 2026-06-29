"""Prometheus Textfile Collector output module.

Writes VM metrics in Prometheus exposition format (version 0.0.4) to stdout.
Intended for use with node_exporter's --collector.textfile.directory option.
"""

import re
import sys

from sources.base import VM

# Metrics to emit, mapping metric name -> VM field name

# TODO: Refactor towards a stable identity metric (container_id/vm_uuid)
# with immutable labels only (name, host, source_type).
# Move mutable fields (networks, volumes) out of labels to avoid
# duplicate series on change. See sources/base.py for data model.
_GAUGE_METRICS: dict[str, str] = {
    "vm_inventory_cpus": "cpus",
    "vm_inventory_ram_mb": "ram_mb",
    "vm_inventory_volumes_count": "volumes_count",
    "vm_inventory_volumes_capacity_total_gb": "volumes_capacity_total_gb",
}

_LABEL_FIELDS: tuple[str, ...] = ("source_type", "name", "host", "state", "cpus", "cpu_usage_mhz", "cpu_usage_percent", "ram_mb", "volumes_count", "volumes_capacity_total_gb", "volumes", "networks")


def _sanitize_label_value(value: str) -> str:
    """Escape characters that are forbidden inside Prometheus label values.

    Per the exposition format spec, backslashes, double-quotes and newlines
    must be escaped.

    Args:
        value: Raw label value string.

    Returns:
        Escaped string safe for inclusion in ``label="value"`` pairs.
    """
    value = value.replace("\\", "\\\\")
    value = value.replace('"', '\\"')
    value = re.sub(r"\n", "\\\\n", value)
    return value


def _build_labels(vm: VM) -> str:
    """Build a Prometheus label set string for a VM.

    Args:
        vm: :class:`~sources.base.VM` instance.

    Returns:
        A string like ``name="foo",host="bar",...`` ready to be wrapped in
        curly braces.
    """
    pairs: list[str] = []
    for field in _LABEL_FIELDS:
        raw = str(getattr(vm, field))
        pairs.append(f'{field}="{_sanitize_label_value(raw)}"')
    return ",".join(pairs)


def write_prometheus(vms: list[VM]) -> None:
    """Write VM metrics in Prometheus exposition format to stdout.

    Emits a ``vm_inventory_info`` gauge (value 1) with all VM fields as labels,
    plus separate gauges for ``vm_inventory_cpus`` and ``vm_inventory_ram_mb``.

    Args:
        vms: List of :class:`~sources.base.VM` instances to emit metrics for.
    """
    out = sys.stdout

    # Info metric – alle Felder als Labels, Wert immer 1
    print("# HELP vm_inventory_info VM inventory info metric", file=out)
    print("# TYPE vm_inventory_info gauge", file=out)
    for vm in vms:
        labels = _build_labels(vm)
        # Triple brackets are neccessary to frame labels in single brackets.
        print(f"vm_inventory_info{{{labels}}} 1", file=out)

    # Numerische Gauges
    for metric_name, vm_field in _GAUGE_METRICS.items():
        print(f"# HELP {metric_name} VM inventory metric: {vm_field}", file=out)
        print(f"# TYPE {metric_name} gauge", file=out)
        for vm in vms:
            labels = _build_labels(vm)
            value = getattr(vm, vm_field)
            # Triple brackets are neccessary to frame labels in single brackets.
            print(f"{metric_name}{{{labels}}} {value}", file=out)

