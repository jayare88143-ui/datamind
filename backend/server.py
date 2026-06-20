from fastapi import FastAPI, APIRouter, HTTPException, Depends, File, UploadFile, status
from fastapi.responses import StreamingResponse
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import os
import logging
from pathlib import Path
from pydantic import BaseModel, Field, ConfigDict, EmailStr
from typing import List, Optional, Dict, Any
import uuid
from datetime import datetime, timezone, timedelta
import pandas as pd
import numpy as np
from scipy import stats
import io
import json
from passlib.context import CryptContext
import jwt
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from emergentintegrations.llm.chat import LlmChat, UserMessage, TextDelta, StreamDone
import asyncio

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

# MongoDB connection
mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]

# JWT & Password
JWT_SECRET = os.environ['JWT_SECRET_KEY']
ALGORITHM = "HS256"
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
security = HTTPBearer()

# Create the main app
app = FastAPI()
api_router = APIRouter(prefix="/api")

# ============= MODELS =============

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

class DataQualityIssue(BaseModel):
    type: str  # "success", "warning", "error"
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

class Anomaly(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    metric: str
    value: float
    expected_range: str
    z_score: float
    severity: str  # "Critical" or "Warning"
    row_index: int
    label: str

class MetricSummary(BaseModel):
    name: str
    latest_value: float
    mom_change: Optional[float]
    trend: str
    trend_percent: float
    values: List[float]
    labels: List[str]
    mean: float
    std_dev: float
    anomalies: List[Anomaly]

class Dataset(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    user_id: str
    name: str
    data: List[Dict[str, Any]]
    original_data: List[Dict[str, Any]]
    numeric_columns: List[str]
    label_columns: List[str]
    metrics: List[MetricSummary]
    anomalies: List[Anomaly]
    quality_score: int
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class ChatMessage(BaseModel):
    role: str  # "user" or "assistant"
    content: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class ChatRequest(BaseModel):
    message: str
    dataset_id: str

class SaveDatasetRequest(BaseModel):
    name: str
    cleaned_data: List[Dict[str, Any]]
    original_data: List[Dict[str, Any]]
    numeric_columns: List[str]
    label_columns: List[str]
    quality_score: int

# ============= AUTH HELPERS =============

def hash_password(password: str) -> str:
    return pwd_context.hash(password)

def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)

def create_token(user_id: str, email: str) -> str:
    payload = {
        "user_id": user_id,
        "email": email,
        "exp": datetime.now(timezone.utc) + timedelta(days=30)
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=ALGORITHM)

async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)) -> Dict:
    try:
        token = credentials.credentials
        payload = jwt.decode(token, JWT_SECRET, algorithms=[ALGORITHM])
        user = await db.users.find_one({"id": payload["user_id"]}, {"_id": 0})
        if not user:
            raise HTTPException(status_code=401, detail="User not found")
        return user
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid token")

# ============= DATA PROCESSING =============

def clean_and_analyze_csv(raw_data: List[Dict]) -> DataQualityReport:
    """Clean CSV data and generate quality report"""
    df = pd.DataFrame(raw_data)
    original_data = raw_data.copy()
    issues = []
    score = 100
    rows_removed = 0
    
    # Remove completely empty rows
    initial_rows = len(df)
    df = df.dropna(how='all')
    rows_removed = initial_rows - len(df)
    if rows_removed > 0:
        issues.append(DataQualityIssue(type="warning", message=f"Removed {rows_removed} completely empty rows"))
        score -= 5
    
    # Remove completely empty columns
    df = df.dropna(axis=1, how='all')
    
    # Trim whitespace from string columns
    for col in df.select_dtypes(include=['object']).columns:
        df[col] = df[col].astype(str).str.strip()
    
    # Detect duplicates
    duplicates = df.duplicated().sum()
    if duplicates > 0:
        issues.append(DataQualityIssue(type="warning", message=f"Found {duplicates} duplicate rows (not auto-removed)"))
        score -= 10
    
    # Detect and separate numeric vs label columns
    numeric_columns = []
    label_columns = []
    
    for col in df.columns:
        # Try to convert to numeric
        try:
            # Clean common numeric patterns
            test_series = df[col].astype(str).str.replace('$', '').str.replace(',', '')
            pd.to_numeric(test_series, errors='raise')
            df[col] = pd.to_numeric(df[col].astype(str).str.replace('$', '').str.replace(',', ''), errors='coerce')
            numeric_columns.append(col)
        except:
            label_columns.append(col)
    
    # Check for missing values in numeric columns
    for col in numeric_columns:
        missing = df[col].isna().sum()
        if missing > 0:
            issues.append(DataQualityIssue(type="error", message=f"Column '{col}' has {missing} missing numeric values"))
            score -= 15
    
    # Success messages
    if rows_removed == 0:
        issues.append(DataQualityIssue(type="success", message="No empty rows found"))
    if duplicates == 0:
        issues.append(DataQualityIssue(type="success", message="No duplicate rows found"))
    if len(numeric_columns) > 0:
        issues.append(DataQualityIssue(type="success", message=f"All {len(numeric_columns)} numeric columns valid"))
    
    score = max(0, score)
    
    return DataQualityReport(
        score=score,
        issues=issues,
        rows_removed=rows_removed,
        duplicates_found=duplicates,
        cleaned_data=df.to_dict('records'),
        original_data=original_data,
        numeric_columns=numeric_columns,
        label_columns=label_columns
    )

def detect_anomalies(df: pd.DataFrame, numeric_columns: List[str], label_columns: List[str]) -> List[Anomaly]:
    """Detect anomalies using z-score method"""
    anomalies = []
    
    for col in numeric_columns:
        values = df[col].dropna()
        if len(values) < 3:
            continue
        
        mean = values.mean()
        std = values.std()
        
        if std == 0:
            continue
        
        for idx, val in enumerate(df[col]):
            if pd.isna(val):
                continue
            
            z_score = abs((val - mean) / std)
            
            if z_score >= 1.8:
                # Get label for this row
                label_val = df.iloc[idx][label_columns[0]] if label_columns else f"Row {idx}"
                
                severity = "Critical" if z_score >= 2.2 else "Warning"
                anomalies.append(Anomaly(
                    metric=col,
                    value=float(val),
                    expected_range=f"{mean-2*std:.1f} - {mean+2*std:.1f}",
                    z_score=float(z_score),
                    severity=severity,
                    row_index=idx,
                    label=str(label_val)
                ))
    
    # Sort by severity and z_score
    anomalies.sort(key=lambda x: (0 if x.severity == "Critical" else 1, -x.z_score))
    return anomalies

def calculate_metrics(df: pd.DataFrame, numeric_columns: List[str], label_columns: List[str], anomalies: List[Anomaly]) -> List[MetricSummary]:
    """Calculate metric summaries with trends"""
    metrics = []
    
    labels = df[label_columns[0]].astype(str).tolist() if label_columns else [f"Row {i}" for i in range(len(df))]
    
    for col in numeric_columns:
        values = df[col].fillna(0).tolist()
        
        if len(values) == 0:
            continue
        
        latest = values[-1]
        mom_change = None
        
        # Calculate month-over-month change
        if len(values) >= 2 and values[-2] != 0:
            mom_change = ((values[-1] - values[-2]) / values[-2]) * 100
        
        # Calculate trend
        if len(values) >= 2:
            trend_slope = np.mean(np.diff(values))
            if abs(trend_slope) < 0.01 * abs(np.mean(values)):
                trend = "flat"
                trend_percent = 0
            elif trend_slope > 0:
                trend = "up"
                trend_percent = (trend_slope / np.mean(values)) * 100 if np.mean(values) != 0 else 0
            else:
                trend = "down"
                trend_percent = (trend_slope / np.mean(values)) * 100 if np.mean(values) != 0 else 0
        else:
            trend = "flat"
            trend_percent = 0
        
        mean_val = np.mean(values)
        std_val = np.std(values)
        
        # Get anomalies for this metric
        metric_anomalies = [a for a in anomalies if a.metric == col]
        
        metrics.append(MetricSummary(
            name=col,
            latest_value=float(latest),
            mom_change=float(mom_change) if mom_change is not None else None,
            trend=trend,
            trend_percent=float(trend_percent),
            values=[float(v) for v in values],
            labels=labels,
            mean=float(mean_val),
            std_dev=float(std_val),
            anomalies=metric_anomalies
        ))
    
    return metrics

# ============= API ROUTES =============

@api_router.post("/auth/signup")
async def signup(user_data: UserCreate):
    # Check if user exists
    existing = await db.users.find_one({"email": user_data.email})
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")
    
    user = User(
        email=user_data.email,
        name=user_data.name
    )
    
    user_dict = user.model_dump()
    user_dict['password'] = hash_password(user_data.password)
    user_dict['created_at'] = user_dict['created_at'].isoformat()
    
    await db.users.insert_one(user_dict)
    
    token = create_token(user.id, user.email)
    return {"token": token, "user": user}

@api_router.post("/auth/login")
async def login(credentials: UserLogin):
    user = await db.users.find_one({"email": credentials.email}, {"_id": 0})
    if not user or not verify_password(credentials.password, user['password']):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    
    token = create_token(user['id'], user['email'])
    user_obj = User(**user)
    return {"token": token, "user": user_obj}

@api_router.get("/auth/me")
async def get_me(current_user: Dict = Depends(get_current_user)):
    return User(**current_user)

@api_router.post("/datasets/upload")
async def upload_csv(file: UploadFile = File(...), current_user: Dict = Depends(get_current_user)):
    """Upload and process CSV file"""
    if not file.filename.endswith('.csv'):
        raise HTTPException(status_code=400, detail="Only CSV files are allowed")
    
    contents = await file.read()
    
    try:
        df = pd.read_csv(io.BytesIO(contents))
        raw_data = df.to_dict('records')
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to parse CSV: {str(e)}")
    
    # Clean and analyze
    quality_report = clean_and_analyze_csv(raw_data)
    
    return quality_report

@api_router.post("/datasets/save")
async def save_dataset(
    request: SaveDatasetRequest,
    current_user: Dict = Depends(get_current_user)
):
    """Save processed dataset"""
    df = pd.DataFrame(request.cleaned_data)
    
    # Detect anomalies
    anomalies = detect_anomalies(df, request.numeric_columns, request.label_columns)
    
    # Calculate metrics
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
        quality_score=request.quality_score
    )
    
    dataset_dict = dataset.model_dump()
    dataset_dict['created_at'] = dataset_dict['created_at'].isoformat()
    
    # Convert nested models to dicts
    dataset_dict['metrics'] = [m.model_dump() for m in metrics]
    dataset_dict['anomalies'] = [a.model_dump() for a in anomalies]
    
    await db.datasets.insert_one(dataset_dict)
    
    return dataset

@api_router.get("/datasets")
async def get_datasets(current_user: Dict = Depends(get_current_user)):
    """Get all datasets for current user"""
    datasets = await db.datasets.find({"user_id": current_user['id']}, {"_id": 0}).to_list(100)
    return datasets

@api_router.get("/datasets/{dataset_id}")
async def get_dataset(dataset_id: str, current_user: Dict = Depends(get_current_user)):
    """Get specific dataset"""
    dataset = await db.datasets.find_one({"id": dataset_id, "user_id": current_user['id']}, {"_id": 0})
    if not dataset:
        raise HTTPException(status_code=404, detail="Dataset not found")
    return dataset

@api_router.delete("/datasets/{dataset_id}")
async def delete_dataset(dataset_id: str, current_user: Dict = Depends(get_current_user)):
    """Delete dataset"""
    result = await db.datasets.delete_one({"id": dataset_id, "user_id": current_user['id']})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Dataset not found")
    return {"message": "Dataset deleted"}

@api_router.get("/datasets/sample/data")
async def get_sample_data():
    """Return sample business data"""
    sample = [
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
        {"month": "Dec", "revenue": 41000, "orders": 290, "cac": 178, "churn": 7.2}
    ]
    return sample

@api_router.post("/chat/stream")
async def chat_stream(request: ChatRequest, current_user: Dict = Depends(get_current_user)):
    """Stream AI chat response"""
    dataset = await db.datasets.find_one({"id": request.dataset_id, "user_id": current_user['id']}, {"_id": 0})
    if not dataset:
        raise HTTPException(status_code=404, detail="Dataset not found")
    
    # Prepare context for AI
    metrics_summary = ""
    for metric in dataset['metrics']:
        metrics_summary += f"\n- {metric['name']}: mean={metric['mean']:.1f}, std={metric['std_dev']:.1f}, trend={metric['trend']} ({metric['trend_percent']:.1f}% per period)"
    
    anomalies_summary = ""
    for anomaly in dataset['anomalies'][:10]:
        anomalies_summary += f"\n- {anomaly['severity']}: {anomaly['metric']}={anomaly['value']} at {anomaly['label']} (z-score: {anomaly['z_score']:.2f})"
    
    data_sample = json.dumps(dataset['data'][:10], indent=2)
    
    system_message = f"""You are an AI data analyst for DataMind. Analyze business data and provide clear, actionable insights.

DATASET CONTEXT:
Numeric columns: {', '.join(dataset['numeric_columns'])}
Label columns: {', '.join(dataset['label_columns'])}

METRICS SUMMARY:{metrics_summary}

DETECTED ANOMALIES:{anomalies_summary}

FIRST 10 ROWS:
{data_sample}

Provide concise answers. Bold key numbers using **text**. End with one actionable recommendation."""
    
    async def generate():
        try:
            chat = LlmChat(
                api_key=os.environ['EMERGENT_LLM_KEY'],
                session_id=f"chat_{request.dataset_id}_{current_user['id']}",
                system_message=system_message
            ).with_model("anthropic", "claude-sonnet-4-6")
            
            user_message = UserMessage(text=request.message)
            
            async for event in chat.stream_message(user_message):
                if isinstance(event, TextDelta):
                    yield f"data: {json.dumps({'content': event.content})}\n\n"
                elif isinstance(event, StreamDone):
                    yield f"data: {json.dumps({'done': True})}\n\n"
                    break
        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)})}\n\n"
    
    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no"
        }
    )

@api_router.post("/metrics/{metric_name}/analyze")
async def analyze_metric(
    metric_name: str,
    dataset_id: str,
    current_user: Dict = Depends(get_current_user)
):
    """Get AI deep-dive analysis for a specific metric"""
    dataset = await db.datasets.find_one({"id": dataset_id, "user_id": current_user['id']}, {"_id": 0})
    if not dataset:
        raise HTTPException(status_code=404, detail="Dataset not found")
    
    # Find the metric
    metric = next((m for m in dataset['metrics'] if m['name'] == metric_name), None)
    if not metric:
        raise HTTPException(status_code=404, detail="Metric not found")
    
    # Prepare focused context
    anomalies_text = ""
    for anomaly in metric['anomalies']:
        anomalies_text += f"\n- {anomaly['severity']}: {anomaly['value']} at {anomaly['label']} (z-score: {anomaly['z_score']:.2f})"
    
    system_message = f"""You are an AI data analyst providing a focused analysis of the metric '{metric_name}'.

METRIC DATA:
- Values: {metric['values']}
- Labels: {metric['labels']}
- Mean: {metric['mean']:.1f}
- Std Dev: {metric['std_dev']:.1f}
- Trend: {metric['trend']} ({metric['trend_percent']:.1f}% per period)
- Latest: {metric['latest_value']}

ANOMALIES:{anomalies_text if anomalies_text else ' None detected'}

Provide:
1. A trend summary
2. What's unusual and likely why
3. The risk if it continues
4. 2-3 recommended actions

Be concise and bold key numbers."""
    
    async def generate():
        try:
            chat = LlmChat(
                api_key=os.environ['EMERGENT_LLM_KEY'],
                session_id=f"analysis_{metric_name}_{dataset_id}",
                system_message=system_message
            ).with_model("anthropic", "claude-sonnet-4-6")
            
            user_message = UserMessage(text=f"Analyze the {metric_name} metric and provide actionable insights.")
            
            async for event in chat.stream_message(user_message):
                if isinstance(event, TextDelta):
                    yield f"data: {json.dumps({'content': event.content})}\n\n"
                elif isinstance(event, StreamDone):
                    yield f"data: {json.dumps({'done': True})}\n\n"
                    break
        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)})}\n\n"
    
    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no"
        }
    )

# Include router
app.include_router(api_router)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get('CORS_ORIGINS', '*').split(','),
    allow_methods=["*"],
    allow_headers=["*"],
)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()
