# System Handbook: swat-releases

## What This Repository Is

Private release notes portal for PCS SWAT internal tools, served at
<https://swatreleases.pcs.lab.twistlock.com> (GlobalProtect VPN required).
Content is generated from `.md` files dropped into GCS, processed by Gemini,
and rendered to static HTML.

**Owner:** bgoldstein / PCS SWAT  **Visibility:** Private (VPN-gated)

---

## Repository Structure

```text
swat-releases/
├── gateway/                    ← COS proxy container (Flask/gunicorn)
│   ├── Dockerfile
│   ├── main.py                 ← Flask proxy: ADC auth to GCS, /latest redirect, URL routing
│   └── requirements.txt
├── scripts/
│   ├── config.py               ← load_config() — reads tools.yaml
│   ├── extract.py              ← reads .md from GCS, calls Gemini, writes JSON artifact
│   ├── render.py               ← renders HTML via Jinja2, uploads to GCS
│   ├── generator/
│   │   └── main.py             ← Cloud Function HTTP entry point (hourly via Cloud Scheduler)
│   ├── prompts/
│   │   ├── model1_user_facing.txt  ← major release Gemini prompt
│   │   └── model1_hotfix.txt       ← hotfix Gemini prompt (Fixed-only entries)
│   └── templates/
│       ├── release-page.html.j2
│       └── catalyst-panel.html.j2
├── config/
│   └── tools.yaml              ← tool registry
├── images/                     ← brand PNGs (base64-embedded in release pages)
├── docs/
│   ├── generator-operations.md ← operational runbook (current)
│   └── pipeline-operations.md  ← DEPRECATED (old GitHub Actions pipeline)
├── tests/
└── .github/workflows/
    ├── deploy-proxy.yml         ← builds proxy Docker image, creates MIG instance template
    └── deploy-generator.yml     ← deploys Cloud Function + Cloud Scheduler
```

---

## Automated Pipeline

**Upload page:** `GET /upload` and `POST /upload` live in `gateway/main.py`. The tool dropdown
is driven by the `UPLOAD_TOOL_IDS` env var in `deploy-proxy.yml` — NOT by reading `config/tools.yaml`
at runtime (tools.yaml is not in the Docker image). When adding a tool, update BOTH.

**Proxy deploy trigger:** The deploy-proxy workflow only fires on `gateway/**` path changes.
A change to `.github/workflows/deploy-proxy.yml` alone (e.g. adding an env var) requires a manual
trigger: `gh workflow run deploy-proxy.yml --repo PCS-LAB-ORG/swat-releases --ref main`

**MIG scope:** The MIG instance template already uses `--scopes=cloud-platform`. New GCP API
access only requires IAM grants on the relevant resource — no instance template or MIG update needed.

Developer drops `{version}.md` into `gs://swat-releases-input/{tool-id}/`.
Cloud Scheduler fires hourly → `swat-releases-generator` Cloud Function →
Gemini → `gs://swat-releases-serve/` → proxy VM serves to browser.

**Manual trigger:**

```bash
gcloud scheduler jobs run swat-releases-generator-hourly \
  --location=us-central1 --project=pcs-swat-resources
```

**Force re-render without Gemini:** edit JSON artifact directly in
`gs://swat-releases-serve/{tool-id}/{version}.json`, then run
`rebuild_index` locally (see `docs/generator-operations.md`).

**Adding a new release:**

```bash
gcloud storage cp 26.8.1.md gs://swat-releases-input/cortex-catalyst/26.8.1.md
```

**Hotfix versioning:** `YY.M.X.NN` (4-part) → appended to parent page's
Fixes section; no new index entry; `latest` pointer unchanged.

---

## GCS Buckets

| Bucket | Purpose |
| --- | --- |
| `gs://swat-releases-input` | `.md` input files from developers |
| `gs://swat-releases-serve` | Private serving bucket (proxy reads via SA) |

**`index.html` in GCS is partially generator-managed.** The generator
rebuilds ONLY `<div id="panel-catalyst">`. All JS/CSS and other panel divs
survive every hourly run. The `copyLink(url, btn)` function in the script
block must always be present.

---

## Infrastructure

- **MIG:** `mig-swat-releases` (us-central1, e2-small, COS, managed)
- **Rolling update params:** `--max-unavailable=4 --max-surge=0 --timeout=600s`
  (us-central1 has 4 zones; regional MIG requires each param to be 0 or ≥ 4)
- **Health check:** reuses `auth-gateway-health` (pipeline SA lacks `compute.healthChecks.create`)
- **Cache-Control:** proxy adds `no-store` to all responses — Prisma Access Browser
  caches `private, max-age=0` aggressively across incognito sessions
- **Pipeline SA:** `swat-releases-pipeline@pcs-swat-resources.iam.gserviceaccount.com`
- **Proxy VM SA:** `cloudrun-testing-svc@pcs-swat-resources.iam.gserviceaccount.com`

---

## Tag Taxonomy

| Tag | Color | Use for |
| --- | --- | --- |
| `Feature` | Green `#3ecf8e` | Net-new capability |
| `Enhancement` | Blue `#4a9eff` | Improvement to existing |
| `Fixed` | Amber `#f59e0b` | Bug fix |
| `Planned` | Yellow `#f4c94f` | Upcoming (user-facing only) |
| `Known` | Orange `#fa582d` | Known issue (user-facing only) |
| `Architecture` | Purple `#a78bfa` | Structural design decision |
| `Infrastructure` | Teal `#06b6d4` | CI/CD, deployment, platform changes |

---

## HTML Page Design

- Background: `#0f1117`, accent: `#fa582d` (Cortex orange)
- Individual release pages: base64-embedded images (self-contained)
- `index.html` SPA: sidebar with `<details>` month groups; clicking a release
  loads it inline via `fetch()` and updates the URL bar via `history.pushState`
- Deep links: `/{tool-id}/{version}` and `/{tool-id}/latest` (proxy handles routing)

---

## Branching

- No direct commits to `main` or `develop`
- Feature branches from `develop`, merged with `git merge --no-ff --no-verify`
- `develop → main`: PR required

### Pulling main safely

```bash
git pull --ff-only   # safe: never creates a merge commit
```

---

## Dev Server

```bash
npm run lint  # HTMLHint + markdownlint + ESLint
PYTHONPATH=. pytest tests/ -v  # 39 tests
```

---

## Open Items

| Item | Notes |
| --- | --- |
| Issue #47 | Structured request logging for proxy MIG |
| Issue #48 | Elegant content management (edit/delete without local Python) |
| Cortex Unity | Hand-authored pages not yet reformatted to new template |
| Dependabot | 20 vulnerabilities (moderate/low) — not yet triaged |
