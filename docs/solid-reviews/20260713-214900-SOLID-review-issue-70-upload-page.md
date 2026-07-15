SOLID REVIEW — issue-70 /upload page (gateway/main.py) — 2026-07-13 21:49 UTC

Scope expanded:
  - tests/test_proxy_upload.py [SCOPE EXPANDED — Step 0a: imports gateway.main, exercises upload() directly]
  - .github/workflows/deploy-proxy.yml [SCOPE EXPANDED — Step 0b: defines UPLOAD_TOOL_IDS and INPUT_BUCKET consumed by the changed module]
  - scripts/generator/main.py [SCOPE EXPANDED — Step 0b: independently consumes INPUT_BUCKET env var]
  - config/tools.yaml [SCOPE EXPANDED — Step 0b/0c: authoritative tool registry read by generator; separate from proxy's UPLOAD_TOOL_IDS]

Scores:
  S — Single Responsibility: 7/10
  O — Open/Closed:           7/10
  L — Liskov Substitution:   9/10
  I — Interface Segregation: 9/10
  D — Dependency Inversion:  7/10
  OVERALL:                   6.6/10

Summary:

The change is well-scoped and appropriately sized for a single-file Flask proxy. The
`_render_upload` helper has a clean keyword-only signature — callers pass only what they
need, and the template substitution is straightforward. Security escaping (`_html.escape`)
is applied at the right points (user-supplied tool_id, version in error messages; validated
values in the success path). The test suite covers the full POST lifecycle including
validation errors, 503 local-mode guard, 409 duplicate detection, and successful upload for
both release and hotfix versions.

Three moderate gaps remain. First, `upload()` is the densest function in the file: it
accumulates validation errors, guards on local mode, checks blob existence, writes to GCS,
and returns rendered HTML — all inline, with no extracted sub-functions. For this proxy's
scale this is manageable, but it is the point most likely to resist future modification
without risk. Second, there are two independently maintained tool lists — `tools.yaml`
(read by the generator Cloud Function) and the `UPLOAD_TOOL_IDS` env var (read by the
proxy) — with no schema or CI check enforcing their alignment. Adding a tool requires
touching both, and drift is silent. Third, `upload()` depends directly on the module-level
`_storage_client` global, which is the established pattern in this file but limits
unit-testability to module-level patching.

None of these gaps rises to a BLOCK in the context of a ~300-line intentionally
single-file proxy. Each is documented below with actionability assessment.

Gaps:
  [S] — upload() mixes field extraction, three-field validation, local-mode guard, GCS
  blob existence check, GCS write, and response rendering in one 45-line function. The
  validation block (lines 214-226) and the GCS block (lines 228-252) are conceptually
  separate; a future change to validation rules or GCS paths must edit the same function
  body. — gateway/main.py:206
    Realistic to fix now: NO
    Why: Extracting _validate_upload() and _write_to_gcs() would improve clarity but
    is not structurally necessary in a single-file proxy; the cost exceeds the benefit
    at this scale.

  [O] — config/tools.yaml (6 tools, authoritative for the generator) and
  UPLOAD_TOOL_IDS in deploy-proxy.yml (6 tools, authoritative for the upload form) are
  separate lists with no enforcement connecting them. Adding a new tool requires edits
  in both files; drift is silent and detectable only at runtime when the dropdown is
  missing a tool. The code-level default "cortex-catalyst" (main.py:24) is vestigial —
  production never uses it. — .github/workflows/deploy-proxy.yml:24 / config/tools.yaml
    Realistic to fix now: YES
    Why: A CI check (or a comment linking the two files) costs little and prevents the
    lists from silently diverging. The vestigial single-tool default could document that
    it is a fallback, not the intended production value.

  [D] — upload() reads _storage_client directly from module global scope (main.py:228,
  236, 248) rather than receiving it as a parameter. The test suite compensates with
  patch.object(proxy_module, "_storage_client", mock_client), which works but requires
  knowledge of the internal module name. This is consistent with how _resolve_latest()
  uses _storage_client (line 169), so the pattern is established, not new. — gateway/main.py:228
    Realistic to fix now: NO
    Why: Injecting the client would require restructuring Flask route registration or
    adding a factory pattern; neither is warranted for a proxy of this size.

  [S] — Version format regex is duplicated: _VERSION_RE_UPLOAD on the server
  (main.py:27) and VRE in the embedded JavaScript (main.py:114). They are currently
  identical. A format change must be applied in both places with no enforcement. This is
  expected for server+client parity, but worth noting. — gateway/main.py:27 and :114
    Realistic to fix now: NO
    Why: The JS regex must live in the HTML for client-side UX; true single-source-of-truth
    would require generating it server-side into the template, which is over-engineering
    for a static format.

Step 1 — Dependency Boundary Audit findings: NONE. google.cloud.storage.Client is
thread-safe and has no shared mutable state. INPUT_BUCKET is env-var configurable. The
GCS blob interface (.exists(), .upload_from_string()) is fully exercised by callers —
no dead interface at this boundary. _credentials (read_only scoped) and _storage_client
(full ADC) are intentionally separate credential paths: the former is for bearer-token
proxying to the serve bucket; the latter is for SDK calls to both buckets.

RECOMMENDATION: CONDITIONAL PASS

Reason: OVERALL 6.6 is within the conditional range; no principle scores below 6. The
upload() handler is the most complex function added, mixing validation, two GCS operations,
and response rendering inline, but it is linear and readable at this scale. The O gap
(dual tool registries: tools.yaml and UPLOAD_TOOL_IDS) is the most actionable finding —
a comment or CI step linking the two lists would eliminate silent drift risk at low cost.
