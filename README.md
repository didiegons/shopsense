# ShopSense AI

ShopSense AI helps shoppers discover, compare, and understand products through natural-language search, structured product data, and evidence-grounded AI explanations.

## Repository Layout

- `frontend/`: Next.js + TypeScript web app (port 3000 locally)
- `backend/`: FastAPI + Pydantic API (port 8000 locally); see [backend/README.md](backend/README.md)
- `docs/`: technical plan, testing, security, accessibility, and deployment documentation

## Local Development

```powershell
# Backend (from backend/)
python -m pip install -r requirements-dev.txt
python -m uvicorn app.main:app --reload

# Frontend (from frontend/)
npm install
npm run dev
```

Open `http://localhost:3000`. The frontend calls `http://localhost:8000` unless `NEXT_PUBLIC_API_URL` is set.

## Checks

```powershell
cd backend; python -m pytest
cd frontend; npx eslint; npx tsc --noEmit; npm run build
```

## Deployment

Both services deploy to Google Cloud Run as separate containers. See [docs/deployment.md](docs/deployment.md).

## Technical Plan

The Part 2 architecture, technology choices, product-data strategy, AI-agent workflow, Cloud Run deployment plan, and class-project MVP scope are documented in [Part 2 Technical Plan](docs/part-2-technical-plan.md).
