# Release Notes Standards

Standards for authoring release notes in this repository. All tools follow one of three models depending on their audience. The model determines what to include, what to filter, and how to frame entries.

---

## The Three Models

### Model 1 — User-Facing (Catalyst model)

**Audience:** Team members, managers, and stakeholders who interact with the application directly.

**Filter:** Only what a user notices when interacting with the tool. Everything else is excluded.

**Include:**

- Net-new features and UI changes
- Quality improvements to answers, outputs, or citations
- Bug fixes that affected user experience
- Known issues and limitations users will encounter
- Planned features coming in future releases

**Omit — always:**

- Backend infrastructure (Cloud Run, BQ schema, alert policies, CI/CD)
- Developer tooling (Docker, test suite, SDK upgrades, conftest changes)
- Internal refactors with no visible behavior change
- Monitoring and observability stack changes
- Documentation updates
- Any change that required no action and caused no observable difference

**Tag taxonomy:** `Feature`, `Enhancement`, `Fixed`, `Planned`, `Known`

**Examples:** Cortex Catalyst

---

### Model 2 — Operational (Cortex Unity model)

**Audience:** Engineers who run, debug, monitor, or hand off the automation. No direct "users" — but someone is always the operator.

**Filter:** Anything that affects the behavior, reliability, observability, or operability of the system. The test: would an engineer debugging an incident, onboarding to the system, or handing it off need to know this?

**Include:**

- Bug fixes — especially silent ones with data integrity impact; name what was affected and for how long
- Net-new capabilities or trigger behaviors
- Infrastructure changes: CI/CD pipeline, trigger config, deployment method, SDK platform migrations
- Significant architectural changes — one-line headline stating the operational consequence (not the implementation)
- Reliability and observability improvements: error handling, logging, retry logic
- Breaking changes to inputs, schemas, CSV contracts, or integrations

**Omit — always:**

- Individual function names, parameter signatures, extracted classes
- Test counts and coverage metrics
- Documentation file names or doc-only changes (CHANGELOG.md, README section updates, etc.)
- Internal implementation details: dataclass field lists, handler registry names, argparse flags
- Minor code cleanup with no behavioral change (removing unused imports, renaming variables)
- Any change whose omission leaves an operator with a complete picture of how the system behaves

**Tag taxonomy:** `Feature`, `Fixed`, `Enhancement`, `Architecture`, `Infrastructure`

**Note on "Technical":** Not used. "Technical" is redundant — everything in release notes is technical. Refactoring that belongs in release notes is significant enough to warrant a precise label: `Architecture` for structural design decisions, `Enhancement` for internal improvements with operational impact, `Infrastructure` for platform or dependency changes. Pure refactoring with no behavioral consequence is omitted.

**Format:**

```text
[Tool Name] Release Notes — [Version]

[1-2 sentence plain-language summary of the release]

Table: Change | Tag | Description
```

Descriptions lead with operational impact, not implementation. "Silent field mapping dropped data on every run since launch — fixed" beats "Fixed KeyError in field_map lookup."

**Examples:** Cortex Unity, SnO Scheduler, AI Sweeper

---

### Model 3 — Engineering Milestones (Search Pipeline model)

**Audience:** Engineering leadership, managers reviewing the body of work, engineers onboarding to the stack.

**Filter:** Substantive architectural decisions and milestones. The test: would this entry help someone understand why the system is designed the way it is, or what generation of the architecture they're looking at?

**Include:**

- Architectural generations and major design decisions, with the rationale
- Schema or indexing strategy changes
- Changes that directly unblocked specific product capabilities
- Performance milestones with measurable before/after impact
- Corpus or data quality decisions

**Omit — always:**

- Dependency version bumps with no architectural consequence
- CI/CD pipeline changes
- Documentation-only changes
- Config tweaks that don't reflect a design decision
- Any change that a future engineer reading the architecture docs wouldn't need to know

**Tag taxonomy:** `Architecture`, `Pipeline`, `Quality`, `Infrastructure`, `Fixed`

**Examples:** Cortex Search Pipeline

---

## Authoring Rules (All Models)

### Lead with impact, not implementation

Every entry should answer: *what can the operator/user now do, or what problem no longer exists?* Not: *what code changed?*

| Instead of | Write |
| --- | --- |
| `Refactored field handler to use registry pattern` | `Adding a new Asana field type is now a data change, not a code change` |
| `Fixed KeyError in field_map lookup` | `Silent mapping failure that dropped Tenant ID on every task since launch — fixed` |
| `Added retry logic with exponential backoff` | `LLM API calls now retry with exponential backoff — transient failures no longer abort the run` |
| `Updated docs/logging.md` | *(omit)* |
| `Removed unused imports, renamed internal variables` | *(omit)* |

### The omit decision

When deciding whether a change belongs in release notes, apply this test in order:

1. **Would an operator or user notice if this wasn't here?** If no — omit.
2. **Does this change what the system does, how reliably it does it, or how someone would debug it?** If no — omit.
3. **Is it purely internal implementation detail?** Function names, test counts, doc file names, variable renames — omit.
4. **Is it a documentation or cleanup change only?** Omit. These belong in the GitHub release, not release notes.

The GitHub release is the place for everything. Release notes are the curated, durable record of what mattered.

### Progressive disclosure

Start with a one-line plain-language release summary. Table rows for individual changes. Link to the GitHub release for full engineering detail — don't reproduce it.

### What belongs where

| Belongs in GitHub release only | Belongs in release notes |
| --- | --- |
| Function names, parameter signatures | Architectural change + operational consequence |
| Test counts and coverage | — |
| Individual file names changed | — |
| Documentation updates | — |
| Minor cleanup and refactoring | — |
| PR and commit links | Link to GitHub release at page footer |
| Full refactor rationale | One-line headline of the consequence |
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
| `Architecture` | Purple | `#a78bfa` | — | Significant structural design decision (operational/engineering models) |
| `Infrastructure` | Teal | `#06b6d4` | — | CI/CD, deployment, platform, SDK migrations |
| `Pipeline` | Teal | `#06b6d4` | — | Data pipeline or retrieval changes (engineering milestones model) |
| `Quality` | Green | `#3ecf8e` | — | Measurable quality improvements (engineering milestones model) |

### Why these labels

- **Feature not New** — "New" describes *when* something appeared; every release note entry is new by definition. "Feature" describes *what kind of change it is* — a net-new capability. Source: Elastic internal taxonomy, Keep a Changelog `Added`.
- **Enhancement not Improved** — A noun that names a category, not an adjective describing an outcome. An enhancement is a change to something that worked as designed but now works better. Source: Elastic taxonomy, widely adopted in developer tooling.
- **Fixed in amber** — Fixed and Feature were both green, making them visually indistinguishable. Amber signals "was broken, now resolved" without the alarm of red.
- **No "Technical" tag** — "Technical" is redundant: everything in release notes is technical. Changes formerly labeled "Technical" are reclassified as `Architecture` (structural design decisions), `Enhancement` (internal improvements with operational impact), or `Infrastructure` (platform/dependency changes) — or omitted if they have no operator consequence.
