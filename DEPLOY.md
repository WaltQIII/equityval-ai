# EquityVal AI — Cloud Run Deployment & FinOps Guardrail Guide (`DEPLOY.md`)

This guide documents the production deployment of **EquityVal AI** onto Google Cloud Run (`us-east1`) with `--max-instances=3`, a fail-closed **$100/month** budget circuit breaker (`/api/health`), and a **14-day GCS auto-deletion lifecycle rule**.

---

## 1. GCS Direct Upload Bucket & 14-Day Auto-Deletion Lifecycle Rule

```bash
export PROJECT_ID="project-01-lab-setup"
export GCS_BUCKET="equityval-ai-raw-uploads"

# Create bucket in us-east1
gcloud storage buckets create "gs://${GCS_BUCKET}" \
  --project="${PROJECT_ID}" \
  --location="us-east1" \
  --uniform-bucket-level-access

# Apply 14-day auto-deletion lifecycle rule
cat << 'EOF' > lifecycle.json
{
  "lifecycle": {
    "rule": [
      {
        "action": {"type": "Delete"},
        "condition": {"age": 14, "matchesPrefix": ["audits/"]}
      }
    ]
  }
}
EOF
gcloud storage buckets update "gs://${GCS_BUCKET}" --lifecycle-file=lifecycle.json
```

---

## 2. Cloud Run Backend & Frontend Deployment (`us-east1`, `--max-instances=3`)

```bash
# Deploy Backend API
gcloud run deploy equityval-ai-backend \
  --source . \
  --region us-east1 \
  --platform managed \
  --allow-unauthenticated \
  --max-instances=3 \
  --min-instances=0 \
  --memory=1Gi \
  --set-env-vars="GCP_MONTHLY_BUDGET_USD=100.0,CLOUD_RUN_MAX_INSTANCES=3,GCS_UPLOAD_BUCKET=equityval-ai-raw-uploads"

# Deploy Next.js 14 Frontend
cd frontend
gcloud run deploy equityval-ai-frontend \
  --source . \
  --region us-east1 \
  --platform managed \
  --allow-unauthenticated \
  --max-instances=3 \
  --min-instances=0 \
  --memory=1Gi
```
