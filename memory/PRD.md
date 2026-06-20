# DataMind - Product Requirements Document

## Original Problem Statement
Build a web app called "DataMind" — an AI-powered analytics assistant for small business teams who don't have a data analyst. The goal: a non-technical person uploads their business data and instantly gets plain-English insights, trend detection, and automatic anomaly alerts.

## Target User Persona
Small business owners and team members without data analysis skills who need quick insights from business metrics (revenue, orders, CAC, churn, etc.)

## Architecture
- **Frontend**: React 19 + React Router + Recharts (sparklines) + jsPDF (export) + TailwindCSS
- **Backend**: FastAPI + Motor (async MongoDB) + pandas/scipy (data processing) + emergentintegrations (Claude Sonnet 4.6)
- **Database**: MongoDB
- **AI**: Claude Sonnet 4.6 via Emergent LLM Key (streaming SSE)
- **Auth**: JWT-based with bcrypt

## Core Features Implemented (Feb 20, 2026)
- ✅ User authentication (signup/login with JWT)
- ✅ CSV upload with drag-drop zone
- ✅ Automatic data cleaning (empty rows, trim spaces, $/comma stripping, duplicate detection)
- ✅ Data Quality Score (0-100) with green/amber/red issue list
- ✅ Auto-detection of numeric vs label columns
- ✅ Anomaly detection using z-score (>= 1.8 = anomaly, >= 2.2 = Critical)
- ✅ Dashboard with KPI cards (latest value, MoM %, anomaly indicators)
- ✅ Metric cards with sparkline charts and trend arrows
- ✅ Anomaly Feed sorted by severity (Critical/Warning labels)
- ✅ Sample data button (12-month business data with December anomalies)
- ✅ AI Chat tab with 4 suggested questions and streaming Claude responses
- ✅ AI Metric Deep-dive (click any metric card for focused analysis)
- ✅ Data tab with raw data table (numeric columns in monospace)
- ✅ PDF Export with metrics, anomalies, and report
- ✅ Per-user data isolation (datasets private to each user)
- ✅ Dark "command center" UI (#0a0a12 navy, #6366f1 indigo, Inter font)

## Verified Working
- Critical anomaly detection: December CAC=178 (z=2.49) and churn=7.2 (z=2.45) correctly flagged
- All 14 backend tests passed (auth, CSV, anomaly, AI chat streaming)
- Frontend E2E flow: signup → empty state → sample data → quality report → dashboard → chat → data table

## Backlog (P1/P2)
- P1: Save multiple datasets per user with sidebar selector to switch between them ✅ (Feb 20, 2026)
- P1: CSV pagination for large files (50K+ rows) ✅ (Feb 20, 2026)
- P2: Dataset rename, delete from UI ✅ (Feb 20, 2026)
- P2: Chat history persistence across sessions ✅ (Feb 20, 2026)
- P2: One-click duplicate removal button ✅ (Feb 20, 2026)
- P2: Date format detection and flagging (pending)

## Iteration 2 (Feb 20, 2026)
- ✅ DatasetSelector dropdown in header with inline rename/delete
- ✅ DataTable pagination (50 rows/page) with Prev/Next + page input
- ✅ AIChat history persisted in MongoDB (`chat_messages` collection)
- ✅ One-click "Remove Duplicates" button in Data Quality report
- ✅ Backend endpoints: PATCH /datasets/{id}/rename, POST /datasets/remove-duplicates, GET/POST/DELETE /chat/history/{dataset_id}, POST /chat/save
- ✅ 25/25 backend tests passing

## Key Files
- Backend: `/app/backend/server.py` (single file with all routes)
- Frontend pages: `/app/frontend/src/pages/{Auth,Dashboard}.js`
- Frontend components: `/app/frontend/src/components/{AIChat,DataQuality,DataTable,MetricDetail,UploadCSV}.js`
- Auth: `/app/frontend/src/contexts/AuthContext.js`

## Credentials
See `/app/memory/test_credentials.md`
