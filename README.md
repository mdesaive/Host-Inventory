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
  infrastructure backends. This way the frequency and time of the possibly
  costy API calls can explicitely be controlled in the sidecar containers. 
  Independent of the Prometheus scrape intervalls.

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
```
 
---
 
## Requirements
 
- Python 3.12
- `pyVmomi` (see `app/requirements.txt`)
- Docker with TCP API enabled (port 2375) on source hosts
- VMware vCenter or vcsim
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
There is an awsome VCenter simulator Docker image available. Check vmware/vcsim.
 
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
networks - useful to plan network setup for new infrastructure hosts.. 

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
  <parameters - refer to crontab examples.>
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
## Prometheus dashboards

Two Grafana dashboards are intended for this data:

**VM inventory** — a table showing all VMs and containers across all hosts,
filterable by host, source type and migration status. Numeric fields like
`vm_inventory_ram_mb` and `vm_inventory_cpu_usage_percent` can be joined
to the identity metric `vm_inventory_info` via the `uid` label.

**Network overview** — a table based on `vm_network_attachment`, showing
which VMs are attached to which networks. Filter by network, host or VM
name to identify all workloads that need to move together during migration.

## Prometheus metric structure
 
| Metric | Description |
|--------|-------------|
| `vm_inventory_info` | Stable identity metric (uid, name, source_type) |
| `vm_inventory_host_info` | Current host of the VM |
| `vm_inventory_state_info` | Power/run state |
| `vm_inventory_volumes_info` | Attached volumes |
| `vm_inventory_networks_info` | Attached networks |
| `vm_inventory_cpus` | CPU count |
| `vm_inventory_ram_mb` | RAM in MB |
| `vm_inventory_cpu_usage_mhz` | CPU usage in MHz (VMware) |
| `vm_inventory_cpu_usage_percent` | CPU usage in % (Docker) |
| `vm_inventory_volumes_count` | Number of attached volumes |
| `vm_inventory_volumes_capacity_gb` | Total volume capacity in GB |
| `vm_network_attachment` | Network attachment (one time series per VM+network pair) |

