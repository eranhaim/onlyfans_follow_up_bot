import json
import logging

from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage

from app.config import settings

logger = logging.getLogger(__name__)


def llm_ready() -> bool:
    return bool(settings.openai_api_key)


def generate_follow_up(
    system_prompt: str,
    chat_history: list[dict],
    available_videos: list[dict] | None = None,
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

    base_system = system_prompt.strip()
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
        content="The user has gone silent. Generate a follow-up message as the model. Remember: respond ONLY in JSON format."
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
