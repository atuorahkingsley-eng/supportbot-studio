# SupportBot Studio v2

A white-label AI customer support chatbot platform. Businesses self-configure a branded bot with a knowledge base, auto-replies, escalation, analytics, and multi-channel integrations.

## Features

- **Smart Routing** — FAQ auto-reply (free) → Claude AI fallback
- **Knowledge Base** — Add FAQs manually or upload PDF/DOCX/CSV/TXT
- **Multi-channel Alerts** — Telegram, Email, Slack, Discord, WhatsApp
- **Analytics** — Conversations, auto-reply rate, savings estimate, CSV export
- **Scheduled Reports** — Daily/weekly summaries via Telegram or email
- **White-label** — Full branding control (name, color, welcome message)

## Local Development

### Prerequisites
- Python 3.11+
- Node.js 18+

### Setup

```bash
# Clone and enter project
git clone <repo> && cd supportbot-studio-v2py

# Backend
python -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt

# Copy env file and fill in your keys
cp .env.example .env

# Frontend
cd frontend
npm install
npm run dev &
cd ..

# Run backend (from project root)
uvicorn backend.main:app --reload
```

Backend runs at `http://localhost:8000`
Frontend dev server at `http://localhost:5173` (proxied to backend)

### Required Environment Variables

| Variable | Description |
|---|---|
| `ANTHROPIC_API_KEY` | **Required** — Claude API key |
| `TELEGRAM_BOT_TOKEN` | For escalation + report notifications |
| `TELEGRAM_CHAT_ID` | Your Telegram chat/group ID |
| `EMAILJS_SERVICE_ID` | EmailJS service ID |
| `EMAILJS_TEMPLATE_ID` | EmailJS template ID |
| `EMAILJS_PUBLIC_KEY` | EmailJS public key |
| `EMAILJS_PRIVATE_KEY` | EmailJS private key |
| `TWILIO_ACCOUNT_SID` | For WhatsApp via Twilio (optional) |
| `TWILIO_AUTH_TOKEN` | Twilio auth token (optional) |

## Deployment (Render.com)

1. Push to GitHub
2. Create new Web Service on Render, connect repo
3. Render will use `render.yaml` automatically
4. Set environment variables in the Render dashboard

## API Reference

| Endpoint | Method | Description |
|---|---|---|
| `/api/health` | GET | Health check |
| `/api/config` | GET/PUT | Bot configuration |
| `/api/knowledge` | GET/POST | List/add FAQs |
| `/api/knowledge/{id}` | DELETE | Remove FAQ |
| `/api/knowledge/upload` | POST | Upload document |
| `/api/chat` | POST | Send message |
| `/api/chat/rate` | POST | Rate conversation |
| `/api/escalate` | POST | Escalate to human |
| `/api/analytics/summary` | GET | Stats overview |
| `/api/analytics/conversations` | GET | Paginated conversation log |
| `/api/analytics/top-questions` | GET | Most asked questions |
| `/api/analytics/hourly` | GET | Hourly message distribution |
| `/api/analytics/export` | GET | Download CSV |
| `/api/webhooks` | GET/POST | List/add webhooks |
| `/api/webhooks/{id}` | PUT/DELETE | Update/remove webhook |
| `/api/webhooks/{id}/test` | POST | Test webhook |
| `/api/reports` | GET/PUT | Report schedule |
