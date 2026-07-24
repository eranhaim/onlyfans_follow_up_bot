# Sprint Handover — LLM-Powered Follow-Up System

## Product Idea

The system automates remarketing messages on Telegram for OnlyFans model management. When a customer DMs a model and then goes silent, the bot sends personalized follow-up messages that feel like the model actually wrote them.

**Key value proposition:** Instead of generic canned messages, an LLM (GPT-4o-mini) generates unique, context-aware messages based on the actual conversation history and a style prompt defined per model. The system can also attach teaser videos from a per-model video bank.

---

## How It Works

### Per-Account Stages

Each connected Telegram account (model) has its own sequence of follow-up stages. Each stage defines:

- **Delay** — hours to wait before sending
- **System prompt** — personality/style instructions for the AI (flirty, direct, playful, etc.)

**Timing rules:**
- Stage 1: fires X hours after the customer's **last message**
- Stage 2+: fires X hours after the **previous follow-up was sent**

When a customer replies, the sequence resets (steps_sent = 0).

### LLM Message Generation

When a follow-up is due:
1. Chat history is fetched from MongoDB
2. The stage's system prompt + history are sent to OpenAI
3. GPT generates a unique message in the model's voice
4. If videos are available, GPT picks one based on tags/description
5. Message (+ optional video) is sent via Telegram

### Video Bank

Each model has a bank of teaser videos stored on S3. Videos have admin-written tags and descriptions so the LLM can intelligently pick which one to send based on context.

---

## Architecture

| Component | Technology | Role |
|-----------|-----------|------|
| Backend API | FastAPI (Python) | REST API, scheduler, Telegram client |
| Database | PostgreSQL | Accounts, stages, conversations, logs |
| Chat History | MongoDB | Stores full message history for LLM context |
| LLM | OpenAI GPT-4o-mini via LangChain | Generates follow-up messages |
| Video Storage | AWS S3 | Stores model video files |
| Scheduler | APScheduler | Runs follow-up checks every 5 min |
| Telegram | Telethon (user API) | Multi-account client management |
| Frontend | React + Vite + i18next | Admin panel (Hebrew/English) |
| Deployment | Docker Compose on EC2 | 4 containers: api, frontend, postgres, mongo |

---

## Admin Panel Tabs

1. **Dashboard** — connection status, tracked chats, pending follow-ups, sent count
2. **Stages** — per-account stage sequence with system prompt editor
3. **Videos** — upload/tag/describe videos per account
4. **Telegram** — connect accounts (phone + 2FA), manage linked accounts

---

## Deployment

- **EC2:** 54.173.144.0:8087
- **Repo:** https://github.com/eranhaim/onlyfans_follow_up_bot.git
- **Deploy command:** `cd ~/onlyfans_follow_up_bot && git pull && docker compose up -d --build`
- **Full reset (drops DB):** `docker compose down -v && docker compose up -d --build`

---

## Environment Variables Needed

| Variable | Status | Notes |
|----------|--------|-------|
| TELEGRAM_API_ID | Set | 27845019 |
| TELEGRAM_API_HASH | Set | Configured |
| OPENAI_API_KEY | **Not set** | Add to enable AI messages |
| AWS_ACCESS_KEY_ID | **Not set** | Add to enable video bank |
| AWS_SECRET_ACCESS_KEY | **Not set** | Add to enable video bank |
| AWS_S3_BUCKET | Set | followup-videos |

---

## What's Left

- [ ] Add OpenAI API key to `.env` on EC2
- [ ] Add AWS credentials and create the S3 bucket
- [ ] Reconnect model Telegram accounts (DB was reset)
- [ ] Create follow-up stages with system prompts per model
- [ ] Upload teaser videos to the video bank
- [ ] Test end-to-end with a real conversation
