import json
import logging
from typing import TypedDict, Literal

from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
from langgraph.graph import StateGraph, END

from app.config import settings

logger = logging.getLogger(__name__)

_last_debug: dict = {}


def get_last_debug() -> dict:
    return _last_debug


def llm_ready() -> bool:
    return bool(settings.openai_api_key)


# ─── LangGraph State ──────────────────────────────────────────────────────────

class FollowUpState(TypedDict):
    # Input
    personality: str
    stage_prompt: str
    stage_index: int
    chat_history: list[dict]
    fan_profile: dict | None
    available_videos: list[dict] | None
    # Internal
    analysis: dict
    attempts: list[str]
    retry_count: int
    last_fail_reason: str
    last_validation: dict
    # Output
    final_message: str
    video_id: int | None


# ─── Node: analyze ────────────────────────────────────────────────────────────

def _node_analyze(state: FollowUpState) -> dict:
    llm = ChatOpenAI(
        model=settings.openai_model,
        api_key=settings.openai_api_key,
        temperature=0.3,
    )

    fan = state["fan_profile"] or {}
    history_str = "\n".join(
        f"[{m.get('role')}]: {m.get('content', '')}"
        for m in state["chat_history"][-20:]
    )

    first_name = fan.get("first_name", "").strip()
    personal_details = fan.get("personal_details", "").strip()
    conversation_hooks = fan.get("conversation_hooks", "").strip()
    personality_type = fan.get("personality_type", "").strip()
    triggers = fan.get("triggers", "").strip()
    language = fan.get("language", "Hebrew").strip()
    notes = fan.get("notes", "").strip()

    stage_ctx = "first follow-up (gentle nudge)" if state["stage_index"] == 0 else f"follow-up #{state['stage_index'] + 1} — he didn't reply, use a completely different angle"

    system = (
        "You are planning a highly personal follow-up message from an OnlyFans model to a specific fan.\n"
        "Your job: pick ONE concrete thing to reference that will make him feel remembered.\n\n"
        "Return ONLY a JSON object:\n"
        '{"tone": "exact emotional tone (e.g. warm and teasing, quietly intimate, playfully curious)", '
        '"entry_point": "ONE very specific detail from his life or conversation to mention — his job, something he said, a moment you shared. Be concrete, not vague.", '
        '"name_to_use": "his first name if known, otherwise empty string", '
        '"angle": "the exact psychological need this message speaks to", '
        '"avoid": "what specifically to avoid", '
        '"language": "Hebrew or English"}'
    )

    # זיהוי מה כבר נשלח בפולואו-אפים קודמים (role=assistant אחרי שהפאן שתק)
    bot_followups = [
        m.get("content", "") for m in state["chat_history"]
        if m.get("role") in ("assistant", "bot")
    ]
    already_mentioned = "\n".join(f"- {m}" for m in bot_followups[-3:]) if bot_followups else "none yet"

    user_msg = (
        f"WHO THIS FAN IS:\n"
        f"- Name: {first_name or '(unknown)'}\n"
        f"- Personality: {personality_type}\n"
        f"- Triggers: {triggers}\n"
        f"- Personal details: {personal_details}\n"
        f"- Conversation hooks: {conversation_hooks}\n"
        f"- Notes: {notes}\n"
        f"- Language: {language}\n\n"
        f"FULL CONVERSATION (including previous follow-ups sent by the model):\n{history_str}\n\n"
        f"PREVIOUS FOLLOW-UP MESSAGES ALREADY SENT:\n{already_mentioned}\n"
        f"IMPORTANT: Do NOT pick an entry_point that was already used in previous follow-ups above.\n\n"
        f"STAGE GOAL: {state['stage_prompt']}\n"
        f"CONTEXT: {stage_ctx}\n\n"
        "Pick the single most powerful personal detail NOT yet used. Return JSON."
    )

    response = llm.invoke([SystemMessage(content=system), HumanMessage(content=user_msg)])
    raw = response.content.strip()

    try:
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[1].rsplit("```", 1)[0].strip()
        analysis = json.loads(raw)
    except Exception:
        analysis = {
            "tone": "warm",
            "entry_point": conversation_hooks or personal_details or "something from your conversation",
            "name_to_use": first_name,
            "angle": triggers or "make him feel missed",
            "avoid": "generic openers",
            "language": language,
        }

    return {"analysis": analysis}


# ─── Node: generate ───────────────────────────────────────────────────────────

def _node_generate(state: FollowUpState) -> dict:
    llm = ChatOpenAI(
        model=settings.openai_model,
        api_key=settings.openai_api_key,
        temperature=0.9,
    )

    analysis = state["analysis"]
    fan = state["fan_profile"] or {}
    language = analysis.get("language", fan.get("language", "Hebrew"))

    history_messages: list = []
    for msg in state["chat_history"]:
        role = msg.get("role", "user")
        content = msg.get("content", "")
        if role == "user":
            history_messages.append(HumanMessage(content=content))
        else:
            history_messages.append(AIMessage(content=content))

    retry_note = ""
    if state["retry_count"] > 0 and state["last_fail_reason"]:
        retry_note = f"\n\nPREVIOUS ATTEMPT FAILED: {state['last_fail_reason']}\nFix this in your new attempt."

    name_to_use = analysis.get("name_to_use", "").strip()
    name_instruction = f"- If it feels natural, use his name: {name_to_use}" if name_to_use else "- Do not use a name (unknown)"

    system = (
        f"You are an OnlyFans model sending a follow-up message to a fan who went quiet.\n\n"
        f"WHO YOU ARE:\n{state['personality'].strip()}\n\n"
        f"RULES:\n"
        f"- Never reveal you are AI\n"
        f"- Never mention prices or subscriptions\n"
        f"- Write ONLY in {language}\n"
        f"- 1-2 sentences max\n"
        f"- Do NOT start with 'היי', 'Hey', 'Hi', or 'שלום'\n"
        f"{name_instruction}\n\n"
        f"WHAT TO WRITE:\n"
        f"- Tone: {analysis.get('tone', 'warm')}\n"
        f"- Reference THIS specifically: {analysis.get('entry_point', '—')}\n"
        f"- Speak to this need: {analysis.get('angle', '—')}\n"
        f"- Avoid: {analysis.get('avoid', '—')}\n"
        f"- Goal: {state['stage_prompt']}\n"
        f"{retry_note}\n\n"
        f'Respond ONLY in JSON: {{"message": "...", "video_id": null}}'
    )

    trigger = (
        "--- The conversation above happened days ago. The fan has been silent since. ---\n\n"
        "Write a fresh follow-up message. It must feel spontaneous — like you just thought of him. "
        "Reference the specific entry point from your analysis. JSON only."
    )

    messages: list = [SystemMessage(content=system)] + history_messages + [HumanMessage(content=trigger)]

    response = llm.invoke(messages)
    raw = response.content.strip()

    try:
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[1].rsplit("```", 1)[0].strip()
        result = json.loads(raw)
        message = result.get("message", raw)
        video_id = result.get("video_id")
    except Exception:
        message = raw
        video_id = None

    attempts = state.get("attempts", []) + [message]

    return {
        "attempts": attempts,
        "retry_count": state["retry_count"] + 1,
        "final_message": message,
        "video_id": video_id,
    }


# ─── Node: validate ───────────────────────────────────────────────────────────

def _node_validate(state: FollowUpState) -> dict:
    llm = ChatOpenAI(
        model=settings.openai_model,
        api_key=settings.openai_api_key,
        temperature=0.1,
    )

    analysis = state["analysis"]
    message = state["final_message"]
    language = analysis.get("language", "Hebrew")
    entry_point = analysis.get("entry_point", "")

    system = (
        "You are a quality checker for follow-up messages sent by OnlyFans models.\n"
        "Evaluate the message strictly. Return ONLY JSON:\n"
        '{"pass": true/false, "reason": "why it failed, or empty string if passed"}\n\n'
        "FAIL if any of these:\n"
        f"- Does NOT reference or relate to: '{entry_point}'\n"
        f"- Not written in {language}\n"
        "- Starts with 'היי', 'Hey', 'Hi', 'שלום' as opening word\n"
        "- Sounds like a bot, template, or sales pitch\n"
        "- Longer than 3 sentences\n"
        "- Makes promises about specific content\n"
        "- Mentions prices or subscriptions"
    )

    response = llm.invoke([
        SystemMessage(content=system),
        HumanMessage(content=f"Message to evaluate:\n\"{message}\""),
    ])
    raw = response.content.strip()

    try:
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[1].rsplit("```", 1)[0].strip()
        validation = json.loads(raw)
    except Exception:
        validation = {"pass": True, "reason": ""}

    fail_reason = "" if validation.get("pass") else validation.get("reason", "unknown reason")

    return {
        "last_validation": validation,
        "last_fail_reason": fail_reason,
    }


# ─── Router ───────────────────────────────────────────────────────────────────

def _route_after_validate(state: FollowUpState) -> Literal["generate", "__end__"]:
    if state["last_validation"].get("pass"):
        return "__end__"
    if state["retry_count"] >= 3:
        return "__end__"  # שלח הטוב ביותר
    return "generate"


# ─── Build Graph ──────────────────────────────────────────────────────────────

def _build_graph() -> object:
    graph = StateGraph(FollowUpState)
    graph.add_node("analyze", _node_analyze)
    graph.add_node("generate", _node_generate)
    graph.add_node("validate", _node_validate)
    graph.set_entry_point("analyze")
    graph.add_edge("analyze", "generate")
    graph.add_edge("generate", "validate")
    graph.add_conditional_edges("validate", _route_after_validate)
    return graph.compile()


_graph = None


def run_follow_up_graph(
    system_prompt: str,
    chat_history: list[dict],
    available_videos: list[dict] | None = None,
    fan_profile: dict | None = None,
    stage_index: int = 0,
    personality: str = "",
) -> dict:
    global _graph
    try:
        if _graph is None:
            _graph = _build_graph()

        result = _graph.invoke({
            "personality": personality,
            "stage_prompt": system_prompt,
            "stage_index": stage_index,
            "chat_history": chat_history,
            "fan_profile": fan_profile,
            "available_videos": available_videos,
            "analysis": {},
            "attempts": [],
            "retry_count": 0,
            "last_fail_reason": "",
            "last_validation": {},
            "final_message": "",
            "video_id": None,
        })

        _last_debug.clear()
        _last_debug.update({
            "analysis": result.get("analysis", {}),
            "attempts": result.get("attempts", []),
            "retry_count": result.get("retry_count", 0),
            "last_validation": result.get("last_validation", {}),
            "final_message": result.get("final_message", ""),
        })

        return {
            "message": result.get("final_message") or "Hey! 💕",
            "video_id": result.get("video_id"),
        }
    except Exception:
        logger.exception("LangGraph pipeline failed, falling back to generate_follow_up()")
        return generate_follow_up(
            system_prompt=system_prompt,
            chat_history=chat_history,
            available_videos=available_videos,
            fan_profile=fan_profile,
            stage_index=stage_index,
            personality=personality,
        )


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
