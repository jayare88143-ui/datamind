"""Tests for the Configure Metrics feature + crash-safe remove_duplicates.

Covers iteration 6 contract:
- POST /datasets/upload returns suggested_metric_configs (column, suggested_display_name,
  suggested_calculation, rationale)
- Smart-suggestion heuristics (revenue/orders -> sum, cac/churn -> mean, *_id -> count,
  all-{0,1} -> sum, default latest / mean by row count)
- POST /datasets/save accepts metric_configs and emits MetricSummary with column +
  calculation fields; backward-compatible default to 'latest' when omitted
- Calculation math (sum/mean/min/max/count/growth/latest) on the canonical 12-row CSV
- POST /datasets/remove-duplicates returns a NEW upload_id, old draft is gone, new
  draft chunks exist
- /metrics/{X}/analyze still matches by original column OR display name
"""
import io
import os
import time
import uuid

import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
API = f"{BASE_URL}/api"

EMAIL = f"TEST_cfg_{uuid.uuid4().hex[:8]}@datamind.com"
PASSWORD = "test123"

SAMPLE_CSV = (
    "month,revenue,orders,cac,churn\n"
    "Jan,42000,310,120,4.1\n"
    "Feb,38000,280,134,4.4\n"
    "Mar,55000,420,118,3.9\n"
    "Apr,61000,475,110,3.7\n"
    "May,48000,360,142,5.8\n"
    "Jun,72000,540,105,3.2\n"
    "Jul,68000,510,109,3.5\n"
    "Aug,59000,445,128,4.0\n"
    "Sep,81000,620,98,2.9\n"
    "Oct,76000,580,102,3.1\n"
    "Nov,93000,710,95,2.7\n"
    "Dec,41000,290,178,7.2\n"
)


# --------------------------- fixtures ---------------------------
@pytest.fixture(scope="module")
def token():
    requests.post(f"{API}/auth/signup", json={"email": EMAIL, "password": PASSWORD, "name": "Cfg Test"})
    r = requests.post(f"{API}/auth/login", json={"email": EMAIL, "password": PASSWORD})
    assert r.status_code == 200, r.text
    return r.json()["token"]


@pytest.fixture(scope="module")
def auth(token):
    return {"Authorization": f"Bearer {token}"}


def _upload(auth, csv_text=SAMPLE_CSV):
    files = {"file": ("test_data.csv", io.BytesIO(csv_text.encode()), "text/csv")}
    r = requests.post(f"{API}/datasets/upload", files=files, headers=auth)
    assert r.status_code == 200, r.text
    return r.json()


# --------------------------- upload + suggestions ---------------------------
class TestSuggestions:
    def test_upload_returns_suggested_configs(self, auth):
        data = _upload(auth)
        assert "suggested_metric_configs" in data
        suggs = data["suggested_metric_configs"]
        assert isinstance(suggs, list) and len(suggs) == 4  # revenue, orders, cac, churn
        for s in suggs:
            assert {"column", "suggested_display_name", "suggested_calculation", "rationale"} <= set(s)
            assert s["suggested_calculation"] in {"latest", "sum", "mean", "min", "max", "count", "growth"}

    def test_heuristics_revenue_orders_sum(self, auth):
        suggs = {s["column"]: s["suggested_calculation"] for s in _upload(auth)["suggested_metric_configs"]}
        assert suggs["revenue"] == "sum", f"revenue -> {suggs['revenue']}"
        assert suggs["orders"] == "sum", f"orders -> {suggs['orders']}"

    def test_heuristics_cac_churn_mean(self, auth):
        suggs = {s["column"]: s["suggested_calculation"] for s in _upload(auth)["suggested_metric_configs"]}
        assert suggs["cac"] == "mean"
        assert suggs["churn"] == "mean"

    def test_heuristic_id_columns_count(self, auth):
        csv = "user_id,signups\n1,10\n2,15\n3,20\n4,25\n"
        suggs = {s["column"]: s["suggested_calculation"] for s in _upload(auth, csv)["suggested_metric_configs"]}
        assert suggs["user_id"] == "count"
        assert suggs["signups"] == "sum"

    def test_heuristic_boolean_column_sum(self, auth):
        csv = "row,active\n1,0\n2,1\n3,1\n4,0\n5,1\n"
        suggs = {s["column"]: s["suggested_calculation"] for s in _upload(auth, csv)["suggested_metric_configs"]}
        assert suggs["active"] == "sum"

    def test_display_name_humanization(self, auth):
        csv = "monthly_revenue,CAC\n100,50\n200,60\n"
        suggs = {s["column"]: s["suggested_display_name"] for s in _upload(auth, csv)["suggested_metric_configs"]}
        assert suggs["monthly_revenue"] == "Monthly Revenue"
        assert suggs["CAC"] == "CAC"  # acronym preserved


# --------------------------- save with metric_configs ---------------------------
class TestSaveWithConfigs:
    def test_save_with_custom_configs(self, auth):
        up = _upload(auth)
        upload_id = up["upload_id"]
        configs = [
            {"column": "revenue", "display_name": "Total Revenue", "calculation": "sum", "enabled": True},
            {"column": "cac", "display_name": "Avg CAC", "calculation": "mean", "enabled": True},
            {"column": "churn", "display_name": "Avg Churn", "calculation": "mean", "enabled": True},
            {"column": "orders", "display_name": "Orders", "calculation": "sum", "enabled": False},
        ]
        body = {
            "upload_id": upload_id,
            "name": f"TEST_cfg_{uuid.uuid4().hex[:6]}",
            "numeric_columns": up["numeric_columns"],
            "label_columns": up["label_columns"],
            "date_columns": up.get("date_columns", []),
            "quality_score": up["score"],
            "metric_configs": configs,
        }
        r = requests.post(f"{API}/datasets/save", json=body, headers=auth)
        assert r.status_code == 200, r.text
        ds = r.json()

        # Only enabled configs become metrics
        metrics_by_col = {m["column"]: m for m in ds["metrics"]}
        assert set(metrics_by_col.keys()) == {"revenue", "cac", "churn"}, list(metrics_by_col)
        assert "orders" not in metrics_by_col

        rev = metrics_by_col["revenue"]
        assert rev["name"] == "Total Revenue"
        assert rev["calculation"] == "sum"
        assert rev["latest_value"] == pytest.approx(734000, rel=1e-4)

        cac = metrics_by_col["cac"]
        assert cac["calculation"] == "mean"
        assert cac["latest_value"] == pytest.approx(119.916666, rel=1e-3)

        churn = metrics_by_col["churn"]
        assert churn["latest_value"] == pytest.approx(4.0416666, rel=1e-3)

        # cleanup
        requests.delete(f"{API}/datasets/{ds['id']}", headers=auth)

    def test_save_backward_compat_no_configs(self, auth):
        up = _upload(auth)
        body = {
            "upload_id": up["upload_id"],
            "name": f"TEST_bc_{uuid.uuid4().hex[:6]}",
            "numeric_columns": up["numeric_columns"],
            "label_columns": up["label_columns"],
            "date_columns": up.get("date_columns", []),
            "quality_score": up["score"],
        }
        r = requests.post(f"{API}/datasets/save", json=body, headers=auth)
        assert r.status_code == 200, r.text
        ds = r.json()
        # default 'latest' for all numeric columns
        for m in ds["metrics"]:
            assert m["calculation"] == "latest"
            assert m["column"] in {"revenue", "orders", "cac", "churn"}
        # revenue latest = Dec = 41000
        rev = next(m for m in ds["metrics"] if m["column"] == "revenue")
        assert rev["latest_value"] == pytest.approx(41000)
        requests.delete(f"{API}/datasets/{ds['id']}", headers=auth)

    @pytest.mark.parametrize("calc,expected", [
        ("sum", 734000),
        ("mean", 734000 / 12),
        ("min", 38000),
        ("max", 93000),
        ("count", 12),
        ("growth", ((41000 - 42000) / 42000) * 100),  # ~-2.38%
        ("latest", 41000),
    ])
    def test_calculation_correctness(self, auth, calc, expected):
        up = _upload(auth)
        body = {
            "upload_id": up["upload_id"],
            "name": f"TEST_calc_{calc}_{uuid.uuid4().hex[:4]}",
            "numeric_columns": up["numeric_columns"],
            "label_columns": up["label_columns"],
            "date_columns": up.get("date_columns", []),
            "quality_score": up["score"],
            "metric_configs": [{"column": "revenue", "display_name": "Rev", "calculation": calc, "enabled": True}],
        }
        r = requests.post(f"{API}/datasets/save", json=body, headers=auth)
        assert r.status_code == 200, r.text
        ds = r.json()
        rev = next(m for m in ds["metrics"] if m["column"] == "revenue")
        assert rev["calculation"] == calc
        assert rev["latest_value"] == pytest.approx(expected, rel=1e-3, abs=0.5)
        requests.delete(f"{API}/datasets/{ds['id']}", headers=auth)


# --------------------------- remove duplicates returns new upload_id ---------------------------
class TestRemoveDuplicatesAtomicity:
    def test_returns_new_upload_id(self, auth):
        csv = SAMPLE_CSV + "Dec,41000,290,178,7.2\n"  # add a dup row
        up = _upload(auth, csv)
        old_id = up["upload_id"]
        assert up["duplicates_found"] >= 1

        r = requests.post(f"{API}/datasets/remove-duplicates", json={"upload_id": old_id}, headers=auth)
        assert r.status_code == 200, r.text
        body = r.json()
        new_id = body["upload_id"]
        assert new_id and new_id != old_id, f"expected new id, got same {new_id}"
        assert body["removed"] >= 1
        assert body["total_rows"] == 12

        # old draft is gone — save against old_id should 404
        save_body = {
            "upload_id": old_id, "name": "TEST_should_fail", "numeric_columns": up["numeric_columns"],
            "label_columns": up["label_columns"], "date_columns": [], "quality_score": up["score"],
        }
        r2 = requests.post(f"{API}/datasets/save", json=save_body, headers=auth)
        assert r2.status_code == 404, f"old upload_id should be gone, got {r2.status_code}"

        # new id works
        save_body["upload_id"] = new_id
        save_body["name"] = f"TEST_dedup_{uuid.uuid4().hex[:6]}"
        r3 = requests.post(f"{API}/datasets/save", json=save_body, headers=auth)
        assert r3.status_code == 200, r3.text
        requests.delete(f"{API}/datasets/{r3.json()['id']}", headers=auth)


# --------------------------- analyze endpoint backwards compat ---------------------------
class TestAnalyzeByColumnOrName:
    def test_analyze_by_column_and_display_name(self, auth):
        up = _upload(auth)
        body = {
            "upload_id": up["upload_id"],
            "name": f"TEST_an_{uuid.uuid4().hex[:6]}",
            "numeric_columns": up["numeric_columns"],
            "label_columns": up["label_columns"],
            "date_columns": [],
            "quality_score": up["score"],
            "metric_configs": [
                {"column": "revenue", "display_name": "Total Revenue", "calculation": "sum", "enabled": True}
            ],
        }
        ds = requests.post(f"{API}/datasets/save", json=body, headers=auth).json()
        ds_id = ds["id"]

        # By column (revenue)
        r1 = requests.post(
            f"{API}/metrics/revenue/analyze",
            params={"dataset_id": ds_id},
            headers=auth,
            timeout=60,
        )
        # AI may fail/slow — accept 200 OR 5xx but not 404 (route must match the column)
        assert r1.status_code != 404, f"analyze by column name should not 404: {r1.text}"

        # By display name "Total Revenue"
        r2 = requests.post(
            f"{API}/metrics/Total Revenue/analyze",
            params={"dataset_id": ds_id},
            headers=auth,
            timeout=60,
        )
        assert r2.status_code != 404, f"analyze by display name should not 404 (back-compat): {r2.text}"

        requests.delete(f"{API}/datasets/{ds_id}", headers=auth)
