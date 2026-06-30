# Host-Inventory

Collects VM and container metadata from Docker and VMware sources and exports
it as CSV or Prometheus metrics via node_exporter textfile collector.

Designed as a lightweight migration-tracking tool — not a real-time monitoring
feed. The scrape interval is intentionally configurable and defaults to 300 s.

## Status

Work in progress — not production-ready.

## Repository Structure

```
.
├── app/
│   ├── main.py                  # Entry point
│   ├── sources/
│   │   ├── base.py              # VM dataclass, base source, annotation parser
│   │   ├── docker.py            # Docker TCP API source
│   │   └── vmware.py            # VMware / vcsim source (pyVmomi)
│   └── output/
│       ├── csv.py               # Semicolon-delimited CSV output
│       └── prometheus.py        # Prometheus exposition format output
├── compose.yaml                 # Production Compose setup
├── compose.yaml.example-vcsim-docker  # Example: multiple Docker + vcsim
├── env.example--vcsim-docker    # Matching .env template
└── textfiles/                   # Bind-mounted .prom files for node_exporter
```

## Data Model

The exporter uses a flat `VM` dataclass that represents both VMware VMs and
Docker containers uniformly:

```python
@dataclass
class VM:
    uid: str                       # VMware: vm.config.uuid | Docker: host__name
    source_type: str               # "vmware" | "docker"
    host: str                      # ESXi host / Docker node hostname
    name: str                      # VM / container name
    state: str                     # VMware: poweredOn/poweredOff/suspended
                                   # Docker:  running/exited/paused/...
    cpus: int                      # CPU count; -1 = unlimited (Docker, no CPU limit)
    cpu_usage_mhz: int             # VMware: overallCpuUsage | Docker: 0
    cpu_usage_percent: float       # Docker: CPU% | VMware: 0.0
    ram_mb: int                    # VMware: provisioned | Docker: current usage
    volumes_count: int             # Number
