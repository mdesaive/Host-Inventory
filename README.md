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
│   │   ├── base.py              # VM dataclass and abstract base source
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
    uid: str                       # VMware: vm.config.uuid | Docker: container name
    source_type: str               # "vmware" | "docker"
    name: str                      # VM / container name
    host: str                      # ESXi host / Docker node hostname
    state: str                     # VMware: poweredOn/poweredOff/suspended
                                   # Docker:  running/exited/paused/...
    cpus: int                      # CPU count; -1 = unlimited (Docker, no CPU limit)
    cpu_usage_mhz: int             # VMware: overallCpuUsage | Docker: 0
    cpu_usage_percent: float       # Docker: CPU% | VMware: 0.0
    ram_mb: int                    # VMware: provisioned | Docker: current usage
    volumes_count: int             # Number of attached disks / mounts
    volumes_capacity_total_gb: int # VMware: sum of disk sizes | Docker: -1
    volumes: str                   # VMware: "Hard disk 1:50GB,Hard disk 2:100GB"
                                   # Docker:  "/data,/config"
    networks: str                  # Comma-separated network names
```

### Prometheus metric structure

The Prometheus output (`--output prometheus`) splits the fields into three
categories to keep time series stable across state changes and migrations.

**Stable identity metric** — labels never change, no new series on state
changes. `uid` remains stable across renames and host migrations:

```
vm_inventory_info{uid, name, source_type} 1
```

**Mutable info metrics** — one metric per mutable string field, value always
1. A series ends (goes stale) when the value changes and a new one starts.
This is intentional and decoupled from the stable identity metric:

```
vm_inventory_host_info{uid, name, source_type, host}       1
vm_inventory_state_info{uid, name, source_type, state}     1
vm_inventory_volumes_info{uid, name, source_type, volumes} 1
vm_inventory_networks_info{uid, name, source_type, networks} 1
```

**Numeric gauges** — stable key labels only, no mutable string fields:

```
vm_inventory_cpus{uid, name, source_type}
vm_inventory_ram_mb{uid, name, source_type}
vm_inventory_cpu_usage_mhz{uid, name, source_type}
vm_inventory_cpu_usage_percent{uid, name, source_type}
vm_inventory_volumes_count{uid, name, source_type}
vm_inventory_volumes_capacity_gb{uid, name, source_type}
```

## Usage

### Requirements

```bash
pip install -r app/requirements.txt
```

Or use a venv:

```bash
python3 -m venv ~/venv-host-inventory
source ~/venv-host-inventory/bin/activate
pip install -r app/requirements.txt
```

### Setup Password File for VMWare

Set up a plain file with limited access rights that containers your VMWare users password.

### Run directly

**CSV output:**

```bash
# Docker
python app/main.py --source docker --output csv \
  --host http://<hostname>:2375

# VMware / vcsim
python app/main.py --source vmware --output csv \
  --host https://<hostname>:443 \
  --username <user> --password-file <path to password file>
```

**Prometheus output (stdout):**

```bash
# Docker
python app/main.py --source docker --output prometheus \
  --host http://<hostname>:2375

# VMware
python app/main.py --source vmware --output prometheus \
  --host https://<hostname>:443 \
  --username <user> --password-file <path to password file> 
```

### Docker Compose setup

The Compose setup runs one `node_exporter` container plus one sidecar per
source. Each sidecar runs `main.py` in a loop and writes a `.prom` file into
a shared bind-mounted `textfiles/` directory. `node_exporter` serves those
files when scraped by Prometheus.

**1. Copy and edit the env file:**

```bash
cp env.example--vcsim-docker .env
vim .env
```

`.env` variables:

| Variable | Description | Example |
|---|---|---|
| `DCK01_HOST` … `DCK06_HOST` | Docker TCP endpoint URLs | `http://10.0.40.15:2375` |
| `VCSIM_HOST` | vCenter / vcsim URL | `https://vcenter.example.com` |
| `VCSIM_USERNAME` | vCenter username | `administrator@vsphere.local` |
| `VCSIM_PASSWORD` | vCenter password | |
| `SCRAPE_INTERVAL` | Seconds between collection runs (default: 300) | `300` |

**2. Start:**

```bash
docker compose -f compose.yaml.example-vcsim-docker up -d
```

**3. Verify:**

```bash
# node_exporter metrics endpoint
curl http://localhost:9101/metrics | grep vm_inventory

# raw .prom files
ls -lh textfiles/
cat textfiles/docker_tools01.prom
```
## Grafana Dashboard

### Concept: join on `uid`

`uid` is the stable anchor across migrations. VMware UUIDs survive renames
and host migrations. Docker container names are stable in Compose stacks
(prefixed with the hostname to ensure uniqueness across nodes).
All numeric metrics carry only `uid` and `source_type` as labels —
mutable fields like `host`, `state`, `name` are joined in via PromQL:

```promql
vm_inventory_info
  * on(uid, source_type) group_left(name)     vm_inventory_name_info
  * on(uid, source_type) group_left(host)     vm_inventory_host_info
  * on(uid, source_type) group_left(state)    vm_inventory_state_info
  * on(uid, source_type) group_left(networks) vm_inventory_networks_info
  * on(uid, source_type) group_left(volumes)  vm_inventory_volumes_info
```

This way a time series survives the move from `esx-01` to `pve-01` without
a gap.

### Building the inventory table

**1. Verify the data source**

Settings → Data Sources → select the Prometheus instance that scrapes the
`node_exporter` running in this Compose stack. Smoke-test in Explore:

```promql
vm_inventory_info
```

If it returns results the full pipeline
(exporter → textfile → node\_exporter → Prometheus → Grafana) is working.

**2. Create a new panel**

Dashboards → New → New Dashboard → Add visualization → select your
Prometheus data source.

**3. Add queries**

Add one query per metric. For every query set two options in the query editor:
- **Format** → `Table`
- **Type** → `Instant`

These two settings are mandatory — without them Grafana shows a time series
instead of a single current value per VM.

Set a **Legend** label for each query — this becomes the column name in the
table after the Merge transform:

| Query | Legend | Metric |
|---|---|---|
| A | `base` | `vm_inventory_info * on(uid, source_type) group_left(name) vm_inventory_name_info * on(uid, source_type) group_left(host) vm_inventory_host_info{host=~"$host"} * on(uid, source_type) group_left(state) vm_inventory_state_info * on(uid, source_type) group_left(networks) vm_inventory_networks_info * on(uid, source_type) group_left(volumes) vm_inventory_volumes_info` |
| B | `CPUs` | `vm_inventory_cpus{source_type=~"$source_type"} * on(uid, source_type) group_left(host) vm_inventory_host_info{host=~"$host"}` |
| C | `RAM (MB)` | `vm_inventory_ram_mb{source_type=~"$source_type"} * on(uid, source_type) group_left(host) vm_inventory_host_info{host=~"$host"}` |
| D | `CPU (MHz)` | `vm_inventory_cpu_usage_mhz{source_type=~"$source_type"} * on(uid, source_type) group_left(host) vm_inventory_host_info{host=~"$host"}` |
| E | `CPU (%)` | `vm_inventory_cpu_usage_percent{source_type=~"$source_type"} * on(uid, source_type) group_left(host) vm_inventory_host_info{host=~"$host"}` |
| F | `Volumes` | `vm_inventory_volumes_count{source_type=~"$source_type"} * on(uid, source_type) group_left(host) vm_inventory_host_info{host=~"$host"}` |
| G | `Capacity (GB)` | `vm_inventory_volumes_capacity_gb{source_type=~"$source_type"} * on(uid, source_type) group_left(host) vm_inventory_host_info{host=~"$host"}` |

Query A is the base — it carries all string fields via join. Queries B–G
each add one numeric value. The `host=~"$host"` and
`source_type=~"$source_type"` filters wire up the dashboard variables
(see step 8).

**4. Transform tab**

Click the **Transform** tab and add the following transforms in order:

1. **Labels to fields**
   - Mode: `Columns`
   - Value field name: `uid`

2. **Merge series / tables**

   The first transform converts Prometheus labels into table columns. The
   second merges all queries into one row per VM matched on `uid`.

3. **Filter fields by name** — tick only the columns you want to display,
   for example: `name`, `source_type`, `host`, `state`, `CPUs`, `RAM (MB)`,
   `CPU (MHz)`, `CPU (%)`, `Volumes`, `Capacity (GB)`, `networks`, `volumes`.
   Hide `uid`, `instance`, `job` and any other internal labels.

4. **Organize fields** — reorder columns by drag and drop and rename any
   remaining fields as needed.

**5. Optional: colour the state column**

Panel options → **Value mappings** → add one mapping per state string:

| Value | Color |
|---|---|
| `running` / `poweredOn` | Green |
| `exited` / `poweredOff` | Red |
| `paused` / `suspended` | Yellow |

**6. Set panel type to Table**

Top right of the panel editor → visualization picker → select **Table**.

**7. Save the dashboard.**

**8. Add filter variables**

Dashboard Settings → Variables → New variable. Add two variables:

Variable 1 — filter by source type:

| Setting | Value |
|---|---|
| Type | Query |
| Name | `source_type` |
| Query | `label_values(vm_inventory_info, source_type)` |
| Include All option | on |

Variable 2 — filter by host:

| Setting | Value |
|---|---|
| Type | Query |
| Name | `host` |
| Query | `label_values(vm_inventory_host_info, host)` |
| Include All option | on |

Save the dashboard settings. Two dropdowns appear at the top of the
dashboard — one to filter by source type (docker / vmware) and one to
filter by host. Selecting **All** shows everything.
