# Host-Inventory

Collects inventory data from Docker and VMware and exports it as CSV or Prometheus metrics via node_exporter textfile collector.

## Status

Work in progress — currently exploring possibilities, not production-ready.

## Structure

TODO

## Exported Data

Will be documented once the setup stabilizes.

## Usage

### Generate CSV inventory

Clone the repo and copy the `./app` directory to a machine with access to a Docker or VMware API.

VMware:
```bash
python main.py --source vmware --output csv --host https://<hostname>:8989 --username <username> --password <password>
```

Docker:
```bash
python main.py --source docker --output csv --host http://<hostname>:2375
```

### Prometheus exporter

Use the Docker Compose setup in the repo root. It starts two containers:

- **collector sidecar**: runs `main.py` on a configurable interval and writes metrics to a bind-mounted directory
- **node_exporter**: serves the metrics from that directory when scraped by Prometheus

This decoupled design intentionally limits scrape frequency — the inventory data is meant as a static migration overview, not a real-time monitoring feed.

#### Configure Docker Compose

```bash
cp env.example .env
vim .env
```

You need to populate the .env file. Feel free to use the example data in env.example.
