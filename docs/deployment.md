# ShopSense Deployment: Google Cloud Run

ShopSense deploys as two Cloud Run services in the existing `forensai` Google Cloud project (project number `425356381200`, region `us-central1`), alongside the existing `forensai` service. That service is not modified. The assignment mentions AWS App Runner; this project uses Google Cloud Run instead, consistent with the ForensAI deployment.

## Architecture

```
Browser ──HTTPS──> shopsense-web   Next.js standalone server, public
   └─────HTTPS──> shopsense-api   FastAPI, public, CORS limited to the web origin
                     ├─ demo catalog (catalog.json) baked into the image
                     └─ optional: Vertex AI via the service account identity (no API keys)
```

The browser calls the API directly, so both services allow unauthenticated access. CORS restricts which websites can call the API from a browser; it is not access control. The API serves demo data only and holds no secrets.

## Resources

All new resources use the `shopsense` prefix.

| Resource | Name | Configuration |
| -------- | ---- | ------------- |
| Cloud Run service | `shopsense-api` | 1 vCPU, 256 MiB, min 0 / max 1 instance, request-based CPU, 30 s timeout |
| Cloud Run service | `shopsense-web` | 1 vCPU, 512 MiB, min 0 / max 1 instance, request-based CPU |
| Service account | `shopsense-api@forensai.iam.gserviceaccount.com` | No roles; add `roles/aiplatform.user` only when enabling Vertex AI |
| Service account | `shopsense-web@forensai.iam.gserviceaccount.com` | No roles |
| Artifact Registry | `shopsense` (Docker, `us-central1`) | Cleanup policy keeps the 10 most recent versions per package. Each Cloud Build push stores the image plus 2 provenance attestations, so this retains about the last 3 builds for rollback. |
| Budget | `shopsense-monthly-5usd` | $5/month alert at 50%, 90%, and 100% for the `forensai` project. An alert only, not a spending cap; it also covers ForensAI because both apps share the project. |

## Configuration

| Service | Variable | Value | Applied |
| ------- | -------- | ----- | ------- |
| shopsense-api | `APP_ENV` | `production` (disables `/docs`, `/redoc`, `/openapi.json`) | Runtime |
| shopsense-api | `CORS_ALLOW_ORIGINS` | Deployed web origins (deterministic and hash-style URLs) | Runtime (no rebuild) |
| shopsense-api | `VERTEX_AI_PROJECT`, `VERTEX_AI_REGION`, `SHOPSENSE_INTENT_MODEL` | Unset at first launch (deterministic parser) | Runtime |
| shopsense-web | `NEXT_PUBLIC_API_URL` | `https://shopsense-api-425356381200.us-central1.run.app` | **Build time**: changing it requires rebuilding the web image |

No secrets are required. Production CORS lists only the deployed web origins. Local development keeps its own default (`http://localhost:3000` calling the local API).

## First Deployment (PowerShell)

```powershell
$P = "forensai"; $R = "us-central1"; $AR = "$R-docker.pkg.dev/$P/shopsense"
$API_URL = "https://shopsense-api-425356381200.$R.run.app"
$WEB_URL = "https://shopsense-web-425356381200.$R.run.app"
$TAG = git rev-parse --short HEAD
```

1. **One-time setup**

   ```powershell
   gcloud services enable billingbudgets.googleapis.com --project $P
   gcloud iam service-accounts create shopsense-api --display-name "ShopSense API (Cloud Run)" --project $P
   gcloud iam service-accounts create shopsense-web --display-name "ShopSense web (Cloud Run)" --project $P
   gcloud artifacts repositories create shopsense --repository-format docker --location $R --description "ShopSense images" --project $P
   gcloud artifacts repositories set-cleanup-policies shopsense --location $R --project $P --policy docs/artifact-cleanup-policy.json
   gcloud billing budgets create --billing-account 01FBD8-082380-A34A2B --display-name shopsense-monthly-5usd --budget-amount 5USD --filter-projects projects/$P --threshold-rule percent=0.5 --threshold-rule percent=0.9 --threshold-rule percent=1.0
   ```

2. **Backend:** build, deploy, then smoke test before continuing.

   ```powershell
   gcloud builds submit backend --tag "$AR/shopsense-api:$TAG" --project $P
   gcloud run deploy shopsense-api --image "$AR/shopsense-api:$TAG" --region $R --project $P `
     --service-account "shopsense-api@$P.iam.gserviceaccount.com" --allow-unauthenticated `
     --cpu 1 --memory 256Mi --min-instances 0 --max-instances 1 --cpu-throttling --timeout 30 `
     --set-env-vars "^@^APP_ENV=production@CORS_ALLOW_ORIGINS=$WEB_URL"
   ```

3. **Frontend:** only after the API smoke tests pass.

   ```powershell
   gcloud builds submit frontend --config frontend/cloudbuild.yaml --substitutions "_API_URL=$API_URL,_TAG=$TAG" --project $P
   gcloud run deploy shopsense-web --image "$AR/shopsense-web:$TAG" --region $R --project $P `
     --service-account "shopsense-web@$P.iam.gserviceaccount.com" --allow-unauthenticated `
     --cpu 1 --memory 512Mi --min-instances 0 --max-instances 1 --cpu-throttling
   ```

4. **CORS for the hash-style web URL:** Cloud Run also serves each service at a `https://<service>-<hash>-uc.a.run.app` URL. Add it so both public URLs work.

   ```powershell
   $WEB_ALT = gcloud run services describe shopsense-web --region $R --project $P --format "value(status.url)"
   gcloud run services update shopsense-api --region $R --project $P --update-env-vars "^@^CORS_ALLOW_ORIGINS=$WEB_URL,$WEB_ALT"
   ```

## Smoke Tests

```powershell
curl.exe -s "$API_URL/health"                                                    # {"status":"ok"}
curl.exe -s -X POST "$API_URL/api/v1/search" -H "Content-Type: application/json" -d '{}'     # 16 results
curl.exe -s -o NUL -w "%{http_code}" "$API_URL/docs"                             # 404 in production
curl.exe -s -i -X OPTIONS "$API_URL/api/v1/search" -H "Origin: $WEB_URL" -H "Access-Control-Request-Method: POST"   # allow-origin = WEB_URL
curl.exe -s -I "$WEB_URL"                                                        # 200 + security headers
gcloud run services describe forensai --region $R --project $P --format "value(status.latestReadyRevisionName)"   # unchanged
```

Then run the browser regression (M01–M23) against `$WEB_URL`.

## Redeploying

- **Backend change:** commit, set `$TAG`, then repeat step 2. Env vars persist; omit `--set-env-vars` to keep the current values.
- **Frontend change:** commit, set `$TAG`, then repeat step 3.
- **API URL change:** rebuild the frontend with the new `_API_URL`.
- **Rollback:** `gcloud run revisions list --service <svc> --region $R` and then `gcloud run services update-traffic <svc> --to-revisions <revision>=100 --region $R`.

## Enabling Vertex AI Later (separate, approved step)

```powershell
gcloud projects add-iam-policy-binding $P --member "serviceAccount:shopsense-api@$P.iam.gserviceaccount.com" --role roles/aiplatform.user
gcloud run services update shopsense-api --region $R --project $P --update-env-vars "VERTEX_AI_PROJECT=$P,VERTEX_AI_REGION=$R,SHOPSENSE_INTENT_MODEL=<confirmed Gemini model ID>"
```

Then run M24. The intent endpoint has no rate limit (security finding #1), so keep `--max-instances 1` and the budget alert in place.

## Teardown

```powershell
gcloud run services delete shopsense-web --region $R --project $P
gcloud run services delete shopsense-api --region $R --project $P
gcloud artifacts repositories delete shopsense --location $R --project $P
gcloud iam service-accounts delete "shopsense-web@$P.iam.gserviceaccount.com" --project $P
gcloud iam service-accounts delete "shopsense-api@$P.iam.gserviceaccount.com" --project $P
```
