"""Pydantic models shared across modules."""
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import uuid

from pydantic import BaseModel, ConfigDict, EmailStr, Field


# ===== Auth =====
class UserCreate(BaseModel):
    email: EmailStr
    password: str
    name: str


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class User(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    email: str
    name: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# ===== Quality / Data =====
class DataQualityIssue(BaseModel):
    type: str  # "success" | "warning" | "error"
    message: str


class DataQualityReport(BaseModel):
    score: int
    issues: List[DataQualityIssue]
    rows_removed: int
    duplicates_found: int
    cleaned_data: List[Dict[str, Any]]
    original_data: List[Dict[str, Any]]
    numeric_columns: List[str]
    label_columns: List[str]
    date_columns: List[str] = []


class Anomaly(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    metric: str
    value: float
    expected_range: str
    z_score: float
    severity: str  # "Critical" | "Warning"
    row_index: int
    label: str


class MetricSummary(BaseModel):
    name: str  # display name (user-customizable)
    column: str = ''  # original CSV column (immutable; used for AI deep-dive URL)
    calculation: str = 'latest'  # 'latest' | 'sum' | 'mean' | 'min' | 'max' | 'count' | 'growth'
    latest_value: float
    mom_change: Optional[float]
    trend: str
    trend_percent: float
    values: List[float]
    labels: List[str]
    mean: float
    std_dev: float
    anomalies: List[Anomaly]


class MetricConfig(BaseModel):
    """Per-metric user configuration set on the ConfigureMetrics screen.

    Two flavours:
    1. Single-column metric — set `column` + `calculation`.
    2. Custom formula metric (PowerBI/Tableau-style) — set `formula` like
       `revenue / orders` or `revenue - cac * orders`. The formula is evaluated
       per row, then reduced to one headline number by `calculation`.
    """
    display_name: str
    enabled: bool = True
    column: Optional[str] = None
    calculation: str = 'latest'
    formula: Optional[str] = None  # if set, takes precedence over `column`


class SuggestedMetricConfig(BaseModel):
    """What the server recommends. Frontend pre-fills the form with these."""
    column: Optional[str] = None
    formula: Optional[str] = None  # set for cross-column suggestions
    suggested_display_name: str
    suggested_calculation: str
    rationale: str


class Dataset(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    user_id: str
    name: str
    data: List[Dict[str, Any]]
    original_data: List[Dict[str, Any]]
    numeric_columns: List[str]
    label_columns: List[str]
    date_columns: List[str] = []
    metrics: List[MetricSummary]
    anomalies: List[Anomaly]
    quality_score: int
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# ===== Chat =====
class ChatRequest(BaseModel):
    message: str
    dataset_id: str


class ChatMessageSave(BaseModel):
    dataset_id: str
    role: str
    content: str


# ===== Mutations =====
class SaveDatasetRequest(BaseModel):
    """New (preferred) save flow: provide upload_id from a recent /upload call.

    Avoids re-sending the (potentially huge) cleaned_data over the wire — the server
    already has it cached as draft chunks from the upload.
    """
    upload_id: str
    name: str
    numeric_columns: List[str]
    label_columns: List[str]
    date_columns: List[str] = []
    quality_score: int
    metric_configs: Optional[List["MetricConfig"]] = None  # noqa: F821 - forward ref


class RenameDatasetRequest(BaseModel):
    name: str


class RemoveDuplicatesRequest(BaseModel):
    """Operates on the server-side draft chunks identified by upload_id."""
    upload_id: str
