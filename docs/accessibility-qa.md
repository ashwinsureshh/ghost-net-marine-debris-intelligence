# Accessibility QA — 2026-09-29

Targeted accessibility checks for the October 10 release, run on the workstation
against the production build served by the API, built from `codex/plan-robustness`
(`main` at af676b3 plus the robustness panel). This covers
the checklist item "targeted accessibility, keyboard, contrast, reduced-motion
and tablet QA". It is a QA record, not a conformance claim.

## Automated — axe-core 4.10.2, WCAG 2.1 A and AA rules

`python scripts/audit_accessibility.py --axe <local axe.min.js>`

| States audited | Result |
|---|---|
| Explore, evidence open, Plan, Research × light and dark (8), every `<details>` expanded | **0 violations** |

The script plants one known violation (an image without alt text) and aborts
unless axe reports it, so this empty result is not from a harness that checked
nothing. Automated rules cover only part of WCAG; the rest is below.

One of my own findings was withdrawn. A shallow DOM query suggested the plan
sliders and agent toggles had no names. Their computed labels are "Cleanup
vessels available", "Planning horizon" and each agent's name, all supplied by
wrapping `<label>` elements.

## Manual — keyboard and focus (Chromium, 1440×900)

| Check | Result |
|---|---|
| First Tab stop | "Skip to content" link |
| Tab order | rail (Explore / Plan / Research / theme) → region select → diagnostics → search → filters → queue rows; logical |
| Focus indicator | 2 px solid outline visible |
| Open evidence from queue | Enter opens it; Escape closes it |
| Approval dialog | focus moves in; stays inside over 8 Tabs; Escape closes; focus returns to "Review and approve plan" |

## Contrast

Computed WCAG ratios for the navy palette (`codex/navy-theme`): all text pairs
are ≥ 4.5:1 in both themes (body 11.2 and 14.6; muted 4.8–8.4). The light-theme
verified and rejected chart colours are 4.35 and 3.81, used only for markers,
bars and icons, where the non-text requirement is 3:1. The current `main`
palette is covered by the axe run above.

## Reduced motion

All console animations are finite. `prefers-reduced-motion: reduce` disables
them in CSS; DispatchPanel's motion/react transitions also honour `useReducedMotion()`.

## Tablet

| Viewport | Horizontal overflow | Notes |
|---|---|---|
| 768×1024 | none | header version text wraps to three lines — cosmetic |
| 1024×768 | none | — |

## Not covered

Screen-reader walkthroughs (NVDA/VoiceOver), Firefox/Safari, touch-only use,
200–400% zoom reflow and map-canvas alternatives beyond the existing queue list.
The map is a visual aid; every detection is also reachable in the keyboard-
operable queue. Treat these as open limitations, not passes.
