# Release Notes Standards

Standards for authoring release notes in this repository. All tools follow one of three models depending on their audience. The model determines what to include, what to filter, and how to frame entries.

---

## The Three Models

### Model 1 — User-Facing (Catalyst model)

**Audience:** Team members, managers, and stakeholders who interact with the application directly.

**Filter:** Only what a user notices when interacting with the tool. Everything else is excluded.

**Include:**

- New features and UI changes
- Quality improvements to answers, outputs, or citations
- Bug fixes that affected user experience
- Known issues and limitations users will encounter

**Exclude:**

- Backend infrastructure (Cloud Run, BQ schema, alert policies, CI/CD)
- Developer tooling (Docker, test suite, SDK upgrades)
- Internal refactors with no visible behavior change
- Monitoring stack changes

**Tag taxonomy:** `Feature`, `Enhancement`, `Fixed`, `Planned`, `Known`

**Examples:** Cortex Catalyst

---

### Model 2 — Operational (Cortex Unity model)

**Audience:** Engineers who run, debug, monitor, or hand off the automation. No direct "users" — but someone is always the operator.

**Filter:** Anything that affects the behavior, reliability, observability, or operability of the system. State architectural changes at headline level — not function-level detail.

**Include:**

- Bug fixes, especially silent ones with data integrity impact (name what was affected)
- New capabilities or behaviors
- Infrastructure changes (CI/CD pipeline, trigger config, deployment method)
- Architectural refactors — one-line headline and operational consequence only
- Reliability and observability improvements
- Breaking changes to inputs, schemas, or integrations

**Exclude:**

- Full lists of extracted/renamed functions
- Test counts
- Individual documentation file names updated
- Internal implementation detail (dataclass fields, handler registries, argparse flags)
- Commit SHAs and PR numbers in body text (link to GitHub release instead)

**Tag taxonomy:** `Feature`, `Fixed`, `Enhancement`, `Technical`, `Infrastructure`

**Format:**

```text
[Tool Name] Release Notes — [Version]

[1-2 sentence plain-language summary of the release]

Table: Feature | Tag | Description
```

Descriptions lead with operational impact, not implementation. "Silent field mapping dropped data on every run since launch" beats "Fixed field name lookup in handler dict."

**Examples:** Cortex Unity, SnO Scheduler, AI Sweeper (automation tools with no direct users)

---

### Model 3 — Engineering Milestones (Search Pipeline model)

**Audience:** Engineering leadership, managers reviewing the body of work, engineers onboarding to the stack.

**Filter:** Substantive architectural decisions and milestones. Not every commit, not user-facing changes, not minor config tweaks.

**Include:**

- Architectural generations and major design decisions
- Schema or indexing strategy changes
- Changes that unblocked specific product capabilities
- Performance milestones with measurable impact
- Corpus or data quality decisions

**Exclude:**

- Dependency bumps and config tweaks with no architectural impact
- CI/CD fixes
- Documentation-only changes

**Tag taxonomy:** `Architecture`, `Pipeline`, `Quality`, `Infrastructure`, `Fixed`

**Examples:** Cortex Search Pipeline

---

## Authoring Rules (All Models)

### Lead with impact, not implementation

| Instead of | Write |
| --- | --- |
| `Refactored field handler to use registry pattern` | `Adding a new Asana field type is now a data change, not a code change` |
| `Fixed KeyError in field_map lookup` | `Silent mapping failure that dropped Tenant ID on every task since launch — fixed` |
| `Added retry logic with exponential backoff` | `LLM API calls now retry with exponential backoff — transient failures no longer abort the run` |

### Progressive disclosure

Start with a one-line plain-language release summary. Then table rows for individual changes. Link to the GitHub release for full engineering detail — don't reproduce it.

### What belongs in the GitHub release vs. release notes

| Belongs in GitHub release | Belongs in release notes |
| --- | --- |
| Function names, parameter signatures | Architectural change + operational consequence |
| Test counts and coverage | — |
| Individual file names changed | — |
| PR and commit links | Link to GitHub release at page footer |
| Full refactor rationale | One-line headline |
| Every config key touched | Config change + what it enables |

### Consistent date format

Release date as written month: `June 2026`, `March 2026`. Not ISO dates.

### Version convention

`YY.M.X` — e.g., `26.6.1`. Older semantic versions (`v0.3.8`) are preserved as-is for historical accuracy but new releases follow this convention.

---

## Tag Reference

| Tag | Color | Hex | Maps to (Keep a Changelog) | Use for |
| --- | --- | --- | --- | --- |
| `Feature` | Green | `#3ecf8e` | Added | Net-new capability that didn't exist before |
| `Enhancement` | Blue | `#4a9eff` | Changed | Improvement to existing functionality |
| `Fixed` | Amber | `#f59e0b` | Fixed | Bug fix — was broken, now correct |
| `Planned` | Yellow | `#f4c94f` | — | Upcoming in a future release (user-facing model only) |
| `Known` | Orange | `#fa582d` | — | Known issue users will encounter (user-facing model only) |
| `Technical` | Purple | `#a78bfa` | — | Refactoring, architecture — headline only, no function detail |
| `Infrastructure` | Teal | `#06b6d4` | — | CI/CD, deployment, cloud config changes |
| `Architecture` | Purple | `#a78bfa` | — | Major design decisions (engineering milestones model) |
| `Pipeline` | Teal | `#06b6d4` | — | Data pipeline or retrieval changes (engineering milestones model) |
| `Quality` | Green | `#3ecf8e` | — | Measurable quality improvements (engineering milestones model) |

### Why these labels

- **Feature not New** — 'New' describes *when* something appeared; every entry in a release note is new. 'Feature' describes *what kind of change it is* — a net-new capability. Source: Elastic internal taxonomy, Keep a Changelog `Added`.
- **Enhancement not Improved/Improvement** — A noun category label, not an adjective. An enhancement is a change to existing functionality that worked as designed but now works better. Source: Elastic, widely adopted in developer tooling.
- **Fixed in amber not green** — Fixed and Feature (formerly New) were both green, making them indistinguishable at a glance. Amber signals 'was broken, now resolved' without the alarm of red.
