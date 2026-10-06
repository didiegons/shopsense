# Assignment 5.4: Accessibility Review

- **Date:** 2026-10-05
- **Target:** WCAG 2.2 Level AA
- **Scope:** ShopSense home/search page (`frontend/app/page.tsx`, `page.module.css`, `globals.css`)

## Method

1. **Automated:** axe-core 4.14 (`wcag2a`, `wcag2aa`, `wcag21a`, `wcag21aa`, `wcag22aa`, `best-practice`) in desktop Chrome on five UI states: initial page; clarification with the blocked-search error; interpretation with OS opt-in and results; no-match; and results at 320 px.
2. **Manual / scripted:** keyboard-only workflow, focus visibility, reflow at 320–1440 px, 200% zoom, the WCAG 1.4.12 text-spacing override, forced-colors (Windows high contrast) emulation, heading and landmark structure, live-region behavior, and contrast calculations for colors axe could not resolve.
3. **Not performed:** testing with a real screen reader (NVDA, Narrator, VoiceOver). It is recommended before the final demonstration.

## Findings

| ID | WCAG | Severity | Finding | Fix / recommendation | Status |
| -- | ---- | -------- | ------- | -------------------- | ------ |
| A1 | 2.5.3 Label in Name (A) | Serious (axe) | The brand link shows "ShopSense AI" but its accessible name was `aria-label="ShopSense home"`. Speech-input users who say "click ShopSense AI" would not match it. Flagged in all five states. | `aria-label` changed to "ShopSense AI home" (`page.tsx`), which contains the visible text. | **Fixed.** axe `label-content-name-mismatch` no longer reported. |
| A2 | 1.4.3 Contrast (AA) | Serious (axe) | The intent-panel note (`.note`, `#64746b` on `#eef2ec`, 12.8 px) was **4.36:1**; the image fallback text (`#64746b` on `#e9eeea`) was **4.21:1**. Both are below 4.5:1. | Both colors changed to `#5a6a61` (`page.module.css`). Muted text elsewhere already passed and is unchanged. | **Fixed.** Measured in the browser: note **5.06:1**, visible fallback **4.87:1**. |
| A3 | 1.4.11 Non-text Contrast (AA) | Moderate | Input and select borders (`#bfcac2` on white) were **1.69:1**, below the 3:1 needed to identify control boundaries. | Border changed to `#879489` (`page.module.css`). | **Fixed.** Measured **3.17:1** on all 5 text/number/select controls. |
| A4 | 1.4.11 / 2.4.7 | Minor | The focus outline (`#cf754b`) is 3.33:1 on white and 3.09:1 on the page background, but **2.94:1** on the intent panel (`#eef2ec`), where the clarification and OS opt-in checkboxes sit. | Slightly darken the outline color, or add a second contrasting ring for focus inside the panel. | Future improvement (non-blocking): focus is still clearly visible as a 3 px outline. |
| A5 | 4.1.3 Status Messages (AA) | Moderate | The intent panel's `aria-live` region is mounted at the same moment as its content, so many screen readers will not announce the first interpretation. The persistent results region wraps the whole results list, so a search may read out every card (up to 16). | Keep one always-mounted, visually hidden status element that announces short summaries ("Requirements interpreted; clarification needed", "9 demo products found"), and remove `aria-live` from the large containers. | Future improvement (non-blocking). Confirm behavior with NVDA/Narrator. |
| A6 | 3.3.2 Labels or Instructions (A) | Moderate | "Minimum RAM" and "Maximum weight" didn't state units, which users need in order to enter correct values. | Labels changed to "Minimum RAM (GB)" and "Maximum weight (kg)" (`page.tsx`). | **Fixed.** Accessible names include the units. |
| A7 | 3.3.1 Error Identification (A), best practice | Minor | Error messages are announced (`role="alert"`) and described in text, but they are not linked to the related control (no `aria-describedby` / `aria-invalid`, e.g. for the over-length query). | Link the query error to `#natural-query` with `aria-describedby` and set `aria-invalid` while it is shown. | Future improvement (non-blocking). |
| A8 | Best practice | Minor | `<header>` is inside `<main>`, so the page has no banner landmark. The disabled **Interpret requirements** button shows a `wait` cursor and no reason when the query is empty. | Move the header outside `<main>`; use `not-allowed` for the empty-query state or add brief helper text. | Future improvement (non-blocking). |

## Verified as Meeting Requirements

- **Keyboard (2.1.1, 2.4.3):** the full workflow works by keyboard. Tab order is logical (home → query → interpret → filters → OS → search), Enter submits the interpretation, and Space toggles checkboxes and triggers search. No keyboard traps.
- **Focus visible (2.4.7):** a 3 px outline appears on every focusable control and stays visible in forced-colors mode.
- **Labels (1.3.1, 4.1.2):** all 8 form controls have accessible names from wrapping or `for` labels; the status and alert roles are used correctly.
- **Structure:** `lang="en"`, a descriptive page title, and a logical heading hierarchy (h1 → h2 sections → h3 product names).
- **Reflow (1.4.10):** no horizontal scrolling from 320 to 1440 px; cards and images stack on narrow screens.
- **Resize text (1.4.4):** content stays readable and unclipped at 200% zoom; realistic long model and specification text wraps.
- **Text spacing (1.4.12):** with the WCAG spacing override at 320 px, nothing is clipped or overflows.
- **Images (1.1.1):** product images have descriptive alt text; the fallback replaces broken images (M14).
- **Target size (2.5.8):** axe's target-size rule passes; the checkboxes are 16 px but sit inside full-width clickable labels.
- **Forced colors:** controls, borders, and focus remain visible in high-contrast emulation.
- **Contrast passing elsewhere:** body and heading text, buttons (white on `#20523f`), provenance and results metadata (`#64746b` on `#f5f7f3`, 4.58:1).

## Re-test After Fixes (A1, A2, A3, A6)

- **axe-core:** 0 violations in all six re-tested states (initial, clarification + error, interpretation + results, no-match, image fallback visible, results at 320 px). The only remaining needs-review items are `color-contrast` checks on the image fallback text while it is covered by a loaded or not-yet-loaded lazy image. Where the fallback is visible, it measures 4.87:1.
- **Reflow:** no horizontal overflow at 320 px.
- **Browser regression:** M01–M16 and M19–M23 re-run and passing (M17/M18 verified separately with the backend stopped; M24 not run).
- **Builds and tests:** frontend ESLint clean, `tsc --noEmit` clean, `next build` succeeds, backend pytest 86 passed.

## Status

A1, A2, A3, and A6 are fixed. A4, A5, A7, and A8 are documented as non-blocking future improvements. A screen-reader pass (NVDA or Narrator) is still recommended before the final demonstration.
