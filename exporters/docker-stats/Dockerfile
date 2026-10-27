# syntax=docker/dockerfile:1
FROM python:3.13-slim AS build
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
COPY requirements.txt .
RUN --mount=type=cache,target=/root/.cache/pip pip install -r requirements.txt

FROM python:3.13-slim
LABEL org.opencontainers.image.title="docker-stats-exporter" \
      org.opencontainers.image.description="Per-container CPU/memory/network from docker.sock, cAdvisor-compatible metric names"
ENV PATH="/opt/venv/bin:$PATH" PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
COPY --from=build /opt/venv /opt/venv
COPY exporter.py /srv/exporter.py
EXPOSE 9417
# Runs as root: reading docker.sock requires it on Docker Desktop. See README security note.
CMD ["python", "/srv/exporter.py"]
