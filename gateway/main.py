import html as _html
import json
import logging
import os
import re
import time

import google.auth
import google.auth.transport.requests
import requests as req_lib
from flask import Flask, Response, redirect, request
from google.cloud import storage

logging.basicConfig(level=logging.INFO)

app = Flask(__name__)


class _JsonFormatter(logging.Formatter):
    _LEVELS = {
        logging.DEBUG: "DEBUG",
        logging.INFO: "INFO",
        logging.WARNING: "WARNING",
        logging.ERROR: "ERROR",
        logging.CRITICAL: "CRITICAL",
    }

    def format(self, record: logging.LogRecord) -> str:
        payload: dict = {
            "severity": self._LEVELS.get(record.levelno, "DEFAULT"),
            "message": record.getMessage(),
        }
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        if hasattr(record, "fields"):
            payload.update(record.fields)
        return json.dumps(payload)


_handler = logging.StreamHandler()
_handler.setFormatter(_JsonFormatter())
app.logger.handlers = [_handler]
app.logger.setLevel(logging.INFO)
app.logger.propagate = False

BACKEND_URL = os.environ.get(
    "BACKEND_URL",
    "https://storage.googleapis.com/swat-releases-serve",
)
SERVE_BUCKET = os.environ.get("SERVE_BUCKET", "swat-releases-serve")
INPUT_BUCKET = os.environ.get("INPUT_BUCKET", "swat-releases-input")
_UPLOAD_TOOL_IDS = [
    t.strip()
    for t in os.environ.get("UPLOAD_TOOL_IDS", "cortex-catalyst").split(",")
    if t.strip()
]
_VERSION_RE_UPLOAD = re.compile(r"^\d{2}\.\d+\.\d+(\.\d+)?$")

_LOCAL_HOSTS = ("localhost", "127.0.0.1", "host.docker.internal")
_IS_LOCAL = any(h in BACKEND_URL for h in _LOCAL_HOSTS)

_VERSION_RE = re.compile(r"^[^/]+/\d+\.\d+\.\d+(?:\.\d+)?$")
_LATEST_RE = re.compile(r"^([^/]+)/latest$")

_UPLOAD_PAGE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Upload Release Notes — SWAT Releases</title>
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{background:#0f1117;color:#e2e8f0;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;min-height:100vh;display:flex;align-items:center;justify-content:center;padding:2rem}
.card{background:#1a1d27;border:1px solid #2d3148;border-radius:12px;padding:2rem;width:100%;max-width:640px}
h1{font-size:1.4rem;font-weight:600;margin-bottom:.25rem;color:#f8fafc}
.sub{font-size:.85rem;color:#64748b;margin-bottom:1.75rem}
.field{margin-bottom:1.25rem}
label{display:block;font-size:.75rem;font-weight:500;color:#94a3b8;margin-bottom:.4rem;text-transform:uppercase;letter-spacing:.05em}
select,input[type=text],textarea{width:100%;background:#0f1117;border:1px solid #2d3148;border-radius:6px;color:#e2e8f0;font-size:.9rem;padding:.6rem .75rem;outline:none;transition:border-color .15s}
select:focus,input[type=text]:focus,textarea:focus{border-color:#fa582d}
textarea{min-height:240px;font-family:'SF Mono','Fira Code',Consolas,monospace;font-size:.8rem;resize:vertical}
.ver-row{display:flex;gap:.75rem;align-items:flex-start}
.ver-row input{flex:1}
.badge{padding:.55rem .75rem;border-radius:6px;font-size:.75rem;font-weight:600;white-space:nowrap;background:#1a1d27;border:1px solid #2d3148;color:#475569}
.badge.release{background:rgba(62,207,142,.15);border-color:#3ecf8e;color:#3ecf8e}
.badge.hotfix{background:rgba(245,158,11,.15);border-color:#f59e0b;color:#f59e0b}
.badge.invalid{background:rgba(239,68,68,.1);border-color:#ef4444;color:#ef4444}
.note{font-size:.75rem;color:#475569;margin-top:.35rem}
.err{background:rgba(239,68,68,.1);border:1px solid #ef4444;border-radius:6px;padding:.75rem 1rem;font-size:.85rem;color:#fca5a5;margin-bottom:1rem}
.ok{background:rgba(62,207,142,.1);border:1px solid #3ecf8e;border-radius:6px;padding:.75rem 1rem;font-size:.85rem;color:#6ee7b7;margin-bottom:1rem}
.ok code{font-family:monospace;background:rgba(0,0,0,.3);padding:.1em .3em;border-radius:3px}
button{width:100%;padding:.7rem 1.5rem;background:#fa582d;color:#fff;border:none;border-radius:6px;font-size:.9rem;font-weight:600;cursor:pointer;transition:background .15s;margin-top:.5rem}
button:hover{background:#e04820}
button:disabled{background:#4a1a0a;color:#7a3a2a;cursor:not-allowed}
input[type=file]{display:none}
.file-btn{display:flex;align-items:center;gap:.5rem;padding:.6rem .75rem;background:#0f1117;border:1px solid #2d3148;border-radius:6px;color:#94a3b8;font-size:.85rem;cursor:pointer;transition:border-color .15s;width:100%}
.file-btn:hover{border-color:#fa582d;color:#e2e8f0}
.fname{font-size:.75rem;color:#475569;margin-top:.35rem}
.fname.loaded{color:#3ecf8e}
.step{display:flex;align-items:baseline;gap:.6rem;margin-bottom:.5rem}
.step-num{flex-shrink:0;width:1.35rem;height:1.35rem;border-radius:50%;background:#fa582d;color:#fff;font-size:.65rem;font-weight:700;display:flex;align-items:center;justify-content:center;margin-top:.05rem}
.step-title{font-size:.75rem;font-weight:500;color:#94a3b8;text-transform:uppercase;letter-spacing:.05em}
.or-divider{display:flex;align-items:center;gap:.5rem;margin:.6rem 0;color:#475569;font-size:.75rem}
.or-divider::before,.or-divider::after{content:'';flex:1;height:1px;background:#2d3148}
</style>
</head>
<body>
<div class="card">
<h1>Upload Release Notes</h1>
<p class="sub">Writes a <code>.md</code> file to the pipeline bucket. The generator picks it up within the hour.</p>
__ERRORS__
__SUCCESS__
<form method="POST" action="/upload">
<div class="field">
<div class="step"><span class="step-num">1</span><span class="step-title">Choose the tool</span></div>
<select name="tool_id" id="tool_id">__TOOL_OPTIONS__</select>
</div>
<div class="field">
<div class="step"><span class="step-num">2</span><span class="step-title">Select file or manually enter release notes below</span></div>
<label for="fileInput" class="file-btn">
<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="17 8 12 3 7 8"/><line x1="12" y1="3" x2="12" y2="15"/></svg>
Choose .md file
</label>
<input type="file" id="fileInput" accept=".md,text/markdown">
<p class="fname" id="fname">No file chosen</p>
</div>
<div class="field">
<div class="step"><span class="step-num">3</span><span class="step-title">Enter version</span></div>
<div class="ver-row">
<input type="text" name="version" id="version" placeholder="26.7.1 or 26.7.1.01" value="__VERSION__" autocomplete="off">
<span class="badge" id="badge">&mdash;</span>
</div>
<p class="note">YY.M.X for releases &nbsp;&bull;&nbsp; YY.M.X.NN for hotfixes &nbsp;&bull;&nbsp; auto-filled from filename</p>
</div>
<div class="field">
<div class="step"><span class="step-num">4</span><span class="step-title">Review and correct release notes if needed</span></div>
<textarea name="content" id="content" placeholder="# 26.7.1 Release Notes&#10;&#10;...">__CONTENT__</textarea>
</div>
<div class="step" style="margin-top:.75rem"><span class="step-num">5</span><span class="step-title">Submit</span></div>
<button type="submit" id="btn">Upload to Pipeline</button>
</form>
</div>
<script>
const VRE=/^\d{2}\.\d+\.\d+(\.\d+)?$/;
const vi=document.getElementById('version');
const badge=document.getElementById('badge');
const btn=document.getElementById('btn');
const fi=document.getElementById('fileInput');
const fname=document.getElementById('fname');
const ct=document.getElementById('content');
function upd(){
  const v=vi.value.trim();
  if(!v){badge.className='badge';badge.innerHTML='&mdash;';btn.disabled=false;return;}
  if(!VRE.test(v)){badge.className='badge invalid';badge.textContent='Invalid';btn.disabled=true;return;}
  const p=v.split('.');
  badge.className='badge '+(p.length===4?'hotfix':'release');
  badge.textContent=p.length===4?'Hotfix':'Release';
  btn.disabled=false;
}
vi.addEventListener('input',upd);
fi.addEventListener('change',function(){
  const f=fi.files[0];
  if(!f)return;
  fname.textContent=f.name;
  fname.className='fname loaded';
  const stem=f.name.replace(/\.md$/i,'');
  if(VRE.test(stem)){vi.value=stem;upd();}
  const r=new FileReader();
  r.onload=function(e){ct.value=e.target.result;};
  r.readAsText(f);
});
upd();
</script>
</body>
</html>"""

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


def _render_upload(
    *,
    tools: list,
    errors: list | None = None,
    success_path: str | None = None,
    tool_id: str = "",
    version: str = "",
    content: str = "",
) -> str:
    tool_options = "".join(
        f'<option value="{t}"{"  selected" if t == tool_id else ""}>{t}</option>'
        for t in tools
    )
    errors_html = ""
    if errors:
        errors_html = '<div class="err">' + "".join(f"<p>{e}</p>" for e in errors) + "</div>"
    success_html = ""
    if success_path:
        success_html = (
            f'<div class="ok"><p>Uploaded to <code>{success_path}</code>.'
            " The pipeline will process it within the hour.</p></div>"
        )
    return (
        _UPLOAD_PAGE
        .replace("__ERRORS__", errors_html)
        .replace("__SUCCESS__", success_html)
        .replace("__TOOL_OPTIONS__", tool_options)
        .replace("__VERSION__", _html.escape(version))
        .replace("__CONTENT__", _html.escape(content))
    )


@app.route("/upload", methods=["GET", "POST"])
def upload():
    if request.method == "GET":
        return _render_upload(tools=_UPLOAD_TOOL_IDS)

    tool_id = request.form.get("tool_id", "").strip()
    version = request.form.get("version", "").strip()
    content = request.form.get("content", "").strip()

    errors = []
    if tool_id not in _UPLOAD_TOOL_IDS:
        errors.append(f"Unknown tool '{_html.escape(tool_id)}'.")
    if not _VERSION_RE_UPLOAD.match(version):
        errors.append("Version must be YY.M.X (release) or YY.M.X.NN (hotfix).")
    if not content:
        errors.append("Release notes content is required.")
    if errors:
        return (
            _render_upload(tools=_UPLOAD_TOOL_IDS, errors=errors,
                           tool_id=tool_id, version=version, content=content),
            400,
        )

    if _storage_client is None:
        return (
            _render_upload(tools=_UPLOAD_TOOL_IDS,
                           errors=["Upload unavailable in local mode."],
                           tool_id=tool_id, version=version, content=content),
            503,
        )

    try:
        blob = _storage_client.bucket(INPUT_BUCKET).blob(f"{tool_id}/{version}.md")
        if blob.exists():
            app.logger.warning("upload_duplicate", extra={"fields": {
                "action": "upload_duplicate", "tool_id": tool_id, "version": version,
            }})
            return (
                _render_upload(
                    tools=_UPLOAD_TOOL_IDS,
                    errors=[f"{_html.escape(version)} already exists for {_html.escape(tool_id)}."
                            " Delete the existing file before re-uploading."],
                    tool_id=tool_id, version=version, content=content,
                ),
                409,
            )
        blob.upload_from_string(content.encode("utf-8"), content_type="text/markdown; charset=utf-8")
    except Exception as exc:
        app.logger.error("upload_error", extra={"fields": {
            "action": "upload_error", "tool_id": tool_id, "version": version,
            "error": str(exc),
        }})
        return (
            _render_upload(tools=_UPLOAD_TOOL_IDS,
                           errors=["Upload failed — GCS error. Try again or contact the SWAT team."],
                           tool_id=tool_id, version=version, content=content),
            500,
        )

    gcs_path = f"gs://{INPUT_BUCKET}/{tool_id}/{version}.md"
    app.logger.info("upload_success", extra={"fields": {
        "action": "upload_success", "tool_id": tool_id, "version": version,
        "gcs_path": gcs_path,
    }})
    return _render_upload(tools=_UPLOAD_TOOL_IDS, success_path=gcs_path)


@app.route("/healthz")
def health():
    return {"status": "healthy", "backend": BACKEND_URL}, 200


@app.route("/", defaults={"path": ""}, methods=["GET", "HEAD"])
@app.route("/<path:path>", methods=["GET", "HEAD"])
def proxy(path):
    t0 = time.monotonic()

    latest_match = _LATEST_RE.match(path)
    if latest_match:
        tool_id = latest_match.group(1)
        try:
            version = _resolve_latest(tool_id)
        except Exception as exc:
            app.logger.error("latest_error", extra={"fields": {
                "action": "latest_error", "tool_id": tool_id, "error": str(exc),
            }})
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

    try:
        token = _get_access_token()
    except Exception as exc:
        app.logger.error("token_error", extra={"fields": {
            "action": "token_error", "path": path, "error": str(exc),
        }})
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
        app.logger.error("backend_error", extra={"fields": {
            "action": "backend_error", "method": request.method,
            "path": path, "error": str(exc),
        }})
        return f"Backend error: {exc}", 502

    latency_ms = round((time.monotonic() - t0) * 1000)
    app.logger.info("proxy_request", extra={"fields": {
        "action": "proxy", "method": request.method, "path": path,
        "gcs_path": gcs_path, "status": resp.status_code, "latency_ms": latency_ms,
    }})

    skip = {"content-encoding", "content-length", "transfer-encoding", "connection",
            "cache-control"}
    out_headers = [(k, v) for k, v in resp.raw.headers.items() if k.lower() not in skip]
    out_headers.append(("Cache-Control", "no-store"))
    return Response(resp.content, resp.status_code, out_headers)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))  # nosec B104 # nosemgrep
