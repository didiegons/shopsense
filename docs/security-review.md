# Assignment 5.4: Security Review

- **Date:** 2026-10-05
- **Scope:** FastAPI backend (`backend/app`), Next.js frontend (`frontend/app`, `frontend/lib`), dependencies, and local runtime configuration.
- **Environment:** Local development. Backend `127.0.0.1:8000`, frontend `localhost:3000`, deterministic intent parser (Vertex AI not configured).

## Method

1. Code review of the API routes, Pydantic models, search service, intent service, Vertex adapter, CORS configuration, and frontend rendering and API client.
2. Repository scan for secrets, credential files, and `.env` handling.
3. Dependency audit: `npm audit` (frontend) and `pip-audit` (the 41 packages installed in the backend virtual environment, run from an isolated audit environment).
4. Live probes against the running API: unknown fields, non-finite numbers, negative/blank values, HTML in inputs, 100k-deep nested JSON, a 25 MB body, a 5 MB query, prompt-injection text, a non-JSON content type, CORS preflights from allowed and foreign origins, and response headers.

## Fixed in This Review

| # | Severity | Finding | Fix | Verification |
| - | -------- | ------- | --- | ------------ |
| 2 | Low | `{"max_budget": NaN}` returned **HTTP 500**. Validation rejected the value, but FastAPI's default 422 body echoed it back and `NaN` cannot be serialized to JSON. The integer field `min_ram_gb` failed the same way. `Infinity` was accepted as a budget or weight, meaning "no limit". | `allow_inf_nan=False` on `max_budget` and `max_weight_kg` in `app/models/search.py`. A `RequestValidationError` handler in `app/main.py` returns the standard 422 shape without the `input` field. | `NaN`, `Infinity`, and `-Infinity` on all three numeric fields return 422 `finite_number`. Tests: `test_search_rejects_non_finite_numbers_with_clean_validation_error` (9 cases). |
| 3 | Low | 422 responses echoed raw user input: a 5 MB query came back in full. | Same handler as #2. Each error keeps `type`, `loc`, `msg`, and `ctx`, without `input`. | `test_validation_errors_do_not_echo_raw_input` covers an oversized query, an HTML marker in a wrong-typed field, and an unknown field's value. `test_finite_numeric_filters_still_match_after_validation_hardening` confirms valid searches are unchanged. |

**Residual note:** `loc` still names the offending field. For an unknown field, that name is client-supplied. This is kept on purpose, because it is how a client learns which field is invalid. Body size limits (#4) bound it.

Backend test suite after the fix: **86 passed** (75 existing + 11 new).

## Accepted Risks and Deployment / Future-Hardening Items

| # | Severity | Finding | Status and recommended action |
| - | -------- | ------- | ----------------------------- |
| 1 | Medium if deployed; Low locally | `/api/v1/intent` has no authentication or rate limit. With Vertex AI enabled, each request is a billed model call, so anyone who can reach the API can drive up cost. | **Accepted for the local demo** (bound to `127.0.0.1`, Vertex off by default). Before deployment: per-client rate limiting or Cloud Run IAM / API gateway, plus a billing budget alert. |
| 4 | Low | No request body size limit. A 25 MB `category_filters` body was accepted and echoed back in `applied_filters`. | **Deployment item.** Enforce a body limit at the proxy (Cloud Run caps requests at 32 MiB) or in middleware, and cap the number of `category_filters` keys. |
| 5 | Low | `/docs` and `/openapi.json` are publicly reachable. The frontend sends `X-Powered-By: Next.js` and no CSP, `X-Frame-Options`, `X-Content-Type-Options`, or `Referrer-Policy` headers. | **Deployment item.** Set `poweredByHeader: false` and a `headers()` block in `next.config.ts`; turn off the API docs outside development via an environment flag. |
| 6 | Low | `backend/requirements.txt` has no version pins, so builds aren't reproducible and supply-chain risk is higher. | **Future hardening** (dependency management, not an immediate vulnerability). Pin with `pip-compile --generate-hashes` or `pip freeze`. |
| 8 | Info, unverified | The Vertex adapter catches `APIError`, `GoogleAuthError`, `OSError`, and `TimeoutError`. Transport errors raised as `httpx.HTTPError` may not be caught, which would give a 500 instead of the deterministic fallback. | **Future hardening.** Not reproducible while Vertex AI is unconfigured. Verify against a live Vertex configuration, then catch `httpx.HTTPError` if confirmed. |
| 9 | Info | User text is inserted into the Vertex prompt (prompt injection). | **Accepted.** Output is constrained to a JSON schema, validated by Pydantic, compared with the deterministic parser, and shown to the user for confirmation. The model has no tools and cannot search or produce product facts, so an injection can only affect the submitting user's own interpretation. |
| 7 | Info | `npm audit` reports 5 high-severity advisories, all in the dev-only `eslint-config-next` → `@next/eslint-plugin-next` → `fast-glob` → `micromatch` → `braces` chain (GHSA-vfj7-8cjw-p6xm). Production dependencies: 0. | **Accepted.** Lint tooling only, not shipped. Don't run `npm audit fix --force` (breaking change); upgrade `eslint-config-next` when a patched release is available. |

## Controls Verified

- **Secrets:** no secrets or credential files in the repository; `.env*` is gitignored; Vertex AI uses Application Default Credentials, not stored keys.
- **Mass assignment:** every request and response model uses `extra="forbid"`; unknown fields such as `is_admin` return 422.
- **Input validation:** positive numeric bounds, finite numbers only, non-blank OS, intent query limited to 1–1,000 characters on the server, category limited to 80 characters.
- **Parser robustness:** 100k-deep nested JSON returns a clean 400; non-JSON content types return 422, which also blocks simple cross-site form posts.
- **CORS:** only `http://localhost:3000` is allowed, without credentials, for `GET`/`POST` with `Content-Type`; a foreign-origin preflight is refused (400, no `Access-Control-Allow-Origin`).
- **Error disclosure:** unexpected errors return a plain "Internal Server Error" with no traceback or stack details.
- **XSS:** React escapes all rendered text; no `dangerouslySetInnerHTML`, `innerHTML`, `eval`, or `new Function` in the app; HTML submitted as input is returned as inert JSON and not rendered as markup.
- **Images:** product images are local static files; `next/image` has no remote patterns configured.
- **Dependencies:** `pip-audit` found no known vulnerabilities; `npm audit --omit=dev` found 0.
