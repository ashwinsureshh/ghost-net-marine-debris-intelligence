# Console map refinement — 2026-09-16

Branch: `codex/marine-atlas-ui`; draft PR #15, stacked on #13.

Display-only clustering groups observations in 56-pixel world-coordinate bins.
Counts are detection records across acquisitions, not distinct debris objects
or vessels. Each record remains available in a group's scrollable member list,
including at maximum zoom. Selection always produces an individual marker.

Layers independently control rejected detections, protected areas, forward
drift/envelope, backward drift/envelope and unmatched SAR observations. Drift
and SAR use the selected detection. A selected rejection remains visible when
other rejections are hidden; the controls explain this exception. Fit observations
frames the visible records, with the region bounding box as an empty fallback.

## Verification

- TypeScript and Vite production build: passed.
- `node --test frontend/tests/mapClusters.test.mjs`: 5 passed (Node 24).
  Covers conservation of records, coincident/selected records, zoom separation,
  negative coordinates, boundaries and order-independent grouping.
- Targeted Python webapp, export, prioritisation and rationale suite: 96 passed.
- Browser at 1440×900 and 390×844, light/dark themes: checked.
- Gonâve: all 247 records represented; hiding rejections with one rejected
  selection retains 65 verified plus that selected record.
- Honduras: all 826 records represented before and after group zoom; the
  181-member desktop and 407-member mobile groups expose every member.
- Maximum zoom: a two-member group remains selectable; the unavailable zoom
  action is absent, and choosing a member updates the evidence/selected marker.
- Layer rendering checked on a verified Gonâve detection: SVG paths reduce
  49 → 47 → 45 → 0 as forward, backward and protected-area layers are disabled;
  SAR markers reduce 5 → 0 independently. Restoring switches restores overlays.
- Mobile layer panel and popup remain within the viewport; no horizontal
  overflow. Escape dismisses layer controls and returns focus to their toggle.
- Popup auto-pan now reserves toolbar space. SVG rendering eliminates the
  observed pending Canvas redraw error after map teardown; no recurrence after
  reload and subsequent interaction checks.

The prior shell QA covered search, region switching, rejected/verified evidence,
zero-capacity replanning, research controls, diagnostics and the named review
gate. No plan was approved during QA. Backend, scoring, artifacts and approval
requirements are unchanged in this refinement.

## Known limits

Bins are a visual grouping, not geographic inference; nearby bins can overlap
at their edges. Zoom, member lists and the searchable queue retain access.
Basemap tiles remain an external dependency, with the existing offline notice
and measured native zoom cap. Existing Vite bundle-size and Starlette/httpx
deprecation warnings remain. No dependencies were added.
