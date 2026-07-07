from datetime import datetime

from pydantic import BaseModel, Field


class FollowUpStepCreate(BaseModel):
    delay_hours: float = Field(gt=0, description="Hours after customer's last message")
    message_text: str = Field(min_length=1, max_length=4000)
    is_active: bool = True


class FollowUpStepUpdate(BaseModel):
    delay_hours: float | None = Field(default=None, gt=0)
    message_text: str | None = Field(default=None, min_length=1, max_length=4000)
    is_active: bool | None = None


class FollowUpStepOut(BaseModel):
    id: int
    position: int
    delay_hours: float
    message_text: str
    is_active: bool

    model_config = {"from_attributes": True}


class ReorderSteps(BaseModel):
    step_ids: list[int]


class TelegramAccountOut(BaseModel):
    id: int
    name: str
    phone: str | None
    is_connected: bool

    model_config = {"from_attributes": True}


class TelegramSendCode(BaseModel):
    phone: str


class TelegramSignIn(BaseModel):
    phone: str
    code: str
    phone_code_hash: str
    password: str | None = None


class TelegramTestSend(BaseModel):
    message: str = " test"


class ConversationOut(BaseModel):
    id: int
    telegram_user_id: int
    display_name: str | None
    last_user_message_at: datetime | None
    steps_sent: int
    last_follow_up_at: datetime | None
    opted_out: bool

    model_config = {"from_attributes": True}


class DashboardStats(BaseModel):
    connected: bool
    active_steps: int
    tracked_conversations: int
    pending_follow_ups: int
    sent_last_24h: int


class LoginRequest(BaseModel):
    password: str


class LoginResponse(BaseModel):
    token: str
