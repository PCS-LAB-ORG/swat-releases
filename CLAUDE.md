# System Handbook: swat-releases

## What This Repository Is

Public-facing HTML release notes for PCS SWAT internal tools. Each tool gets its own subfolder. Release notes are self-contained HTML files — all images are base64-encoded inline, no build step required.

**Owner:** bgoldstein / PCS SWAT
**Visibility:** Public — these pages are intended to be shared with the team and accessible without authentication.

---

## Repository Structure

```text
swat-releases/
├── images/                          ← shared brand assets (logos, backgrounds, icons)
│   ├── cortex-icon.png
│   ├── cortex-background.png
│   ├── cortex_RGB_logo_By-Line_Negative.png
│   └── cortex_RGB_logo_Lockup_Negative.png   ← not currently used, keep for reference
├── cortex-catalyst/                 ← Cortex Catalyst release notes
│   ├── 26.6.1.html
│   ├── 26.3.1.html
│   ├── 26.2.2.html
│   └── 26.2.1.html
└── cortex-search-pipeline/          ← cortex-search-pipeline release notes (future)
```

---

## Adding a New Release Notes Page

1. Copy the most recent release's HTML file as a starting point
2. Update: version badge, release date, hero meta, version nav pills, all section content
3. Update the version nav pills on ALL existing pages to include the new release as a linked pill
4. The new release's pill is `active` (orange); all others are `<a href="...">` links

### Version nav pill order (newest → oldest, left to right)

Always maintain this order in the nav across all pages:

```text
June 2026 — 26.6.1  |  March 2026 — 26.3.1  |  Feb 2026 — 26.2.2  |  Feb 2026 — 26.2.1
```

Add new releases to the LEFT of the existing sequence.

---

## Content Guidelines

Release notes in this repo are **user-facing only**. Exclude:

- Backend infrastructure changes (Cloud Run, MIG, CI/CD, BQ schema, alert policies)
- Developer tooling (Docker, test suite, SDK upgrades, conftest patches)
- Monitoring stack changes (dashboards, log metrics, alert policies)
- Internal refactors with no visible behavior change

Include:

- Any change a user notices when interacting with the application
- New features, UI changes, quality improvements to answers/citations
- Bug fixes that affected user experience
- Known issues and limitations users will encounter

---

## HTML Page Design

All pages share the same dark theme template:

- Background: `#0f1117`, accent: `#fa582d` (Cortex orange)
- Fixed watermark background image (cortex-background.png, 7% opacity, top-right)
- Sticky topbar with By-Line logo centered, version badge right
- Self-contained: all images base64-encoded inline — no external dependencies
- Favicon: cortex-icon.png (base64 inline in `<head>`)

Feature tags: `New` (green), `Improved` (blue), `Planned` (yellow), `Known` (orange), `Fixed` (green)

---

## Branching

Follow the same GitOps rules as other PCS SWAT repos:

- No direct commits to `main`
- Every change on a branch: `chore/add-26.7.1-release-notes`, etc.
- Merge via PR

---

## Open Items

| Item | Notes |
| --- | --- |
| GitHub Pages | Enable once repo is public and content is reviewed. Settings → Pages → Deploy from main `/` root. |
| Index page | Central hub at root `index.html` — built, sidebar navigation with all tools. |
| cortex-search-pipeline | Folder exists, no pages yet. |
| `cortex_RGB_logo_Lockup_Negative.png` | In images/ for reference but not currently used in any page. |
