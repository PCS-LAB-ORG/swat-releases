SOLID REVIEW — fix/issue-80-generator-multi-panel-index — 2026-07-23 17:52 UTC

Scope expanded: none. Codebase-wide grep (Step 0a) found all callers of
IndexUpdater, GCSIndexUpdater, rebuild_panel, and rebuild_catalyst_panel within the
diff or test files. Step 0b found panel_id consumers in render.py, generator/main.py,
and tests only. Step 0c confirmed all construction sites of GCSIndexUpdater and
IndexUpdater are in tests or the diff. No additional files required.

Scores:
  S — Single Responsibility: 7/10
  O — Open/Closed:           7/10
  L — Liskov Substitution:   8/10
  I — Interface Segregation: 6/10
  D — Dependency Inversion:  7/10
  OVERALL:                   6.0/10

Summary:
The core change — generalizing rebuild_catalyst_panel to rebuild_panel by reading
panel_id from the tool dict rather than hardcoding "catalyst" in the regex — is
well-executed. The config opt-in pattern (tools declare panel_id; the loop skips
tools without it) is extensible without code modification, which is a genuine OCP
improvement. VALID_TAGS expansion is additive and non-breaking. The test suite
update correctly captures the new invariant (two panels rebuilt, not one) and adds
a non-catalyst panel integration test.

Three gaps limit the score: (1) rebuild_index hardcodes is_default=True for every
tool in the loop, which means all rebuilt panels receive the `active` CSS class —
only the catalyst panel is supposed to carry it, and non-catalyst panels previously
did not. This is a functional regression introduced by this change. (2) The
"catalyst-panel.html.j2" template name is hardcoded inside both updater classes,
so adding a tool that needs a different panel layout requires modifying both classes.
(3) The full panel-replace algorithm (regex start, regex end, splice) is duplicated
between IndexUpdater and GCSIndexUpdater; only the I/O layer differs.

Gaps:
  [ISP] — rebuild_index does not expose is_default as a parameter and always calls
  rebuild_panel(tool, ..., is_default=True) for every tool in the panel loop.
  The template renders `class="tool-panel active"` when is_default=True. Before
  this change, only cortex-catalyst was rebuilt and was always active; all other
  panels retained their original HTML (no active class). After this change, all six
  panels are rebuilt with is_default=True, giving all six panels the `active` CSS
  class. The original index.html design has only the catalyst panel marked active;
  non-catalyst panels carry no active class. This change silently overwrites that
  distinction on every hourly run. Whether it causes simultaneous multi-panel display
  depends on the CSS in GCS index.html (not in the git repo), but it is a
  semantic regression regardless. — generator/main.py:79
    Realistic to fix now: YES
    Why: Add `is_default: bool = True` parameter to rebuild_index and thread it
    through to rebuild_panel; in run_generator pass
    is_default=(tool["id"] == "cortex-catalyst") or derive from a
    `default_panel: true` config field in tools.yaml.

  [OCP] — Both IndexUpdater.rebuild_panel (render.py:160) and
  GCSIndexUpdater.rebuild_panel (render.py:246) hardcode the template name
  "catalyst-panel.html.j2". The method is now generic (panel_id is dynamic), but
  the template is not. Adding a tool with a different panel layout requires modifying
  both classes. The tool dict already flows into both methods; a one-line change to
  read tool.get("panel_template", "catalyst-panel.html.j2") closes this at zero
  risk since all current tools share one template. — render.py:160, render.py:246
    Realistic to fix now: YES
    Why: Single additive change to each class; no test impact; future-proofs the
    multi-panel design without touching tool config for existing tools.

  [SRP] — The six-step panel-replace algorithm (render template, read content,
  regex start boundary, regex end boundary, compute splice, write result) is
  duplicated verbatim between IndexUpdater.rebuild_panel (render.py:151-184) and
  GCSIndexUpdater.rebuild_panel (render.py:237-272). Only the I/O calls differ
  (file read/write vs. blob download/upload). A shared private function
  _splice_panel_content(content: str, panel_id: str, panel_html: str) -> str
  would eliminate the duplication and ensure a regex fix applies to both classes.
  Pre-existing, not introduced by this change. — render.py:151, render.py:237
    Realistic to fix now: YES
    Why: Pure extraction with no behavioral change; reduces the surface where the
    regex logic must be maintained in parallel.

  [D] — rebuild_index constructs TemplateEngine("scripts/templates") and
  GCSIndexUpdater(engine, gcs_client, serve_bucket) internally on every call.
  render_version does the same (GCSIndexUpdater, GCSHTMLRenderer, load_assets).
  The test suite patches rebuild_index as a whole unit, meaning its internal
  construction logic is never exercised. This contrasts with process_release, which
  accepts all its dependencies as injected keyword arguments in the same module.
  Pre-existing, not introduced by this change. — generator/main.py:49-52,
  generator/main.py:73-75
    Realistic to fix now: NO
    Why: Would require threading engine/updater through rebuild_index and
    render_version signatures and updating callers; significant refactor scope
    versus the improvement this PR targets.

  [D/coupling] — rebuild_index imports _group_by_month from scripts.render using a
  local import of a private symbol (prefixed with _). Private symbols signal
  implementation-internal scope; cross-module imports of private symbols create
  tight coupling that bypasses the module's public API. _group_by_month should
  either be made public (remove the underscore) or moved to scripts.config as a
  shared utility. Pre-existing. — generator/main.py:72
    Realistic to fix now: YES
    Why: One-character rename in render.py (remove underscore) and update the
    import comment; no behavioral change.

RECOMMENDATION: CONDITIONAL PASS

Reason: The generalization of the panel rebuild loop from a catalyst-only sentinel
to a config-driven opt-in is a sound design improvement. The primary blocker is the
is_default=True hardcoding in rebuild_index for all tools in the loop: since all six
tools now declare panel_id, every hourly run will stamp all six panels with
class="tool-panel active", overwriting the active/inactive distinction the original
HTML establishes. This should be resolved before the generator runs against the live
GCS index.html. The template hardcoding (OCP) and splice duplication (SRP) are
manageable debt that can be tracked as issues rather than blocking the merge.
