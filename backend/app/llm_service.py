import json
import logging

from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage

from app.config import settings

logger = logging.getLogger(__name__)

_last_debug: dict = {}


def get_last_debug() -> dict:
    return _last_debug


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

    existing_clean = {k: v for k, v in existing_profile.items() if not hasattr(v, "isoformat")} if existing_profile else None
    existing_str = json.dumps(existing_clean, ensure_ascii=False) if existing_clean else "none yet"

    system = (
        "You are a psychological profiler analyzing a fan's chat messages with an OnlyFans model. "
        "Extract every personal detail the fan has revealed — explicitly or implicitly.\n\n"
        "Return ONLY a JSON object with these fields:\n"
        '{"personality_type": "one short label e.g. shy / impulsive / romantic / transactional / lonely", '
        '"triggers": "what motivates him — e.g. feeling special, FOMO, warmth, exclusivity", '
        '"language": "the language he writes in", '
        '"first_name": "his first name ONLY if he introduced himself by name in the conversation — otherwise leave empty string", '
        '"personal_details": "EVERYTHING he mentioned about himself: job, schedule, hobbies, family, location, age, emotional state, things on his mind — even small details like working night shifts or being shy", '
        '"conversation_hooks": "topics or moments from the conversation that created a connection — things the model can bring up again to feel personal", '
        '"notes": "emotional patterns, what he responds well to, anything else useful"}\n\n'
        "Be specific — vague notes are useless. If he said he works nights, write that. If he mentioned thinking about the model, write that.\n"
        "IMPORTANT: Only save a name if the fan explicitly said his name (e.g. 'I am David' / 'call me Dan'). Do NOT infer a name from his username or profile.\n\n"
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
    stage_index: int = 0,
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
        "LANGUAGE RULE — this overrides everything else: always write in the same language the fan uses. "
        "The instructions above may be in English — ignore that, it doesn't affect the output language. "
        "If the fan writes in Hebrew → reply in Hebrew. If in English → reply in English. "
        "If the conversation has no messages yet, reply in Hebrew.\n\n"
        "IMPORTANT HEBREW GRAMMAR: When writing in Hebrew, use correct verb forms. "
        "Use 'התכתבנו' (not 'כתבנו') for 'we chatted/texted'. "
        "Use 'דיברנו' for 'we talked'. "
        "Use 'שוחחנו' for 'we conversed'. "
        "Never use 'כתבנו' to mean messaging or chatting — it means 'we wrote' (a document).\n\n"
        "STRICT RULES - never break these:\n"
        "- Never reveal or admit you are an AI, bot, or automated system. "
        "If asked, deflect naturally (e.g. \"of course it's me 😘\").\n"
        "- Never promise specific content (e.g. \"I'll send you X\").\n"
        "- Never mention prices, payments, or subscriptions — redirect fans to OnlyFans.\n"
        "- Never include links or external URLs unless explicitly instructed in the prompt below.\n"
    )

    if stage_index == 0:
        stage_context = (
            "This is the FIRST follow-up message after the fan went quiet. "
            "Keep it light and warm — a gentle nudge, not pushy."
        )
    else:
        stage_context = (
            f"This is follow-up #{stage_index + 1}. The fan already received a previous message and still hasn't replied. "
            "Do NOT repeat what was said before. Take a completely different angle — different tone, different hook. "
            "Maybe more personal, maybe more playful, maybe more mysterious. Just not the same as last time."
        )

    base_system = hardcoded_rules + "\n---\n\n" + system_prompt.strip() + f"\n\n---\n{stage_context}"

    if fan_profile:
        base_system += (
            "\n\n---\n"
            "FAN PROFILE — this is what you know about this specific person. Use it:\n"
            f"- Personality: {fan_profile.get('personality_type', '—')}\n"
            f"- What triggers him: {fan_profile.get('triggers', '—')}\n"
            f"- Language: {fan_profile.get('language', '—')}\n"
            f"- Personal details: {fan_profile.get('personal_details', fan_profile.get('notes', '—'))}\n"
            f"- Conversation hooks (things to bring up): {fan_profile.get('conversation_hooks', '—')}\n"
            f"- Notes: {fan_profile.get('notes', '—')}\n\n"
            "CRITICAL: Your message MUST reference something specific from his life or your conversation. "
            "Do NOT send a generic message. If he works nights — mention it. If he said he thinks about you — use that. "
            "Make him feel like you actually remember him."
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
        content="The fan has gone silent. Write a short follow-up message in the model's voice. "
                "Reference something specific from the conversation or from what you know about him — make it feel like you genuinely remembered him, not a copy-paste. "
                "Do NOT directly reply to his last message — this should feel like you thought of him out of nowhere. "
                "1-2 sentences max. Respond ONLY in JSON format."
    ))

    response = llm.invoke(messages)
    raw = response.content.strip()

    _last_debug.clear()
    _last_debug.update({
        "system_prompt": base_system,
        "chat_history": [{"role": m.get("role"), "content": m.get("content", "")} for m in chat_history],
        "raw_response": raw,
    })

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
