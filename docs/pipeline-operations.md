# Pipeline Operations Reference

> **Note:** This document describes the original GitHub Actions pipeline, which was replaced in July 2026.
> For the current GCS-based generator, see `docs/generator-operations.md`.

Operational guide for the automated release notes pipeline. Covers manual dispatch, correction workflows, skip logic, local development, and adding new tools.

---

## Architecture Overview

```text
schedule / workflow_dispatch
        │
        ▼
    poll.py          ← checks catalyst-rag-agent for latest release; sets new_versions output
        │
        ▼
   extract.py        ← fetches release body from GitHub; calls Gemini 3.5 Flash; writes JSON artifact
        │
        ▼
    render.py        ← renders release HTML page; updates all other version navs; rebuilds index.html panel
        │
        ▼
   pr_body.py        ← generates PR description from JSON artifact
        │
        ▼
  gh pr create       ← creates branch auto/release-notes/cortex-catalyst-{version}
  gh pr merge        ← auto-merges to main
  branch delete      ← cleans up
```

**Auth:** Workload Identity Federation (WIF) — no service account key. Two secrets pulled from GCP Secret Manager:

| Secret | Used by |
| --- | --- |
| `svc-pcs-lab-GitHub-Org-Access-Token` | `poll.py`, `extract.py` — reading releases from `catalyst-rag-agent` |
| `svc-pcs-lab-github-swat-releases-actions-token` | `render.py` step — creating and merging PRs |

---

## Manual Dispatch

To trigger a run outside the daily 06:00 UTC schedule:

```bash
# Trigger for a new release (poll logic determines what's new)
gh workflow run generate-release-notes.yml --repo PCS-LAB-ORG/swat-releases

# Force-process a specific version (bypasses all skip logic)
gh workflow run generate-release-notes.yml \
  --repo PCS-LAB-ORG/swat-releases \
  -f force_version=27.7.1
```

**When to use which:**

| Scenario | Command |
| --- | --- |
| New release exists, don't want to wait for 06:00 cron | plain `gh workflow run` — poll detects it naturally |
| Pipeline ran but failed partway (JSON written, render failed) | `force_version` — poll would skip it (artifact exists); force bypasses |
| Gemini produced bad output, want to re-generate | `force_version` — overwrites existing artifact and re-renders |
| Manually edited JSON artifact, want to re-render only | run `render.py` locally (see below) — no need to call Gemini again |

**`force_version` behavior:**

- `poll.py` skips its normal detection and returns only the specified version
- `extract.py` receives `--force` and overwrites the existing JSON artifact even if it already exists

**Monitoring the run:**

```bash
# List recent runs
gh run list --workflow=generate-release-notes.yml --repo PCS-LAB-ORG/swat-releases --limit 5

# Watch a run in real time (get run ID from list above)
gh run watch <run-id> --repo PCS-LAB-ORG/swat-releases

# View logs for a failed run
gh run view <run-id> --log-failed --repo PCS-LAB-ORG/swat-releases
```

After a successful run, the branch is created, PR opened, auto-merged, and branch deleted — all within the workflow. Check GitHub Pages status:

```bash
until [ "$(gh api repos/PCS-LAB-ORG/swat-releases/pages --jq '.status')" = "built" ]; do
  echo "still building..."; sleep 5
done && echo "deployed"
```

---

## Skip Logic

Understanding why a run may produce no output:

| Check | Where | Skips when |
| --- | --- | --- |
| Poll skip | `poll.py` | `cortex-catalyst/{version}.html` **or** `data/cortex-catalyst/{version}.json` already exists |
| Extract skip | `extract.py` | `data/cortex-catalyst/{version}.json` already exists (unless `--force`) |
| Workflow step skip | `generate-release-notes.yml` | `steps.poll.outputs.new_versions` is empty — the generate step has `if: steps.poll.outputs.new_versions != ''` |

**`force_version` bypasses all of these** — poll returns the version regardless, extract overwrites, workflow always runs the generate step.

The poll check is an OR: either artifact existing counts as "already processed." This means a partially failed run (JSON written, HTML not rendered) will be skipped by a normal re-run — use `force_version` to recover.

---

## Correcting a Generated Release

If Gemini produced wrong or incomplete content:

1. Edit the JSON artifact directly:

   ```bash
   $EDITOR data/cortex-catalyst/{version}.json
   ```

   Valid tags: `Feature`, `Enhancement`, `Fixed`, `Planned`, `Known`

2. Re-dispatch with `force_version` to re-render from the edited artifact:

   ```bash
   gh workflow run generate-release-notes.yml \
     --repo PCS-LAB-ORG/swat-releases \
     -f force_version={version}
   ```

   This overwrites the JSON artifact with a fresh Gemini call **then** renders. If you want to keep your manual edits and only re-render, run render locally:

   ```bash
   PYTHONPATH=. python3 scripts/render.py cortex-catalyst {version}
   ```

   Then commit and push directly to the release branch (or create a fix branch from develop per normal workflow).

---

## Local Development

Prerequisites: Python 3.12, Node.js, GCP credentials with access to Vertex AI and Secret Manager.

```bash
# Auth
export GITHUB_TOKEN=$(gh auth token)
export GOOGLE_CLOUD_PROJECT=pcs-swat-resources
export GOOGLE_CLOUD_LOCATION=global
gcloud auth application-default login   # if not already authenticated

# Extract (calls Gemini — costs tokens)
PYTHONPATH=. python3 scripts/extract.py cortex-catalyst {version} --force

# Render (local, no external calls)
PYTHONPATH=. python3 scripts/render.py cortex-catalyst {version}

# Preview
npm run dev   # http://localhost:8765
```

`extract.py` without `--force` is a no-op if the JSON artifact already exists. Run with `--force` whenever you want a fresh Gemini call.

**Run tests:**

```bash
pip install -r scripts/requirements.txt pytest
PYTHONPATH=. pytest tests/ -v
```

---

## Pipeline Script Reference

### `scripts/poll.py`

Detects new releases and writes the `new_versions` space-separated output for the workflow.

- Only checks the **latest** release (index 0 of the GitHub releases API). Older releases require explicit `force_version`.
- Currently hardcoded to `config["tools"][0]` — Catalyst only. Multi-tool support requires extending this.
- When `INPUT_FORCE_VERSION` is set, returns that version directly without checking GitHub.

### `scripts/extract.py <tool_id> <version> [--force]`

Calls Gemini 3.5 Flash via Vertex AI and writes `data/{folder}/{version}.json`.

- Validates Gemini output: required fields (`version`, `date`, `summary`, `entries`, `release_url`), valid tags per entry.
- **Always overrides `date` from the GitHub API `published_at` field** — never trusts Gemini for dates.
- `release_url` is always the canonical GitHub release URL, not whatever Gemini generates.

### `scripts/render.py <tool_id> <version>`

Renders HTML and rebuilds `index.html`.

- Renders the new release page from `data/{folder}/{version}.json`
- Re-renders **all other existing JSON-backed pages** to update their version navigation lists
- Rebuilds the Catalyst panel in `index.html` from all artifacts + hand-authored HTML pages
- Assets (favicon, logo, background) are extracted from an existing HTML page as base64 data URIs — the newest existing `.html` in the tool folder is used as the source

### `scripts/pr_body.py <tool_folder_path> <version>`

Generates the PR description body from the JSON artifact. Prints to stdout — the workflow captures it with command substitution.

### `config/tools.yaml`

Tool registry. Each tool entry:

```yaml
- id: cortex-catalyst          # used by extract.py and render.py as <tool_id>
  name: "Cortex® Catalyst"    # display name in HTML
  repo: PCS-LAB-ORG/catalyst-rag-agent   # GitHub repo to poll
  folder: cortex-catalyst      # subfolder for HTML pages and data/ artifacts
  panel_id: catalyst           # CSS id suffix for the index.html panel (panel-{panel_id})
  model: user-facing           # informational only
  prompt: scripts/prompts/model1_user_facing.txt
  description: >               # shown in the index panel
    ...
  app_url: https://...         # shown as a link in release pages
```

---

## Adding a New Tool

1. Add an entry to `config/tools.yaml` following the schema above.
2. Create a prompt file at `scripts/prompts/{prompt_filename}.txt`. See `model1_user_facing.txt` as the reference for user-facing tools.
3. Create the folder: `mkdir {folder}` and `mkdir data/{folder}`.
4. Add an HTML panel div to `index.html` (copy the Catalyst panel structure, update ids and text).
5. Add a Jinja2 panel template at `scripts/templates/{tool-id}-panel.html.j2` if the index panel structure differs from Catalyst.
6. Update `poll.py` — currently hardcoded to `config["tools"][0]`. When adding a second tool, change the poll logic to iterate all tools.

---

## JSON Artifact Schema

`data/cortex-catalyst/{version}.json`:

```json
{
  "version": "26.7.1",
  "date": "July 2026",
  "release_url": "https://github.com/PCS-LAB-ORG/catalyst-rag-agent/releases/tag/26.7.1",
  "summary": "One-sentence plain-language release summary.",
  "entries": [
    {
      "tag": "Feature",
      "title": "Short title",
      "description": "Impact-first description — what can the user now do or what no longer fails?"
    }
  ]
}
```

Valid tags: `Feature`, `Enhancement`, `Fixed`, `Planned`, `Known`

The JSON artifact is the source of truth for a release. Edit it to correct Gemini output, then re-render.

---

## Known Limitations

| Limitation | Notes |
| --- | --- |
| Single-tool poll | `poll.py` only checks `config["tools"][0]` — extend before adding a second tool |
| Latest release only | Normal schedule only processes the most recent release; older ones need `force_version` |
| No dry-run mode | `extract.py` calls Gemini on every `--force` invocation — there is no "validate only" path |
| Asset extraction fragility | `render.py` extracts base64 assets via regex from existing HTML; breaks if the HTML structure changes significantly |
