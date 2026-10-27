# Expo Station

A Docker observability project. A small "kitchen" app takes orders and cooks them; a monitoring
stack (Prometheus, Grafana, Loki, Alloy, Alertmanager) watches it the way an expo cook watches the pass.

## Phase 1: the kitchen

| Service | Role | Kitchen term |
|---|---|---|
| `order-api` | FastAPI app that takes orders, `/metrics` on :8000 | Front of house |
| `line-worker` | Pulls tickets off the queue and cooks them, `/metrics` on :9100 | The line |
| `rail` | Redis list holding pending tickets | Ticket rail |
| `db` | Postgres, stores every ticket | The pantry / ticket book |

## Run it

```bash
cp .env.example .env
openssl rand -base64 24 | tr -d '\n' > secrets/db_password.txt
docker compose up -d --build
docker compose ps          # all four should reach (healthy)
./scripts/fire-orders.sh 20
```

- API docs: http://localhost:8000/docs
- App metrics: http://localhost:8000/metrics
- Live-reload while coding: `docker compose watch`

## Phase 2: the expo station (metrics)

| Service | Role | URL |
|---|---|---|
| `prometheus` | Scrapes every target every 15s, stores 7 days, runs recording rules | http://localhost:9090 |
| `docker-stats` | Per-container CPU, memory, network via the Docker API (our own exporter) | internal :9417 |
| `grafana` | "Expo Station" dashboard, provisioned from this repo | http://localhost:3000 |

```bash
openssl rand -base64 18 | tr -d '\n' > secrets/grafana_admin_password.txt
docker compose up -d --build
cat secrets/grafana_admin_password.txt   # log in to Grafana as admin with this
```

Check every scrape target is `UP`: http://localhost:9090/targets

### Everything is code

- `prometheus/prometheus.yml`: scrape jobs
- `prometheus/rules/kitchen.rules.yml`: recording rules (p95 ticket time, 86 ratio, etc.)
- `grafana/provisioning/`: datasource and dashboard provider
- `grafana/dashboards/expo-station.json`: the dashboard itself. Edits made in the UI won't save;
  change the JSON (or export from the UI and commit it).

### Lessons from building it

- **cAdvisor doesn't work on Docker Desktop with Docker 29.** cAdvisor 0.60 needs the
  containerd socket even in Docker mode, and Docker Desktop only exposes `docker.sock` to
  containers. On native Linux, `--containerd=<socket> --containerd-namespace=moby` fixes it
  (Docker 29 keeps containers in containerd's `moby` namespace). On Desktop there is no socket
  to point at, so `exporters/docker-stats/` reads the Docker API instead and publishes the
  same metric names cAdvisor uses, so the dashboard didn't change.
- **cAdvisor moved registries.** `gcr.io/cadvisor` stopped updating Dec 2025; use `ghcr.io/google/cadvisor`.
- **Histogram buckets can lie.** p95 ticket time flatlined at exactly 60s, the top bucket,
  while real tickets waited minutes. The top bucket must exceed the worst real value.
- **A counter label doesn't exist until it's incremented.** With no 86'd tickets yet, the
  error-ratio query returned nothing instead of 0%. Pre-create every label combination at 0.
- **"No data" isn't "zero".** p95 latency showed a green `0` when nothing was being served.
  Panels now say "No tickets" when there's no data instead of faking a perfect score.
- **Healthchecks look like traffic.** Docker hits `/health` every 10s (0.1 req/s). The traffic
  panel excludes it so it shows customers only.

### Security note

`docker-stats` mounts `/var/run/docker.sock`. That is root-equivalent access to Docker even
when mounted `:ro` (read-only blocks file writes, not API calls). Acceptable for a local lab;
in anything shared, put a read-only Docker socket proxy in front of it.

## Metrics exposed

| Metric | Type | Signal |
|---|---|---|
| `expo_http_request_duration_seconds` | histogram | Latency |
| `expo_http_requests_total` | counter | Traffic / errors |
| `kitchen_tickets_fired_total` | counter | Traffic |
| `kitchen_tickets_cooked_total{outcome="86d"}` | counter | Errors |
| `kitchen_ticket_time_seconds` | histogram | Latency (end to end) |
| `kitchen_rail_depth` | gauge | Saturation |
