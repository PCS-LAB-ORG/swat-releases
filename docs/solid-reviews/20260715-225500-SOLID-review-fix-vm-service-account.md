SOLID REVIEW — fix: vm-service-account — 2026-07-15 22:55 UTC

Scope expanded:
  [SCOPE EXPANDED — Step 0b config key consumer] .github/workflows/deploy-generator.yml —
    references WIF_SERVICE_ACCOUNT (same SA as the corrected VM_SERVICE_ACCOUNT); read to
    confirm consistent SA usage across both workflows.
  [SCOPE EXPANDED — Step 0b config key consumer] CLAUDE.md — documents both "Pipeline SA"
    and "Proxy VM SA" identities; read to audit documentation consistency post-change.

APPLICABILITY NOTE: SOLID principles are designed for object-oriented and procedural code.
This change modifies a single env var in a GitHub Actions YAML workflow. Scores below are
evaluated on CI/CD analogues: step separation (S), config extensibility (O), contract
compliance (L), parameter minimality (I), and dependency externalization (D). L is scored
neutral (8) throughout — there is no polymorphism or substitution surface in CI YAML.

Scores:
  S — Single Responsibility: 8/10
  O — Open/Closed:           9/10
  L — Liskov Substitution:   8/10  [N/A — scored neutral]
  I — Interface Segregation: 8/10
  D — Dependency Inversion:  9/10
  OVERALL:                   8.4/10

Summary:
The corrected workflow is well-structured. All GCP resource identifiers (project ID, SA
emails, region, WIF provider path, network, bucket names) are centralized in the env block
at the top of the file; no hardcoded values appear inside individual steps. The idempotent
template-creation guard and the explicit rollout wait both reflect sound CI/CD design. The
change correctly aligns VM_SERVICE_ACCOUNT with the established swat-releases-pipeline SA
used by WIF_SERVICE_ACCOUNT in both workflows.

One gap warrants a follow-up commit: CLAUDE.md's Infrastructure table still names
cloudrun-testing-svc@pcs-swat-resources.iam.gserviceaccount.com as "Proxy VM SA". That
entry is now incorrect — the VM instances are attached to swat-releases-pipeline. A
developer consulting CLAUDE.md during incident response or IAM auditing will get the wrong
SA identity.

Gaps:
  [D / Config consistency] — CLAUDE.md Infrastructure section lists
    "Proxy VM SA: cloudrun-testing-svc@pcs-swat-resources.iam.gserviceaccount.com" but
    the workflow now attaches swat-releases-pipeline to VM instances. The live reference
    document is out of sync with the deployed configuration.
    File: CLAUDE.md, Infrastructure table ("Proxy VM SA" row)
    Realistic to fix now: YES
    Why: One-line update to CLAUDE.md; trivial to apply on a docs/ chore branch.

  [I / Redundant env var] — After this change both WIF_SERVICE_ACCOUNT and VM_SERVICE_ACCOUNT
    resolve to the same value (swat-releases-pipeline@pcs-swat-resources.iam.gserviceaccount.com).
    The two-variable structure is still the correct pattern if the SAs ever diverge again, so
    this is an observation rather than a required fix. The current workflow could reference
    WIF_SERVICE_ACCOUNT directly at line 132 to make the identity explicit, but the redundancy
    is harmless.
    File: .github/workflows/deploy-proxy.yml, line 28 vs line 30
    Realistic to fix now: NO
    Why: The separate variable names preserve the conceptual distinction between CI identity
    and VM runtime identity; collapsing them would reduce clarity for the marginal gain of
    removing one env declaration.

RECOMMENDATION: CONDITIONAL PASS

Reason: The workflow scores above 8.0 overall and no principle falls below 6. The only
actionable gap — CLAUDE.md's stale "Proxy VM SA" entry — is a documentation inconsistency,
not a code defect. The fix itself is correct: VM_SERVICE_ACCOUNT now matches the SA that
holds the required GCS and Compute IAM grants for this project. Proceed; file a docs chore
to update CLAUDE.md's Infrastructure table before the next operator consults it.
