"""DataMind API - FastAPI app entry point.

Composes the auth/datasets/chat routers and wires CORS + MongoDB indexes.
"""
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from fastapi import APIRouter, FastAPI
from starlette.middleware.cors import CORSMiddleware

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

# Import after load_dotenv so module-level env reads succeed
from auth import router as auth_router  # noqa: E402
from chat_routes import router as chat_router  # noqa: E402
from datasets_routes import router as datasets_router  # noqa: E402
from db import client, ensure_indexes  # noqa: E402


@asynccontextmanager
async def lifespan(app: FastAPI):
    await ensure_indexes()
    yield
    client.close()


app = FastAPI(lifespan=lifespan)

api_router = APIRouter(prefix="/api")
api_router.include_router(auth_router)
api_router.include_router(datasets_router)
api_router.include_router(chat_router)

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
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
)
logger = logging.getLogger(__name__)
