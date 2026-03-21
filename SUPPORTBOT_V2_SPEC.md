# SupportBot Studio v2 — Full Python Rebuild

## PROJECT SPEC (Feed this to Claude Code)

You are building **SupportBot Studio v2** — a white-label AI customer support chatbot platform that businesses can self-configure. This is a complete rebuild from a Node.js prototype into Python with full automation capabilities.

---

## TECH STACK

- **Backend:** FastAPI (Python 3.11+)
- **Frontend:** React (Vite) — embedded in the same project, served by FastAPI in production
- **Database:** SQLite (via SQLAlchemy) — zero config, file-based, portable
- **Task Scheduler:** APScheduler (for scheduled reports)
- **AI:** Anthropic Claude API (claude-sonnet-4-20250514)
- **File Processing:** PyPDF2, python-docx, pandas (for CSV/TXT)
- **Notifications:** Telegram Bot API, EmailJS API
- **Deployment:** Render.com (single service)

---

## PROJECT STRUCTURE

```
supportbot-studio/
├── backend/
│   ├── main.py                 # FastAPI app entry point
│   ├── config.py               # Environment config (pydantic-settings)
│   ├── database.py             # SQLAlchemy setup + models
│   ├── routers/
│   │   ├── chat.py             # /api/chat — Claude AI proxy
│   │   ├── escalate.py         # /api/escalate — Telegram + Email
│   │   ├── knowledge.py        # /api/knowledge — CRUD FAQs + doc upload
│   │   ├── analytics.py        # /api/analytics — stats, logs, export
│   │   ├── webhooks.py         # /api/webhooks — Slack, Discord, WhatsApp
│   │   ├── reports.py          # /api/reports — scheduled report config
│   │   └── config_api.py       # /api/config — chatbot brand settings
│   ├── services/
│   │   ├── ai_chat.py          # Claude API wrapper + smart routing
│   │   ├── auto_reply.py       # Keyword/fuzzy matcher for FAQ auto-replies
│   │   ├── doc_processor.py    # PDF, DOCX, CSV, TXT → knowledge base
│   │   ├── telegram_notify.py  # Telegram message sender
│   │   ├── email_notify.py     # EmailJS sender
│   │   ├── webhook_sender.py   # Slack, Discord, WhatsApp webhook dispatcher
│   │   └── report_scheduler.py # APScheduler daily/weekly report generator
│   └── utils/
│       ├── text_similarity.py  # Fuzzy matching for auto-reply
│       └── csv_export.py       # Generate CSV from conversations
├── frontend/
│   ├── src/
│   │   ├── App.jsx             # Main app with all views
│   │   ├── main.jsx            # React entry
│   │   ├── components/
│   │   │   ├── AdminPanel.jsx      # Config + Knowledge Base + Doc Upload
│   │   │   ├── ChatWidget.jsx      # Customer-facing chat bubble
│   │   │   ├── AnalyticsDashboard.jsx  # Stats, charts, conversation log
│   │   │   ├── WebhookSettings.jsx # Configure Slack/Discord/WhatsApp
│   │   │   └── ReportSettings.jsx  # Configure scheduled reports
│   │   └── styles/
│   │       └── globals.css
│   ├── index.html
│   ├── vite.config.js
│   └── package.json
├── uploads/                    # Uploaded docs (gitignored)
├── data/
│   └── supportbot.db           # SQLite database (gitignored)
├── requirements.txt
├── .env.example
├── .gitignore
├── render.yaml
└── README.md
```

---

## DATABASE MODELS (SQLAlchemy + SQLite)

### BotConfig
Stores the chatbot's brand/configuration per instance.
```
id: int (PK)
business_name: str
agent_name: str
brand_color: str (hex)
welcome_message: str
escalation_email: str
created_at: datetime
updated_at: datetime
```

### FAQEntry
Individual FAQ items in the knowledge base.
```
id: int (PK)
question: str
answer: str
source: str ("manual" | "uploaded_doc")
source_filename: str (nullable)
embedding_text: str (question + answer combined, used for matching)
created_at: datetime
```

### Conversation
Each chat session.
```
id: int (PK)
session_id: str (uuid)
started_at: datetime
ended_at: datetime (nullable)
escalated: bool (default false)
customer_email: str (nullable)
rating: int (nullable, 1-4)
message_count: int
```

### Message
Individual messages within a conversation.
```
id: int (PK)
conversation_id: int (FK → Conversation)
role: str ("user" | "assistant")
content: str
was_auto_reply: bool (default false)
created_at: datetime
```

### WebhookConfig
Configured webhook endpoints.
```
id: int (PK)
platform: str ("slack" | "discord" | "whatsapp")
webhook_url: str
enabled: bool (default true)
notify_on: str ("escalation" | "all" | "daily_summary")
created_at: datetime
```

### ReportSchedule
Scheduled report configurations.
```
id: int (PK)
frequency: str ("daily" | "weekly")
send_via: str ("telegram" | "email" | "both")
send_at_hour: int (0-23, UTC)
send_on_day: int (nullable, 0=Mon for weekly)
enabled: bool (default true)
last_sent_at: datetime (nullable)
```

---

## API ENDPOINTS

### Chat — `/api/chat` (POST)
Smart routing: checks auto-reply first, falls back to Claude.
```json
Request: { "session_id": "uuid", "message": "How do I reset my password?" }
Response: { "reply": "...", "was_auto_reply": true, "session_id": "uuid" }
```

**Logic:**
1. Check if message fuzzy-matches any FAQ (>85% similarity) → auto-reply (free, no API call)
2. If no match → send to Claude with knowledge base as system prompt
3. Save message + reply to database
4. If Claude suggests escalation → flag in response

### Auto-Reply — `backend/services/auto_reply.py`
Uses difflib.SequenceMatcher for fuzzy string matching.
```python
def find_auto_reply(user_message: str, faqs: list[FAQEntry], threshold: float = 0.85) -> str | None:
    """
    Compare user_message against all FAQ questions.
    If similarity >= threshold, return the FAQ answer.
    Otherwise return None (falls through to Claude).
    """
```

### Knowledge Base — `/api/knowledge`
- `GET /api/knowledge` — list all FAQs
- `POST /api/knowledge` — add FAQ manually
- `DELETE /api/knowledge/{id}` — remove FAQ
- `POST /api/knowledge/upload` — upload PDF/DOCX/CSV/TXT

**Document Processing (`doc_processor.py`):**
- **PDF:** Extract text with PyPDF2, split into chunks by paragraph, generate Q&A pairs using Claude
- **DOCX:** Extract text with python-docx, same chunking + Q&A generation
- **CSV:** Each row becomes a FAQ (columns: question, answer)
- **TXT:** Split by double newlines, generate Q&A pairs using Claude

Q&A generation prompt for Claude:
```
Given this text from a business document, generate FAQ-style question and answer pairs.
Each pair should be a common customer question and a helpful answer.
Return JSON array: [{"q": "...", "a": "..."}, ...]
Only generate questions a customer would actually ask.
Text: {chunk}
```

### Escalation — `/api/escalate` (POST)
Sends conversation transcript via Telegram + Email + configured webhooks.
```json
Request: {
  "session_id": "uuid",
  "customer_email": "customer@example.com"
}
```
**Logic:**
1. Fetch conversation from DB by session_id
2. Format transcript
3. Send Telegram notification (if configured)
4. Send EmailJS email (if configured)
5. Fire webhooks for any platform configured with notify_on="escalation"
6. Update conversation.escalated = true

### Analytics — `/api/analytics`
- `GET /api/analytics/summary` — total convos, messages, resolution rate, avg rating, auto-reply rate
- `GET /api/analytics/conversations` — paginated conversation list with filters
- `GET /api/analytics/top-questions` — most asked questions
- `GET /api/analytics/hourly` — message distribution by hour
- `GET /api/analytics/export` — download CSV of all conversations

**Key metric: Auto-reply rate** — shows how much money the bot is saving by not calling Claude.

### Webhooks — `/api/webhooks`
- `GET /api/webhooks` — list configured webhooks
- `POST /api/webhooks` — add webhook
- `PUT /api/webhooks/{id}` — update webhook
- `DELETE /api/webhooks/{id}` — remove webhook
- `POST /api/webhooks/{id}/test` — send test message

**Webhook formats:**

Slack:
```json
POST webhook_url
{ "text": "🚨 *SupportBot Escalation*\nCustomer: email\nMessages: 5\n\nTranscript..." }
```

Discord:
```json
POST webhook_url
{ "content": "🚨 **SupportBot Escalation**\nCustomer: email\nMessages: 5\n\nTranscript..." }
```

WhatsApp (via Twilio):
```
POST https://api.twilio.com/2010-04-01/Accounts/{SID}/Messages.json
Body: escalation summary
From: whatsapp:+14155238886
To: whatsapp:{configured_number}
```

### Reports — `/api/reports`
- `GET /api/reports` — get schedule config
- `PUT /api/reports` — update schedule config

**Report content (generated by report_scheduler.py):**
```
📊 SupportBot Daily Report — {business_name}
Date: {date}

Conversations: {count}
Messages: {count}
Auto-replies: {count} ({percentage}% — saved ${estimated_savings})
Escalations: {count}
Avg Rating: {rating}/4

Top 5 Questions:
1. {question} — {count}x
2. ...

Resolution Rate: {rate}%
```

APScheduler runs in background, checks ReportSchedule table, sends via configured channels.

### Config — `/api/config`
- `GET /api/config` — get current bot config
- `PUT /api/config` — update bot config

### Health — `/api/health` (GET)
```json
{ "status": "ok", "has_api_key": true, "faq_count": 15, "auto_reply_ready": true }
```

---

## FRONTEND PAGES

### 1. Configure Tab
- Business name, agent name, brand color, welcome message, escalation email
- Knowledge base: list FAQs, add/remove manually
- **NEW: Upload zone** — drag-and-drop area for PDF/DOCX/CSV/TXT files. Shows upload progress, then lists extracted Q&A pairs for review before adding to knowledge base
- Save button persists to backend

### 2. Chat Demo Tab
- Same chat widget as before but now with:
  - Auto-reply badge: when bot responds from FAQ cache, show small "⚡ Instant reply" tag
  - Escalation flow with email capture → fires real Telegram + Email + webhooks
  - Rating bar after 4+ messages
  - "Online now" status indicator

### 3. Analytics Tab
- Stat cards: Conversations, Messages, Auto-Reply Rate (with $ saved estimate), Avg Rating
- Hourly activity bar chart
- Top questions list
- Conversation log with escalation/rating badges
- **NEW: Auto-reply savings calculator** — shows "You saved ~$X.XX this month by auto-replying to {count} messages"
- CSV export button

### 4. Integrations Tab (NEW)
- **Webhooks section:** Add Slack/Discord/WhatsApp webhooks with test button
- **Scheduled Reports section:** Toggle daily/weekly, pick time, choose delivery (Telegram/email/both)
- Each webhook shows connection status (green dot = last test passed)

### Design Guidelines
- Font: DM Sans + Space Mono (monospace accents)
- Dark header (#18181B), light body (#FAFAF9)
- Brand color from config as accent throughout
- Cards with 14px border-radius, subtle borders (#E4E4E7)
- Status indicators: green dots for connected, amber for warnings, red for errors
- Toast notifications for save/upload/test actions
- Tab navigation in header bar

---

## ENVIRONMENT VARIABLES (.env)

```
# Required
ANTHROPIC_API_KEY=

# Telegram (for escalation + reports)
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=

# EmailJS (for escalation + reports)
EMAILJS_SERVICE_ID=
EMAILJS_TEMPLATE_ID=
EMAILJS_PUBLIC_KEY=
EMAILJS_PRIVATE_KEY=

# WhatsApp via Twilio (optional)
TWILIO_ACCOUNT_SID=
TWILIO_AUTH_TOKEN=
TWILIO_WHATSAPP_FROM=
TWILIO_WHATSAPP_TO=
```

---

## DEPLOYMENT (render.yaml)

```yaml
services:
  - type: web
    name: supportbot-studio
    runtime: python
    buildCommand: |
      pip install -r requirements.txt
      cd frontend && npm install && npm run build && cd ..
    startCommand: uvicorn backend.main:app --host 0.0.0.0 --port $PORT
    envVars:
      - key: ANTHROPIC_API_KEY
        sync: false
      - key: TELEGRAM_BOT_TOKEN
        sync: false
      - key: TELEGRAM_CHAT_ID
        sync: false
      - key: EMAILJS_SERVICE_ID
        sync: false
      - key: EMAILJS_TEMPLATE_ID
        sync: false
      - key: EMAILJS_PUBLIC_KEY
        sync: false
      - key: EMAILJS_PRIVATE_KEY
        sync: false
```

FastAPI serves the built React frontend from `frontend/dist/` as static files, with a catch-all route for client-side routing.

---

## REQUIREMENTS.TXT

```
fastapi>=0.104.0
uvicorn>=0.24.0
sqlalchemy>=2.0.0
pydantic-settings>=2.0.0
python-dotenv>=1.0.0
httpx>=0.25.0
python-multipart>=0.0.6
apscheduler>=3.10.0
PyPDF2>=3.0.0
python-docx>=1.0.0
pandas>=2.1.0
aiofiles>=23.0.0
```

---

## BUILD ORDER (for Claude Code)

Build in this exact order so each piece can be tested before moving on:

1. **Project scaffold** — folder structure, requirements.txt, .env.example, .gitignore
2. **Database** — SQLAlchemy models, auto-create tables on startup
3. **Config API** — GET/PUT bot settings, persisted to DB
4. **Knowledge Base API** — CRUD FAQs, stored in DB
5. **Auto-Reply service** — fuzzy matching against FAQs
6. **Chat API** — smart routing (auto-reply → Claude fallback), saves to DB
7. **Analytics API** — queries DB for stats, conversation logs, CSV export
8. **Escalation API** — Telegram + EmailJS + webhook dispatch
9. **Document Upload** — file processing → Q&A extraction → knowledge base
10. **Webhook API** — CRUD webhooks, test endpoint
11. **Report Scheduler** — APScheduler background task for daily/weekly reports
12. **Frontend** — React app with all 4 tabs
13. **Static file serving** — FastAPI serves frontend/dist in production
14. **Deployment config** — render.yaml, README with setup instructions

---

## KEY SELLING POINTS (for Upwork clients)

When selling this to clients, emphasize:
1. **Auto-reply saves money** — common questions answered instantly without paying for AI API calls
2. **Learns from their docs** — upload a PDF manual and the bot knows the answers
3. **Multi-channel alerts** — escalations go to Telegram, email, Slack, Discord, WhatsApp
4. **Analytics prove ROI** — show clients exactly how many questions the bot handled and how much they saved
5. **Scheduled reports** — business owners get daily/weekly summaries without lifting a finger
6. **White-label** — completely customizable branding, no "powered by" that clients can't remove
