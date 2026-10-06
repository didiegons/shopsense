# ShopSense AI: Part 2 Technical Plan

## Product Goal and Design Principle

ShopSense AI helps shoppers turn an everyday request into a shortlist they can trust. For example, "a lightweight laptop under $1,000 for cybersecurity school that can handle virtual machines" should become explicit constraints and preferences, then a set of products whose factual attributes can be checked.

The central design rule is: **the catalog is the source of product facts; AI is an assistant for understanding and explaining those facts.** Price, specifications, ratings, availability, and retailer links must be retrieved from structured records with source and freshness metadata. The model must not invent or silently fill missing values. This separation makes the experience more useful and gives the team a testable boundary for accuracy.

## 1. Full-Stack Architecture

### Request and data flow

1. A shopper enters a natural-language request in the Next.js web app.
2. The app sends it to a FastAPI endpoint. The backend validates the request and asks a Gemini model to convert it into a typed intent object, such as budget, weight preference, intended workloads, and required memory. The model may return a clarification question when a critical requirement is ambiguous.
3. The backend validates the parsed intent against a schema and normalizes values. Hard requirements, such as maximum budget or a minimum amount of memory, remain explicit filters rather than being left to a model score.
4. PostgreSQL applies hard filters and uses pgvector similarity to find semantically relevant candidates. The backend reranks that smaller candidate set using transparent criteria, such as constraint satisfaction, semantic relevance, and data completeness.
5. The API returns structured product records and evidence to the frontend. Only then may the AI generate a short fit explanation, comparison narrative, or review summary grounded in those records.
6. Public comparison routes render on the server using the same structured data and can be crawled without a client-side search session.

### Components

- **Frontend:** Next.js with the App Router, TypeScript, and server-rendered public product and comparison routes. Interactive search and comparison controls use client components only where interaction requires them.
- **Backend:** Python FastAPI service owns intent parsing, catalog search, ranking, comparison, review summarization, and retailer integrations. It exposes versioned JSON endpoints and an OpenAPI contract.
- **Database:** Cloud SQL for PostgreSQL stores normalized catalog records, offers, provenance, saved comparisons, and user preferences. The pgvector extension stores product-description embeddings next to their product identifiers.
- **AI integration:** A small backend AI adapter calls Gemini through Vertex AI. It handles structured intent extraction and evidence-constrained explanations; a separate embedding adapter creates or refreshes vectors. Provider calls stay behind backend interfaces so a model can be changed without changing frontend contracts.
- **Product data:** A catalog-import adapter normalizes the MVP seed file or later retailer feeds into one internal schema. Retailer-specific fields do not leak into the UI contract.
- **Object storage:** Google Cloud Storage holds versioned import files and, if licensing permits, app-owned assets. Retailer image URLs can be stored as references when allowed; do not copy or proxy retailer images without checking their terms.
- **Hosting and delivery:** Two Cloud Run services (Next.js web and FastAPI API) are built as containers, stored in Artifact Registry, and deployed by Cloud Build or GitHub Actions. Cloud SQL, Secret Manager, and Cloud Logging/Monitoring complete the initial Google Cloud setup.

### Initial API surface

- `POST /api/v1/search` accepts a query and optional session context; returns parsed requirements, results, evidence, and any clarification question.
- `GET /api/v1/products/{product_id}` returns the current normalized product and offer data.
- `POST /api/v1/comparisons` accepts product IDs and returns a factual comparison plus grounded narrative fields.
- `GET /api/v1/comparisons/{slug}` serves data for a public, stable comparison page.
- `POST /api/v1/reviews/summarize` summarizes only available review text or trusted review aggregates, with sample size and date range.

The browser should never call model APIs directly. Enforce request size limits, timeouts, rate limits, and input validation at the API boundary.

## 2. Recommended Technology Stack

| Area                            | Recommendation                                              | Why it fits                                                                                                                                                                                                                                                                                                |
| ------------------------------- | ----------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Frontend                        | Next.js App Router + TypeScript                             | Supports interactive search and server-rendered, linkable comparison pages in one web application. TypeScript helps keep API responses aligned with UI types.                                                                                                                                              |
| Backend                         | Python + FastAPI + Pydantic                                 | A clear service boundary, automatic OpenAPI documentation, typed input/output validation, and a mature ecosystem for AI and data ingestion.                                                                                                                                                                |
| Relational data                 | Cloud SQL for PostgreSQL                                    | Product specifications, offers, retailers, provenance, and user-owned comparisons are relational and benefit from transactions and constraints. It is managed and integrates with Cloud Run.                                                                                                               |
| Vector search                   | pgvector in PostgreSQL                                      | Keeps a workshop-sized catalog and semantic vectors together, avoids operating a separate vector service, and can combine vector similarity with SQL filters. Reassess only when measured query volume or corpus size justifies it.                                                                        |
| Intent, explanations, summaries | Gemini Flash through Vertex AI                              | A low-latency model class is appropriate for short structured tasks. Vertex AI fits the Google Cloud deployment and can use the Cloud Run service identity rather than a long-lived API key. Keep the model ID configurable and verify the selected model and region are supported at implementation time. |
| Embeddings                      | Vertex AI text embeddings, generated in a backend batch job | Produces vectors for product descriptions and queries. Store the model/version with each vector and re-embed when the model or source text changes. Verify current model availability and vector dimensions before creating the database index.                                                            |
| Authentication                  | Firebase Authentication, optional for MVP                   | Provides a straightforward Google/email sign-in path for saved preferences and comparisons. Anonymous search and public pages should work without an account. Do not build an account system until a user-specific feature needs it.                                                                       |
| File storage                    | Google Cloud Storage                                        | Durable storage for import snapshots, exports, and permitted app-owned media; it is not the system of record for product facts.                                                                                                                                                                            |
| Hosting                         | Google Cloud Run + Artifact Registry                        | Runs the web and API containers with managed HTTPS, revision-based rollouts, and scale-to-zero behavior that suits a class MVP. Cloud SQL is the persistent database, not local container storage.                                                                                                         |
| CI/CD and observability         | Cloud Build or GitHub Actions; Cloud Logging and Monitoring | Automates repeatable container builds and deployments and gives a small team visible build, request, and error history.                                                                                                                                                                                    |

For an MVP, avoid adding a dedicated search cluster, message broker, or microservices for every feature. PostgreSQL, two services, and a small background import/embedding job are enough to learn whether shoppers value the workflow.

## 3. Key Features and Business Value

### Conversational product search

Translate a shopper's words into visible, editable requirements. For the example request, the system might infer a budget ceiling, low weight preference, school use, and a need for sufficient RAM/storage and CPU capacity for virtual machines. Distinguish hard constraints from preferences, show the interpretation to the user, and ask a follow-up if the query cannot be resolved safely. This reduces the gap between how people describe a need and how catalogs are organized.

### Semantic search

Embed normalized product descriptions and the query, retrieve similar candidates with pgvector, then apply structured constraints in SQL. Semantic retrieval helps match concepts such as "run several virtual machines" to relevant CPU and memory attributes even when the product text uses different wording. It must not override a hard budget or invent a missing specification. Return a useful empty state rather than relaxing constraints silently.

### Side-by-side comparison

Let shoppers select a small number of products and compare normalized price, weight, processor, memory, storage, display, rating, availability, and source freshness in consistent units. Highlight missing values instead of implying equivalence. This makes tradeoffs visible and helps a shopper choose based on their actual workload rather than marketing descriptions.

### Personalized recommendations

For the MVP, personalize only from explicit, optional preferences (budget range, portability, operating-system preference, and saved comparison history). Let users inspect, edit, and clear those preferences. Explain which preferences affected ranking. Do not infer sensitive traits, require an account, or claim that recommendations are objective. This supports repeat use without creating a large personalization or privacy project.

### Review summarization

Summarize only review text or aggregates obtained through a permitted source. Show sample count, source, and date range; separate recurring positives from recurring complaints; and preserve uncertainty when the sample is small or biased. Never generate a rating or quote and present it as real customer feedback. Summaries reduce reading time while leaving access to the original review source where permitted.

### Public SEO/AEO/GEO comparison pages

Give a saved comparison a stable, descriptive URL and render its meaningful content on the server. Include a concise factual title and summary, a crawlable comparison table, canonical URL, sitemap entry, Open Graph metadata, and appropriate structured data (for example, `Product` or `ItemList` only when its fields are accurate and eligible). Include source links and an "as of" timestamp. Do not publish thin pages for every query combination; index only curated or user-published comparisons with durable value, and use `noindex` for private or low-quality pages. These practices make pages understandable to search engines and answer engines, but cannot guarantee indexing, ranking, or citation by AI search products.

## 4. Real Product Data Strategy

### Class-project MVP

Use a small, clearly labeled seed catalog (for example, 30-100 laptop records) in CSV/JSON, loaded by a repeatable import script. Include product name, manufacturer, category, normalized specifications, current price if verified, availability, image/source URL, retailer, `source_checked_at`, and whether the record is demo or live data. A practical first version can use manually verified records from manufacturer or retailer pages for a limited comparison set, with links back to those sources. Keep demo prices and availability obviously labeled and do not represent them as live offers.

A public dataset can help exercise the import and search pipeline, but check its license, attribution rules, field definitions, age, and redistribution terms before using it. Many product/review datasets are historical research snapshots, not current inventory. Do not treat a dataset rating or review as current retailer data. For a class demo, an openly licensed or instructor-provided dataset is safer than scraping live retail pages.

### Later live-data options

- **eBay Browse API:** A realistic first retailer integration to investigate for searchable listings and item details. Review current developer access, affiliate requirements, returned-field coverage, refresh limits, and display rules before committing to it.
- **Amazon Product Advertising API (or its current successor):** Can provide product/offer data for approved affiliates, but access eligibility, attribution, caching, refresh, and display requirements are constraints, not implementation details to bypass.
- **Affiliate networks and retailer feeds:** Providers such as Impact, Awin, and CJ may offer merchant-specific catalogs after approval. Each feed needs its own adapter and terms review.
- **Merchant catalog APIs:** Google Merchant APIs are primarily for a merchant's own catalog and are not a general product-search API for arbitrary retailers.

Do not scrape retailer sites unless their terms and robots policies explicitly permit the intended use. Before a production integration, check licensing, affiliate disclosures, price freshness obligations, image rights, geographic availability, and whether reviews may be stored or summarized.

### Production ingestion boundary

Define a normalized internal `Product`, `Offer`, `Specification`, `ReviewAggregate`, and `DataSource` model. Preserve source product IDs and source URLs. Each offer should include currency, price, availability, checked-at time, and source. A retailer adapter maps its feed to this schema; a scheduled job refreshes data within the provider's allowed interval and records failures. Expired or unavailable offers should be marked stale, not quietly shown as current. Keep demo and production catalogs distinguishable in both data and UI.

## 5. Using AI Coding Agents

Claude Code, Cursor, or GitHub Copilot can accelerate implementation, but they should work from the architecture, data contracts, and acceptance tests rather than inventing those decisions. Keep secrets out of prompts and local agent context. Review generated code, run tests, inspect dependency changes, and have the agent explain any security-sensitive edits. Give agents one bounded task at a time and ask them not to alter unrelated files.

Example prompts:

- "Implement Pydantic request and response models for `POST /api/v1/search` from this contract. Add validation tests for budget, missing fields, and malformed model output. Do not call an LLM in these tests."
- "Build a catalog importer for this documented CSV format. Normalize units, preserve source URL and checked-at time, reject invalid prices, and make repeated imports idempotent. Add tests for duplicate IDs and missing specifications."
- "Implement product candidate retrieval using SQL hard filters followed by pgvector similarity. Hard filters must never be relaxed. Return the reason a candidate matched and which requirements are missing."
- "Create a server-rendered comparison page from this API response. Include canonical metadata, a factual comparison table, source and freshness labels, and responsive keyboard-accessible controls. Do not add facts that are absent from the API."
- "Review this AI explanation endpoint for prompt injection through product descriptions and reviews, unsupported factual claims, excessive logging of personal data, and missing timeouts. Report findings before proposing code changes."

The developer remains responsible for product-source permissions, model behavior, architecture decisions, and the final deployed behavior.

## 6. Google Cloud Run Deployment Flow

1. **Repository and build:** Keep `frontend/` and `backend/` as separate container build contexts with pinned dependencies and health endpoints. On a merge to the main branch, Cloud Build or GitHub Actions runs lint, unit tests, contract tests, and image builds, then pushes versioned images to Artifact Registry.
2. **Database:** Provision Cloud SQL for PostgreSQL in the chosen region, enable pgvector, create a least-privilege application database user, and apply schema migrations as a controlled release step or one-off Cloud Run Job. Do not run migrations automatically in every web/API instance startup. Use the Cloud SQL connector or supported private connectivity; do not expose the database publicly. Use TLS and least-privilege IAM.
3. **Secrets and identity:** Put database credentials or other unavoidable secrets in Secret Manager. Grant each Cloud Run service account access only to the secrets and resources it needs. Prefer service identity for Vertex AI access where supported instead of storing model API keys. Never commit `.env` files or bake secrets into images.
4. **Configuration:** Pass non-secret configuration as Cloud Run environment variables, such as `DATABASE_NAME`, `DATABASE_HOST` or connector settings, `VERTEX_AI_PROJECT`, `VERTEX_AI_REGION`, `MODEL_ID`, `FRONTEND_ORIGIN`, and `APP_ENV`. Inject secrets from Secret Manager as environment variables or mounted files. Validate required configuration at startup without printing secret values.
5. **Deploy services:** Deploy the FastAPI API and Next.js web application as separate Cloud Run services. Configure the web service to call the API using an authenticated internal service URL where the architecture permits; otherwise protect the API with authentication, authorization, and strict CORS rather than relying on CORS as access control. Give the API's service account Cloud SQL and Vertex AI permissions.
6. **Revisions and rollout:** Every deployment creates an immutable revision. Start with a small percentage or a staging revision, run smoke checks for search, product detail, and a public comparison page, then shift traffic to the new revision. Keep the prior revision available for quick rollback. Database changes must be backward-compatible during a rolling deployment (expand, deploy, migrate/dual-read as needed, then contract later).
7. **Scaling and operations:** Allow scale-to-zero for the class MVP, set a sensible maximum instance count, and tune concurrency and CPU/memory after measuring. Set connection-pool size and Cloud Run maximum instances so combined database connections stay below Cloud SQL limits. Consider a minimum instance only if cold-start latency is a demonstrated problem. Add request timeouts, structured logs, error-rate/latency dashboards, and alerts for failed imports or database saturation. Cloud Run's local filesystem is ephemeral; persist data in Cloud SQL or Cloud Storage.

A typical flow is: commit -> checks -> build images -> push to Artifact Registry -> deploy revision -> smoke test -> shift traffic. Keep dev/staging and production configuration separate even if the workshop initially uses only one environment.

## 7. What I Will Do Differently from App #1, ForensAI

- **Plan architecture before coding:** Sketch the user request flow, service boundaries, data lifecycle, and deployment diagram first. This reduces mid-project rewrites and clarifies which component owns each decision.
- **Define data contracts earlier:** Agree on product, offer, source, search request, and search response schemas before implementing screens and AI prompts. Generate or verify frontend types from OpenAPI so both sides do not drift.
- **Design testing and responsible-AI controls earlier:** Test intent parsing separately from retrieval and explanation. Use fixture catalogs and deterministic tests; assert that hard constraints are honored and generated explanations only cite returned fields. Add clear source/freshness labels, privacy limits, prompt-injection handling, and review-data provenance before demo day.
- **Think about scale before large-data problems appear:** Measure catalog size, vector-search latency, query cost, and database connections. Start with PostgreSQL and pgvector, add indexes and caching based on measurements, and postpone a separate vector database or search cluster until evidence justifies the operational cost.
- **Separate factual retrieval from generative explanations:** The database/API returns product facts and candidates. AI translates intent and explains evidence; it does not create price, specifications, ratings, or availability. This makes errors easier to detect and explanations easier to audit.

These are process improvements for this project, not claims about implementation details of ForensAI beyond the comparison provided in the assignment context.

## 8. MVP Scope and Workshop Plan

### Build for the class MVP

- A responsive product-search page with natural-language input and visible, editable parsed requirements.
- A small verified or explicitly demo-labeled laptop catalog with provenance and freshness fields.
- Structured filters for budget and a few high-value specifications, plus pgvector semantic retrieval over product descriptions.
- A ranked results list showing factual attributes, source, and why a result matched or missed a requirement.
- Comparison of two or three products using a shared specification table.
- A constrained AI fit explanation and a review-summary demonstration only where permitted review data exists; provide a truthful unavailable state otherwise.
- One or a few public, server-rendered comparison pages with stable URLs, metadata, source links, and freshness timestamps.
- Automated tests for schemas, catalog import, hard-filter behavior, API contracts, explanation grounding, and one browser workflow.
- A working Cloud Run deployment with Secret Manager and Cloud SQL connectivity.

### Postpone

- Broad multi-retailer live price aggregation and real-time inventory guarantees.
- A production affiliate program, checkout, or order processing.
- Accounts, complex preference profiles, and collaborative/social sharing beyond a basic optional saved comparison.
- Large-scale review ingestion, sentiment analytics, and unrestricted review crawling.
- A standalone vector database, Elasticsearch/OpenSearch, streaming pipeline, or extensive microservice split.
- Automatic publication and indexing of every generated comparison, extensive A/B testing, and claims that a page will appear in AI answers.
- Fine-tuning, autonomous shopping agents, or model-generated product facts.

A practical build sequence is: (1) catalog schema and seeded data, (2) deterministic browse/filter API and UI, (3) intent extraction and semantic retrieval, (4) comparisons and grounded explanations, (5) public rendered pages and SEO metadata, (6) focused tests and Cloud Run deployment. At each stage, keep a working end-to-end path so the project remains demonstrable if later AI or deployment work runs short.

## Success Criteria and Risks

The MVP is successful when a shopper can enter a natural-language need, see an editable interpretation, receive products that meet hard constraints, inspect the evidence behind each result, compare options, and share a crawlable public comparison page. Measure retrieval quality with a small hand-labeled set of queries and expected candidates rather than relying only on a convincing demo.

The main risks are stale or impermissibly sourced catalog data, AI explanations that overstate evidence, embedding/model changes, and Cloud SQL connection exhaustion during scaling. Mitigate them with provenance and freshness fields, strict structured outputs and grounding checks, versioned embeddings, and coordinated limits on Cloud Run instances and database pools. Search-engine and AI-answer visibility remain outcomes to monitor, not promises the architecture can make.
