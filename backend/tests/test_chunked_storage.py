"""Iteration 4: chunked storage tests for large CSVs (P4 bug fix)."""
import io
import os
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
    s = requests.Session()
    return s


@pytest.fixture(scope="module")
def auth_headers(session):
    r = session.post(f"{API}/auth/login", json={"email": TEST_EMAIL, "password": TEST_PASS})
    if r.status_code != 200:
        r = session.post(f"{API}/auth/signup", json={"email": TEST_EMAIL, "password": TEST_PASS, "name": "Test User"})
    token = r.json()["token"]
    return {"Authorization": f"Bearer {token}"}


def _build_csv(n_rows: int, n_cols: int = 41) -> bytes:
    """Build a synthetic CSV with the requested shape."""
    random.seed(42)
    cols = ["respondent_id", "submitted_at", "csat_score", "nps_score"] + [f"q{i}" for i in range(n_cols - 4)]
    rows = []
    for i in range(n_rows):
        row = {
            "respondent_id": f"R{i:08d}",
            "submitted_at": f"2024-{random.randint(1,12):02d}-{random.randint(1,28):02d}",
            "csat_score": random.randint(1, 5),
            "nps_score": random.randint(0, 10),
        }
        for j in range(n_cols - 4):
            row[f"q{j}"] = ''.join(random.choices(string.ascii_letters, k=8))
        rows.append(row)
    return pd.DataFrame(rows, columns=cols).to_csv(index=False).encode()


@pytest.fixture(scope="module")
def large_dataset(session, auth_headers):
    """Upload+save 19,418 rows × 41 cols and yield dataset id; cleanup after."""
    csv_bytes = _build_csv(19_418, 41)
    t0 = time.time()
    files = {"file": ("csat_synth.csv", io.BytesIO(csv_bytes), "text/csv")}
    r = session.post(f"{API}/datasets/upload", headers=auth_headers, files=files, timeout=180)
    print(f"\nupload took {time.time()-t0:.1f}s, status={r.status_code}, size={len(csv_bytes)/1e6:.1f}MB")
    assert r.status_code == 200, f"upload failed: {r.status_code} {r.text[:200]}"
    rep = r.json()
    # Upload response must be lean: no cleaned_data, no original_data
    assert "cleaned_data" not in rep
    assert "original_data" not in rep
    assert "upload_id" in rep
    assert rep["total_rows"] == 19_418
    assert len(rep["preview_data"]) <= 50
    payload = {
        "upload_id": rep["upload_id"],
        "name": "TEST_chunked_19k",
        "numeric_columns": rep["numeric_columns"],
        "label_columns": rep["label_columns"],
        "date_columns": rep.get("date_columns", []),
        "quality_score": rep["score"],
    }
    t1 = time.time()
    r2 = session.post(f"{API}/datasets/save", headers=auth_headers, json=payload, timeout=180)
    print(f"save took {time.time()-t1:.1f}s, status={r2.status_code}")
    assert r2.status_code == 200, f"save failed: {r2.status_code} {r2.text[:300]}"
    ds = r2.json()
    yield ds
    session.delete(f"{API}/datasets/{ds['id']}", headers=auth_headers, timeout=60)


def test_large_csv_save_returns_200(large_dataset):
    """P4: 19,418 row save must not 500 with DocumentTooLarge."""
    assert large_dataset["id"]
    assert large_dataset["name"] == "TEST_chunked_19k"
    assert large_dataset.get("total_rows") == 19_418


def test_metadata_has_only_50_preview_rows(session, auth_headers, large_dataset):
    """GET /datasets/{id} returns only 50 preview rows in `data` (not full 19K)."""
    r = session.get(f"{API}/datasets/{large_dataset['id']}", headers=auth_headers, timeout=30)
    assert r.status_code == 200
    ds = r.json()
    assert len(ds["data"]) == 50, f"Expected 50 preview rows, got {len(ds['data'])}"
    assert ds["total_rows"] == 19_418


def test_paginated_rows_endpoint(session, auth_headers, large_dataset):
    """GET /datasets/{id}/rows?skip=10000&limit=5 returns 5 rows from row 10000."""
    ds_id = large_dataset["id"]
    r = session.get(f"{API}/datasets/{ds_id}/rows", headers=auth_headers,
                    params={"skip": 10_000, "limit": 5}, timeout=30)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["total"] == 19_418
    assert body["skip"] == 10_000
    assert body["limit"] == 5
    assert len(body["rows"]) == 5
    # row at position 10000 should have respondent_id R00010000
    assert body["rows"][0]["respondent_id"] == "R00010000"
    assert body["rows"][4]["respondent_id"] == "R00010004"


def test_paginated_rows_skip_0(session, auth_headers, large_dataset):
    """First page returns first 5 rows from chunk 0."""
    r = session.get(f"{API}/datasets/{large_dataset['id']}/rows", headers=auth_headers,
                    params={"skip": 0, "limit": 5}, timeout=30)
    assert r.status_code == 200
    body = r.json()
    assert len(body["rows"]) == 5
    assert body["rows"][0]["respondent_id"] == "R00000000"


def test_paginated_rows_last_chunk(session, auth_headers, large_dataset):
    """Reading rows near the end (chunk_index=3) should work."""
    r = session.get(f"{API}/datasets/{large_dataset['id']}/rows", headers=auth_headers,
                    params={"skip": 19_415, "limit": 10}, timeout=30)
    assert r.status_code == 200
    body = r.json()
    # only 3 rows remain (19415, 19416, 19417)
    assert len(body["rows"]) == 3
    assert body["rows"][-1]["respondent_id"] == "R00019417"


def test_paginated_rows_cross_chunk_boundary(session, auth_headers, large_dataset):
    """Reading rows spanning two chunks (4998..5002) should stitch correctly."""
    r = session.get(f"{API}/datasets/{large_dataset['id']}/rows", headers=auth_headers,
                    params={"skip": 4_998, "limit": 5}, timeout=30)
    assert r.status_code == 200
    body = r.json()
    assert len(body["rows"]) == 5
    ids = [row["respondent_id"] for row in body["rows"]]
    assert ids == ["R00004998", "R00004999", "R00005000", "R00005001", "R00005002"]


def test_paginated_rows_requires_auth(session, large_dataset):
    r = session.get(f"{API}/datasets/{large_dataset['id']}/rows", params={"skip": 0, "limit": 5})
    assert r.status_code in (401, 403)


def test_paginated_rows_dataset_not_found(session, auth_headers):
    r = session.get(f"{API}/datasets/does-not-exist/rows", headers=auth_headers,
                    params={"skip": 0, "limit": 5}, timeout=15)
    assert r.status_code == 404


def test_paginated_rows_limit_capped(session, auth_headers, large_dataset):
    """limit > 500 should be capped to 500."""
    r = session.get(f"{API}/datasets/{large_dataset['id']}/rows", headers=auth_headers,
                    params={"skip": 0, "limit": 2000}, timeout=30)
    assert r.status_code == 200
    body = r.json()
    assert body["limit"] == 500
    assert len(body["rows"]) == 500


def test_upload_row_limit_50k_rejected(session, auth_headers):
    """A CSV with >50,000 rows must return 413 with friendly message."""
    csv_bytes = _build_csv(50_001, 5)
    files = {"file": ("toobig.csv", io.BytesIO(csv_bytes), "text/csv")}
    r = session.post(f"{API}/datasets/upload", headers=auth_headers, files=files, timeout=180)
    assert r.status_code == 413, f"Expected 413, got {r.status_code}: {r.text[:200]}"
    body = r.json()
    msg = (body.get("detail") or body.get("message") or "").lower()
    assert "row" in msg or "50,000" in msg or "50000" in msg


def test_delete_large_dataset_cascade(session, auth_headers):
    """Deleting a chunked dataset must also remove its chunks. Verified by save->delete->get rows -> 404."""
    csv_bytes = _build_csv(6_000, 5)  # 2 chunks
    files = {"file": ("c.csv", io.BytesIO(csv_bytes), "text/csv")}
    rep = session.post(f"{API}/datasets/upload", headers=auth_headers, files=files, timeout=120).json()
    payload = {
        "upload_id": rep["upload_id"],
        "name": "TEST_cascade",
        "numeric_columns": rep["numeric_columns"],
        "label_columns": rep["label_columns"],
        "date_columns": rep.get("date_columns", []),
        "quality_score": rep["score"],
    }
    ds = session.post(f"{API}/datasets/save", headers=auth_headers, json=payload, timeout=120).json()
    ds_id = ds["id"]
    # Verify chunks exist
    r = session.get(f"{API}/datasets/{ds_id}/rows", headers=auth_headers,
                    params={"skip": 0, "limit": 5}, timeout=15)
    assert r.status_code == 200
    assert len(r.json()["rows"]) == 5
    # Delete
    r2 = session.delete(f"{API}/datasets/{ds_id}", headers=auth_headers, timeout=30)
    assert r2.status_code == 200
    # GET dataset -> 404, GET rows -> 404
    r3 = session.get(f"{API}/datasets/{ds_id}/rows", headers=auth_headers,
                     params={"skip": 0, "limit": 5}, timeout=15)
    assert r3.status_code == 404

    # Verify chunks are physically gone (best-effort, via Mongo direct)
    mongo_url = os.environ.get('MONGO_URL')
    db_name = os.environ.get('DB_NAME')
    if mongo_url and db_name:
        try:
            from pymongo import MongoClient
            c = MongoClient(mongo_url, serverSelectionTimeoutMS=3000)
            remaining = c[db_name].dataset_rows.count_documents({"dataset_id": ds_id})
            assert remaining == 0, f"Found {remaining} orphaned chunks after delete"
            c.close()
        except ImportError:
            pass


def test_chunked_storage_4_chunks_in_mongo(session, auth_headers, large_dataset):
    """Direct DB check: 19,418 rows must produce 4 chunks (5000+5000+5000+4418)."""
    mongo_url = os.environ.get('MONGO_URL')
    db_name = os.environ.get('DB_NAME')
    if not mongo_url or not db_name:
        pytest.skip("MONGO_URL not exposed")
    try:
        from pymongo import MongoClient
    except ImportError:
        pytest.skip("pymongo not installed")
    c = MongoClient(mongo_url, serverSelectionTimeoutMS=3000)
    chunks = list(c[db_name].dataset_rows.find({"dataset_id": large_dataset["id"]}, {"_id": 0, "chunk_index": 1, "rows": 1}))
    assert len(chunks) == 4, f"Expected 4 chunks, got {len(chunks)}"
    by_index = {ch["chunk_index"]: len(ch["rows"]) for ch in chunks}
    assert by_index == {0: 5000, 1: 5000, 2: 5000, 3: 4418}, by_index
    c.close()


def test_backward_compat_small_csv_works(session, auth_headers):
    """A small 12-row CSV (legacy size) still saves and rows endpoint returns all 12."""
    sample = session.get(f"{API}/datasets/sample/data").json()
    csv_bytes = pd.DataFrame(sample).to_csv(index=False).encode()
    files = {"file": ("small.csv", io.BytesIO(csv_bytes), "text/csv")}
    rep = session.post(f"{API}/datasets/upload", headers=auth_headers, files=files, timeout=30).json()
    payload = {
        "upload_id": rep["upload_id"],
        "name": "TEST_small_compat",
        "numeric_columns": rep["numeric_columns"],
        "label_columns": rep["label_columns"],
        "date_columns": rep.get("date_columns", []),
        "quality_score": rep["score"],
    }
    ds = session.post(f"{API}/datasets/save", headers=auth_headers, json=payload, timeout=30).json()
    try:
        assert ds.get("total_rows") == 12
        # preview has all 12 (since 12 < PREVIEW_ROWS=50)
        r = session.get(f"{API}/datasets/{ds['id']}", headers=auth_headers, timeout=15)
        assert len(r.json()["data"]) == 12
        # /rows endpoint also returns 12
        r2 = session.get(f"{API}/datasets/{ds['id']}/rows", headers=auth_headers,
                         params={"skip": 0, "limit": 100}, timeout=15)
        body = r2.json()
        assert body["total"] == 12
        assert len(body["rows"]) == 12
    finally:
        session.delete(f"{API}/datasets/{ds['id']}", headers=auth_headers, timeout=15)
