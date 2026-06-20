"""Backend tests for DataMind"""
import os
import io
import json
import uuid
import requests
import pytest

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'https://datamind-analytics-1.preview.emergentagent.com').rstrip('/')
API = f"{BASE_URL}/api"

TEST_EMAIL = "test@datamind.com"
TEST_PASS = "test123"


@pytest.fixture(scope="session")
def session():
    return requests.Session()


@pytest.fixture(scope="session")
def auth_token(session):
    # Try login first
    r = session.post(f"{API}/auth/login", json={"email": TEST_EMAIL, "password": TEST_PASS})
    if r.status_code == 200:
        return r.json()["token"]
    # Otherwise signup
    r = session.post(f"{API}/auth/signup", json={"email": TEST_EMAIL, "password": TEST_PASS, "name": "Test User"})
    assert r.status_code == 200, f"Signup failed: {r.status_code} {r.text}"
    return r.json()["token"]


@pytest.fixture
def auth_headers(auth_token):
    return {"Authorization": f"Bearer {auth_token}"}


# ===== AUTH =====

def test_signup_new_user(session):
    email = f"TEST_{uuid.uuid4().hex[:8]}@test.com"
    r = session.post(f"{API}/auth/signup", json={"email": email, "password": "pass1234", "name": "New User"})
    assert r.status_code == 200, r.text
    data = r.json()
    assert "token" in data and "user" in data
    assert data["user"]["email"] == email


def test_signup_duplicate(session):
    r = session.post(f"{API}/auth/signup", json={"email": TEST_EMAIL, "password": TEST_PASS, "name": "Dup"})
    assert r.status_code == 400


def test_login_success(session):
    r = session.post(f"{API}/auth/login", json={"email": TEST_EMAIL, "password": TEST_PASS})
    assert r.status_code == 200, r.text
    assert "token" in r.json()


def test_login_invalid(session):
    r = session.post(f"{API}/auth/login", json={"email": TEST_EMAIL, "password": "wrong"})
    assert r.status_code == 401


def test_auth_me(session, auth_headers):
    r = session.get(f"{API}/auth/me", headers=auth_headers)
    assert r.status_code == 200, r.text
    assert r.json()["email"] == TEST_EMAIL


def test_auth_me_no_token(session):
    r = session.get(f"{API}/auth/me")
    assert r.status_code in (401, 403)


# ===== SAMPLE DATA =====

def test_sample_data(session):
    r = session.get(f"{API}/datasets/sample/data")
    assert r.status_code == 200
    data = r.json()
    assert len(data) == 12
    # Verify December anomalies
    dec = [d for d in data if d["month"] == "Dec"][0]
    assert dec["cac"] == 178
    assert dec["churn"] == 7.2


# ===== CSV UPLOAD =====

def test_csv_upload_and_quality(session, auth_headers):
    csv = "month,revenue,orders,cac,churn\nJan,42000,310,120,4.1\nFeb,38000,280,134,4.4\nMar,55000,420,118,3.9\nDec,41000,290,178,7.2\n"
    files = {"file": ("test.csv", io.BytesIO(csv.encode()), "text/csv")}
    r = session.post(f"{API}/datasets/upload", headers=auth_headers, files=files)
    assert r.status_code == 200, r.text
    rep = r.json()
    assert "score" in rep
    assert "numeric_columns" in rep
    assert "revenue" in rep["numeric_columns"]
    assert "month" in rep["label_columns"]


def test_csv_upload_invalid_extension(session, auth_headers):
    files = {"file": ("test.txt", io.BytesIO(b"data"), "text/plain")}
    r = session.post(f"{API}/datasets/upload", headers=auth_headers, files=files)
    assert r.status_code == 400


# ===== DATASET SAVE / GET / DELETE =====

def _upload_and_save(session, auth_headers, name="TEST_ds", sample_override=None):
    """Helper using the NEW upload_id flow."""
    import pandas as pd
    sample = sample_override if sample_override is not None else session.get(f"{API}/datasets/sample/data").json()
    csv_bytes = pd.DataFrame(sample).to_csv(index=False).encode()
    files = {"file": ("sample.csv", io.BytesIO(csv_bytes), "text/csv")}
    r = session.post(f"{API}/datasets/upload", headers=auth_headers, files=files)
    assert r.status_code == 200, r.text
    rep = r.json()
    payload = {
        "upload_id": rep["upload_id"],
        "name": name,
        "numeric_columns": rep["numeric_columns"],
        "label_columns": rep["label_columns"],
        "date_columns": rep.get("date_columns", []),
        "quality_score": rep["score"],
    }
    r2 = session.post(f"{API}/datasets/save", headers=auth_headers, json=payload)
    assert r2.status_code == 200, f"save failed: {r2.status_code} {r2.text}"
    return r2.json(), rep


@pytest.fixture
def sample_dataset_id(session, auth_headers):
    ds, _ = _upload_and_save(session, auth_headers, name="TEST_sample")
    yield ds["id"]
    session.delete(f"{API}/datasets/{ds['id']}", headers=auth_headers)


def test_dataset_save_and_anomalies(session, auth_headers, sample_dataset_id):
    r = session.get(f"{API}/datasets/{sample_dataset_id}", headers=auth_headers)
    assert r.status_code == 200
    ds = r.json()
    # Anomalies present for Dec
    anomalies = ds["anomalies"]
    assert len(anomalies) > 0
    # Find CAC and churn Dec anomalies
    cac_anomaly = next((a for a in anomalies if a["metric"] == "cac"), None)
    churn_anomaly = next((a for a in anomalies if a["metric"] == "churn"), None)
    assert cac_anomaly is not None, "CAC anomaly not detected"
    assert churn_anomaly is not None, "Churn anomaly not detected"
    assert cac_anomaly["label"] == "Dec"
    assert cac_anomaly["severity"] == "Critical"
    assert cac_anomaly["z_score"] >= 2.2
    # Metrics
    assert len(ds["metrics"]) == 4


def test_datasets_list(session, auth_headers, sample_dataset_id):
    r = session.get(f"{API}/datasets", headers=auth_headers)
    assert r.status_code == 200
    assert any(d["id"] == sample_dataset_id for d in r.json())


def test_dataset_delete(session, auth_headers):
    ds, _ = _upload_and_save(session, auth_headers, name="TEST_del")
    ds_id = ds["id"]
    r3 = session.delete(f"{API}/datasets/{ds_id}", headers=auth_headers)
    assert r3.status_code == 200
    r4 = session.get(f"{API}/datasets/{ds_id}", headers=auth_headers)
    assert r4.status_code == 404


# ===== CHAT STREAMING =====

def test_chat_stream(session, auth_headers, sample_dataset_id):
    r = session.post(
        f"{API}/chat/stream",
        headers=auth_headers,
        json={"message": "What is the biggest anomaly?", "dataset_id": sample_dataset_id},
        stream=True,
        timeout=60,
    )
    assert r.status_code == 200
    content = ""
    saw_done = False
    for line in r.iter_lines(decode_unicode=True):
        if not line or not line.startswith("data: "):
            continue
        payload = json.loads(line[6:])
        if "content" in payload:
            content += payload["content"]
        if payload.get("done"):
            saw_done = True
            break
        if "error" in payload:
            pytest.fail(f"Stream error: {payload['error']}")
    assert len(content) > 20, f"Empty content: {content!r}"


def test_metric_analyze_stream(session, auth_headers, sample_dataset_id):
    r = session.post(
        f"{API}/metrics/cac/analyze?dataset_id={sample_dataset_id}",
        headers=auth_headers,
        stream=True,
        timeout=60,
    )
    assert r.status_code == 200
    content = ""
    for line in r.iter_lines(decode_unicode=True):
        if not line or not line.startswith("data: "):
            continue
        payload = json.loads(line[6:])
        if "content" in payload:
            content += payload["content"]
        if payload.get("done"):
            break
        if "error" in payload:
            pytest.fail(f"Stream error: {payload['error']}")
    assert len(content) > 20



# ===== NEW FEATURES: RENAME, REMOVE-DUPLICATES, CHAT HISTORY =====

def _create_dataset(session, auth_headers, name="TEST_new", with_dupes=False):
    """Helper to create a dataset using the NEW upload_id flow."""
    sample = session.get(f"{API}/datasets/sample/data").json()
    if with_dupes:
        sample = sample + [sample[0], sample[1]]
    ds, rep = _upload_and_save(session, auth_headers, name=name, sample_override=sample)
    return ds["id"], rep


# --- Rename Dataset ---

def test_rename_dataset_success(session, auth_headers):
    ds_id, _ = _create_dataset(session, auth_headers, name="TEST_rename_old")
    try:
        r = session.patch(f"{API}/datasets/{ds_id}/rename", headers=auth_headers,
                          json={"name": "TEST_rename_new"})
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["name"] == "TEST_rename_new"
        # verify persistence
        r2 = session.get(f"{API}/datasets/{ds_id}", headers=auth_headers)
        assert r2.status_code == 200
        assert r2.json()["name"] == "TEST_rename_new"
    finally:
        session.delete(f"{API}/datasets/{ds_id}", headers=auth_headers)


def test_rename_dataset_not_found(session, auth_headers):
    r = session.patch(f"{API}/datasets/nonexistent-id/rename", headers=auth_headers,
                      json={"name": "x"})
    assert r.status_code == 404


def test_rename_dataset_requires_auth(session):
    r = session.patch(f"{API}/datasets/some-id/rename", json={"name": "x"})
    assert r.status_code in (401, 403)


# --- Remove Duplicates ---

def test_remove_duplicates_success(session, auth_headers):
    import pandas as pd
    data_with_dups = [
        {"month": "Jan", "revenue": 100},
        {"month": "Feb", "revenue": 200},
        {"month": "Jan", "revenue": 100},
        {"month": "Mar", "revenue": 300},
        {"month": "Feb", "revenue": 200},
    ]
    csv_bytes = pd.DataFrame(data_with_dups).to_csv(index=False).encode()
    files = {"file": ("d.csv", io.BytesIO(csv_bytes), "text/csv")}
    rep = session.post(f"{API}/datasets/upload", headers=auth_headers, files=files).json()
    r = session.post(f"{API}/datasets/remove-duplicates", headers=auth_headers,
                     json={"upload_id": rep["upload_id"]})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["removed"] == 2
    assert body["remaining"] == 3
    assert "preview_data" in body
    assert body["total_rows"] == 3


def test_remove_duplicates_no_dupes(session, auth_headers):
    import pandas as pd
    data = [{"a": 1}, {"a": 2}, {"a": 3}]
    csv_bytes = pd.DataFrame(data).to_csv(index=False).encode()
    files = {"file": ("d.csv", io.BytesIO(csv_bytes), "text/csv")}
    rep = session.post(f"{API}/datasets/upload", headers=auth_headers, files=files).json()
    r = session.post(f"{API}/datasets/remove-duplicates", headers=auth_headers,
                     json={"upload_id": rep["upload_id"]})
    assert r.status_code == 200
    body = r.json()
    assert body["removed"] == 0
    assert body["remaining"] == 3


def test_remove_duplicates_requires_auth(session):
    r = session.post(f"{API}/datasets/remove-duplicates", json={"upload_id": "x"})
    assert r.status_code in (401, 403)


def test_remove_duplicates_unknown_upload_id(session, auth_headers):
    r = session.post(f"{API}/datasets/remove-duplicates", headers=auth_headers,
                     json={"upload_id": "does-not-exist-uuid"})
    assert r.status_code == 404


# --- Chat History CRUD ---

def test_chat_save_and_get(session, auth_headers):
    ds_id, _ = _create_dataset(session, auth_headers, name="TEST_chat")
    try:
        # Save user message
        r = session.post(f"{API}/chat/save", headers=auth_headers,
                         json={"dataset_id": ds_id, "role": "user", "content": "hello"})
        assert r.status_code == 200, r.text
        assert "id" in r.json()

        # Save assistant message
        r2 = session.post(f"{API}/chat/save", headers=auth_headers,
                          json={"dataset_id": ds_id, "role": "assistant", "content": "hi there"})
        assert r2.status_code == 200

        # Get history
        r3 = session.get(f"{API}/chat/history/{ds_id}", headers=auth_headers)
        assert r3.status_code == 200
        msgs = r3.json()
        assert len(msgs) == 2
        # Sorted by timestamp ascending
        assert msgs[0]["role"] == "user"
        assert msgs[0]["content"] == "hello"
        assert msgs[1]["role"] == "assistant"
        assert msgs[1]["content"] == "hi there"
    finally:
        session.delete(f"{API}/datasets/{ds_id}", headers=auth_headers)


def test_chat_history_not_found_dataset(session, auth_headers):
    r = session.get(f"{API}/chat/history/nonexistent-id", headers=auth_headers)
    assert r.status_code == 404


def test_chat_history_requires_auth(session):
    r = session.get(f"{API}/chat/history/some-id")
    assert r.status_code in (401, 403)


def test_chat_clear_history(session, auth_headers):
    ds_id, _ = _create_dataset(session, auth_headers, name="TEST_chat_clear")
    try:
        # Save 2 messages
        session.post(f"{API}/chat/save", headers=auth_headers,
                     json={"dataset_id": ds_id, "role": "user", "content": "q1"})
        session.post(f"{API}/chat/save", headers=auth_headers,
                     json={"dataset_id": ds_id, "role": "assistant", "content": "a1"})

        # Clear
        r = session.delete(f"{API}/chat/history/{ds_id}", headers=auth_headers)
        assert r.status_code == 200

        # Verify empty
        r2 = session.get(f"{API}/chat/history/{ds_id}", headers=auth_headers)
        assert r2.status_code == 200
        assert r2.json() == []
    finally:
        session.delete(f"{API}/datasets/{ds_id}", headers=auth_headers)


def test_delete_dataset_clears_chat(session, auth_headers):
    ds_id, _ = _create_dataset(session, auth_headers, name="TEST_del_clears_chat")
    # Add chat msg
    session.post(f"{API}/chat/save", headers=auth_headers,
                 json={"dataset_id": ds_id, "role": "user", "content": "x"})
    # Verify present
    msgs = session.get(f"{API}/chat/history/{ds_id}", headers=auth_headers).json()
    assert len(msgs) == 1
    # Delete dataset
    r = session.delete(f"{API}/datasets/{ds_id}", headers=auth_headers)
    assert r.status_code == 200
    # Dataset is gone => chat history returns 404 (since ownership check fails)
    r2 = session.get(f"{API}/chat/history/{ds_id}", headers=auth_headers)
    assert r2.status_code == 404


# ===== ITERATION 3: DATE DETECTION + INDEXES + ORDERING =====

def _upload_csv(session, auth_headers, csv_text, filename="t.csv"):
    files = {"file": (filename, io.BytesIO(csv_text.encode()), "text/csv")}
    r = session.post(f"{API}/datasets/upload", headers=auth_headers, files=files)
    assert r.status_code == 200, r.text
    return r.json()


def test_date_detection_inconsistent_format(session, auth_headers):
    """Mixed date formats should be flagged as error and lower the score."""
    csv = "date,revenue\n2024-01-15,100\n03/04/2024,200\n2024-03-20,300\n04/05/2024,400\n2024-05-25,500\n"
    rep = _upload_csv(session, auth_headers, csv)
    assert "date_columns" in rep
    assert "date" in rep["date_columns"], f"date col missing: {rep['date_columns']}"
    assert "date" not in rep["label_columns"]
    assert "date" not in rep["numeric_columns"]
    # Should be flagged as error
    err_msgs = [i for i in rep["issues"] if i["type"] == "error" and "date" in i["message"].lower()]
    assert len(err_msgs) >= 1, f"No error for mixed date formats: {rep['issues']}"
    # Score impacted
    assert rep["score"] < 100


def test_date_detection_consistent_format(session, auth_headers):
    csv = "month,revenue\n2024-01-15,100\n2024-02-15,200\n2024-03-15,300\n2024-04-15,400\n"
    rep = _upload_csv(session, auth_headers, csv)
    assert "month" in rep["date_columns"]
    assert "month" not in rep["label_columns"]
    assert "month" not in rep["numeric_columns"]
    # Should have a success issue mentioning consistent date format
    success = [i for i in rep["issues"] if i["type"] == "success" and "consistent date" in i["message"].lower()]
    assert len(success) >= 1, f"No success msg for consistent dates: {rep['issues']}"


def test_no_date_columns_when_absent(session, auth_headers):
    csv = "month,revenue,orders\nJan,1000,10\nFeb,2000,20\nMar,3000,30\n"
    rep = _upload_csv(session, auth_headers, csv)
    assert rep["date_columns"] == []
    assert "month" in rep["label_columns"]


def test_datasets_sorted_newest_first(session, auth_headers):
    """The dataset list must be sorted by created_at desc (newest first)."""
    import time
    created_ids = []
    try:
        for i in range(3):
            ds, _ = _upload_and_save(session, auth_headers, name=f"TEST_order_{i}")
            created_ids.append(ds["id"])
            time.sleep(0.05)

        r = session.get(f"{API}/datasets", headers=auth_headers)
        assert r.status_code == 200
        all_ds = r.json()
        ours = [d for d in all_ds if d["id"] in created_ids]
        order_by_returned = [d["id"] for d in ours]
        expected = list(reversed(created_ids))
        assert order_by_returned == expected, f"Expected newest-first {expected} got {order_by_returned}"
    finally:
        for did in created_ids:
            session.delete(f"{API}/datasets/{did}", headers=auth_headers)


def test_mongodb_indexes_present(session, auth_headers):
    """Indirect verification: by calling endpoints that use the indexed fields, they should
    all succeed. We can't query Mongo directly from here, but a more direct check via
    pymongo against MONGO_URL is best-effort."""
    import os
    mongo_url = os.environ.get('MONGO_URL')
    db_name = os.environ.get('DB_NAME')
    if not mongo_url or not db_name:
        pytest.skip("MONGO_URL / DB_NAME not exposed to test env")
    try:
        from pymongo import MongoClient
    except ImportError:
        pytest.skip("pymongo not installed in test env")

    c = MongoClient(mongo_url, serverSelectionTimeoutMS=3000)
    db = c[db_name]
    chat_idx = list(db.chat_messages.list_indexes())
    chat_keys = [tuple(i['key'].items()) for i in chat_idx]
    expected_chat = (('dataset_id', 1), ('user_id', 1), ('timestamp', 1))
    assert any(tuple(k) == expected_chat for k in chat_keys), f"chat_messages compound index missing: {chat_keys}"

    ds_idx = list(db.datasets.list_indexes())
    ds_keys = [tuple(i['key'].items()) for i in ds_idx]
    expected_ds = (('user_id', 1), ('created_at', -1))
    assert any(tuple(k) == expected_ds for k in ds_keys), f"datasets index missing: {ds_keys}"

    users_idx = list(db.users.list_indexes())
    users_keys = [tuple(i['key'].items()) for i in users_idx]
    assert any(('email', 1) in k for k in users_keys), f"users.email index missing: {users_keys}"
    c.close()
