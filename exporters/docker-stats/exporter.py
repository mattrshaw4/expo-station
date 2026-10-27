"""docker-stats-exporter: per-container CPU, memory and network from the Docker API.

Why this exists: cAdvisor needs the containerd socket, and Docker Desktop doesn't expose it
to containers (only docker.sock). This reads the same numbers `docker stats` shows, through
docker.sock, and publishes them under cAdvisor's metric names so dashboards work unchanged.
"""

import logging
import os
import time
from concurrent.futures import ThreadPoolExecutor

import docker
from prometheus_client import start_http_server
from prometheus_client.core import REGISTRY, CounterMetricFamily, GaugeMetricFamily

PORT = int(os.getenv("PORT", "9417"))
PROJECT = os.getenv("COMPOSE_PROJECT", "")  # empty = every container on the host
LABELS = ["name", "container_label_com_docker_compose_project",
          "container_label_com_docker_compose_service"]

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("docker-stats-exporter")
client = docker.from_env(timeout=10)


def _labels(c) -> list[str]:
    lab = c.labels or {}
    return [c.name, lab.get("com.docker.compose.project", ""), lab.get("com.docker.compose.service", "")]


def _working_set(mem: dict) -> float:
    """Usage minus inactive page cache, the number the OOM killer cares about (cgroup v1 or v2)."""
    stats = mem.get("stats", {})
    inactive = stats.get("inactive_file", stats.get("total_inactive_file", 0))
    usage = mem.get("usage", 0)
    return float(max(usage - inactive, 0))


def _stats(c):
    try:
        return c, c.stats(stream=False, one_shot=True)  # one_shot: no 1s wait for a 2nd sample
    except Exception as exc:  # noqa: BLE001 - a container can vanish mid-scrape
        log.warning("stats failed for %s: %s", c.name, exc)
        return c, None


class DockerStatsCollector:
    def collect(self):
        start = time.perf_counter()
        cpu = CounterMetricFamily("container_cpu_usage_seconds_total",
                                  "Cumulative CPU time consumed", labels=LABELS)
        mem = GaugeMetricFamily("container_memory_working_set_bytes",
                                "Working set memory", labels=LABELS)
        mem_limit = GaugeMetricFamily("container_spec_memory_limit_bytes",
                                      "Memory limit (0 = unlimited)", labels=LABELS)
        rx = CounterMetricFamily("container_network_receive_bytes_total",
                                 "Bytes received", labels=LABELS)
        tx = CounterMetricFamily("container_network_transmit_bytes_total",
                                 "Bytes transmitted", labels=LABELS)
        up = GaugeMetricFamily("docker_stats_exporter_up", "1 if the Docker API answered")

        try:
            filters = {"label": f"com.docker.compose.project={PROJECT}"} if PROJECT else None
            containers = client.containers.list(filters=filters)
        except Exception as exc:  # noqa: BLE001
            log.error("docker API unreachable: %s", exc)
            up.add_metric([], 0)
            yield up
            return

        with ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(_stats, containers))

        for c, s in results:
            if not s:
                continue
            lv = _labels(c)
            cpu.add_metric(lv, s.get("cpu_stats", {}).get("cpu_usage", {}).get("total_usage", 0) / 1e9)
            mem.add_metric(lv, _working_set(s.get("memory_stats", {})))
            limit = s.get("memory_stats", {}).get("limit", 0)
            mem_limit.add_metric(lv, float(limit if limit < 2**62 else 0))
            nets = s.get("networks") or {}
            rx.add_metric(lv, float(sum(n.get("rx_bytes", 0) for n in nets.values())))
            tx.add_metric(lv, float(sum(n.get("tx_bytes", 0) for n in nets.values())))

        up.add_metric([], 1)
        duration = GaugeMetricFamily("docker_stats_exporter_scrape_seconds", "Time to collect stats")
        duration.add_metric([], time.perf_counter() - start)
        yield from (cpu, mem, mem_limit, rx, tx, up, duration)


if __name__ == "__main__":
    REGISTRY.register(DockerStatsCollector())
    start_http_server(PORT)
    log.info("listening on :%d (project filter: %s)", PORT, PROJECT or "none")
    while True:
        time.sleep(3600)
