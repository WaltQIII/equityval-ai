# EquityVal AI — Algorithmic Real Estate Appraisal Bias & Reconsideration of Value (ROV) Auditor

**EquityVal AI** (*Venture 2: Algorithmic Real Estate Appraisal Bias and Reconsideration of Value (ROV) Auditor*) is an enterprise B2B/B2C compliance and valuation audit platform engineered on the **SkySim AI Production Baseline Stack**.

---

## Live Production Deployment (Google Cloud Run `us-east1`)

- **Live Frontend Application:** [https://equityval-ai-frontend-745110910494.us-east1.run.app](https://equityval-ai-frontend-745110910494.us-east1.run.app) *(also [https://equityval-ai-frontend-yh57ey7s7q-ue.a.run.app](https://equityval-ai-frontend-yh57ey7s7q-ue.a.run.app))*
- **Live Backend API:** [https://equityval-ai-backend-745110910494.us-east1.run.app](https://equityval-ai-backend-745110910494.us-east1.run.app) *(also [https://equityval-ai-backend-yh57ey7s7q-ue.a.run.app](https://equityval-ai-backend-yh57ey7s7q-ue.a.run.app))*
- **Live Interactive OpenAPI / Swagger Docs:** [https://equityval-ai-backend-745110910494.us-east1.run.app/docs](https://equityval-ai-backend-745110910494.us-east1.run.app/docs)
- **Live $100 Budget Circuit Breaker Health Check:** [https://equityval-ai-backend-745110910494.us-east1.run.app/api/health](https://equityval-ai-backend-745110910494.us-east1.run.app/api/health)
- **GitHub Repository:** [https://github.com/WaltQIII/equityval-ai](https://github.com/WaltQIII/equityval-ai)

---

It addresses the **$48,000 average home undervaluation disparity** ($156 billion in lost Black homeownership equity nationwide) by combining:
1. **FHFA / HUD / Fair Housing Act Form 1004 NLP Prohibited-Phrase Auditing**: Flags subjective and discriminatory narrative language (*"changing demographic trends"*, *"pride of ownership"*, *"crime"*, *"distressed corridor"*) and generates compliant objective rewrites.
2. **Google Gemini / Vertex AI Multimodal UAD Condition & Quality Scoring (`C1.0–C6.0`, `Q1.0–Q6.0`)**: Audits property inspection imagery against appraiser ratings (e.g., `C3.1` vs downgraded `C4.0`) with a deterministic local fallback so local dev and `pytest` run with zero external API failures.
3. **Spatial Hedonic Regression & Redlining Boundary Comp Auditor**: Detects when an appraiser bypassed closer arms-length comparable sales in favor of distressed/REO properties across historical HOLC D-grade redlining boundaries.
4. **Lender-Ready Reconsideration of Value (ROV) Dossier Compiler**: Exports standardized `.json`, `.md`, and `.csv` ROV appeal packages compliant with FHFA, Fannie Mae, Freddie Mac, HUD, and FHA Interagency ROV guidance, gated by a mandatory **Interagency ROV & USPAP Regulatory Compliance Attestation Shield**.

---

## Architecture & SkySim AI Production Baseline Stack

- **`frontend/`**: Next.js 14 (App Router), React 18, TypeScript, Tailwind CSS (mobile-responsive dark UI with Welcome Sign-Up/Log-In Gate, Guest Demo mode, plain-English Tester Guide modal, and interactive Geospatial Redlining SVG Map).
- **`backend/`**: Python 3.12, FastAPI, Uvicorn, Pydantic v2, SciPy, NumPy.
- **AI & Data Layer**:
  - Google Gemini / Vertex AI connector with deterministic local fallback (`backend/app/services/vision_auditor.py`).
  - Google Cloud Firestore (`google-cloud-firestore`) with automatic in-memory fallback (`backend/app/services/store.py`).
  - Google Cloud Storage (`google-cloud-storage`) with V4 Signed `PUT` URLs and a 14-day auto-deletion lifecycle rule (`backend/app/api/uploads.py`).
- **Auth & Monetization**:
  - Firestore-backed Sign-Up / Sign-In (`/api/auth/register`, `/api/auth/login`) with PBKDF2-HMAC-SHA256 password hashing and signed bearer tokens (`backend/app/api/auth.py`).
  - Stripe Checkout + Signed Webhooks (`Stripe-Signature` HMAC-SHA256) + Stripe Tax (`txcd_10103001`, Florida DOR Rule 12A-1.032 B2B SaaS tax-exempt logic) (`backend/app/services/billing.py`).
- **Cloud Deployment & FinOps Guardrails**:
  - Production `Dockerfile`, `frontend/Dockerfile`, and `cloudbuild.yaml`.
  - Deployed to Google Cloud Run (`us-east1`) with `--max-instances=3` and a fail-closed $100/month budget circuit breaker (`/api/health`).
