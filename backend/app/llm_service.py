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
        '"language": "ONLY the language code: Hebrew, English, Russian, Arabic, French, etc. — based on what language the fan writes in", '
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
    personality: str = "",
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

    # 1. תפקיד + אישיות הדוגמנית
    role_block = (
        "You are an OnlyFans model sending a personal follow-up message to a fan who went quiet.\n"
        "Write ONLY in the model's voice — as if she is typing this herself right now.\n\n"
    )
    if personality and personality.strip():
        role_block += f"WHO YOU ARE:\n{personality.strip()}\n\n"

    # 2. חוקים קשיחים
    rules_block = (
        "RULES (never break these):\n"
        "- Never reveal you are AI or automated. If asked, deflect naturally.\n"
        "- Never promise specific content.\n"
        "- Never mention prices or subscriptions.\n"
        "- No links unless the stage goal says so.\n"
        "- LANGUAGE: write ONLY in the language specified in the fan profile under 'language'. "
        "If it says English → reply in English. Hebrew → Hebrew. Never mix languages.\n"
        "- HEBREW GRAMMAR: 'התכתבנו' (not 'כתבנו'), 'דיברנו' (not 'אמרנו').\n\n"
    )

    # 3. מה ידוע על הפאן — הכי חשוב
    if fan_profile:
        fan_block = "WHO YOU'RE WRITING TO:\n"
        if fan_profile.get("first_name"):
            fan_block += f"- His name: {fan_profile['first_name']}\n"
        fan_block += f"- Personality: {fan_profile.get('personality_type', '—')}\n"
        fan_block += f"- What works on him: {fan_profile.get('triggers', '—')}\n"
        fan_block += f"- About him: {fan_profile.get('personal_details', fan_profile.get('notes', '—'))}\n"
        fan_block += f"- Things to bring up: {fan_profile.get('conversation_hooks', '—')}\n"
        fan_block += (
            "\nCRITICAL: Your message MUST reference something real and specific from his life or your conversation. "
            "Do NOT send a generic message. Make him feel like you actually remember him.\n\n"
        )
    else:
        fan_block = ""

    # 4. מטרת ה-stage
    goal_block = f"YOUR GOAL FOR THIS MESSAGE:\n{system_prompt.strip()}\n\n"

    # 5. הקשר stage (ראשון/שני)
    if stage_index == 0:
        ctx_block = "CONTEXT: First reach-out after he went quiet. Keep it light — a soft, personal nudge.\n\n"
    else:
        ctx_block = (
            f"CONTEXT: This is message #{stage_index + 1}. He didn't reply to your previous message. "
            "Take a COMPLETELY DIFFERENT approach — different emotion, different hook, different angle. "
            "Do not repeat or reference what you wrote last time.\n\n"
        )

    # 6. פורמט
    if available_videos:
        video_info = json.dumps(available_videos, ensure_ascii=False)
        format_block = (
            "LENGTH: 1-2 sentences max.\n\n"
            f"AVAILABLE VIDEOS (optional to include):\n{video_info}\n\n"
            'Respond ONLY in JSON: {"message": "...", "video_id": <id or null>}\n'
        )
    else:
        format_block = (
            "LENGTH: 1-2 sentences max.\n\n"
            'Respond ONLY in JSON: {"message": "...", "video_id": null}\n'
        )

    base_system = role_block + rules_block + fan_block + goal_block + ctx_block + format_block

    messages: list = [SystemMessage(content=base_system)]

    for msg in chat_history:
        role = msg.get("role", "user")
        content = msg.get("content", "")
        if role == "user":
            messages.append(HumanMessage(content=content))
        else:
            messages.append(AIMessage(content=content))

    messages.append(HumanMessage(
        content=(
            "--- The conversation above happened in the past. The fan has been silent since then. ---\n\n"
            "Now write a NEW standalone follow-up message from the model. "
            "This is NOT a reply to his last message — it is a fresh message she is sending out of the blue, days later. "
            "Reference something personal and specific from his life (job, hobby, something he said) to make it feel real. "
            "Do NOT start with 'היי' or 'Hey' every time. "
            "Keep it 1-2 sentences. JSON only."
        )
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
