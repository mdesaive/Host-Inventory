"""Prometheus Textfile Collector output module.

Writes VM metrics in Prometheus exposition format (version 0.0.4) to stdout.
Intended for use with node_exporter's --collector.textfile.directory option.

Metric structure:
    - vm_inventory_info: stable identity metric, immutable labels only
    - vm_inventory_*_info: one metric per mutable string field
    - vm_inventory_<field>: numeric gauges, stable key labels only
"""
import re
import sys
from sources.base import VM


# Stable identity labels — never change for a given VM
_STABLE_LABELS: tuple[str, ...] = ("uid", "source_type")

# Mutable string fields — each gets its own info metric
_MUTABLE_INFO_FIELDS: tuple[tuple[str, str], ...] = (
    ("name",     "Current name of the VM"),
    ("host",     "Current host of the VM"),
    ("state",    "Current power/run state of the VM"),
    ("volumes",  "Current volumes attached to the VM"),
    ("networks", "Current networks attached to the VM"),
)

# Numeric gauges — labels: stable key only
_GAUGE_METRICS: tuple[tuple[str, str, str], ...] = (
    ("vm_inventory_cpus",               "cpus",                    "Number of CPUs"),
    ("vm_inventory_ram_mb",             "ram_mb",                  "RAM in megabytes"),
    ("vm_inventory_cpu_usage_mhz",      "cpu_usage_mhz",           "CPU usage in MHz"),
    ("vm_inventory_cpu_usage_percent",  "cpu_usage_percent",       "CPU usage in percent"),
    ("vm_inventory_volumes_count",      "volumes_count",           "Number of attached volumes"),
    ("vm_inventory_volumes_capacity_gb","volumes_capacity_total_gb","Total volumes capacity in GB"),
)


def _escape_label_value(value: str) -> str:
    """Escape a string for safe use as a Prometheus label value.

    Per exposition format 0.0.4: backslashes, double-quotes and newlines
    must be escaped.

    Args:
        value: Raw label value.

    Returns:
        Escaped string suitable for inclusion in ``label="value"`` pairs.
    """
    value = value.replace("\\", "\\\\")
    value = value.replace('"', '\\"')
    value = re.sub(r"\n", "\\\\n", value)
    return value


def _build_label_str(vm: VM, extra_fields: tuple[str, ...] = ()) -> str:
    """Build a Prometheus label string from stable key fields plus optional extras.

    The stable key fields (``uid``, ``name``, ``source_type``) are always
    included first.  Additional field names passed via *extra_fields* are
    appended in order.

    Args:
        vm: :class:`~sources.base.VM` instance to read field values from.
        extra_fields: Additional VM field names to include after the stable key.

    Returns:
        Comma-separated ``key="value"`` pairs, ready to be wrapped in ``{}``.
    """
    fields = _STABLE_LABELS + extra_fields
    pairs: list[str] = []
    for field in fields:
        raw = _escape_label_value(str(getattr(vm, field)))
        pairs.append(f'{field}="{raw}"')
    return ",".join(pairs)


def _emit_metric_block(
    metric_name: str,
    help_text: str,
    lines: list[str],
) -> None:
    """Write a complete metric block (HELP, TYPE, data lines) to stdout.

    Args:
        metric_name: Prometheus metric name.
        help_text: Human-readable description for the HELP line.
        lines: Pre-formatted exposition lines (without trailing newline).
    """
    out = sys.stdout
    print(f"# HELP {metric_name} {help_text}", file=out)
    print(f"# TYPE {metric_name} gauge", file=out)
    for line in lines:
        print(line, file=out)


def write_prometheus(vms: list[VM]) -> None:
    """Write VM metrics in Prometheus exposition format (0.0.4) to stdout.

    Emits three categories of metrics:

    1. ``vm_inventory_info`` — stable identity gauge (value 1), labels:
       ``uid``, ``name``, ``source_type`` only.
    2. ``vm_inventory_<field>_info`` — one gauge per mutable string field
       (``host``, ``state``, ``volumes``, ``networks``), value 1.
    3. Numeric gauges for CPU, RAM, disk — stable key labels only.

    Args:
        vms: List of :class:`~sources.base.VM` instances to emit metrics for.
    """
    # --- 1. Stable identity metric ---
    lines = [
        f"vm_inventory_info{{{_build_label_str(vm)}}} 1"
        for vm in vms
    ]
    _emit_metric_block(
        "vm_inventory_info",
        "Stable identity metric for VM inventory",
        lines,
    )

    # --- 2. Mutable string info metrics ---
    for field, help_text in _MUTABLE_INFO_FIELDS:
        metric_name = f"vm_inventory_{field}_info"
        lines = [
            f"{metric_name}{{{_build_label_str(vm, (field,))}}} 1"
            for vm in vms
        ]
        _emit_metric_block(metric_name, help_text, lines)

    # --- 3. Numeric gauges ---
    for metric_name, vm_field, help_text in _GAUGE_METRICS:
        lines = [
            f"{metric_name}{{{_build_label_str(vm)}}} {getattr(vm, vm_field)}"
            for vm in vms
        ]
        _emit_metric_block(metric_name, help_text, lines)
