"""Datasets CRUD with server-side temp caching.

Upload caches the cleaned_data on the server as 'draft' chunks (TTL 1h) and returns
a small response with only metadata + a 50-row preview. Save references the upload_id
and promotes the draft chunks to committed — no need to re-send the full data over
the wire. This is critical for large CSVs (the user's 19,418-row file produced a 50MB
JSON round-trip the browser couldn't handle reliably).
"""
import io
import math
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List

import pandas as pd
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile

from analysis import calculate_metrics, clean_and_analyze_csv, detect_anomalies
from auth import get_current_user
from db import db
from models import (
    Dataset,
    RemoveDuplicatesRequest,
    RenameDatasetRequest,
    SaveDatasetRequest,
)

router = APIRouter(tags=["datasets"])

CHUNK_SIZE = 5000
PREVIEW_ROWS = 50
MAX_ROWS = 50_000


def _sanitize(obj: Any) -> Any:
    """Recursively replace NaN/Infinity floats with None so the response is valid JSON.

    pandas.to_dict('records') yields float('nan') for missing numerics, which the
    stdlib json encoder rejects. Pydantic models handle this via jsonable_encoder,
    but we're returning a hand-rolled dict from /upload so we sanitize ourselves.
    """
    if isinstance(obj, float):
        if math.isnan(obj) or math.isinf(obj):
            return None
        return obj
    if isinstance(obj, dict):
        return {k: _sanitize(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_sanitize(v) for v in obj]
    return obj


async def _store_chunks(
    dataset_id: str,
    user_id: str,
    data: List[dict],
    status: str = "committed",
) -> None:
    """Persist rows split into CHUNK_SIZE-sized documents.

    `status="draft"` is paired with the TTL index in db.py so untouched uploads
    expire automatically; we strip the field when promoting to committed.
    """
    if not data:
        return
    now = datetime.now(timezone.utc)
    chunks = []
    for i in range(0, len(data), CHUNK_SIZE):
        chunk = {
            "dataset_id": dataset_id,
            "user_id": user_id,
            "chunk_index": i // CHUNK_SIZE,
            "rows": data[i:i + CHUNK_SIZE],
        }
        if status == "draft":
            chunk["status"] = "draft"
            chunk["created_at"] = now
        chunks.append(chunk)
    await db.dataset_rows.insert_many(chunks)


async def _load_all_draft_rows(upload_id: str, user_id: str) -> List[dict]:
    """Fetch the full cached payload for an upload_id. Raises 404 if expired/missing."""
    cursor = db.dataset_rows.find(
        {"dataset_id": upload_id, "user_id": user_id, "status": "draft"},
        {"_id": 0},
    ).sort("chunk_index", 1)

    rows: List[dict] = []
    async for chunk in cursor:
        rows.extend(chunk["rows"])

    if not rows:
        raise HTTPException(
            status_code=404,
            detail="Upload session not found or expired. Please re-upload the file.",
        )
    return rows


async def _load_rows(dataset_id: str, user_id: str, skip: int, limit: int) -> List[dict]:
    """Paginated row reader (Data tab). Reads only chunks overlapping the requested range."""
    if limit <= 0:
        return []
    start_chunk = skip // CHUNK_SIZE
    end_chunk = (skip + limit - 1) // CHUNK_SIZE

    cursor = db.dataset_rows.find(
        {
            "dataset_id": dataset_id,
            "user_id": user_id,
            "chunk_index": {"$gte": start_chunk, "$lte": end_chunk},
            "status": {"$ne": "draft"},  # exclude in-flight uploads
        },
        {"_id": 0},
    ).sort("chunk_index", 1)

    rows: List[dict] = []
    async for chunk in cursor:
        rows.extend(chunk["rows"])

    local_skip = skip - start_chunk * CHUNK_SIZE
    return rows[local_skip:local_skip + limit]


@router.post("/datasets/upload")
async def upload_csv(file: UploadFile = File(...), current_user: Dict = Depends(get_current_user)):
    """Parse + auto-clean a CSV, cache the cleaned data server-side, return a small report.

    Response shape (never includes the full cleaned_data):
      { upload_id, score, issues, rows_removed, duplicates_found, numeric_columns,
        label_columns, date_columns, total_rows, preview_data: <=50 rows }
    """
    if not file.filename.endswith('.csv'):
        raise HTTPException(status_code=400, detail="Only CSV files are allowed")

    contents = await file.read()
    try:
        df = pd.read_csv(io.BytesIO(contents), low_memory=False)
        raw_data = df.to_dict('records')
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to parse CSV: {str(e)}")

    if len(raw_data) > MAX_ROWS:
        raise HTTPException(
            status_code=413,
            detail=(
                f"This file has {len(raw_data):,} rows. For best results, upload up to "
                f"~{MAX_ROWS:,} rows or summarize your data first (e.g. daily/monthly "
                "totals instead of every transaction)."
            ),
        )

    report = clean_and_analyze_csv(raw_data)

    upload_id = str(uuid.uuid4())
    # Sanitize before storing so chunks read back later are also JSON-safe
    safe_cleaned = _sanitize(report.cleaned_data)
    await _store_chunks(upload_id, current_user['id'], safe_cleaned, status="draft")

    return {
        "upload_id": upload_id,
        "score": report.score,
        "issues": [i.model_dump() for i in report.issues],
        "rows_removed": report.rows_removed,
        "duplicates_found": report.duplicates_found,
        "numeric_columns": report.numeric_columns,
        "label_columns": report.label_columns,
        "date_columns": report.date_columns,
        "total_rows": len(safe_cleaned),
        "preview_data": safe_cleaned[:PREVIEW_ROWS],
    }


@router.post("/datasets/save")
async def save_dataset(request: SaveDatasetRequest, current_user: Dict = Depends(get_current_user)):
    """Promote a draft upload to a permanent dataset.

    Loads the cached rows by `upload_id`, computes metrics + anomalies, writes the
    dataset metadata document, and flips the chunk status from draft → committed
    (in place — no copy). Idempotent on the chunk side: if the dataset already
    exists for this upload_id we 409.
    """
    existing = await db.datasets.find_one({"id": request.upload_id})
    if existing:
        raise HTTPException(status_code=409, detail="This upload has already been saved")

    cleaned_data = await _load_all_draft_rows(request.upload_id, current_user['id'])
    df = pd.DataFrame(cleaned_data)

    anomalies = detect_anomalies(df, request.numeric_columns, request.label_columns)
    metrics = calculate_metrics(df, request.numeric_columns, request.label_columns, anomalies)

    dataset = Dataset(
        id=request.upload_id,  # reuse the upload_id so chunks already point to us
        user_id=current_user['id'],
        name=request.name,
        data=cleaned_data[:PREVIEW_ROWS],
        original_data=[],
        numeric_columns=request.numeric_columns,
        label_columns=request.label_columns,
        date_columns=request.date_columns,
        metrics=metrics,
        anomalies=anomalies,
        quality_score=request.quality_score,
    )

    dataset_dict = dataset.model_dump()
    dataset_dict['created_at'] = dataset_dict['created_at'].isoformat()
    dataset_dict['metrics'] = [m.model_dump() for m in metrics]
    dataset_dict['anomalies'] = [a.model_dump() for a in anomalies]
    dataset_dict['total_rows'] = len(cleaned_data)

    await db.datasets.insert_one(dataset_dict)

    # Promote draft chunks → committed (TTL no longer applies because the filter is on status)
    await db.dataset_rows.update_many(
        {"dataset_id": request.upload_id, "user_id": current_user['id'], "status": "draft"},
        {"$unset": {"status": "", "created_at": ""}},
    )

    dataset_dict.pop('_id', None)
    return dataset_dict


@router.post("/datasets/remove-duplicates")
async def remove_duplicates(
    request: RemoveDuplicatesRequest,
    current_user: Dict = Depends(get_current_user),
):
    """Run dedupe on the server-side draft data and rewrite the chunks in place."""
    cleaned_data = await _load_all_draft_rows(request.upload_id, current_user['id'])
    df = pd.DataFrame(cleaned_data)
    initial = len(df)
    df_dedup = df.drop_duplicates().reset_index(drop=True)
    deduped_rows = _sanitize(df_dedup.to_dict('records'))
    removed = initial - len(deduped_rows)

    # Replace draft chunks atomically-ish: delete then re-insert
    await db.dataset_rows.delete_many(
        {"dataset_id": request.upload_id, "user_id": current_user['id'], "status": "draft"},
    )
    await _store_chunks(request.upload_id, current_user['id'], deduped_rows, status="draft")

    return {
        "removed": removed,
        "remaining": len(deduped_rows),
        "preview_data": deduped_rows[:PREVIEW_ROWS],
        "total_rows": len(deduped_rows),
    }


@router.get("/datasets")
async def get_datasets(current_user: Dict = Depends(get_current_user)):
    datasets = await db.datasets.find(
        {"user_id": current_user['id']},
        {"_id": 0},
    ).sort("created_at", -1).to_list(100)
    return datasets


@router.get("/datasets/{dataset_id}")
async def get_dataset(dataset_id: str, current_user: Dict = Depends(get_current_user)):
    dataset = await db.datasets.find_one({"id": dataset_id, "user_id": current_user['id']}, {"_id": 0})
    if not dataset:
        raise HTTPException(status_code=404, detail="Dataset not found")
    return dataset


@router.get("/datasets/{dataset_id}/rows")
async def get_dataset_rows(
    dataset_id: str,
    skip: int = 0,
    limit: int = 50,
    current_user: Dict = Depends(get_current_user),
):
    if limit > 500:
        limit = 500
    dataset = await db.datasets.find_one(
        {"id": dataset_id, "user_id": current_user['id']},
        {"_id": 0, "total_rows": 1},
    )
    if not dataset:
        raise HTTPException(status_code=404, detail="Dataset not found")

    rows = await _load_rows(dataset_id, current_user['id'], skip, limit)
    return {
        "rows": rows,
        "total": dataset.get('total_rows', 0),
        "skip": skip,
        "limit": limit,
    }


@router.delete("/datasets/{dataset_id}")
async def delete_dataset(dataset_id: str, current_user: Dict = Depends(get_current_user)):
    result = await db.datasets.delete_one({"id": dataset_id, "user_id": current_user['id']})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Dataset not found")
    await db.dataset_rows.delete_many({"dataset_id": dataset_id, "user_id": current_user['id']})
    await db.chat_messages.delete_many({"dataset_id": dataset_id, "user_id": current_user['id']})
    return {"message": "Dataset deleted"}


@router.patch("/datasets/{dataset_id}/rename")
async def rename_dataset(
    dataset_id: str,
    request: RenameDatasetRequest,
    current_user: Dict = Depends(get_current_user),
):
    result = await db.datasets.update_one(
        {"id": dataset_id, "user_id": current_user['id']},
        {"$set": {"name": request.name}},
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Dataset not found")
    return {"message": "Dataset renamed", "name": request.name}


@router.get("/datasets/sample/data")
async def get_sample_data():
    """Built-in 12-month business sample for the Try Sample Data button."""
    return [
        {"month": "Jan", "revenue": 42000, "orders": 310, "cac": 120, "churn": 4.1},
        {"month": "Feb", "revenue": 38000, "orders": 280, "cac": 134, "churn": 4.4},
        {"month": "Mar", "revenue": 55000, "orders": 420, "cac": 118, "churn": 3.9},
        {"month": "Apr", "revenue": 61000, "orders": 475, "cac": 110, "churn": 3.7},
        {"month": "May", "revenue": 48000, "orders": 360, "cac": 142, "churn": 5.8},
        {"month": "Jun", "revenue": 72000, "orders": 540, "cac": 105, "churn": 3.2},
        {"month": "Jul", "revenue": 68000, "orders": 510, "cac": 109, "churn": 3.5},
        {"month": "Aug", "revenue": 59000, "orders": 445, "cac": 128, "churn": 4.0},
        {"month": "Sep", "revenue": 81000, "orders": 620, "cac": 98, "churn": 2.9},
        {"month": "Oct", "revenue": 76000, "orders": 580, "cac": 102, "churn": 3.1},
        {"month": "Nov", "revenue": 93000, "orders": 710, "cac": 95, "churn": 2.7},
        {"month": "Dec", "revenue": 41000, "orders": 290, "cac": 178, "churn": 7.2},
    ]
