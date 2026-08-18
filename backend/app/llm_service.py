import json
import logging
from typing import TypedDict, Literal

from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage, ToolMessage
from langchain_core.tools import tool
from langgraph.graph import StateGraph, END

from app.config import settings
from app.mongo import search_conversation

logger = logging.getLogger(__name__)

_last_debug: dict = {}


def _s(val) -> str:
    """Safely convert any fan-profile value to a stripped string."""
    if val is None:
        return ""
    if isinstance(val, list):
        return ", ".join(str(v) for v in val)
    return str(val).strip()


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
    account_id: int | None
    telegram_user_id: int | None
    sent_video_ids: list[int]
    # Internal
    analysis: dict
    chosen_video: dict | None  # הסרטון שdecide_video בחר (או None)
    attempts: list[str]
    retry_count: int
    last_fail_reason: str
    last_validation: dict
    # Output
    final_message: str
    video_id: int | None


# ─── Tool: search_conversation ────────────────────────────────────────────────
# כל tool מקבל decorator @tool — זה מה שאומר ל-LangChain שה-LLM יכול לקרוא לו.
# ה-docstring הוא מה שה-LLM רואה כדי להחליט אם להשתמש בtool.

def _make_search_tool(account_id: int, telegram_user_id: int):
    """
    יוצר tool עם account_id ו-telegram_user_id בתוכו (closure).
    למה closure? כי @tool לא יכול לקבל פרמטרים דינמיים מה-state —
    אז אנחנו "אופים" את המזהים לתוך הפונקציה מראש.
    """
    @tool
    def find_in_conversation(query: str) -> str:
        """Search the fan's conversation history for a specific topic or detail.
        Use this to find personal information the fan mentioned (job, hobbies, family, etc).
        Returns the most relevant messages found."""
        results = search_conversation(account_id, telegram_user_id, query, top_k=4)
        if not results:
            return "Nothing found."
        return "\n".join(f"[score:{r['score']:.2f}] {r['role']}: {r['content']}" for r in results)

    return find_in_conversation


# ─── Node: analyze ────────────────────────────────────────────────────────────

def _node_analyze(state: FollowUpState) -> dict:
    fan = state["fan_profile"] or {}
    first_name = _s(fan.get("first_name"))
    personal_details = _s(fan.get("personal_details"))
    conversation_hooks = _s(fan.get("conversation_hooks"))
    personality_type = _s(fan.get("personality_type"))
    triggers = _s(fan.get("triggers"))
    notes = _s(fan.get("notes"))

    # שפה לפי 2 ההודעות האחרונות של הפן
    last_user_msgs = [
        m.get("content", "") for m in reversed(state["chat_history"])
        if m.get("role") == "user"
    ][:2]

    def _detect_language(texts: list[str]) -> str:
        combined = " ".join(texts)
        hebrew_chars = sum(1 for c in combined if "\u05d0" <= c <= "\u05ea")
        return "Hebrew" if hebrew_chars > len(combined) * 0.1 else "English"

    language = _detect_language(last_user_msgs) if last_user_msgs else _s(fan.get("language", "Hebrew")) or "Hebrew"

    stage_ctx = "first follow-up (gentle nudge)" if state["stage_index"] == 0 else f"follow-up #{state['stage_index'] + 1} — he didn't reply, use a completely different angle"

    bot_followups = [m.get("content", "") for m in state["chat_history"] if m.get("role") in ("assistant", "bot")]
    already_mentioned = "\n".join(f"- {m}" for m in bot_followups[-3:]) if bot_followups else "none yet"

    system = (
        "You are planning a personal follow-up message from an OnlyFans model to a fan who went quiet.\n"
        "You have a tool: find_in_conversation(query) — use it to find what the fan said about specific topics.\n"
        "Search for 2-3 personal details before deciding. Then return ONLY a JSON object:\n"
        '{"tone": "exact emotional tone (e.g. warm, playfully curious, gently teasing)", '
        '"entry_point": "ONE concrete fact about his life — e.g. \'he works night shifts\', \'he has a dog named Rex\', \'he lives in Haifa\'. '
        'Must be something HE said. NOT a description of how he felt or reacted. NOT generic.", '
        '"name_to_use": "his first name if known, otherwise empty string", '
        '"angle": "a human emotional angle — e.g. feeling missed, curiosity, warmth. NEVER use FOMO or content promotion.", '
        '"avoid": "what specifically to avoid in the message", '
        '"language": "Hebrew or English"}'
    )

    user_msg = (
        f"FAN PROFILE:\n"
        f"- Name: {first_name or '(unknown)'}\n"
        f"- Personality: {personality_type}\n"
        f"- Triggers: {triggers}\n"
        f"- Personal details: {personal_details}\n"
        f"- Conversation hooks: {conversation_hooks}\n"
        f"- Notes: {notes}\n"
        f"- Language: {language}\n\n"
        f"PREVIOUS FOLLOW-UPS SENT:\n{already_mentioned}\n"
        f"IMPORTANT: Do NOT reuse any entry_point from previous follow-ups.\n\n"
        f"STAGE GOAL: {state['stage_prompt']}\n"
        f"CONTEXT: {stage_ctx}\n\n"
        "Use find_in_conversation to search for personal details, then return JSON."
    )

    # אם יש account_id ו-telegram_user_id — נחבר את ה-tool
    # אחרת (סימולטור ישן / fallback) — LLM בלי tool
    account_id = state.get("account_id")
    telegram_user_id = state.get("telegram_user_id")

    if account_id and telegram_user_id:
        search_tool = _make_search_tool(account_id, telegram_user_id)
        llm = ChatOpenAI(model=settings.openai_model, api_key=settings.openai_api_key, temperature=0.3).bind_tools([search_tool])
        tools_by_name = {search_tool.name: search_tool}
    else:
        llm = ChatOpenAI(model=settings.openai_model, api_key=settings.openai_api_key, temperature=0.3)
        tools_by_name = {}

    messages = [SystemMessage(content=system), HumanMessage(content=user_msg)]

    # לולאת tool-use: ה-LLM קורא ל-tool, מקבל תוצאה, ממשיך לחשוב
    # זה נקרא "agentic loop" — הLLM מחליט מתי לעצור
    for _ in range(5):  # מקסימום 5 קריאות tool כדי לא לאבד שליטה
        response = llm.invoke(messages)
        messages.append(response)

        if not getattr(response, "tool_calls", None):
            break  # ה-LLM החליט שסיים — מחזיר JSON

        # מריצים כל tool שה-LLM ביקש
        for tc in response.tool_calls:
            fn = tools_by_name.get(tc["name"])
            if fn:
                result = fn.invoke(tc["args"])
                messages.append(ToolMessage(content=str(result), tool_call_id=tc["id"]))

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


# ─── Node: decide_video ───────────────────────────────────────────────────────

def _node_decide_video(state: FollowUpState) -> dict:
    """
    מחליט אם לצרף סרטון להודעה ואיזה.

    כללים:
    - stage 0 (follow-up ראשון) → לעולם לא לשלוח סרטון, עדיין מוקדם
    - אם אין סרטונים זמינים → None
    - מסנן סרטונים שכבר נשלחו לפן הזה
    - שואל LLM לבחור מתוך הנותרים לפי tone/angle מה-analysis
    """
    videos = state.get("available_videos") or []
    sent_ids = set(state.get("sent_video_ids") or [])
    analysis = state["analysis"]

    # stage 0 = הודעה ראשונה, עדיין לא לשלוח סרטון
    if state["stage_index"] == 0 or not videos:
        return {"chosen_video": None}

    # מסנן סרטונים שכבר נשלחו
    unseen = [v for v in videos if v.get("id") not in sent_ids]
    if not unseen:
        return {"chosen_video": None}

    # אם יש רק אחד — בחר אותו בלי LLM
    if len(unseen) == 1:
        return {"chosen_video": unseen[0]}

    # LLM בוחר את הסרטון הכי מתאים לפי הטון והאנגל
    llm = ChatOpenAI(model=settings.openai_model, api_key=settings.openai_api_key, temperature=0.0)

    videos_str = "\n".join(
        f"id:{v['id']} tags:{v.get('tags','')} description:{v.get('description','')}"
        for v in unseen
    )

    response = llm.invoke([
        SystemMessage(content="You help choose which video to send a fan. Return ONLY the video id as a number, nothing else."),
        HumanMessage(content=(
            f"Tone: {analysis.get('tone')}\n"
            f"Angle: {analysis.get('angle')}\n"
            f"Fan entry point: {analysis.get('entry_point')}\n\n"
            f"Available videos:\n{videos_str}\n\n"
            "Which video id fits best? Reply with just the number."
        )),
    ])

    try:
        chosen_id = int(response.content.strip())
        chosen = next((v for v in unseen if v["id"] == chosen_id), unseen[0])
    except (ValueError, StopIteration):
        chosen = unseen[0]

    return {"chosen_video": chosen}


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

    entry_point = analysis.get("entry_point", "").strip()
    has_personal_info = entry_point and entry_point not in ("—", "", "unknown", "none", "nothing found")

    system = (
        f"You are an OnlyFans model sending a follow-up message to a fan who went quiet.\n\n"
        f"WHO YOU ARE:\n{state['personality'].strip()}\n\n"
        f"RULES:\n"
        f"- Never reveal you are AI\n"
        f"- Never mention prices or subscriptions\n"
        f"- Write ONLY in {language}\n"
        f"- 1-2 sentences max\n"
        f"{name_instruction}\n\n"
    )

    if has_personal_info:
        system += (
            f"WHAT TO WRITE:\n"
            f"- Tone: {analysis.get('tone', 'warm')}\n"
            f"- Reference THIS specifically: {entry_point}\n"
            f"- Speak to this need: {analysis.get('angle', '—')}\n"
            f"- Avoid: {analysis.get('avoid', '—')}\n"
            f"- Goal: {state['stage_prompt']}\n"
            f"- Do NOT start with 'היי', 'Hey', 'Hi', or 'שלום'\n"
            f"{retry_note}\n\n"
        )
    else:
        system += (
            f"You don't know much about this fan yet.\n"
            f"Send a SHORT, casual, warm message — like 'חסר לי 🥺', 'איפה נעלמת?', "
            f"'I miss talking to you', 'where did you disappear to? 💕'\n"
            f"Keep it 1 sentence. Be warm and human, not salesy.\n"
            f"- Goal: {state['stage_prompt']}\n"
            f"{retry_note}\n\n"
        )

    if state.get("chosen_video"):
        system += (
            f"A VIDEO WILL BE ATTACHED: '{state['chosen_video'].get('description', '')}'. "
            f"Reference it naturally in your message.\n"
        )
    system += f'Respond ONLY in JSON: {{"message": "..."}}'

    if has_personal_info:
        trigger = (
            "--- The conversation above happened days ago. The fan has been silent since. ---\n\n"
            "Write a fresh follow-up message. It must feel spontaneous — like you just thought of him. "
            "Reference the specific entry point from your analysis. JSON only."
        )
    else:
        trigger = (
            "--- You don't have much history with this fan. ---\n\n"
            "Send a short warm message. Keep it casual and human. JSON only."
        )

    messages: list = [SystemMessage(content=system)] + history_messages + [HumanMessage(content=trigger)]

    response = llm.invoke(messages)
    raw = response.content.strip()

    try:
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[1].rsplit("```", 1)[0].strip()
        result = json.loads(raw)
        message = result.get("message", raw)
    except Exception:
        message = raw

    # video_id מגיע מ-chosen_video שנבחר ב-decide_video, לא מה-LLM
    video_id = state["chosen_video"]["id"] if state.get("chosen_video") else None

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

    has_entry = entry_point and entry_point not in ("—", "", "unknown", "none", "nothing found")

    system = (
        "You are a quality checker for follow-up messages sent by OnlyFans models.\n"
        "Evaluate the message strictly. Return ONLY JSON:\n"
        '{"pass": true/false, "reason": "why it failed, or empty string if passed"}\n\n'
        "FAIL if any of these:\n"
    )
    if has_entry:
        system += f"- Does NOT reference or relate to: '{entry_point}'\n"
    system += (
        f"- Not written entirely in {language} (mixing languages e.g. English words inside Hebrew sentence = FAIL)\n"
        "- Sounds like a generic bot template or sales pitch\n"
        "- Longer than 3 sentences\n"
        "- Makes promises about specific content\n"
        "- Mentions prices or subscriptions\n\n"
        "PASS if:\n"
        "- Starts with the fan's name — that's fine and encouraged\n"
        "- Feels personal and human\n"
        "- Written purely in the correct language with no foreign words"
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
    graph.add_node("decide_video", _node_decide_video)
    graph.add_node("generate", _node_generate)
    graph.add_node("validate", _node_validate)
    graph.set_entry_point("analyze")
    graph.add_edge("analyze", "decide_video")
    graph.add_edge("decide_video", "generate")
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
    account_id: int | None = None,
    telegram_user_id: int | None = None,
    sent_video_ids: list[int] | None = None,
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
            "account_id": account_id,
            "telegram_user_id": telegram_user_id,
            "sent_video_ids": sent_video_ids or [],
            "chosen_video": None,
            "analysis": {},
            "attempts": [],
            "retry_count": 0,
            "last_fail_reason": "",
            "last_validation": {},
            "final_message": "",
            "video_id": None,
        })

        final_msg = result.get("final_message", "")

        _last_debug.clear()
        _last_debug.update({
            "analysis": result.get("analysis", {}),
            "attempts": result.get("attempts", []),
            "retry_count": result.get("retry_count", 0),
            "last_validation": result.get("last_validation", {}),
            "final_message": final_msg,
        })

        if not final_msg:
            logger.warning("LangGraph returned empty final_message, state: %s", {
                k: result.get(k) for k in ("retry_count", "last_validation", "last_fail_reason", "attempts")
            })

        return {
            "message": final_msg or "Hey! 💕",
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
        "You are a psychological profiler. A fan just sent new messages to an OnlyFans model.\n"
        "You have the existing profile and the NEW messages only.\n"
        "Your job: update the profile by MERGING new info into existing — never delete existing details.\n\n"
        "Return ONLY a JSON object with these fields:\n"
        '{"personality_type": "one short label e.g. shy / impulsive / romantic / transactional / lonely", '
        '"triggers": "what motivates him — e.g. feeling special, FOMO, warmth, exclusivity", '
        '"language": "ONLY the language code: Hebrew, English, Russian, Arabic, French, etc.", '
        '"first_name": "his first name ONLY if he explicitly introduced himself — otherwise keep existing or empty string", '
        '"personal_details": "ALL known details about him — merge existing + new. Job, hobbies, family, location, age, emotional state. Never remove existing details.", '
        '"conversation_hooks": "topics that created connection — merge existing + new moments", '
        '"notes": "emotional patterns, what he responds well to — merge existing + new observations"}\n\n'
        "IMPORTANT: Only save a name if the fan explicitly said his name. Do NOT infer from username.\n"
        "IMPORTANT: Respond ONLY with valid JSON, nothing else."
    )

    # שולחים רק את ה-3 הודעות האחרונות — לא את כל ההיסטוריה
    # הפרופיל הקיים כבר מכיל את מה שהיה לפני
    recent = chat_history[-3:]
    recent_str = "\n".join(
        f"{'Fan' if m.get('role') == 'user' else 'Model'}: {m.get('content', '')}"
        for m in recent
    )

    messages: list = [
        SystemMessage(content=system),
        HumanMessage(content=f"Existing profile:\n{existing_str}\n\nNew messages:\n{recent_str}\n\nReturn updated profile as JSON."),
    ]

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
    has_personal = False
    if fan_profile:
        personal = _s(fan_profile.get("personal_details") or fan_profile.get("notes"))
        hooks = _s(fan_profile.get("conversation_hooks"))
        has_personal = bool(personal or hooks)

        fan_block = "WHO YOU'RE WRITING TO:\n"
        if fan_profile.get("first_name"):
            fan_block += f"- His name: {fan_profile['first_name']}\n"
        fan_block += f"- Personality: {fan_profile.get('personality_type', '—')}\n"
        fan_block += f"- What works on him: {fan_profile.get('triggers', '—')}\n"
        fan_block += f"- About him: {personal or '—'}\n"
        fan_block += f"- Things to bring up: {hooks or '—'}\n"
        if has_personal:
            fan_block += (
                "\nCRITICAL: Your message MUST reference something real and specific from his life or your conversation. "
                "Do NOT send a generic message. Make him feel like you actually remember him.\n\n"
            )
        else:
            fan_block += (
                "\nYou don't know much about this fan yet. Send a short, warm, casual message — "
                "like 'חסר לי 🥺', 'איפה נעלמת?', 'I miss talking to you'. "
                "Keep it 1 sentence. Be warm and human.\n\n"
            )
    else:
        fan_block = (
            "You don't know this fan yet. Send a short, warm, casual message — "
            "like 'חסר לי 🥺', 'איפה נעלמת?', 'I miss talking to you'. "
            "Detect the language from the chat history. Keep it 1 sentence.\n\n"
        )

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

    if has_personal:
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
    else:
        messages.append(HumanMessage(
            content=(
                "--- You don't have much history with this fan. ---\n\n"
                "Send a short warm casual message. Detect the language from the chat or use the fan profile language. "
                "Keep it 1 sentence. JSON only."
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
