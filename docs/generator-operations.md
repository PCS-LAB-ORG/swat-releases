# Generator Operations Reference

The release notes generator runs as a Cloud Function (`swat-releases-generator`) triggered hourly by Cloud Scheduler. It reads `.md` files from `gs://swat-releases-input` and writes rendered HTML to `gs://swat-releases-serve`.

---

## Architecture

```mermaid
flowchart LR
    Dev["Developer\n(writes .md)"] --> Input["gs://swat-releases-input\n/{tool-id}/{version}.md"]
    Input -->|"Cloud Scheduler\nhourly (0 * * * *)"| CF["Cloud Function\nswat-releases-generator\n(us-central1, gen2, Python 3.12)"]
    CF -->|"Vertex AI"| Gemini["Gemini 3.5 Flash"]
    Gemini --> CF
    CF --> Serve["gs://swat-releases-serve\n/{tool-id}/{version}.json\n/{tool-id}/{version}.html\n/index.html"]
    Serve --> LB["Cloud LB\n+ Cloud Armor\n(GlobalProtect IP allowlist)"]
    LB --> MIG["MIG: mig-swat-releases\n(e2-small, COS)"]
    MIG --> GW["gateway container\n(Flask/gunicorn, port 8080)"]
    GW --> Browser["Browser\n(VPN required)"]
```

**Proxy routing:**

| Path | Resolves to |
| --- | --- |
| `/` | `index.html` |
| `/{tool-id}/{version}` | `{tool-id}/{version}.html` (`.html` appended by proxy) |
| `/{tool-id}/latest` | 302 redirect to current latest version |

---

## Skip Logic

The generator iterates every `.md` file in `gs://swat-releases-input`. Whether it calls Gemini depends on what already exists in the serve bucket:

| Condition | Behavior |
| --- | --- |
| Major release: `{tool-id}/{version}.json` exists in serve bucket | Gemini skipped — existing JSON re-used; HTML re-rendered |
| Major release: no JSON artifact yet | Gemini called; JSON and HTML written |
| Hotfix: parent JSON `fixes[]` already contains this hotfix version | Skipped entirely |
| Hotfix: parent major release not yet in serve bucket | Skipped with warning log; retried next hourly run |
| Unknown `tool-id` (not in `config/tools.yaml`) | Skipped with warning log |

**Note:** Gemini is NOT re-called just because the `.md` file is re-uploaded to the input bucket. Skip logic is controlled entirely by what exists in the serve bucket (`{version}.json`). To force a fresh Gemini call on an already-processed version, delete the JSON artifact from the serve bucket first (see [Force re-extraction](#force-re-extraction)).

---

## Triggering a Run

### Wait for hourly schedule

The scheduler fires at the top of every hour automatically.

### Manual trigger

```bash
gcloud scheduler jobs run swat-releases-generator-hourly \
  --location=us-central1 --project=pcs-swat-resources
```

### Force re-extraction

To force Gemini to re-process an already-processed version, delete its JSON artifact from the serve bucket, then trigger:

```bash
# 1. Delete the existing artifact (removes the skip guard)
gcloud storage rm gs://swat-releases-serve/cortex-catalyst/26.8.1.json

# 2. Trigger the generator
gcloud scheduler jobs run swat-releases-generator-hourly \
  --location=us-central1 --project=pcs-swat-resources
```

The `.md` file must still be present in `gs://swat-releases-input` for the generator to pick it up.

---

## Adding a Release

1. Write release notes in `.md` format (see [docs/release-notes-standards.md](release-notes-standards.md))
1. Name the file `{version}.md` (e.g., `26.8.1.md` for a major release, `26.8.1.01.md` for a hotfix)
1. Upload to `gs://swat-releases-input/{tool-id}/`:

```bash
gcloud storage cp 26.8.1.md gs://swat-releases-input/cortex-catalyst/26.8.1.md
```

1. Trigger the scheduler job or wait for the next hourly run

---

## Deleting a Release

1. Remove the HTML and JSON artifacts from the serving bucket:

```bash
gcloud storage rm gs://swat-releases-serve/cortex-catalyst/26.8.1.html
gcloud storage rm gs://swat-releases-serve/cortex-catalyst/26.8.1.json
```

1. Remove the source `.md` from the input bucket (prevents re-processing on the next hourly run):

```bash
gcloud storage rm gs://swat-releases-input/cortex-catalyst/26.8.1.md
```

1. Rebuild the index so the sidebar no longer lists the deleted release:

```bash
export GOOGLE_CLOUD_PROJECT=pcs-swat-resources
gcloud auth application-default login  # if needed
PYTHONPATH=. python - << 'EOF'
from google.cloud import storage
from scripts.config import load_config
from scripts.generator.main import rebuild_index

gcs = storage.Client()
config = load_config("config/tools.yaml")
tool = config["tools"][0]
rebuild_index(tool, gcs, "swat-releases-serve")
print("Index rebuilt")
EOF
```

1. If the deleted version was the `latest`, update the pointer manually:

```bash
# Point latest at the new most-recent version
echo -n "26.7.1" | gcloud storage cp - gs://swat-releases-serve/cortex-catalyst/latest
```

---

## Monitoring

### View recent logs

```bash
gcloud functions logs read swat-releases-generator \
  --gen2 --region=us-central1 --limit=100
```

### Filter for errors only

```bash
gcloud logging read \
  'resource.type="cloud_run_revision" AND jsonPayload.action="error"' \
  --project=pcs-swat-resources --limit=20
```

### Filter for processing summary

```bash
gcloud logging read \
  'resource.type="cloud_run_revision" AND jsonPayload.action="summary"' \
  --project=pcs-swat-resources --limit=10
```

### Check scheduler job history

```bash
gcloud scheduler jobs describe swat-releases-generator-hourly \
  --location=us-central1 --project=pcs-swat-resources
```

---

## Correcting Generated Release Notes

1. Edit the JSON artifact directly in GCS:

```bash
gcloud storage cp gs://swat-releases-serve/cortex-catalyst/26.8.1.json /tmp/26.8.1.json
# edit /tmp/26.8.1.json
gcloud storage cp /tmp/26.8.1.json gs://swat-releases-serve/cortex-catalyst/26.8.1.json
```

1. Re-render by triggering the generator. The `.md` file must be present in the input bucket. Because the JSON artifact already exists, Gemini is not called — the edited JSON is used directly:

```bash
gcloud scheduler jobs run swat-releases-generator-hourly \
  --location=us-central1 --project=pcs-swat-resources
```

1. Or render locally without touching the input bucket:

```bash
export GOOGLE_CLOUD_PROJECT=pcs-swat-resources
export INPUT_BUCKET=swat-releases-input
export SERVE_BUCKET=swat-releases-serve
gcloud auth application-default login
PYTHONPATH=. python - << 'EOF'
from google.cloud import storage
from scripts.render import load_assets, GCSHTMLRenderer, GCSIndexUpdater, TemplateEngine, load_all_release_data_from_gcs
from scripts.config import load_config
import json

client = storage.Client()
config = load_config("config/tools.yaml")
tool = config["tools"][0]
version = "26.8.1"

artifact = json.loads(client.bucket("swat-releases-serve").blob(f"cortex-catalyst/{version}.json").download_as_text())
assets = load_assets("images")
engine = TemplateEngine("scripts/templates")
updater = GCSIndexUpdater(engine, client, "swat-releases-serve")
renderer = GCSHTMLRenderer(engine, updater, assets, client)

all_releases = load_all_release_data_from_gcs(client, "swat-releases-serve", "cortex-catalyst")
all_versions = [{"version": r["version"], "label": f"{r['date']} — {r['version']}", "is_current": r["version"] == version, "href": r["version"]} for r in all_releases]
renderer.render_and_upload(tool, version, artifact, all_versions, "swat-releases-serve")
print("Done")
EOF
```

---

## Hotfix Processing

```mermaid
flowchart TD
    Upload["Upload 26.8.1.01.md to\ngs://swat-releases-input/cortex-catalyst/"] --> Detect["Generator detects\n4-part version → hotfix"]
    Detect --> ParentCheck{"26.8.1.json\nexists in serve bucket?"}
    ParentCheck -->|No| Skip["Skip with warning\n(retried next hour)"]
    ParentCheck -->|Yes| AlreadyCheck{"26.8.1.01 already\nin fixes[] array?"}
    AlreadyCheck -->|Yes| SkipDupe["Skip (already processed)"]
    AlreadyCheck -->|No| Gemini["Gemini extracts fix entries\n(all entries tagged Fixed)"]
    Gemini --> Append["Append fix record to\nparent JSON fixes[] array"]
    Append --> Rerender["Re-render 26.8.1.html\n(includes new Fixes section)"]
    Rerender --> Done["Done — no new index entry,\nlatest pointer unchanged"]
```

### Submitting a hotfix

Write the fix notes as a `.md` file named with the hotfix version (e.g., `26.8.1.01.md`):

```markdown
# Cortex Catalyst 26.8.1.01

## Fixes
- Resolved an issue where multi-document queries returned empty results when
  source documents exceeded 50 pages.
```

Upload to the same tool folder in the input bucket:

```bash
gcloud storage cp 26.8.1.01.md gs://swat-releases-input/cortex-catalyst/26.8.1.01.md
```

The generator detects the 4-part version (`YY.M.X.NN`) and appends the formatted fix entries to the parent major release page (`26.8.1`). The parent release must already be processed before the hotfix is submitted.

### How hotfixes are processed

Hotfix versions (`26.8.1.01`, `26.8.1.02`) are automatically detected by the 4-part version format. The generator:

1. Finds the parent major release JSON (`26.8.1.json`) in the serving bucket
1. Calls Gemini to extract fix entries from the hotfix `.md` — all entries are validated to use the `Fixed` tag; any other tag causes a validation error
1. Appends a fix record to the `fixes[]` array in the parent JSON
1. Re-renders the parent page (`26.8.1.html`) to include the new Fixes section
1. Does NOT create a new index entry or update the `latest` pointer

The parent major release must exist before a hotfix can be processed.

### JSON artifact shape after a hotfix

```json
{
  "version": "26.8.1",
  "date": "August 2026",
  "summary": "...",
  "entries": [...],
  "fixes": [
    {
      "version": "26.8.1.01",
      "date": "August 2026",
      "entries": [
        { "tag": "Fixed", "title": "...", "description": "..." }
      ]
    }
  ]
}
```

---

## Troubleshooting

| Symptom | Likely cause | Fix |
| --- | --- | --- |
| Version not processed, no log entry | `.md` file is named incorrectly or missing `.md` extension | Check `gcloud storage ls gs://swat-releases-input/cortex-catalyst/` |
| Version processed but HTML unchanged | JSON artifact already existed; Gemini not re-called | Edit JSON in GCS and re-trigger, or use force re-extraction (delete JSON first) |
| Hotfix skipped with `parent_not_found` | Parent major release not yet processed | Upload and trigger parent first |
| `RuntimeError: Could not find panel-catalyst div` | `index.html` in serving bucket is malformed or missing | Download from GCS version history and restore; `index.html` is not tracked in git |
| Cloud Function times out (300s limit) | Large number of unprocessed files | Trigger multiple times or process in smaller batches |
| Gemini returns invalid JSON | Model flakiness | Manual trigger re-runs Gemini; check logs for raw response |
| Hotfix validation error: wrong tag | Hotfix `.md` contains non-Fixed entries | Hotfix entries must only describe bug fixes; all entries are validated as `Fixed` |
