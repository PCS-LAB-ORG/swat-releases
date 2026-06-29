# System Handbook: swat-releases

## What This Repository Is

Public-facing HTML release notes for PCS SWAT internal tools, served via GitHub Pages at <https://pcs-lab-org.github.io/swat-releases/>. New releases are generated automatically by a GitHub Actions pipeline (Gemini 3.5 Flash → JSON → HTML). Hand-authored pages remain in place for pre-pipeline releases.

**Owner:** bgoldstein / PCS SWAT
**Visibility:** Public

---

## Repository Structure

```text
swat-releases/
├── index.html                        ← SPA portal: sidebar nav + collapsible month groups per tool
├── images/                           ← shared brand assets (relative paths, not base64-embedded)
├── config/
│   └── tools.yaml                    ← tool registry for the pipeline (add tools here)
├── scripts/                          ← automated pipeline
│   ├── poll.py                       ← detects new releases (latest only)
│   ├── extract.py                    ← calls Gemini 3.5 Flash, writes data/{folder}/{version}.json
│   ├── render.py                     ← JSON + HTML → rendered page + rebuilt index panel
│   ├── pr_body.py                    ← generates PR description
│   ├── prompts/model1_user_facing.txt← Gemini system prompt (Model 1 standards)
│   ├── templates/                    ← Jinja2 templates
│   └── requirements.txt             ← google-genai, jinja2, pyyaml, requests
├── data/
│   └── cortex-catalyst/             ← JSON artifacts (Gemini output, human-editable)
├── cortex-catalyst/                 ← release pages (hand-authored + pipeline-generated)
├── cortex-insights/                 ← hand-authored
├── cortex-unity/                    ← hand-authored
├── cortex-search-pipeline/          ← coming soon
├── docs/
│   └── release-notes-standards.md   ← three-model framework + tag taxonomy + citations
├── tests/                           ← pytest (24 tests, all scripts covered)
└── .github/workflows/
    └── generate-release-notes.yml   ← daily cron 06:00 UTC + workflow_dispatch
```

---

## Automated Pipeline

New Catalyst releases are generated automatically. The pipeline:

1. Polls `catalyst-rag-agent` for the latest release
2. Sends the release body to Gemini 3.5 Flash with a user-facing filter prompt
3. Writes a JSON artifact to `data/cortex-catalyst/{version}.json`
4. Renders HTML via Jinja2 → `cortex-catalyst/{version}.html`
5. Rebuilds the Catalyst panel in `index.html`
6. Creates a branch `auto/release-notes/cortex-catalyst-{version}`, PRs to main, merges

**Manual correction:** edit the JSON artifact directly, then trigger `workflow_dispatch` with `force_version={version}`.

**To add a new tool:** add an entry to `config/tools.yaml` and create a prompt file in `scripts/prompts/`.

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

## Hand-Authoring a Release Notes Page (pre-pipeline releases or pipeline overrides)

1. Copy the most recent release HTML as a starting point
2. Update: version badge, release date, hero meta, all section content
3. DO NOT add version nav pills — navigation is through the index SPA sidebar
4. The index panel updates automatically when render.py runs

See `docs/release-notes-standards.md` for the three-model content framework and tag taxonomy.

---

## Tag Taxonomy

| Tag | Color | Use for |
| --- | --- | --- |
| `Feature` | Green `#3ecf8e` | Net-new capability |
| `Enhancement` | Blue `#4a9eff` | Improvement to existing |
| `Fixed` | Amber `#f59e0b` | Bug fix |
| `Planned` | Yellow `#f4c94f` | Upcoming (user-facing only) |
| `Known` | Orange `#fa582d` | Known issue (user-facing only) |
| `Architecture` | Purple `#a78bfa` | Structural design decision (operational/engineering) |
| `Infrastructure` | Teal `#06b6d4` | CI/CD, deployment, platform changes |

---

## HTML Page Design

- Background: `#0f1117`, accent: `#fa582d` (Cortex orange)
- `index.html` uses relative image paths (`images/`)
- Individual release pages use base64-embedded images (self-contained, shareable)
- Individual pages have NO version nav pills — users navigate via the index SPA sidebar
- `index.html` SPA: sidebar with collapsible `<details>` month groups; clicking a release loads it inline
- `scroll-margin-top: 120px` on `section` elements (clears sticky topbar when TOC anchors fire)

---

## Branching

- No direct commits to `main` or `develop`
- Feature branches from `develop`, merged with `git merge --no-ff --no-verify`
- `develop → main`: PR required, CI must pass
- Auto-generated pipeline branches: `auto/release-notes/cortex-catalyst-{version}` — merged directly to main by the workflow

---

## Dev Server

```bash
npm run dev   # hot-reload at localhost:8765
npm run lint  # HTMLHint + markdownlint + ESLint
```

---

## Open Items

| Item | Notes |
| --- | --- |
| Issue #12 | Pipeline live, awaiting first real production release to close |
| Issue #10 | Data-driven pipeline architecture documented, not built |
| cortex-search-pipeline | Folder exists, no pages yet |
| VM hosting | Option documented in #10; GitHub Pages is current default |
