import logging
import os
import re

import google.auth
import google.auth.transport.requests
import requests as req_lib
from flask import Flask, Response, redirect, request
from google.cloud import storage

logging.basicConfig(level=logging.INFO)

app = Flask(__name__)

BACKEND_URL = os.environ.get(
    "BACKEND_URL",
    "https://storage.googleapis.com/swat-releases-serve",
)
SERVE_BUCKET = os.environ.get("SERVE_BUCKET", "swat-releases-serve")

_LOCAL_HOSTS = ("localhost", "127.0.0.1", "host.docker.internal")
_IS_LOCAL = any(h in BACKEND_URL for h in _LOCAL_HOSTS)

_VERSION_RE = re.compile(r"^[^/]+/\d+\.\d+\.\d+(?:\.\d+)?$")
_LATEST_RE = re.compile(r"^([^/]+)/latest$")

# Module-level singletons — credentials cached and refreshed only on expiry
if not _IS_LOCAL:
    _credentials, _ = google.auth.default(
        scopes=["https://www.googleapis.com/auth/devstorage.read_only"]
    )
    _storage_client = storage.Client()
else:
    _credentials = None
    _storage_client = None


def _get_access_token() -> str | None:
    if _IS_LOCAL:
        return None
    auth_req = google.auth.transport.requests.Request()
    _credentials.refresh(auth_req)
    return _credentials.token


def _resolve_latest(tool_id: str) -> str:
    if _IS_LOCAL:
        return "local-dev-version"
    blob = _storage_client.bucket(SERVE_BUCKET).blob(f"{tool_id}/latest")
    return blob.download_as_text().strip()


@app.route("/healthz")
def health():
    return {"status": "healthy", "backend": BACKEND_URL}, 200


@app.route("/", defaults={"path": ""}, methods=["GET", "HEAD"])
@app.route("/<path:path>", methods=["GET", "HEAD"])
def proxy(path):
    latest_match = _LATEST_RE.match(path)
    if latest_match:
        tool_id = latest_match.group(1)
        try:
            version = _resolve_latest(tool_id)
        except Exception as exc:
            app.logger.error(f"latest lookup failed: {exc}")
            return f"latest lookup error: {exc}", 502
        return redirect(f"/{tool_id}/{version}", 302)

    if not path or path.endswith("/"):
        gcs_path = path + "index.html"
    elif _VERSION_RE.match(path):
        gcs_path = path + ".html"
    else:
        gcs_path = path

    target = f"{BACKEND_URL.rstrip('/')}/{gcs_path}"
    if request.query_string:
        target = f"{target}?{request.query_string.decode()}"

    app.logger.info(f"Proxying {request.method} /{path} → {target}")

    try:
        token = _get_access_token()
    except Exception as exc:
        app.logger.error(f"Token error: {exc}")
        return f"Token error: {exc}", 500

    headers = {k: v for k, v in request.headers if k.lower() != "host"}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    try:
        resp = req_lib.request(
            method=request.method,
            url=target,
            headers=headers,
            data=request.get_data(),
            allow_redirects=False,
            timeout=30,
        )
    except Exception as exc:
        app.logger.error(f"Backend error: {exc}")
        return f"Backend error: {exc}", 502

    skip = {"content-encoding", "content-length", "transfer-encoding", "connection"}
    out_headers = [(k, v) for k, v in resp.raw.headers.items() if k.lower() not in skip]
    return Response(resp.content, resp.status_code, out_headers)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))  # nosec B104 # nosemgrep
