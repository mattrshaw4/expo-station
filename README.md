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

## Metrics exposed

| Metric | Type | Signal |
|---|---|---|
| `expo_http_request_duration_seconds` | histogram | Latency |
| `expo_http_requests_total` | counter | Traffic / errors |
| `kitchen_tickets_fired_total` | counter | Traffic |
| `kitchen_tickets_cooked_total{outcome="86d"}` | counter | Errors |
| `kitchen_ticket_time_seconds` | histogram | Latency (end to end) |
| `kitchen_rail_depth` | gauge | Saturation |
