"""MongoDB connection and lifespan setup."""
import logging
import os
from motor.motor_asyncio import AsyncIOMotorClient

logger = logging.getLogger(__name__)

mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]


async def ensure_indexes() -> None:
    """Create MongoDB indexes for query performance. Logs (but does not raise) on failure
    so a misshapen pre-existing collection cannot block app startup."""
    index_specs = [
        ("chat_messages", [("dataset_id", 1), ("user_id", 1), ("timestamp", 1)], {}),
        ("datasets", [("user_id", 1), ("created_at", -1)], {}),
        ("users", "email", {"unique": True}),
        ("dataset_rows", [("dataset_id", 1), ("user_id", 1), ("chunk_index", 1)], {}),
        # TTL index: auto-delete draft chunks 1h after upload if user never proceeds.
        # partialFilterExpression keeps committed chunks immune.
        (
            "dataset_rows",
            [("created_at", 1)],
            {
                "expireAfterSeconds": 3600,
                "partialFilterExpression": {"status": "draft"},
            },
        ),
    ]
    for collection, keys, opts in index_specs:
        try:
            await db[collection].create_index(keys, **opts)
        except Exception as exc:
            logger.warning("Could not create index on %s: %s", collection, exc)
