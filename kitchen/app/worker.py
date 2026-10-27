"""line-worker: pulls tickets off the rail, "cooks" them, and marks them served (or 86'd)."""

import json
import logging
import os
import pathlib
import random
import signal
import time

import psycopg
import redis
from prometheus_client import Counter, Histogram, start_http_server

from app.common import MENU, RAIL_KEY, REDIS_URL, db_conninfo, get_logger, log

logger = get_logger("line-worker")

FAIL_RATE = float(os.getenv("FAIL_RATE", "0.02"))  # chance a ticket gets 86'd
METRICS_PORT = int(os.getenv("METRICS_PORT", "9100"))
HEARTBEAT = pathlib.Path("/tmp/heartbeat")  # the healthcheck watches this file's age

TICKETS_COOKED = Counter(
    "kitchen_tickets_cooked_total", "Tickets finished by the line", ["dish", "outcome"]
)
TICKET_TIME = Histogram(
    "kitchen_ticket_time_seconds",
    "Fired-to-served time per ticket",
    ["dish"],
    # Top bucket must exceed the worst real ticket time, or p95 flatlines at the top bucket
    # (it read exactly 60s while real tickets waited minutes on a backed-up rail).
    buckets=(0.5, 1, 2, 3, 5, 8, 13, 21, 34, 60, 120, 300, 600),
)

# Pre-create every label combination at 0. A counter series doesn't exist until first
# incremented, so with no 86'd tickets yet the error-ratio query returned *nothing*
# (shown as "No tickets") instead of 0%.
for _dish in MENU:
    for _outcome in ("served", "86d"):
        TICKETS_COOKED.labels(_dish, _outcome)
    TICKET_TIME.labels(_dish)

running = True


def _stop(signum, _frame):
    global running
    running = False
    log(logger, logging.INFO, "shutdown requested", signal=signal.Signals(signum).name)


signal.signal(signal.SIGTERM, _stop)
signal.signal(signal.SIGINT, _stop)


def cook(conn: psycopg.Connection, order_id: int, dish: str) -> None:
    low, high = MENU.get(dish, (1.0, 2.0))
    time.sleep(random.uniform(low, high))

    if random.random() < FAIL_RATE:
        conn.execute("UPDATE tickets SET status = '86d' WHERE id = %s", (order_id,))
        TICKETS_COOKED.labels(dish, "86d").inc()
        log(logger, logging.WARNING, "ticket 86'd", order_id=order_id, dish=dish)
        return

    row = conn.execute(
        """
        UPDATE tickets SET status = 'served', served_at = now()
        WHERE id = %s
        RETURNING EXTRACT(EPOCH FROM served_at - fired_at)
        """,
        (order_id,),
    ).fetchone()
    ticket_time = float(row[0]) if row else 0.0
    TICKET_TIME.labels(dish).observe(ticket_time)
    TICKETS_COOKED.labels(dish, "served").inc()
    log(logger, logging.INFO, "ticket served", order_id=order_id, dish=dish,
        ticket_time_s=round(ticket_time, 3))


def main() -> None:
    start_http_server(METRICS_PORT)
    rail = redis.Redis.from_url(REDIS_URL, decode_responses=True)
    conn = psycopg.connect(**db_conninfo(), autocommit=True)
    log(logger, logging.INFO, "line worker on station", fail_rate=FAIL_RATE)

    while running:
        HEARTBEAT.touch()
        try:
            item = rail.blpop([RAIL_KEY], timeout=5)  # wake every 5s so SIGTERM is honoured
        except redis.RedisError as exc:
            log(logger, logging.ERROR, "rail unreachable", error=str(exc))
            time.sleep(2)
            continue
        if item is None:
            continue

        ticket = json.loads(item[1])
        try:
            cook(conn, ticket["order_id"], ticket["dish"])
        except psycopg.OperationalError as exc:
            log(logger, logging.ERROR, "db connection lost, reconnecting",
                order_id=ticket["order_id"], error=str(exc))
            rail.lpush(RAIL_KEY, item[1])  # put the ticket back on the rail
            time.sleep(2)
            conn = psycopg.connect(**db_conninfo(), autocommit=True)

    conn.close()
    log(logger, logging.INFO, "line worker off station")


if __name__ == "__main__":
    main()
