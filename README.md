# Host Inventory

Copyright (C) 2026 Melanie Desaive <melanie@desaive.de>  
Licensed under the GNU General Public License v3.0 — see [LICENSE](LICENSE)

---

## Overview

Host Inventory collects metadata from virtual machines and containers and
outputs it either as CSV or in Prometheus Textfile Collector format.

**Sources:** VMware vSphere (via pyVmomi) and Docker (via TCP API)

**Design principles:**

- API calls are categorised as *cheap* (frequent) or *expensive* (infrequent).
  Currently all calls are cheap; expensive is reserved as an extension point
  for future more in depth data collection.
- **CSV output** is intended for manual, interactive queries and migration
  planning.
- **Prometheus output** is intended for continuous monitoring and Grafana
  dashboards.
- **A Docker Compose setup** is included. This provides in one container a
  scrape endpoint to Prometheus and implements in one or more sidecar
  containers the Python code which performs the API calls to the
  infrastructure backends. **This way the frequency and time of the possibly
  costy API calls can explicitely be controlled in the sidecar containers**.
  **Independent of the Prometheus scrape intervalls**.

---

## Project structure

```
app/                    Python application
├── main.py             CLI entrypoint
├── sources/            Data sources
│   ├── base.py         VM dataclass and abstract base class
│   ├── docker.py       Docker source (TCP API)
│   └── vmware.py       VMware source (pyVmomi)
└── output/             Output modules
    ├── csv.py          CSV output (all VM fields)
    ├── csv_networks.py CSV output (network attachments, long format)
    ├── prometheus.py   Prometheus output (VM metrics)
    └── prometheus_networks.py  Prometheus output (network attachments)

crontabs/               Crontab files per sidecar type (not in repo)
env_files/              Per-host environment variables (not in repo)
secrets/                Password files (not in repo)
textfiles/              Prometheus .prom files (not in repo)
examples/               Example configuration files
grafana/                Ready-to-import Grafana dashboard JSONs
```

---

## Requirements

- Python 3.12
- `pyVmomi` (see `app/requirements.txt`)
- Docker with TCP API enabled (port 2375) on source hosts
- VMware vCenter or vcsim

---

## Setting inventory annotations

Migration planning fields and general resource info are maintained directly
at the VM or container using a structured annotation block:

```
[INVENTORY: info_stakeholder=team-x; info_os_contact=jdoe;
info_downtime_impact=4; migration_batch=2; migration_status=planned;
migration_difficulty=3; migration_target=pve-01; migration_notes=some notes]
Any text after the block is kept as free-text annotation.
```

Keys, VM fields and Prometheus labels are identical by convention
(full symmetry from annotation to dashboard).

| Key | Type | Description |
|-----|------|-------------|
| `info_stakeholder` | string | Downtime coordination contact |
| `info_os_contact` | string | Guest OS contact |
| `info_downtime_impact` | int 1-5 | Impact of downtime |
| `migration_batch` | string | Migration phase/wave |
| `migration_status` | enum | `not_started`, `planned`, `in_progress`, `done`, `not_planned` |
| `migration_difficulty` | int 1-5 | Estimated migration difficulty |
| `migration_target` | string | Target host/cluster on Proxmox (`none` if not applicable) |
| `migration_notes` | string | Migration-specific notes |

Rules:

- Key/value pairs are separated by `;` — values must therefore not contain
  semicolons. Spaces in values are fine.
- Unknown keys are ignored. If **no** known key is found, the entire block
  (including brackets) is treated as free text.
- Free text after the block ends up in the `info_annotation` label.
- Integer fields default to `0` if missing or invalid.

### VMware

Put the block into the VM's **Notes** field in vCenter (Edit Notes).

### Docker

Set the container label `host-inventory.annotation`. In Compose, use the
**mapping syntax** with a folded block scalar — the list syntax
(`- "key=value"`) cannot hold multi-line values:

```yaml
services:
  myservice:
    labels:
      host-inventory.annotation: >-
        [INVENTORY: info_stakeholder=team-x; info_os_contact=jdoe;
        info_downtime_impact=4; migration_batch=2;
        migration_status=planned; migration_difficulty=3;
        migration_target=pve-01; migration_notes=some notes]
        Free-text description of the service.
```

Labels are set at container **create** time — after editing the Compose
file, run `docker compose up -d` (a plain restart is not enough). Verify
with:

```bash
docker inspect <container> \
  --format '{{ index .Config.Labels "host-inventory.annotation" }}'
```

---

## CSV queries (manual)

All VMs as CSV:

```bash
python app/main.py --source docker --output csv-vms --host http://<host name or IP>:2375
```

Network attachments as CSV (long format, suitable for pivot tables):

```bash
python app/main.py --source docker --output csv-networks --host http://<host name or IP>:2375
```

VMware against vcsim:
There is an awesome vCenter simulator Docker image available. Check vmware/vcsim.

```bash
python app/main.py --source vmware --output csv-vms \
    --host https://<VCSimulator host name or IP>:8989 \
    --username user --password pass --no-verify-ssl
```

Write output to file:

```bash
python app/main.py --source vmware --output csv-vms \
    --host https://vcenter.example.com \
    --username administrator@vsphere.local \
    --password-file secrets/vmware_password.txt \
    -o inventory.csv
```

### Using the network CSV for migration planning

The `csv-networks` output produces one row per VM and network in long
format. Open it in LibreOffice Calc or Excel and create a pivot table
(Insert → Pivot Table) with VM name and host as row fields and network
as the column field. This gives you a matrix showing which VMs share
networks - useful to plan network setup for new infrastructure hosts.

---

## Grafana dashboards

Ready-to-import dashboard JSONs are in `grafana/`:

- `dashboard_grafana_12_vms_extended.json` — inventory
  table plus sum stats (CPU, RAM, storage) and a per-network VM count panel
- `dashboard_grafana_12_networks.json` — network attachment overview based
  on `vm_network_attachment`
- `dashboard_grafana_12_vms_minimal.json` — basic VM inventory table; superseded by
  the extended version, kept for reference

Import via Dashboards → Import (or paste into an existing dashboard's
JSON model). Adjust the datasource UID if it differs from your Prometheus
datasource.

### Operational notes

**The main table query is an inner join.** Query A of the *Instances*
panel multiplies `vm_inventory_info` with every `*_info` / `info_*` metric
via `* on(uid, source_type) group_left(<label>)`. If one of these metrics
disappears (e.g. after renaming a metric in the exporter without updating
the dashboard), the whole join silently returns nothing — the table still
looks plausible because the numeric queries (B–J) keep filling rows, but
all label columns (networks, volumes, migration_*, info_*) vanish. To
check which metrics exist:

```promql
count by (__name__) ({__name__=~"vm_inventory_.*"})
```

All metrics should be present with roughly identical series counts.

**Columns appear with the data.** Prometheus drops empty label values, so
a column (e.g. `migration_target`) only exists in the table if at least
one VM in the current filter carries a value. Sparse annotations therefore
lead to a "shifting" column set — this is expected behaviour, not a bug.

**Exporter changes require dashboard updates.** Metric and label names
appear in the panel queries, in the variable definitions
(`label_values(...)`), in the transform options and in field overrides.
When renaming, search the dashboard JSON for the old name to catch all
occurrences.

---

## Metrics

All metrics carry the stable identity labels `uid`, `source_type`, `host`
and `name`. The `*_info` / `info_*` metrics additionally carry their value
as a label (constant value `1`); the remaining metrics are numeric gauges.

| Metric | Description |
|--------|-------------|
| `vm_inventory_info` | Stable identity metric (labels: uid, source_type, host, name) |
| `vm_inventory_state_info` | Power/run state (label `state`) |
| `vm_inventory_volumes_info` | Attached volumes, comma-separated (label `volumes`) |
| `vm_inventory_networks_info` | Attached networks, comma-separated (label `networks`) |
| `vm_inventory_migration_batch_info` | Migration phase/wave (label `migration_batch`) |
| `vm_inventory_migration_status_info` | Migration status (label `migration_status`) |
| `vm_inventory_migration_target_info` | Migration target host/cluster (label `migration_target`) |
| `vm_inventory_migration_notes_info` | Migration-specific notes (label `migration_notes`) |
| `vm_inventory_info_annotation` | Free-text annotation (label `info_annotation`) |
| `vm_inventory_info_stakeholder` | Downtime coordination contact (label `info_stakeholder`) |
| `vm_inventory_info_os_contact` | Guest OS contact (label `info_os_contact`) |
| `vm_inventory_cpus` | vCPUs (VMware) / CPU limit (Docker); unlimited containers report the host's thread count, `-1` = undetermined |
| `vm_inventory_ram_mb` | RAM in MB; provisioned (VMware) or current usage (Docker) |
| `vm_inventory_cpu_usage_mhz` | CPU usage in MHz (VMware; `0` for Docker) |
| `vm_inventory_cpu_usage_percent` | CPU usage in percent of one thread (Docker, `docker stats` semantics; `0` for VMware) |
| `vm_inventory_migration_difficulty` | Migration difficulty, 1–5 |
| `vm_inventory_info_downtime_impact` | Downtime impact, 1–5 |
| `vm_inventory_volumes_count` | Number of attached volumes |
| `vm_inventory_volumes_capacity_gb` | Total volume capacity in GB (VMware; `-1` for Docker) |
| `vm_network_attachment` | Network attachment, one series per VM+network pair (label `network`) |

---

## Docker Compose setup

- One **sidecar container** per host runs the script on a cron schedule and
  writes `.prom` files to a shared volume.
- A **node_exporter** container reads those `.prom` files and exposes them
  to Prometheus.

### 1. Copy and edit example files

```bash
cp examples/compose.yaml.example compose.yaml
cp examples/env_docker.example env_files/env_docker01
cp examples/env_vmware.example env_files/env_vmware
cp examples/crontab-docker.example crontabs/crontab-docker
cp examples/crontab-vmware.example crontabs/crontab-vmware
```

### 2. Store the VMware password

```bash
mkdir -p secrets
echo "your_vcenter_password" > secrets/vmware_password.txt
chmod 600 secrets/vmware_password.txt
```

### 3. Build image and start stack

```bash
docker compose build
docker compose up -d
```

### 4. Check logs

```bash
docker compose logs -f
```

### 5. Trigger a run manually

To run a collection immediately without waiting for the next cron trigger:

```bash
docker compose exec <sidecar container name> sh -c 'python /app/main.py \
  <parameters - refer to crontab examples>'
```

The environment variables are already set inside the container.

---

## Environment variables (env_files)

One file per Docker host, e.g. `env_files/env_docker01`:

```
INV_HOST=http://10.0.40.11:2375
INV_PROM_FILE_CHEAP=docker01_cheap.prom
```

For VMware, `env_files/env_vmware`:

```
INV_HOST=https://vcenter.example.com
INV_USERNAME=administrator@vsphere.local
INV_PROM_FILE_CHEAP=vmware_cheap.prom
```

---
