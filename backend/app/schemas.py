from datetime import datetime

from pydantic import BaseModel, Field


# --- Follow-Up Stages (per account) ---

class FollowUpStageCreate(BaseModel):
    account_id: int | None = None
    delay_hours: float = Field(gt=0)
    system_prompt: str = ""
    is_active: bool = True


class FollowUpStageUpdate(BaseModel):
    delay_hours: float | None = Field(default=None, gt=0)
    system_prompt: str | None = None
    is_active: bool | None = None


class FollowUpStageOut(BaseModel):
    id: int
    account_id: int
    position: int
    delay_hours: float
    system_prompt: str
    is_active: bool

    model_config = {"from_attributes": True}


class ReorderStages(BaseModel):
    stage_ids: list[int]


# --- Videos ---

class VideoOut(BaseModel):
    id: int
    account_id: int
    filename: str
    tags: str
    description: str
    created_at: datetime

    model_config = {"from_attributes": True}


class VideoUpdate(BaseModel):
    tags: str | None = None
    description: str | None = None


# --- Telegram ---

class TelegramAccountOut(BaseModel):
    id: int
    name: str
    phone: str | None
    is_connected: bool
    personality: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class TelegramAccountUpdate(BaseModel):
    name: str | None = None
    personality: str | None = None


class TelegramSendCode(BaseModel):
    phone: str


class TelegramSignIn(BaseModel):
    phone: str
    code: str
    phone_code_hash: str
    password: str | None = None


class TelegramTestSend(BaseModel):
    message: str = " test"


# --- Conversations ---

class ConversationOut(BaseModel):
    id: int
    account_id: int
    telegram_user_id: int
    display_name: str | None
    last_user_message_at: datetime | None
    steps_sent: int
    last_follow_up_at: datetime | None
    opted_out: bool

    model_config = {"from_attributes": True}


# --- Channels ---

class ChannelAccountOut(BaseModel):
    id: int
    name: str
    phone: str | None
    is_connected: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class TelegramChannelOut(BaseModel):
    id: int
    channel_account_id: int
    channel_id: int
    title: str
    username: str | None
    subscribers_count: int
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class ChannelSubscriberOut(BaseModel):
    user_id: int
    first_name: str | None = None
    last_name: str | None = None
    username: str | None = None


# --- Dashboard ---

class DashboardStats(BaseModel):
    connected: bool
    active_stages: int
    tracked_conversations: int
    pending_follow_ups: int
    sent_last_24h: int


# --- Auth ---

class LoginRequest(BaseModel):
    password: str


class LoginResponse(BaseModel):
    token: str
