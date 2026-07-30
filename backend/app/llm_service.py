import json
import logging

from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage

from app.config import settings

logger = logging.getLogger(__name__)


def llm_ready() -> bool:
    return bool(settings.openai_api_key)


def analyze_fan(
    chat_history: list[dict],
    existing_profile: dict | None = None,
) -> dict:
    """
    Analyze a fan's messages and return an updated profile dict.
    Returns: {
        "personality_type": str,
        "triggers": str,
        "language": str,
        "notes": str,
    }
    """
    if not llm_ready():
        raise ValueError("OPENAI_API_KEY not configured")

    llm = ChatOpenAI(
        model=settings.openai_model,
        api_key=settings.openai_api_key,
        temperature=0.2,
    )

    existing_str = json.dumps(existing_profile, ensure_ascii=False) if existing_profile else "none yet"

    system = (
        "You are a psychological profiler analyzing a fan's chat messages with an OnlyFans model. "
        "Based on the conversation, build a short profile of the fan to help the model engage him better.\n\n"
        "Return ONLY a JSON object with these fields:\n"
        '{"personality_type": "one short label e.g. shy / impulsive / romantic / transactional / lonely", '
        '"triggers": "what motivates him — e.g. feeling special, FOMO, warmth, excitement", '
        '"language": "the language he writes in", '
        '"notes": "any useful details — job, interests, emotional state, things he mentioned"}\n\n'
        "IMPORTANT: Respond ONLY with valid JSON, nothing else."
    )

    messages: list = [
        SystemMessage(content=system),
        HumanMessage(content=f"Existing profile: {existing_str}\n\nConversation (fan messages only matter):\n"),
    ]
    for msg in chat_history:
        role = msg.get("role", "user")
        content = msg.get("content", "")
        if role == "user":
            messages.append(HumanMessage(content=f"Fan: {content}"))
        else:
            messages.append(AIMessage(content=f"Model: {content}"))

    messages.append(HumanMessage(content="Now return the updated fan profile as JSON."))

    response = llm.invoke(messages)
    raw = response.content.strip()

    try:
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[1].rsplit("```", 1)[0].strip()
        return json.loads(raw)
    except (json.JSONDecodeError, KeyError):
        logger.warning("analyze_fan returned non-JSON: %s", raw[:200])
        return existing_profile or {}


def generate_follow_up(
    system_prompt: str,
    chat_history: list[dict],
    available_videos: list[dict] | None = None,
    fan_profile: dict | None = None,
) -> dict:
    """
    Generate a follow-up message using GPT.

    Returns: {"message": str, "video_id": int | None}
    """
    if not llm_ready():
        raise ValueError("OPENAI_API_KEY not configured")

    llm = ChatOpenAI(
        model=settings.openai_model,
        api_key=settings.openai_api_key,
        temperature=0.9,
    )

    messages: list = []

    hardcoded_rules = (
        "You are a follow-up assistant for an OnlyFans model. "
        "Your job is to write short, personal messages in the model's voice to fans who have gone quiet. "
        "The goal is to re-engage them — make them feel missed, curious, or excited to come back. "
        "Keep messages short (1-3 sentences), warm, and natural. Never sound automated or salesy.\n\n"
        "Reply in the same language the fan writes in. "
        "If the conversation has no messages yet, reply in Hebrew.\n\n"
        "STRICT RULES - never break these:\n"
        "- Never reveal or admit you are an AI, bot, or automated system. "
        "If asked, deflect naturally (e.g. \"of course it's me 😘\").\n"
        "- Never promise specific content (e.g. \"I'll send you X\").\n"
        "- Never mention prices, payments, or subscriptions — redirect fans to OnlyFans.\n"
        "- Never include links or external URLs unless explicitly instructed in the prompt below.\n"
    )

    base_system = hardcoded_rules + "\n---\n\n" + system_prompt.strip()

    if fan_profile:
        base_system += (
            "\n\n---\n"
            "FAN PROFILE — use this to tailor your message to this specific person:\n"
            f"- Personality: {fan_profile.get('personality_type', '—')}\n"
            f"- What triggers him: {fan_profile.get('triggers', '—')}\n"
            f"- Language: {fan_profile.get('language', '—')}\n"
            f"- Notes: {fan_profile.get('notes', '—')}\n"
            "Write your message in a way that speaks directly to this fan's psychology."
        )
    if available_videos:
        video_info = json.dumps(available_videos, ensure_ascii=False)
        base_system += (
            "\n\n---\n"
            "You may optionally send a video with your message. "
            "Here are the available videos:\n"
            f"{video_info}\n\n"
            "If you want to include a video, respond in this exact JSON format:\n"
            '{"message": "your message text", "video_id": <id>}\n\n'
            "If you don't want to include a video, respond in this format:\n"
            '{"message": "your message text", "video_id": null}\n\n'
            "IMPORTANT: Respond ONLY with valid JSON, nothing else."
        )
    else:
        base_system += (
            "\n\n---\n"
            "Respond in this exact JSON format:\n"
            '{"message": "your message text", "video_id": null}\n\n'
            "IMPORTANT: Respond ONLY with valid JSON, nothing else."
        )

    messages.append(SystemMessage(content=base_system))

    for msg in chat_history:
        role = msg.get("role", "user")
        content = msg.get("content", "")
        if role == "user":
            messages.append(HumanMessage(content=content))
        else:
            messages.append(AIMessage(content=content))

    messages.append(HumanMessage(
        content="The fan has gone silent. Send a follow-up message to re-engage them. Do NOT directly reply to their last message — write a new message that feels natural and unprompted. Remember: respond ONLY in JSON format."
    ))

    response = llm.invoke(messages)
    raw = response.content.strip()

    try:
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[1].rsplit("```", 1)[0].strip()
        result = json.loads(raw)
        return {
            "message": result.get("message", raw),
            "video_id": result.get("video_id"),
        }
    except (json.JSONDecodeError, KeyError):
        logger.warning("LLM returned non-JSON response, using raw text: %s", raw[:200])
        return {"message": raw, "video_id": None}
