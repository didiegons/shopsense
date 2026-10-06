# ShopSense — Assignment 5.4 Testing & Security Report

**Date:** 2026-10-05 · **Stack:** Next.js + TypeScript frontend; FastAPI + Pydantic backend; optional Vertex AI (Gemini) intent extraction with a deterministic fallback · **Supporting records:** `manual-test-execution.md`, `security-review.md`, `accessibility-review.md`

## 1. Testing Summary

| Area | Method | Result |
| ---- | ------ | ------ |
| Manual functional tests M01–M24 | Desktop Chrome driven by Playwright, capturing each request and response; network delay simulated for loading states; backend really stopped for M17/M18 | **M01–M23 passed.** **M24 not run**: Vertex AI was not configured. |
| Backend unit/integration tests | `pytest` | **86 passed** (75 existing + 11 added in this review) |
| Frontend static checks | ESLint, `tsc --noEmit`, `next build` | **All passed** |
| Security | Code review, secret scan, `npm audit`, `pip-audit`, live hostile-input probes of the API | 2 issues fixed; remaining items documented (Section 3) |
| Accessibility | axe-core 4.14 (WCAG 2.2 AA + best practice) on six UI states, plus keyboard, reflow, zoom, text-spacing and forced-colors checks | **0 axe violations after fixes** (Section 4) |

The manual tests cover search and navigation (M01–M03), OS handling and clarification (M04–M09), search results, no-match and image fallback (M10–M14), loading and error states (M15–M19), and accessibility, responsiveness and zoom (M20–M23).

## 2. Bugs Found and Fixed

| Bug | Root cause | Fix | Verification |
| --- | ---------- | --- | ------------ |
| `POST /api/v1/search` returned HTTP 500 while `/api/v1/intent` worked | Stale Uvicorn processes from before the product-image change were still serving requests. Their old `Product` model (`extra="forbid"`) rejected the new `image_url` field in `catalog.json`. The OneDrive-synced folder stopped `--reload` from noticing the change. | No code change. Stopped the stale processes and restarted the backend with `WATCHFILES_FORCE_POLLING=true`. | Search returns 200 with and without filters. |
| **M14:** broken-image icon and alt text overlapped the "Demo image unavailable" fallback | `.productImage { display: block }` overrode the HTML `hidden` attribute | Added `.productImage[hidden] { display: none; }` | Image blocked → only the fallback shows; unblocked images still load. |
| **M17/M18:** backend outage showed the raw text "Failed to fetch" | A network failure is thrown before the response-status handling in `lib/api.ts` runs | `extractIntent` and `searchProducts` now catch network errors and show a clear message ("Could not reach the ShopSense service…") | Re-tested with the backend stopped; the page stays usable. |

## 3. Security Issues Identified and Resolved

**Fixed (findings #2 and #3):**
- **Non-finite numbers:** `{"max_budget": NaN}` caused an HTTP 500, because the 422 error echoed `NaN`, which cannot be serialized as JSON. `Infinity` was accepted as "no limit". The float search fields now use `allow_inf_nan=False`.
- **Echoed input:** 422 responses echoed raw input back to the client (for example, a 5 MB query). A custom validation-error handler now returns the standard error details without the `input` field.
- **Tests:** 11 new tests prove that `NaN`, `Infinity` and `-Infinity` return a clean 422 on all numeric fields, that oversized or invalid values are not echoed, and that valid numeric searches are unchanged.

**Accepted or deferred (documented, no change made):**

| # | Item | Disposition |
| - | ---- | ----------- |
| 1 | No authentication or rate limit on `/api/v1/intent`; risk of running up Vertex AI costs | Accepted for the local demo; add rate limiting or IAM and a billing alert before deploying |
| 4 | No request body size limit | Deployment item: enforce at the proxy or in middleware |
| 5 | Public `/docs`; no security headers; `X-Powered-By` header sent | Deployment item: add headers in `next.config.ts`; turn off docs in production |
| 6 | Unpinned Python dependencies | Future hardening: pin with hashes |
| 7 | 5 high-severity `npm audit` advisories, all in the dev-only ESLint dependency chain | Accepted: not shipped; production audit is clean |
| 8 | Vertex adapter may not catch `httpx` transport errors | Unverified while Vertex is unconfigured; verify later |
| 9 | Prompt injection through the user's query | Accepted: output is schema-constrained and validated, and the model cannot search or produce product facts |

**Controls verified:** no secrets in the repository and `.env*` gitignored; unknown fields rejected (`extra="forbid"`); CORS limited to `http://localhost:3000` without credentials; non-JSON content types and deeply nested JSON rejected cleanly; no tracebacks returned to clients; no unsafe HTML-rendering APIs in the frontend; `pip-audit` found no known vulnerabilities and `npm audit --omit=dev` reported 0.

## 4. Accessibility Findings and Fixes

| ID | Finding (WCAG) | Resolution |
| -- | -------------- | ---------- |
| A1 | The brand link's accessible name "ShopSense home" did not include the visible text "ShopSense AI" (2.5.3) | **Fixed:** name is now "ShopSense AI home" |
| A2 | Muted text on tinted backgrounds was 4.36:1 and 4.21:1 (1.4.3) | **Fixed:** now 5.06:1 and 4.87:1 |
| A3 | Input borders were 1.69:1 (1.4.11) | **Fixed:** now 3.17:1 |
| A6 | RAM and weight labels had no units (3.3.2) | **Fixed:** "Minimum RAM (GB)", "Maximum weight (kg)" |
| A4, A5, A7, A8 | Focus-ring contrast on the intent panel (2.94:1); live-region announcement timing and verbosity; errors not linked to their inputs; header inside `<main>` and the disabled-button cursor | Documented as non-blocking future improvements |

**Verified:** full keyboard operation with logical focus order and a visible 3 px focus outline; all controls labeled; `lang="en"` and a sensible heading structure; no horizontal overflow from 320 to 1440 px; readable at 200% zoom and with the WCAG text-spacing override; usable in forced-colors mode. Screen-reader testing (NVDA or Narrator) has not yet been done and is recommended before the demonstration.

## 5. Responsible AI and Reliability Measures

- **AI is optional and has a fallback.** The backend uses Vertex AI only when it is configured. Missing configuration, transport or authentication errors, or malformed or invalid AI output fall back to the deterministic parser.
- **AI output is constrained and validated.** The model must return JSON matching a schema, and the Pydantic intent model validates it before use. The prompt tells the model to extract only stated requirements and not to produce product facts or recommendations.
- **Cross-checking and clarification.** AI output is compared with the deterministic parser. Low confidence (below 0.65) or disagreement on a hard constraint triggers a clarification request. Ambiguous input such as "Windows or Ubuntu" is never turned into a filter.
- **The user stays in control.** Interpreting a request never runs a search. Interpreted values appear in editable fields, and only the visible values are sent to search. A stated OS *preference* becomes a filter only after the user opts in. Searching with an unresolved clarification needs explicit confirmation, and that confirmation resets for each new query (M05–M09).
- **Honest results.** Search applies every hard filter strictly and never silently relaxes one. A no-match search says so plainly (M12). Product cards are labeled as demo data, with availability and the date checked, and images are marked as generic demo illustrations.
- **Transparency.** The UI shows which parser was used (AI or deterministic), whether it agreed with the other parser, the confidence score, and the phrases matched in the query.

## 6. Final Validation Results

| Check | Result |
| ----- | ------ |
| Manual tests M01–M23 | **Passed** (M14, M17 and M18 re-tested after their fixes) |
| Manual test M24 (live Vertex AI) | **Not run**: Vertex AI not configured |
| Backend `pytest` | **86 passed** |
| Frontend ESLint / TypeScript (`tsc --noEmit`) / production build (`next build`) | **Passed / passed / passed** |
| axe-core (WCAG 2.2 AA), after fixes | **0 violations** in all re-tested states |
| Dependency audits | `pip-audit`: no known vulnerabilities; `npm audit --omit=dev`: 0 |

**Remaining work:** run M24 once Vertex AI is configured and approved; do a screen-reader pass; address the deployment items (#1, #4, #5) before any public deployment.
