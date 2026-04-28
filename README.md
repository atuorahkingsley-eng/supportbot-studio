# SupportBot Studio v2

White-label AI customer support SaaS. One backend hosts many tenants — each tenant gets a branded chat widget, knowledge base, lead capture, analytics, and a script tag they paste into their site.

Think Intercom, but you own the server and Claude does the talking.

## What you get

- **Multi-tenant** — Super admin creates tenants, each tenant logs into their own dashboard.
- **AI chat** — Claude Sonnet handles conversation, falls back to FAQ auto-reply when confidence is high.
- **Knowledge base** — FAQs typed in or extracted from PDF/DOCX/CSV/TXT uploads.
- **Voice input** — Web Speech API in the widget, toggleable per bot.
- **Returning visitor memory** — Cookie-based visitor tracking, prior conversations summarized into prompt context.
- **Multi-language** — Claude detects the user's language and replies in it.
- **Proactive sales** — Discount offers, demo CTAs, exit-intent overlays, lead board.
- **Escalation** — Telegram, email (EmailJS), Slack, Discord, WhatsApp (Twilio).
- **Analytics** — Conversations, top questions, hourly heatmap, language split, voice usage, CSV export.
- **Scheduled reports** — Daily / weekly digests via Telegram or email.
- **Auto-healing** — Background job uses Claude to diagnose recurring errors and retry.
- **Embed widget** — One `<script>` tag, no iframe wrangling on the client side.

## Stack

- **Backend** — FastAPI (Python 3.11+), APScheduler for cron, slowapi for rate limits, SQLAlchemy ORM.
- **Database** — SQLite at `data/supportbot.db`. One file, easy backup.
- **AI** — Anthropic Claude (`claude-sonnet-4-20250514` for chat, `claude-3-5-haiku` for healer/health).
- **Frontend** — React + Vite, built to `frontend/dist/`, served by FastAPI in prod.
- **Auth** — JWT in HttpOnly cookie. Two cookies: `sb_super_token` (super admin), `sb_client_token` (tenant).
- **Widget** — Plain JS at `static/widget.js`, injects an iframe pointing at `/embed/:botId`.

## Local development

### Prereqs
- Python 3.11+
- Node 18+

### First-time setup

```bash
git clone <repo>
cd supportbot-studio-v2py

# Backend
python -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install -r requirements.txt

# Env
cp .env.example .env
# Fill in ANTHROPIC_API_KEY, JWT_SECRET_KEY, SUPER_ADMIN_PASSWORD at minimum
# Generate a JWT key: python -c "import secrets; print(secrets.token_hex(32))"

# Frontend (one-time install + build, OR run dev server in parallel)
cd frontend
npm install
npm run build          # produces frontend/dist/ — served by backend in prod
# OR for hot reload during dev:
# npm run dev          # runs at :5173, proxies /api to :8000
cd ..

# Run backend
uvicorn backend.main:app --reload
```

Backend at `http://localhost:8000`. If you ran `npm run build`, the React app is served at `/` automatically. Otherwise visit the Vite dev server at `http://localhost:5173`.

### Default super admin

On first boot, a super admin is created from `SUPER_ADMIN_USERNAME` / `SUPER_ADMIN_PASSWORD` in `.env`. Log in at `/super-admin`.

### Env vars

Required:
| Var | Notes |
|---|---|
| `ANTHROPIC_API_KEY` | Claude API key |
| `JWT_SECRET_KEY` | 32-byte hex. `python -c "import secrets; print(secrets.token_hex(32))"` |
| `SUPER_ADMIN_USERNAME` | Default `admin` |
| `SUPER_ADMIN_PASSWORD` | Set this. Boot guard refuses to start in prod with the default. |
| `APP_URL` | Public URL of the deployed app. Used as the credentialed CORS origin for admin endpoints. Dev: `http://localhost:8000`. |

Optional (notifications):
| Var | Used for |
|---|---|
| `TELEGRAM_BOT_TOKEN` / `TELEGRAM_CHAT_ID` | Escalations + scheduled reports |
| `EMAILJS_*` (4 vars) | Email escalation |
| `TWILIO_ACCOUNT_SID` / `TWILIO_AUTH_TOKEN` / `TWILIO_WHATSAPP_FROM` / `TWILIO_WHATSAPP_TO` | WhatsApp escalation |

Optional (auto-heal):
| Var | Default |
|---|---|
| `AUTO_HEAL_ENABLED` | `true` |
| `HEALTH_CHECK_INTERVAL_MINUTES` | `15` |
| `MAX_HEAL_RETRIES` | `2` |

`ENV=dev` in `.env` skips the boot guard so you can run with the default password locally.

## API reference

All endpoints prefixed `/api`. Auth is cookie-based — log in once, the cookie carries through.

### Auth — `/api/auth`
| Method | Path | Auth | What it does |
|---|---|---|---|
| POST | `/super/login` | none (5 / 15 min) | Super admin login |
| POST | `/login` | none (5 / 15 min) | Tenant login |
| POST | `/logout` | any | Clears cookies |
| GET | `/me` | any | Returns current user (super or tenant) |
| PUT | `/change-password` | tenant | Self-service password change |

### Admin — `/api/admin` (super admin only)
| Method | Path | What it does |
|---|---|---|
| GET / POST | `/tenants` | List / create tenant |
| PUT / DELETE | `/tenants/{id}` | Update / delete tenant |
| POST | `/tenants/{id}/reset-password` | Reset a tenant's password |
| POST | `/tenants/{id}/reset-api-key` | Issue new API key |
| GET | `/billing` | Per-tenant usage + plan |
| GET | `/overview` | Aggregate stats across all tenants |
| GET | `/system` | Server stats (DB size, uptime, scheduler jobs) |
| POST | `/reset-monthly-counters` | Manual trigger of the monthly reset job |
| PUT | `/super/password` | Super admin self-service password change |
| GET | `/health` | Full health snapshot |
| GET | `/errors` | Error log with filters |
| GET | `/errors/stats` | Error rate + breakdown |
| POST | `/errors/{id}/resolve` | Mark resolved |
| POST | `/errors/{id}/retry` | Replay a failed operation |

### Chat — `/api/chat`
| Method | Path | Auth | What it does |
|---|---|---|---|
| POST | `/` | tenant | Authenticated chat (admin testing) |
| POST | `/public` | none (20 / min) | Public widget chat — what the embed calls |
| POST | `/rate` | none | Thumbs up/down on a conversation |

### Config — `/api/config`
| Method | Path | Auth | What it does |
|---|---|---|---|
| GET / PUT | `/` | tenant | Bot config (name, color, welcome, voice toggle) |
| GET | `/public/{bot_id}` | none (20 / min) | Safe config for the widget |

### Knowledge — `/api/knowledge` (tenant)
| Method | Path | What it does |
|---|---|---|
| GET / POST | `/` | List / add FAQ |
| DELETE | `/{id}` | Remove FAQ |
| POST | `/upload` | Upload PDF/DOCX/CSV/TXT — extracts FAQ pairs |

### Sales — `/api/sales`
| Method | Path | Auth | What it does |
|---|---|---|---|
| GET / PUT | `/config` | tenant | Sales config (offers, exit-intent, popup timing) |
| GET | `/leads` | tenant | Lead board |
| POST | `/leads/capture` | tenant | Manual lead entry |
| POST | `/leads/capture/public` | none (20 / min) | Widget-side lead capture |
| PUT | `/leads/{id}/follow-up` | tenant | Mark contacted / status |
| GET | `/leads/stats` | tenant | Conversion numbers |

### Visitors — `/api/visitors` (tenant)
| Method | Path | What it does |
|---|---|---|
| GET | `/` | List visitors with tag filters |
| GET | `/{visitor_id}/history` | Past conversations + AI summary |

### Webhooks — `/api/webhooks` (tenant)
| Method | Path | What it does |
|---|---|---|
| GET / POST | `/` | List / add webhook (Slack, Discord, WhatsApp, custom_https) |
| PUT / DELETE | `/{id}` | Update / remove |
| POST | `/{id}/test` | Send a test payload |

URLs are validated against a per-platform allowlist (https only) to prevent SSRF.

See [docs/webhooks.md](docs/webhooks.md) for webhook receiver integration.

### Reports — `/api/reports` (tenant)
| Method | Path | What it does |
|---|---|---|
| GET / PUT | `/` | Schedule daily / weekly digest via Telegram or email |

### Analytics — `/api/analytics` (tenant)
| Method | Path | What it does |
|---|---|---|
| GET | `/summary` | Totals + auto-reply rate + estimated savings |
| GET | `/conversations` | Paginated conversation log |
| GET | `/top-questions` | Most-asked questions |
| GET | `/hourly` | Hour-of-day distribution |
| GET | `/languages` | Language split |
| GET | `/export` | CSV download (Excel-injection safe) |

### Escalate — `/api/escalate`
| Method | Path | Auth | What it does |
|---|---|---|---|
| POST | `/` | tenant | Trigger escalation from admin UI |
| POST | `/public` | none | Widget-side escalation, retries via background job if all channels fail |

### Health — `/api/health`
| Method | Path | What it does |
|---|---|---|
| GET | `/` | DB + Anthropic + Telegram reachability, disk, error rate, tenant count |

## Embed widget

Drop this into the client's site. That's it.

```html
<script src="https://your-app.onrender.com/widget.js" data-bot-id="bot_xxxxx"></script>
```

The script injects an iframe pointing at `/embed/<bot-id>`. The iframe pulls public config from `/api/config/public/<bot-id>`, then chats via `/api/chat/public`. No CORS pain — public endpoints accept any origin (no credentials). Admin endpoints stay locked to `APP_URL`.

Get the `data-bot-id` value from the tenant's dashboard after the super admin creates them.

## Deploy to Render

1. Push to GitHub.
2. Create a new Web Service on Render, point it at the repo.
3. Render reads `render.yaml` — Python runtime, persistent disk mounted at `/data`, build + start commands wired up.
4. Set these env vars in the Render dashboard (don't commit secrets):
   - `ANTHROPIC_API_KEY`
   - `JWT_SECRET_KEY`
   - `SUPER_ADMIN_PASSWORD`
   - `APP_URL` — your Render URL, e.g. `https://supportbot-studio.onrender.com`
   - Anything else you actually use (Telegram, EmailJS, Twilio).
5. Deploy. First boot creates the super admin from your env vars.
6. Log in at `https://your-app.onrender.com/super-admin`, create your first tenant.

The persistent disk holds `data/supportbot.db` and `uploads/`. Don't lose it.

## Project layout

```
backend/
  main.py              # FastAPI entry, lifespan, tiered CORS, static serving
  config.py            # pydantic-settings, boot guard
  database.py          # All SQLAlchemy models + init_db + column migrations
  routers/             # auth_api, admin, chat, config_api, knowledge, sales,
                       # visitors, webhooks, reports, analytics, escalate, health
  services/            # ai_chat, auto_reply, doc_processor, telegram_notify,
                       # email_notify, webhook_sender, report_scheduler,
                       # rate_limit, health_monitor, healer, auth
  middleware/          # error_handler
  utils/               # text_similarity, csv_export
frontend/
  src/                 # App.jsx + components (AdminPanel, ChatWidget, etc.)
  dist/                # Built bundle, served by FastAPI in prod
static/
  widget.js            # Embed loader
data/
  supportbot.db        # SQLite, persisted on disk
migrate_visitor_constraint.py   # Idempotent migration: composite unique on visitors
```

## Notes

- **Rate limits**: public endpoints 20/min per IP, login endpoints 5 per 15 min. 429 with a clear message.
- **CORS**: tiered. Public endpoints accept any origin (no creds). Everything else locked to `APP_URL` with credentials.
- **Boot guard**: refuses to start in prod (`ENV != "dev"`) if `JWT_SECRET_KEY` or `SUPER_ADMIN_PASSWORD` are still defaults.
- **Tenant isolation**: every tenant-scoped query filters by `bot_id`. Visitors have a composite unique on `(bot_id, visitor_id)` — same visitor across two bots is two rows.
