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

## Iteration 5 (Feb 20, 2026) — Architectural pivot: server-side temp caching

### THIRD ATTEMPT at fixing the recurring "Proceed-to-Dashboard not working" P0
Previous chunked-storage fix solved the Mongo 16MB doc limit but the **browser** still couldn't handle the 50MB JSON round-trip required to save a 19k-row dataset. User reported it still broken.

**Root cause (real one this time):** Save endpoint required the frontend to round-trip the full cleaned_data + original_data — for the user's CSV that meant 50MB body up + 50MB body back from upload + 50MB body up to save. Browsers reliably hit memory or network thresholds on this.

**Fix — server-side draft caching:**
- `/datasets/upload` now caches cleaned data as 'draft' chunks in `dataset_rows` collection (TTL 1h via Mongo index `(created_at, 1)` + `partialFilterExpression {status: 'draft'}`)
- Upload response is now metadata-only: `upload_id`, `score`, `issues`, column lists, `total_rows`, `preview_data` (50 rows). **60KB instead of 50MB.**
- `/datasets/save` accepts just `upload_id` + name + column configs → looks up cached chunks → flips status draft→committed via `$unset` (no copy, dataset.id reuses upload_id)
- `/datasets/remove-duplicates` operates on the cached data by upload_id; updates chunks in place
- Sample data flow now also goes through `/upload` for unified code path
- NaN/Infinity values sanitized to None for JSON-safe responses
- Idempotency: second save with same upload_id returns 409

**Verified end-to-end with user's actual 11MB / 19,418-row CSAT CSV:**
- Upload: 60,115 bytes response (was ~50MB)
- Save body: 781 bytes (was ~50MB)
- Save time: 0.3s (was 4s+)
- Dashboard renders 8 KPI cards, 1396 anomalies, sparklines

50/50 backend tests passing, browser E2E verified.
- ✅ **ROOT CAUSE**: User's real CSV (19,418 rows × 41 cols) produced a 57MB Mongo doc — exceeded BSON 16MB limit → save 500 silently → Proceed-to-Dashboard never advanced.
- ✅ **FIX**: Chunked storage. `dataset_rows` collection stores 5,000-row chunks. `datasets` metadata now holds only a 50-row preview + total_rows count.
- ✅ New endpoint `GET /api/datasets/{id}/rows?skip=&limit=` for on-demand paginated row access (caps at 500/req).
- ✅ Hard cap at 50,000 rows on upload (returns 413 with friendly message, matches user-facing UI tip).
- ✅ DataTable on FE fetches rows on-demand when the requested page isn't in the embedded preview; falls back to dataset.data for backward compat with pre-chunked saved datasets.
- ✅ Delete cascade: deleting a dataset clears its rows + chat messages.
- ✅ A11y: DatasetSelector now has aria-label. Recharts: ResponsiveContainer minWidth=0 silences width(-1) warning on first paint.
- ✅ 41/41 backend tests passing. End-to-end verified with synthetic 19,418-row CSV.
- ✅ **P4 BUG FIX**: Proceed-to-Dashboard now shows the just-uploaded dataset (was showing arbitrary Mongo-order dataset). FE prepends new dataset to local state; backend now sorts datasets by created_at desc.
- ✅ **P2** Date format detection: `_detect_date_column` in analysis.py detects date columns via regex+format-trial. Flags inconsistent formats as error (-8 score), consistent formats as success. New `date_columns: List[str]` field in `DataQualityReport`.
- ✅ **P3** MongoDB indexes via `ensure_indexes()` in lifespan: `chat_messages(dataset_id, user_id, timestamp)`, `datasets(user_id, created_at desc)`, unique `users(email)`. Wrapped in try/except so misshapen pre-existing collections don't block startup.
- ✅ **P3** Refactored server.py (~680 → 53 lines) into 7 focused modules:
  - `db.py` - Mongo client + ensure_indexes
  - `models.py` - all Pydantic models
  - `auth.py` - JWT, password, signup/login routes
  - `analysis.py` - CSV cleaning, date detection, anomaly detection, metric calc
  - `datasets_routes.py` - dataset CRUD + sample data
  - `chat_routes.py` - AI chat streaming + history + metric analyze
  - `server.py` - app composition only
- ✅ 29/29 backend tests passing

## Backlog (next)
- P2: Date Columns stat card in DataQuality UI (alongside Numeric/Label columns)
- P3: Stronger date format ambiguity detection (e.g. 01/02/2024 vs 02/01/2024)
- P3: Pagination for original-data preservation when file > 50K rows

## Key Files
- Backend: `/app/backend/server.py` (single file with all routes)
- Frontend pages: `/app/frontend/src/pages/{Auth,Dashboard}.js`
- Frontend components: `/app/frontend/src/components/{AIChat,DataQuality,DataTable,MetricDetail,UploadCSV}.js`
- Auth: `/app/frontend/src/contexts/AuthContext.js`

## Credentials
See `/app/memory/test_credentials.md`
