"""AI chat + metric deep-dive endpoints using Claude Sonnet 4.6 (SSE streaming)."""
import json
import os
import uuid
from datetime import datetime, timezone
from typing import Dict

from emergentintegrations.llm.chat import LlmChat, StreamDone, TextDelta, UserMessage
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from auth import get_current_user
from db import db
from models import ChatMessageSave, ChatRequest

router = APIRouter(tags=["chat"])

_SSE_HEADERS = {"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}


def _build_system_message(dataset: dict) -> str:
    metrics_summary = "".join(
        f"\n- {m['name']}: mean={m['mean']:.1f}, std={m['std_dev']:.1f}, "
        f"trend={m['trend']} ({m['trend_percent']:.1f}% per period)"
        for m in dataset['metrics']
    )
    anomalies_summary = "".join(
        f"\n- {a['severity']}: {a['metric']}={a['value']} at {a['label']} (z-score: {a['z_score']:.2f})"
        for a in dataset['anomalies'][:10]
    )
    data_sample = json.dumps(dataset['data'][:10], indent=2, default=str)

    return f"""You are an AI data analyst for DataMind. Analyze business data and provide clear, actionable insights.

DATASET CONTEXT:
Numeric columns: {', '.join(dataset['numeric_columns'])}
Label columns: {', '.join(dataset['label_columns'])}

METRICS SUMMARY:{metrics_summary}

DETECTED ANOMALIES:{anomalies_summary}

FIRST 10 ROWS:
{data_sample}

Provide concise answers. Bold key numbers using **text**. End with one actionable recommendation."""


def _stream_claude(session_id: str, system_message: str, user_text: str):
    async def generate():
        try:
            chat = LlmChat(
                api_key=os.environ['EMERGENT_LLM_KEY'],
                session_id=session_id,
                system_message=system_message,
            ).with_model("anthropic", "claude-sonnet-4-6")

            async for event in chat.stream_message(UserMessage(text=user_text)):
                if isinstance(event, TextDelta):
                    yield f"data: {json.dumps({'content': event.content})}\n\n"
                elif isinstance(event, StreamDone):
                    yield f"data: {json.dumps({'done': True})}\n\n"
                    break
        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)})}\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream", headers=_SSE_HEADERS)


@router.post("/chat/stream")
async def chat_stream(request: ChatRequest, current_user: Dict = Depends(get_current_user)):
    dataset = await db.datasets.find_one(
        {"id": request.dataset_id, "user_id": current_user['id']},
        {"_id": 0},
    )
    if not dataset:
        raise HTTPException(status_code=404, detail="Dataset not found")

    return _stream_claude(
        session_id=f"chat_{request.dataset_id}_{current_user['id']}",
        system_message=_build_system_message(dataset),
        user_text=request.message,
    )


@router.post("/metrics/{metric_name}/analyze")
async def analyze_metric(
    metric_name: str,
    dataset_id: str,
    current_user: Dict = Depends(get_current_user),
):
    dataset = await db.datasets.find_one(
        {"id": dataset_id, "user_id": current_user['id']},
        {"_id": 0},
    )
    if not dataset:
        raise HTTPException(status_code=404, detail="Dataset not found")

    # Match by `column` (immutable CSV header) OR `name` (legacy/display) for back-compat
    metric = next(
        (m for m in dataset['metrics']
         if m.get('column') == metric_name or m.get('name') == metric_name),
        None,
    )
    if not metric:
        raise HTTPException(status_code=404, detail="Metric not found")

    anomalies_text = "".join(
        f"\n- {a['severity']}: {a['value']} at {a['label']} (z-score: {a['z_score']:.2f})"
        for a in metric['anomalies']
    ) or " None detected"

    system_message = f"""You are an AI data analyst providing a focused analysis of the metric '{metric_name}'.

METRIC DATA:
- Values: {metric['values']}
- Labels: {metric['labels']}
- Mean: {metric['mean']:.1f}
- Std Dev: {metric['std_dev']:.1f}
- Trend: {metric['trend']} ({metric['trend_percent']:.1f}% per period)
- Latest: {metric['latest_value']}

ANOMALIES:{anomalies_text}

Provide:
1. A trend summary
2. What's unusual and likely why
3. The risk if it continues
4. 2-3 recommended actions

Be concise and bold key numbers."""

    return _stream_claude(
        session_id=f"analysis_{metric_name}_{dataset_id}",
        system_message=system_message,
        user_text=f"Analyze the {metric_name} metric and provide actionable insights.",
    )


@router.get("/chat/history/{dataset_id}")
async def get_chat_history(dataset_id: str, current_user: Dict = Depends(get_current_user)):
    dataset = await db.datasets.find_one({"id": dataset_id, "user_id": current_user['id']}, {"_id": 0})
    if not dataset:
        raise HTTPException(status_code=404, detail="Dataset not found")

    messages = await db.chat_messages.find(
        {"dataset_id": dataset_id, "user_id": current_user['id']},
        {"_id": 0},
    ).sort("timestamp", 1).to_list(500)
    return messages


@router.post("/chat/save")
async def save_chat_message(message: ChatMessageSave, current_user: Dict = Depends(get_current_user)):
    doc = {
        "id": str(uuid.uuid4()),
        "user_id": current_user['id'],
        "dataset_id": message.dataset_id,
        "role": message.role,
        "content": message.content,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    await db.chat_messages.insert_one(doc)
    return {"message": "Saved", "id": doc["id"]}


@router.delete("/chat/history/{dataset_id}")
async def clear_chat_history(dataset_id: str, current_user: Dict = Depends(get_current_user)):
    await db.chat_messages.delete_many({"dataset_id": dataset_id, "user_id": current_user['id']})
    return {"message": "History cleared"}
