# Automation Reference — swat-releases Pipeline

**Repo:** PCS-LAB-ORG/swat-releases
**Pages:** <https://pcs-lab-org.github.io/swat-releases/>
**Cron:** daily 06:00 UTC (`generate-release-notes.yml`)

---

## Pipeline Flow

```text
poll.py → extract.py → render.py → pr_body.py → gh pr create + REST merge
```

1. **poll.py** — checks only `releases[0]` (most recent) of `catalyst-rag-agent`. Compares against existing `data/cortex-catalyst/*.json` and `cortex-catalyst/*.html`. Outputs `new_versions` to `$GITHUB_OUTPUT`. If nothing new, subsequent steps are skipped.
2. **extract.py** — fetches the release body from GitHub API, sends it to Gemini 3.5 Flash (Vertex AI), validates JSON, overwrites `data["date"]` from `published_at` (never trust Gemini for dates), writes `data/cortex-catalyst/{version}.json`.
3. **render.py** — reads the JSON artifact + Jinja2 template, renders `cortex-catalyst/{version}.html`, then rebuilds the Catalyst panel in `index.html` (scanning both JSON artifacts AND hand-authored HTML pages for the full history).
4. **pr_body.py** — generates a human-readable PR description from the artifact.
5. **Workflow** — commits, force-pushes to `auto/release-notes/cortex-catalyst-{version}`, creates PR, merges via REST API (`PUT /pulls/{n}/merge`), deletes the branch.

---

## Script Inventory

| File | Purpose |
| --- | --- |
| `scripts/poll.py` | Detects new releases; only checks `releases[0]` |
| `scripts/extract.py` | Calls Gemini, validates JSON, writes artifact |
| `scripts/render.py` | Jinja2 render + index.html panel rebuild |
| `scripts/pr_body.py` | Generates PR description from artifact |
| `scripts/prompts/model1_user_facing.txt` | Gemini system prompt (user-facing filter) |
| `scripts/templates/release-page.html.j2` | Release page template |
| `scripts/templates/catalyst-panel.html.j2` | Index sidebar Catalyst panel partial |
| `config/tools.yaml` | Tool registry (Catalyst only for now) |
| `.github/workflows/generate-release-notes.yml` | Cron + workflow_dispatch |

---

## Infrastructure

| Resource | Value |
| --- | --- |
| WIF SA | `swat-releases-pipeline@pcs-swat-resources.iam.gserviceaccount.com` |
| WIF pool | `projects/855530889800/locations/global/workloadIdentityPools/github-actions-pool/providers/github-provider` |
| SA roles | `roles/aiplatform.user`, `roles/secretmanager.secretAccessor` |
| Org token secret | `svc-pcs-lab-GitHub-Org-Access-Token` (read all repos; used as GITHUB_TOKEN in poll/extract) |
| PR token secret | `svc-pcs-lab-github-swat-releases-actions-token` (Contents+PRs Write on swat-releases; used as GH_TOKEN for `gh` CLI) |
| GCP project | `pcs-swat-resources` |
| Gemini model | `gemini-3.5-flash` (GA May 19, 2026) |

---

## Triggering the Pipeline

**Normal:** runs automatically daily at 06:00 UTC.

**Force-reprocess a version:**

```bash
gh workflow run generate-release-notes.yml --field force_version=26.7.1
```

Bypasses skip logic and overwrites the existing JSON artifact.

**Local test:**

```bash
export GITHUB_TOKEN=$(gh auth token)
export GOOGLE_CLOUD_PROJECT=pcs-swat-resources
export GOOGLE_CLOUD_LOCATION=global
PYTHONPATH=. python3 scripts/extract.py cortex-catalyst 26.7.1 --force
PYTHONPATH=. python3 scripts/render.py cortex-catalyst 26.7.1
npm run dev  # view at localhost:8765
```

---

## Critical Gotchas (all discovered during live testing June 26 2026)

### Gemini client setup

```python
# CORRECT — vertexai=True is required; env var alone is insufficient
genai.Client(vertexai=True, project="pcs-swat-resources", location="global",
             http_options=HttpOptions(api_version="v1"))

# WRONG — GOOGLE_GENAI_USE_ENTERPRISE=True env var alone does NOT work
genai.Client()
```

### Token scoping

- `GITHUB_TOKEN` (Actions auto) — scoped to swat-releases only; cannot read cross-repo releases
- Org token from Secret Manager — required for any API call to `catalyst-rag-agent`
- Org policy blocks GitHub Actions bot from creating/merging PRs — use human-user PAT as `GH_TOKEN`, not `secrets.GITHUB_TOKEN`

### Fine-grained PAT limitations

- Cannot use GraphQL `mergePullRequest` or `enablePullRequestAutoMerge` mutations
- Use REST instead: `gh api repos/PCS-LAB-ORG/swat-releases/pulls/{n}/merge -X PUT -f merge_method=merge`
- Merging requires **Contents:Write** in addition to Pull Requests:Write

### Secret Manager output

```bash
# MUST strip trailing newline or Bearer auth fails with 401
SECRET=$(gcloud secrets versions access latest --secret=NAME --project=PROJ | tr -d '[:space:]')
```

### Multi-release loop (batch processing)

- `git pull origin main` before each `git checkout -b` — PR auto-merge is async; local main goes stale
- `git push --force` on auto-branches — safe because only the pipeline writes to them

### PYTHONPATH in workflow

```yaml
env:
  PYTHONPATH: ${{ github.workspace }}  # required on every step running Python scripts
```

### Date sourcing

- Always override `data["date"]` from GitHub API's `published_at` after Gemini extraction
- Gemini cannot be trusted for temporal facts in the release body

---

## Navigation Design

- **Individual release pages** — NO version nav pills; navigation is through the index SPA sidebar
- **Index panel** — reads both `data/cortex-catalyst/*.json` (Gemini-generated, has summary) AND `cortex-catalyst/*.html` without a JSON counterpart (hand-authored, date extracted from hero-meta `Released` field)
- `load_all_release_data(html_folder=...)` combines both sources

---

## Adding a New Tool

1. Add an entry to `config/tools.yaml` (tool key, GitHub org/repo, folder name)
2. Create a system prompt at `scripts/prompts/{tool_key}_user_facing.txt`
3. Create the tool's subfolder at repo root
4. The workflow loop iterates `config/tools.yaml` — no workflow edits needed

---

## Open Items (as of 2026-06-29)

| Issue | Status |
| --- | --- |
| #12 | Pipeline live; not closed — waiting for first real production release |
| #10 | Data-driven architecture researched, documented, not built |
| cortex-insights, cortex-unity | Hand-authored pages exist; no pipeline support |
| S&O Planner, AI Sweeper | "Coming soon" state; no pages |
