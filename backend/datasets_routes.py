"""Datasets CRUD: upload, save, list, get, delete, rename, remove-duplicates, paginated rows."""
import io
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

# Chunk size for splitting cleaned_data across multiple Mongo docs to stay under
# the 16 MB BSON document limit. ~5 000 rows × ~40 cols × ~80 chars ≈ 12 MB worst-case.
CHUNK_SIZE = 5000

# Number of rows we include directly in the dataset metadata response so dashboards/charts
# load instantly without an extra round-trip. Data tab fetches the rest via /rows.
PREVIEW_ROWS = 50

MAX_ROWS = 50_000  # hard cap, matches the user-facing tip in the upload UI


def _strip_chunks_meta(rows: List[dict]) -> List[dict]:
    return [{k: v for k, v in r.items() if k not in ('_id',)} for r in rows]


async def _store_chunks(dataset_id: str, user_id: str, data: List[dict]) -> None:
    if not data:
        return
    chunks = []
    for i in range(0, len(data), CHUNK_SIZE):
        chunks.append({
            "dataset_id": dataset_id,
            "user_id": user_id,
            "chunk_index": i // CHUNK_SIZE,
            "rows": data[i:i + CHUNK_SIZE],
        })
    await db.dataset_rows.insert_many(chunks)


async def _load_rows(dataset_id: str, user_id: str, skip: int, limit: int) -> List[dict]:
    """Load `limit` rows starting at `skip` by reading only the chunks that overlap."""
    if limit <= 0:
        return []
    start_chunk = skip // CHUNK_SIZE
    end_chunk = (skip + limit - 1) // CHUNK_SIZE

    cursor = db.dataset_rows.find(
        {
            "dataset_id": dataset_id,
            "user_id": user_id,
            "chunk_index": {"$gte": start_chunk, "$lte": end_chunk},
        },
        {"_id": 0},
    ).sort("chunk_index", 1)

    rows: List[dict] = []
    async for chunk in cursor:
        rows.extend(chunk['rows'])

    local_skip = skip - start_chunk * CHUNK_SIZE
    return rows[local_skip:local_skip + limit]


@router.post("/datasets/upload")
async def upload_csv(file: UploadFile = File(...), current_user: Dict = Depends(get_current_user)):
    """Parse CSV and run the auto-cleaner; returns a quality report (does NOT save)."""
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

    return clean_and_analyze_csv(raw_data)


@router.post("/datasets/save")
async def save_dataset(request: SaveDatasetRequest, current_user: Dict = Depends(get_current_user)):
    """Persist a cleaned dataset, compute metrics + anomalies, chunk-store the rows."""
    df = pd.DataFrame(request.cleaned_data)

    anomalies = detect_anomalies(df, request.numeric_columns, request.label_columns)
    metrics = calculate_metrics(df, request.numeric_columns, request.label_columns, anomalies)

    dataset = Dataset(
        user_id=current_user['id'],
        name=request.name,
        data=request.cleaned_data[:PREVIEW_ROWS],  # only a preview lives in metadata
        original_data=[],  # full original is preserved via dataset_rows chunks
        numeric_columns=request.numeric_columns,
        label_columns=request.label_columns,
        metrics=metrics,
        anomalies=anomalies,
        quality_score=request.quality_score,
    )

    dataset_dict = dataset.model_dump()
    dataset_dict['created_at'] = dataset_dict['created_at'].isoformat()
    dataset_dict['metrics'] = [m.model_dump() for m in metrics]
    dataset_dict['anomalies'] = [a.model_dump() for a in anomalies]
    dataset_dict['total_rows'] = len(request.cleaned_data)

    await db.datasets.insert_one(dataset_dict)
    await _store_chunks(dataset.id, current_user['id'], request.cleaned_data)

    # Strip Mongo's _id (just in case) before returning to client
    dataset_dict.pop('_id', None)
    return dataset_dict


@router.get("/datasets")
async def get_datasets(current_user: Dict = Depends(get_current_user)):
    """All datasets for the current user, newest first. Strips full `data` for list view."""
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
    """Paginated row access for the Data tab."""
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


@router.post("/datasets/remove-duplicates")
async def remove_duplicates(
    request: RemoveDuplicatesRequest,
    current_user: Dict = Depends(get_current_user),
):
    df = pd.DataFrame(request.cleaned_data)
    initial_count = len(df)
    df_dedup = df.drop_duplicates().reset_index(drop=True)
    removed = initial_count - len(df_dedup)
    return {
        "cleaned_data": df_dedup.to_dict('records'),
        "removed": removed,
        "remaining": len(df_dedup),
    }


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
