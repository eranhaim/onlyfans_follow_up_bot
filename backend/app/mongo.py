import logging
from datetime import datetime

from pymongo import MongoClient
from pymongo.collection import Collection

from app.config import settings

logger = logging.getLogger(__name__)

_client: MongoClient | None = None


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
    get_chat_collection().insert_one({
        "account_id": account_id,
        "telegram_user_id": telegram_user_id,
        "role": role,
        "content": content,
        "timestamp": datetime.utcnow(),
    })


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
    profiles_col = db["fan_profiles"]
    profiles_col.create_index([("account_id", 1), ("telegram_user_id", 1)], unique=True)
    logger.info("MongoDB initialized (db=%s)", db.name)
