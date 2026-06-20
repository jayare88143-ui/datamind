"""Datasets CRUD: upload, save, list, get, delete, rename, remove-duplicates, sample data."""
import io
from typing import Dict, List

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


@router.post("/datasets/upload")
async def upload_csv(file: UploadFile = File(...), current_user: Dict = Depends(get_current_user)):
    """Parse CSV and run the auto-cleaner; returns a quality report (does NOT save)."""
    if not file.filename.endswith('.csv'):
        raise HTTPException(status_code=400, detail="Only CSV files are allowed")

    contents = await file.read()
    try:
        df = pd.read_csv(io.BytesIO(contents))
        raw_data = df.to_dict('records')
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to parse CSV: {str(e)}")

    return clean_and_analyze_csv(raw_data)


@router.post("/datasets/save")
async def save_dataset(request: SaveDatasetRequest, current_user: Dict = Depends(get_current_user)):
    """Persist a cleaned dataset, compute metrics + anomalies, and return the saved record."""
    df = pd.DataFrame(request.cleaned_data)

    anomalies = detect_anomalies(df, request.numeric_columns, request.label_columns)
    metrics = calculate_metrics(df, request.numeric_columns, request.label_columns, anomalies)

    dataset = Dataset(
        user_id=current_user['id'],
        name=request.name,
        data=request.cleaned_data,
        original_data=request.original_data,
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

    await db.datasets.insert_one(dataset_dict)
    return dataset


@router.get("/datasets")
async def get_datasets(current_user: Dict = Depends(get_current_user)):
    """All datasets for the current user, newest first."""
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


@router.delete("/datasets/{dataset_id}")
async def delete_dataset(dataset_id: str, current_user: Dict = Depends(get_current_user)):
    result = await db.datasets.delete_one({"id": dataset_id, "user_id": current_user['id']})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Dataset not found")
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
