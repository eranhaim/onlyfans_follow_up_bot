import logging
import math
from datetime import datetime

from openai import OpenAI
from pymongo import MongoClient
from pymongo.collection import Collection

from app.config import settings

logger = logging.getLogger(__name__)

_client: MongoClient | None = None
_openai: OpenAI | None = None


def get_openai_client() -> OpenAI:
    global _openai
    if _openai is None:
        _openai = OpenAI(api_key=settings.openai_api_key)
    return _openai


def get_embedding(text: str) -> list[float]:
    """Returns 1536-dim embedding vector for the given text."""
    response = get_openai_client().embeddings.create(
        model="text-embedding-3-small",
        input=text.strip(),
    )
    return response.data[0].embedding


def get_mongo_client() -> MongoClient:
    global _client
    if _client is None:
        _client = MongoClient(settings.mongodb_url)
    return _client


def get_db():
    return get_mongo_client().get_default_database()


def get_chat_collection() -> Collection:
    return get_db()["chat_messages"]


def store_message(account_id: int, telegram_user_id: int, role: str, content: str) -> None:
    doc = {
        "account_id": account_id,
        "telegram_user_id": telegram_user_id,
        "role": role,
        "content": content,
        "timestamp": datetime.utcnow(),
    }
    try:
        doc["embedding"] = get_embedding(content)
    except Exception:
        logger.warning("Failed to embed message, storing without embedding")
    get_chat_collection().insert_one(doc)


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    """dot(a,b) / (|a| * |b|) — כמה שני וקטורים קרובים זה לזה (0 עד 1)."""
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def search_conversation(
    account_id: int,
    telegram_user_id: int,
    query: str,
    top_k: int = 5,
    min_score: float = 0.5,
) -> list[dict]:
    """Returns the top_k most semantically similar messages to query."""
    query_vec = get_embedding(query)

    # שולפים רק הודעות שיש להן embedding
    docs = list(get_chat_collection().find(
        {"account_id": account_id, "telegram_user_id": telegram_user_id, "embedding": {"$exists": True}},
        {"_id": 0, "role": 1, "content": 1, "timestamp": 1, "embedding": 1},
    ))

    # מחשבים similarity לכל הודעה
    scored = [
        {"role": d["role"], "content": d["content"], "score": _cosine_similarity(query_vec, d["embedding"])}
        for d in docs
    ]

    # מסננים ומחזירים את הכי רלוונטיים
    results = sorted([s for s in scored if s["score"] >= min_score], key=lambda x: x["score"], reverse=True)
    return results[:top_k]


def get_chat_history(account_id: int, telegram_user_id: int, limit: int = 20) -> list[dict]:
    cursor = (
        get_chat_collection()
        .find(
            {"account_id": account_id, "telegram_user_id": telegram_user_id},
            {"_id": 0, "role": 1, "content": 1, "timestamp": 1},
        )
        .sort("timestamp", -1)
        .limit(limit)
    )
    messages = list(cursor)
    messages.reverse()
    return messages


def delete_chat_history(account_id: int, telegram_user_id: int | None = None) -> int:
    query: dict = {"account_id": account_id}
    if telegram_user_id is not None:
        query["telegram_user_id"] = telegram_user_id
    result = get_chat_collection().delete_many(query)
    return result.deleted_count


def get_fan_profiles_collection() -> Collection:
    return get_db()["fan_profiles"]


def get_fan_profile(account_id: int, telegram_user_id: int) -> dict | None:
    return get_fan_profiles_collection().find_one(
        {"account_id": account_id, "telegram_user_id": telegram_user_id},
        {"_id": 0},
    )


def save_fan_profile(account_id: int, telegram_user_id: int, profile: dict) -> None:
    get_fan_profiles_collection().update_one(
        {"account_id": account_id, "telegram_user_id": telegram_user_id},
        {"$set": {**profile, "account_id": account_id, "telegram_user_id": telegram_user_id, "updated_at": datetime.utcnow()}},
        upsert=True,
    )


def init_mongo() -> None:
    db = get_db()
    col = db["chat_messages"]
    col.create_index([("account_id", 1), ("telegram_user_id", 1), ("timestamp", -1)])
    # index על embedding קיום — מאפשר סינון מהיר של הודעות שיש להן embedding
    col.create_index([("account_id", 1), ("telegram_user_id", 1), ("embedding", 1)])
    profiles_col = db["fan_profiles"]
    profiles_col.create_index([("account_id", 1), ("telegram_user_id", 1)], unique=True)
    logger.info("MongoDB initialized (db=%s)", db.name)
