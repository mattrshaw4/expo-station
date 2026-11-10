# syntax=docker/dockerfile:1
# Standard library only: no pip, no build stage needed.
FROM python:3.13-slim
LABEL org.opencontainers.image.title="expo-station-printer" \
      org.opencontainers.image.description="Prints Alertmanager webhooks as JSON log lines"
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
RUN useradd --system --uid 10001 --no-create-home printer
COPY --chown=printer:printer printer.py /srv/printer.py
USER printer
EXPOSE 9095
CMD ["python", "/srv/printer.py"]
