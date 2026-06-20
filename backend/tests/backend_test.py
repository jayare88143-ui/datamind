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

@pytest.fixture
def sample_dataset_id(session, auth_headers):
    """Build full dataset via sample data + save endpoint."""
    sample = session.get(f"{API}/datasets/sample/data").json()
    # Upload via CSV path to get quality report
    import pandas as pd
    df = pd.DataFrame(sample)
    csv_bytes = df.to_csv(index=False).encode()
    files = {"file": ("sample.csv", io.BytesIO(csv_bytes), "text/csv")}
    r = session.post(f"{API}/datasets/upload", headers=auth_headers, files=files)
    assert r.status_code == 200
    rep = r.json()

    # Save dataset - note: endpoint uses query/body params (Body inferred since no Body() but JSON-like types)
    # Try as JSON body
    payload = {
        "name": "TEST_sample",
        "cleaned_data": rep["cleaned_data"],
        "original_data": rep["original_data"],
        "numeric_columns": rep["numeric_columns"],
        "label_columns": rep["label_columns"],
        "quality_score": rep["score"],
    }
    r2 = session.post(f"{API}/datasets/save", headers=auth_headers, json=payload)
    if r2.status_code != 200:
        # Try with name as query param
        r2 = session.post(
            f"{API}/datasets/save?name=TEST_sample&quality_score={rep['score']}",
            headers=auth_headers,
            json={
                "cleaned_data": rep["cleaned_data"],
                "original_data": rep["original_data"],
                "numeric_columns": rep["numeric_columns"],
                "label_columns": rep["label_columns"],
            },
        )
    assert r2.status_code == 200, f"save failed: {r2.status_code} {r2.text}"
    ds = r2.json()
    yield ds["id"]
    # cleanup
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
    # Create then delete
    sample = session.get(f"{API}/datasets/sample/data").json()
    import pandas as pd
    csv_bytes = pd.DataFrame(sample).to_csv(index=False).encode()
    files = {"file": ("s.csv", io.BytesIO(csv_bytes), "text/csv")}
    rep = session.post(f"{API}/datasets/upload", headers=auth_headers, files=files).json()
    payload = {
        "name": "TEST_del",
        "cleaned_data": rep["cleaned_data"],
        "original_data": rep["original_data"],
        "numeric_columns": rep["numeric_columns"],
        "label_columns": rep["label_columns"],
        "quality_score": rep["score"],
    }
    r2 = session.post(f"{API}/datasets/save", headers=auth_headers, json=payload)
    if r2.status_code != 200:
        r2 = session.post(
            f"{API}/datasets/save?name=TEST_del&quality_score={rep['score']}",
            headers=auth_headers,
            json={k: payload[k] for k in ["cleaned_data", "original_data", "numeric_columns", "label_columns"]},
        )
    ds_id = r2.json()["id"]
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
