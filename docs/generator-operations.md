# Generator Operations Reference

The release notes generator runs as a Cloud Function (`swat-releases-generator`) triggered hourly by Cloud Scheduler. It reads `.md` files from `gs://swat-releases-input` and writes rendered HTML to `gs://swat-releases-serve`.

---

## Triggering a Run

### Wait for hourly schedule

The scheduler fires at the top of every hour automatically.

### Manual trigger

```bash
gcloud scheduler jobs run swat-releases-generator-hourly --location=us-central1
```

### Force re-process a version (overwrite existing artifact)

Upload the `.md` file again (overwrite in GCS) then trigger manually. The generator will re-extract and re-render.

To only re-render without calling Gemini again, manually upload an edited `.md` — but note the generator always calls Gemini for any unprocessed file. If you want to edit the JSON artifact directly, use `force` mode (see below).

---

## Adding a Release

1. Write release notes in `.md` format (AI-assisted)
1. Name the file `{version}.md` (e.g., `26.8.1.md` for a major release, `26.8.1.01.md` for a hotfix)
1. Upload to `gs://swat-releases-input/{tool-id}/`:

```bash
gcloud storage cp 26.8.1.md gs://swat-releases-input/cortex-catalyst/26.8.1.md
```

1. Trigger the scheduler job or wait for the next hourly run

---

## Skip Logic

| Condition | Behavior |
| --- | --- |
| Major release: `{tool-id}/{version}.json` exists in serving bucket | Skipped (artifact already processed) |
| Hotfix: parent JSON `fixes[]` already contains this hotfix version | Skipped |
| Hotfix: parent major release not yet in serving bucket | Skipped with warning log; retried next hourly run |
| Unknown `tool-id` (not in `config/tools.yaml`) | Skipped with warning log |

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
gcloud scheduler jobs describe swat-releases-generator-hourly --location=us-central1
```

---

## Correcting Generated Release Notes

1. Edit the JSON artifact directly in GCS:

```bash
gcloud storage cp gs://swat-releases-serve/cortex-catalyst/26.8.1.json /tmp/26.8.1.json
# edit /tmp/26.8.1.json
gcloud storage cp /tmp/26.8.1.json gs://swat-releases-serve/cortex-catalyst/26.8.1.json
```

1. Re-render only (no Gemini call) by triggering the generator with the artifact already present — BUT the `.md` file must also NOT exist in the input bucket, or it will be re-extracted. To avoid this:

```bash
# Option: remove .md from input bucket after first successful processing
gcloud storage rm gs://swat-releases-input/cortex-catalyst/26.8.1.md
# Then edit the JSON artifact and manually render (see below)
```

1. Or run render locally:

```bash
export GOOGLE_CLOUD_PROJECT=pcs-swat-resources
export INPUT_BUCKET=swat-releases-input
export SERVE_BUCKET=swat-releases-serve
gcloud auth application-default login
PYTHONPATH=. python - << 'EOF'
from google.cloud import storage
from scripts.render import load_assets, GCSHTMLRenderer, GCSIndexUpdater, TemplateEngine, load_all_release_data_from_gcs
from scripts.poll import load_config
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

Hotfix versions (`26.8.1.01`, `26.8.1.02`) are automatically detected by the 4-part version format. The generator:

1. Finds the parent major release JSON (`26.8.1.json`) in the serving bucket
1. Appends fix entries to the `fixes[]` array
1. Re-renders the parent page (`26.8.1.html`) to include the new Fixes section
1. Does NOT create a new index entry or update the `latest` pointer

The parent major release must exist before a hotfix can be processed.

---

## Troubleshooting

| Symptom | Likely cause | Fix |
| --- | --- | --- |
| Version not processed, no error log | `.md` file is named incorrectly or missing `.md` extension | Check `gcloud storage ls gs://swat-releases-input/cortex-catalyst/` |
| Hotfix skipped with `parent_not_found` | Parent major release not yet processed | Upload and trigger parent first |
| `RuntimeError: Could not find panel-catalyst div` | `index.html` in serving bucket is malformed or missing | Re-seed from repo: `gcloud storage cp index.html gs://swat-releases-serve/index.html` |
| Cloud Function times out | Large number of unprocessed files | Trigger multiple times or increase `--timeout` on the function |
| Gemini returns invalid JSON | Model flakiness | Manual trigger re-runs Gemini; check logs for raw response |
