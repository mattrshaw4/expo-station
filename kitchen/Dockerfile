# syntax=docker/dockerfile:1
ARG PYTHON_VERSION=3.13

# ---- Stage 1: build the virtualenv (pip, caches, build tooling stay here) ----
FROM python:${PYTHON_VERSION}-slim AS build
ENV PIP_DISABLE_PIP_VERSION_CHECK=1
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
COPY requirements.txt .
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install -r requirements.txt

# ---- Stage 2: runtime image (only the venv + app code) ----
FROM python:${PYTHON_VERSION}-slim AS runtime
LABEL org.opencontainers.image.title="expo-station-kitchen" \
      org.opencontainers.image.description="Sample kitchen app for the Expo Station observability stack"
ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1
RUN useradd --system --uid 10001 --no-create-home kitchen
COPY --from=build /opt/venv /opt/venv
WORKDIR /srv
COPY --chown=kitchen:kitchen app ./app
USER kitchen
EXPOSE 8000 9100
# Exec form so the process gets SIGTERM directly and shuts down cleanly.
CMD ["uvicorn", "app.api:app", "--host", "0.0.0.0", "--port", "8000"]
