"""order-api: takes orders (tickets), records them in Postgres, and fires them onto the rail."""

import json
import logging
import time
from contextlib import asynccontextmanager

import redis
from fastapi import FastAPI, HTTPException, Request, Response
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Gauge, Histogram, generate_latest
from psycopg_pool import ConnectionPool
from pydantic import BaseModel

from app.common import MENU, RAIL_KEY, REDIS_URL, db_conninfo, get_logger, log

logger = get_logger("order-api")

# --- Metrics -------------------------------------------------------------------
HTTP_REQUESTS = Counter(
    "expo_http_requests_total", "HTTP requests handled", ["method", "route", "status"]
)
HTTP_LATENCY = Histogram(
    "expo_http_request_duration_seconds", "HTTP request latency", ["method", "route"]
)
TICKETS_FIRED = Counter("kitchen_tickets_fired_total", "Tickets fired to the rail", ["dish"])
RAIL_DEPTH = Gauge("kitchen_rail_depth", "Tickets waiting on the rail (queue depth)")

# --- Connections ---------------------------------------------------------------
pool = ConnectionPool(kwargs=db_conninfo(), min_size=1, max_size=10, open=False)
rail = redis.Redis.from_url(REDIS_URL, decode_responses=True)


def _rail_depth() -> float:
    try:
        return float(rail.llen(RAIL_KEY))
    except redis.RedisError:
        return float("nan")  # shows as a gap in the graph instead of breaking the scrape


RAIL_DEPTH.set_function(_rail_depth)


@asynccontextmanager
async def lifespan(_: FastAPI):
    pool.open(wait=True, timeout=30)
    log(logger, logging.INFO, "kitchen open", menu=list(MENU))
    yield
    pool.close()
    log(logger, logging.INFO, "kitchen closed")


app = FastAPI(title="Expo Station: order-api", lifespan=lifespan)


@app.middleware("http")
async def metrics_middleware(request: Request, call_next):
    start = time.perf_counter()
    status = 500
    try:
        response = await call_next(request)
        status = response.status_code
        return response
    finally:
        # Label by route template (/orders/{order_id}), not raw path, to keep cardinality low.
        route = request.scope.get("route")
        path = route.path if route else "unmatched"
        if path != "/metrics":
            HTTP_REQUESTS.labels(request.method, path, str(status)).inc()
            HTTP_LATENCY.labels(request.method, path).observe(time.perf_counter() - start)


class OrderIn(BaseModel):
    dish: str


@app.post("/orders", status_code=202)
def fire_order(order: OrderIn):
    dish = order.dish.lower()
    if dish not in MENU:
        raise HTTPException(status_code=400, detail=f"86'd: '{dish}' isn't on the menu {list(MENU)}")

    with pool.connection() as conn:
        row = conn.execute(
            "INSERT INTO tickets (dish) VALUES (%s) RETURNING id", (dish,)
        ).fetchone()
    order_id = row[0]

    rail.rpush(RAIL_KEY, json.dumps({"order_id": order_id, "dish": dish}))
    TICKETS_FIRED.labels(dish).inc()
    log(logger, logging.INFO, "ticket fired", order_id=order_id, dish=dish)
    return {"order_id": order_id, "dish": dish, "status": "fired"}


@app.get("/orders/{order_id}")
def get_order(order_id: int):
    with pool.connection() as conn:
        row = conn.execute(
            "SELECT id, dish, status, fired_at, served_at FROM tickets WHERE id = %s", (order_id,)
        ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="No such ticket")
    return dict(zip(["order_id", "dish", "status", "fired_at", "served_at"], row))


@app.get("/menu")
def menu():
    return {"menu": list(MENU)}


@app.get("/health")
def health():
    problems = []
    try:
        with pool.connection(timeout=2) as conn:
            conn.execute("SELECT 1")
    except Exception:  # noqa: BLE001 - any DB failure means unhealthy
        problems.append("db")
    try:
        rail.ping()
    except redis.RedisError:
        problems.append("rail")
    if problems:
        raise HTTPException(status_code=503, detail={"unhealthy": problems})
    return {"status": "ok"}


@app.get("/metrics")
def metrics():
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
