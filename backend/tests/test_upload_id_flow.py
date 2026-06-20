"""Iteration 5: tests for the new upload_id-based flow.

Covers:
- Upload response shape & size (no cleaned_data, <100KB).
- Save body size (just upload_id + metadata).
- 404 on unknown/expired upload_id.
- 409 on double save.
- NaN sanitization (missing numeric values come back as null, not NaN).
- TTL index on dataset_rows.created_at with partial filter status=draft.
- /rows excludes draft chunks.
"""
import io
import json
import os
import math
import random
import string
import time
import pytest
import requests
import pandas as pd

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'https://datamind-analytics-1.preview.emergentagent.com').rstrip('/')
API = f"{BASE_URL}/api"

TEST_EMAIL = "test@datamind.com"
TEST_PASS = "test123"


@pytest.fixture(scope="module")
def session():
    return requests.Session()


@pytest.fixture(scope="module")
def auth_headers(session):
    r = session.post(f"{API}/auth/login", json={"email": TEST_EMAIL, "password": TEST_PASS})
    if r.status_code != 200:
        r = session.post(f"{API}/auth/signup", json={"email": TEST_EMAIL, "password": TEST_PASS, "name": "Test User"})
    return {"Authorization": f"Bearer {r.json()['token']}"}


def _make_csv(n_rows=200, n_cols=10):
    random.seed(7)
    cols = ["id", "score"] + [f"q{i}" for i in range(n_cols - 2)]
    rows = []
    for i in range(n_rows):
        row = {"id": f"R{i:05d}", "score": random.randint(1, 5)}
        for j in range(n_cols - 2):
            row[f"q{j}"] = ''.join(random.choices(string.ascii_letters, k=5))
        rows.append(row)
    return pd.DataFrame(rows, columns=cols).to_csv(index=False).encode()


# ===== UPLOAD RESPONSE SHAPE =====

def test_upload_response_contains_no_cleaned_data(session, auth_headers):
    files = {"file": ("t.csv", io.BytesIO(_make_csv(100, 5)), "text/csv")}
    r = session.post(f"{API}/datasets/upload", headers=auth_headers, files=files, timeout=60)
    assert r.status_code == 200
    rep = r.json()
    # Must NOT have full payload
    assert "cleaned_data" not in rep
    assert "original_data" not in rep
    # Must have new fields
    for k in ("upload_id", "score", "issues", "numeric_columns", "label_columns",
              "date_columns", "total_rows", "preview_data", "duplicates_found", "rows_removed"):
        assert k in rep, f"missing key: {k}"
    assert isinstance(rep["upload_id"], str) and len(rep["upload_id"]) >= 32
    assert rep["total_rows"] == 100
    assert len(rep["preview_data"]) == 50  # PREVIEW_ROWS cap


def test_upload_response_size_under_100kb_even_for_max_rows(session, auth_headers):
    """A 19,418-row, 41-col upload must round-trip in < 100KB."""
    csv_bytes = _make_csv(19_418, 41)
    files = {"file": ("big.csv", io.BytesIO(csv_bytes), "text/csv")}
    r = session.post(f"{API}/datasets/upload", headers=auth_headers, files=files, timeout=240)
    assert r.status_code == 200
    body = r.content
    assert len(body) < 100_000, f"upload response too large: {len(body)} bytes"
    rep = r.json()
    assert rep["total_rows"] == 19_418
    # cleanup: drop the draft chunks by saving then deleting
    payload = {
        "upload_id": rep["upload_id"],
        "name": "TEST_size_check",
        "numeric_columns": rep["numeric_columns"],
        "label_columns": rep["label_columns"],
        "date_columns": rep.get("date_columns", []),
        "quality_score": rep["score"],
    }
    r2 = session.post(f"{API}/datasets/save", headers=auth_headers, json=payload, timeout=120)
    assert r2.status_code == 200
    session.delete(f"{API}/datasets/{rep['upload_id']}", headers=auth_headers, timeout=60)


# ===== SAVE PATH =====

def test_save_body_is_small(session, auth_headers):
    files = {"file": ("s.csv", io.BytesIO(_make_csv(50, 5)), "text/csv")}
    rep = session.post(f"{API}/datasets/upload", headers=auth_headers, files=files).json()
    payload = {
        "upload_id": rep["upload_id"],
        "name": "TEST_small_body",
        "numeric_columns": rep["numeric_columns"],
        "label_columns": rep["label_columns"],
        "date_columns": rep.get("date_columns", []),
        "quality_score": rep["score"],
    }
    serialized = json.dumps(payload)
    assert len(serialized) < 2048, f"save body too big: {len(serialized)}"
    r = session.post(f"{API}/datasets/save", headers=auth_headers, json=payload)
    assert r.status_code == 200
    session.delete(f"{API}/datasets/{rep['upload_id']}", headers=auth_headers)


def test_save_unknown_upload_id_returns_404(session, auth_headers):
    payload = {
        "upload_id": "00000000-0000-0000-0000-000000000000",
        "name": "TEST_404",
        "numeric_columns": [],
        "label_columns": [],
        "date_columns": [],
        "quality_score": 100,
    }
    r = session.post(f"{API}/datasets/save", headers=auth_headers, json=payload)
    assert r.status_code == 404
    body = r.json()
    msg = (body.get("detail") or "").lower()
    assert "upload" in msg and ("expired" in msg or "not found" in msg)


def test_save_idempotency_409_on_second_save(session, auth_headers):
    files = {"file": ("d.csv", io.BytesIO(_make_csv(30, 4)), "text/csv")}
    rep = session.post(f"{API}/datasets/upload", headers=auth_headers, files=files).json()
    payload = {
        "upload_id": rep["upload_id"],
        "name": "TEST_idem",
        "numeric_columns": rep["numeric_columns"],
        "label_columns": rep["label_columns"],
        "date_columns": rep.get("date_columns", []),
        "quality_score": rep["score"],
    }
    r1 = session.post(f"{API}/datasets/save", headers=auth_headers, json=payload)
    assert r1.status_code == 200
    try:
        r2 = session.post(f"{API}/datasets/save", headers=auth_headers, json=payload)
        assert r2.status_code == 409
        body = r2.json()
        msg = (body.get("detail") or "").lower()
        assert "already" in msg or "saved" in msg
    finally:
        session.delete(f"{API}/datasets/{rep['upload_id']}", headers=auth_headers)


# ===== NaN SANITIZATION =====

def test_nan_in_numeric_column_returned_as_null(session, auth_headers):
    csv = "month,revenue,orders\nJan,100,10\nFeb,,20\nMar,300,\n"
    files = {"file": ("n.csv", io.BytesIO(csv.encode()), "text/csv")}
    r = session.post(f"{API}/datasets/upload", headers=auth_headers, files=files)
    assert r.status_code == 200
    # response body parses as valid JSON (NaN would have broken json.loads)
    body = r.content.decode()
    assert "NaN" not in body, "NaN literal leaked into JSON response"
    rep = r.json()
    # preview_data contains nulls where NaN would have been
    rev_vals = [row["revenue"] for row in rep["preview_data"]]
    orders_vals = [row["orders"] for row in rep["preview_data"]]
    assert None in rev_vals or None in orders_vals, f"expected null in {rev_vals}/{orders_vals}"
    # save still works
    payload = {
        "upload_id": rep["upload_id"],
        "name": "TEST_nan",
        "numeric_columns": rep["numeric_columns"],
        "label_columns": rep["label_columns"],
        "date_columns": rep.get("date_columns", []),
        "quality_score": rep["score"],
    }
    r2 = session.post(f"{API}/datasets/save", headers=auth_headers, json=payload)
    assert r2.status_code == 200, r2.text
    session.delete(f"{API}/datasets/{rep['upload_id']}", headers=auth_headers)


# ===== ROWS ENDPOINT FILTERS DRAFTS =====

def test_rows_endpoint_excludes_draft_chunks_from_other_upload(session, auth_headers):
    """A draft upload that hasn't been saved should not be readable via /rows."""
    files = {"file": ("d.csv", io.BytesIO(_make_csv(60, 4)), "text/csv")}
    rep = session.post(f"{API}/datasets/upload", headers=auth_headers, files=files).json()
    # don't save -> the /rows endpoint on this upload_id should 404 (no dataset row)
    r = session.get(f"{API}/datasets/{rep['upload_id']}/rows",
                    headers=auth_headers, params={"skip": 0, "limit": 5})
    assert r.status_code == 404


# ===== TTL INDEX VERIFICATION =====

def test_dataset_rows_has_ttl_index_on_draft(session, auth_headers):
    """Verify the TTL index (created_at, 1) with expireAfterSeconds=3600 and partialFilter status=draft."""
    mongo_url = os.environ.get('MONGO_URL')
    db_name = os.environ.get('DB_NAME')
    if not mongo_url or not db_name:
        pytest.skip("MONGO_URL not in env")
    try:
        from pymongo import MongoClient
    except ImportError:
        pytest.skip("pymongo not installed")
    c = MongoClient(mongo_url, serverSelectionTimeoutMS=3000)
    idxs = list(c[db_name].dataset_rows.list_indexes())
    ttl = [
        i for i in idxs
        if i.get("expireAfterSeconds") == 3600
        and i.get("partialFilterExpression", {}).get("status") == "draft"
        and dict(i["key"]).get("created_at") == 1
    ]
    assert len(ttl) == 1, f"TTL draft index missing/wrong: {idxs}"
    c.close()


# ===== PAGINATED /rows ON 19K AT MID-RANGE =====

def test_paginated_rows_skip_15000_limit_3(session, auth_headers):
    """Spec: GET /datasets/{id}/rows?skip=15000&limit=3 returns 3 rows; total=19417 after dedupe."""
    # Build a 19,418-row CSV; the dedupe in clean_and_analyze_csv may remove duplicates randomly,
    # so we use a guaranteed-unique id column.
    csv_bytes = _make_csv(19_418, 8)
    files = {"file": ("big.csv", io.BytesIO(csv_bytes), "text/csv")}
    rep = session.post(f"{API}/datasets/upload", headers=auth_headers, files=files, timeout=240).json()
    assert rep["total_rows"] == 19_418  # no dupes due to unique id
    payload = {
        "upload_id": rep["upload_id"],
        "name": "TEST_paginate_mid",
        "numeric_columns": rep["numeric_columns"],
        "label_columns": rep["label_columns"],
        "date_columns": rep.get("date_columns", []),
        "quality_score": rep["score"],
    }
    r = session.post(f"{API}/datasets/save", headers=auth_headers, json=payload, timeout=120)
    assert r.status_code == 200
    try:
        r2 = session.get(f"{API}/datasets/{rep['upload_id']}/rows",
                         headers=auth_headers, params={"skip": 15_000, "limit": 3})
        assert r2.status_code == 200
        body = r2.json()
        assert body["total"] == 19_418
        assert len(body["rows"]) == 3
        assert body["rows"][0]["id"] == "R15000"
    finally:
        session.delete(f"{API}/datasets/{rep['upload_id']}", headers=auth_headers, timeout=60)
