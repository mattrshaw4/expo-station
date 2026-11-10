"""The ticket printer at the pass: receives Alertmanager webhooks and prints each alert as a log line.

Standard library only (no pip install). Output is one JSON object per line, the same shape the
kitchen services use, so Alloy parses it and every alert lands in Loki next to the app's logs.
"""

import json
import sys
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PORT = 9095
SEVERITY_LEVEL = {"critical": "error", "warning": "warning"}


def emit(level: str, msg: str, **fields) -> None:
    now = time.time()
    record = {
        "ts": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(now)) + f".{int(now % 1 * 1000):03d}Z",
        "level": level,
        "service": "printer",
        "msg": msg,
        **{k: v for k, v in fields.items() if v is not None},  # skip empty fields (e.g. no job label)
    }
    print(json.dumps(record), flush=True)


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/health":
            self._reply(200, b"ok")
        else:
            self._reply(404, b"not found")

    def do_POST(self):
        if self.path != "/alert":
            self._reply(404, b"not found")
            return
        try:
            length = int(self.headers.get("Content-Length", 0))
            payload = json.loads(self.rfile.read(length))
        except (ValueError, json.JSONDecodeError) as exc:
            emit("error", "bad webhook payload", error=str(exc))
            self._reply(400, b"bad payload")
            return

        for alert in payload.get("alerts", []):
            labels = alert.get("labels", {})
            notes = alert.get("annotations", {})
            resolved = alert.get("status") == "resolved"
            emit(
                "info" if resolved else SEVERITY_LEVEL.get(labels.get("severity"), "warning"),
                "ALL CLEAR" if resolved else "ALERT",
                alertname=labels.get("alertname"),
                severity=labels.get("severity"),
                job=labels.get("job"),
                # On "all clear", the summary still holds the numbers from when it fired, which
                # reads like it's still broken. Label it as what it was.
                **({"was": notes.get("summary")} if resolved else {"summary": notes.get("summary")}),
                started=alert.get("startsAt"),
            )
        self._reply(200, b"printed")

    def _reply(self, code: int, body: bytes) -> None:
        self.send_response(code)
        self.send_header("Content-Type", "text/plain")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_args):  # silence the default access log; we print our own lines
        pass


if __name__ == "__main__":
    emit("info", "ticket printer ready", port=PORT)
    try:
        ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
    except KeyboardInterrupt:
        sys.exit(0)
