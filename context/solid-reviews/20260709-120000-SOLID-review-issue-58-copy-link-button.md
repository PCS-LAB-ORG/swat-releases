SOLID REVIEW — issue-58 copy-link button (develop → main) — 2026-07-09 12:00 UTC

Scope expanded:
  - scripts/render.py [SCOPE EXPANDED — Step 0a: primary caller of both changed templates]
  - scripts/generator/main.py [SCOPE EXPANDED — Step 0a: pipeline entry point that calls render.py]

Scores:
  S — Single Responsibility: 7/10
  O — Open/Closed:           8/10
  L — Liskov Substitution:   8/10
  I — Interface Segregation: 9/10
  D — Dependency Inversion:  7/10
  OVERALL:                   6.6/10

Summary:

The diff contains one net change: the copy-link button (`.hero-copy-btn`) added to
`release-page.html.j2`. The `catalyst-panel.html.j2` diff between main and develop is
empty — those commits cancelled or were already present in main, so the net state is
identical in both branches.

The change is architecturally consistent with the project's self-contained page design
(documented in CLAUDE.md: individual release pages are shareable, single-file HTML). The
inline JavaScript approach is intentional, not accidental. The button was added without
modifying any existing markup — clean OCP addition.

The primary gap is SVG duplication. The chain-link icon is defined twice in the same
file: once as the actual `<button>` child element (the rendered icon), and again as the
JavaScript string literal `L` inside the `onclick` handler (the reset value after the
clipboard confirmation animation). Both definitions must be kept byte-for-byte identical.
If the icon path changes, the editor must update two separate locations — one as real
HTML, one as a JavaScript-escaped string — with no tooling to enforce they stay in sync.

The boundary audit (Step 1) found no issues. `render.py`'s `TemplateEngine.render()`,
`HTMLRenderer.render_release_page()`, and `GCSHTMLRenderer.render_and_upload()` all pass
the same template context as before. No new Jinja2 variables were introduced; the button
uses only browser-native APIs (`navigator.clipboard`, `window.location.href`). The
template interface is unchanged. `render.py` itself shows no SRP or OCP violations at
the call boundary.

Domain note: This is UI/template code. I and L carry more weight per the weighting
guidance. I is strong (9/10). L is not meaningfully applicable (no type hierarchy). S
and D carry 1.5× weight; S is reduced by the SVG duplication.

Gaps:
  [S] — Chain-link SVG defined twice in release-page.html.j2: once as rendered button
  content (HTML), once as the JS reset string variable `L` in the onclick handler.
  A change to the icon requires two coordinated edits with no tooling enforcement.
  — scripts/templates/release-page.html.j2:169-175 (onclick attribute + button child SVG)
    Realistic to fix now: YES
    Why: Extract the icon path data to a JS constant above the onclick, or use a
    data attribute on the button to hold the link-icon SVG, so it is sourced from one
    place at runtime. Alternatively, use a named SVG symbol (`<defs>/<symbol>` + `<use>`)
    defined once in the page and referenced by both the static render and the JS reset.

  [S] — All three concerns of the copy interaction — clipboard write, icon swap, title
  reset — are collapsed into a single `onclick` IIFE with no named functions. This is
  readable now but would become opaque if error branches or additional affordances
  (e.g., fallback for HTTP contexts where clipboard API is unavailable) are added.
  — scripts/templates/release-page.html.j2:169-175
    Realistic to fix now: NO
    Why: The current complexity is low enough that refactoring to a named function in a
    `<script>` block is cosmetic at this scope. It becomes meaningful if the interaction
    grows. Worth revisiting if a clipboard fallback (execCommand or prompt) is added.

  [D] — SVG markup is hardcoded as an escaped string literal inside the onclick handler.
  Any icon design change requires manually escaping the SVG and updating the handler
  string — a dependency on the icon's exact serialized form baked into behavior logic.
  — scripts/templates/release-page.html.j2:170-171
    Realistic to fix now: YES (same fix as the [S] gap above — resolves both)
    Why: Sourcing the icon from the DOM (via `innerHTML` snapshot on load or a `<defs>`
    reference) removes the hardcoded string and eliminates the duplication in one move.

RECOMMENDATION: CONDITIONAL PASS

Reason: Overall 6.6; no principle below 4; no SRP or OCP violations in core modules
(`render.py`, `generator/main.py`). The boundary audit found the template interface is
clean and unchanged. The only actionable gap — the SVG defined twice — is a concrete
dual-maintenance point in `release-page.html.j2` that is straightforward to fix using a
DOM-sourced approach or a `<defs>/<symbol>` reference. Proceed to merge; file a
follow-up issue for the SVG deduplication.
