# KAY_SKILL.md — How to Work With Kay

> Load this skill at the start of any project session with Kay.
> It governs communication style, project analysis, architecture expectations, and coding standards.

---

## WHO KAY IS

Kay is a developer based in Lagos, Nigeria. Entrepreneurial mindset — every project must be practical and monetizable. Runs SupportBot Studio (white-label AI customer support SaaS) and builds automation products (Telegram bots, supplier pipelines, social schedulers).

**Core stack Kay works in:**
- Python 3.11+ · FastAPI · Telegram bots (`python-telegram-bot`)
- Claude API (Anthropic) · Serper.dev · Zoho SMTP
- SQLite / CSV storage · Docker · GitHub Actions · Render / Vercel

**Kay's builder pattern:**
1. Blueprint first (architecture + spec)
2. Build in layers (core → discovery/logic → output/delivery → tests)
3. Test end-to-end before going live
4. Monetize or deploy before adding Phase 2 features

---

## HOW TO TALK TO KAY

### Communication rules (always apply)

| Rule | Detail |
|---|---|
| **Brief and direct** | Lead with the answer. No preambles. |
| **Analogies** | Use simple analogies — they help Kay learn. Think "explain like Kay is 10." |
| **Plain language** | No jargon dumps. If a technical word is needed, define it in one sentence with an analogy. |
| **Ask before elaborating** | If a full explanation would take more than ~5 sentences, ask: *"Want the full breakdown?"* |
| **No fluff** | No "Great question!", no "Certainly!", no lengthy disclaimers. |

### Tone examples

✅ Good: *"Think of `scraper.py` like a street scout — it visits a supplier's website and picks up any email address it finds in the footer. Under the hood, it's an HTTP-based utility that uses BeautifulSoup4 to parse the supplier's public contact page and extract the first valid email."*

Lead with the analogy, follow with the technical detail. Plain English first, tech second — always in that order.

---

## HOW TO ANALYZE KAY'S PROJECTS

Before writing any code or giving any recommendation, do this in order:

### Step 1 — Read the architecture
Understand:
- What the project does (one sentence)
- The directory layout and what each folder owns
- The data flow (where data enters → transforms → exits)
- What is ACTIVE vs PARKED vs DORMANT

### Step 2 — State your reasoning
Before touching any file, say:
```
Target file: src/discovery/search.py
Purpose: [one line]
Depends on: [imports/models it uses]
Used by: [who calls this]
Fits architecture because: [reason]
```

### Step 3 — Flag conflicts before acting
If a request conflicts with the architecture, **STOP and ask**. Never silently bend the rules.

### Step 4 — Show impact
When adding or changing something, always note:
- What it touches downstream
- Whether tests need updating
- Whether this is a breaking change

---

## ARCHITECTURE PRINCIPLES (apply to all Kay's projects)

These are non-negotiables across every project Kay builds:

### Separation of concerns
Each layer does ONE job. It does not know about the others.

| Layer | Job | Does NOT know about |
|---|---|---|
| **discovery/** | Find data, return model objects | Email, sending, storage |
| **outreach/** | Write and send | How suppliers were found |
| **tracking/** | Log and report | Business logic |
| **core/** | Types, config, logging, errors | Everything else |

Think of it like a restaurant kitchen: the waiter (discovery) takes the order, the chef (outreach) cooks it, the cashier (tracking) logs the sale. None of them do each other's jobs.

> **SupportBot Studio note:** This project does not have a `core/` folder. Backend layout is `routers/` + `services/` + `utils/` + `alembic/` under `backend/`. The separation principle still applies — just with project-specific folder names.

### Adapter pattern for extensible sources
New sources (directories, APIs, scrapers) → drop in a new adapter file that implements the base class. **Never modify `main.py` to add a new source.**

### Parking lot discipline
If a source hits a structural blocker (Cloudflare, JS-render, ToS), it gets PARKED:
- Register with `disabled=True`
- Add `pytest.mark.skip` to its tests
- Keep the code — it's the cheapest starting point for revival
- Do NOT revive without an architecture discussion

### Data flow is linear
```
[Source adapters] → [Supplier model] → [Enrichment pass] → [AI drafting] → [Send] → [Track]
```
Nothing skips a step. Nothing calls backwards up the chain.

---

## CODING STANDARDS (always enforce)

| Standard | Rule |
|---|---|
| **Types** | `mypy --strict` must pass. No implicit `Any`. Every function fully typed. |
| **Naming** | `snake_case` functions/vars/modules · `PascalCase` classes · `UPPER_SNAKE` constants |
| **Functions** | Small and single-purpose. If you need a comment to explain *what* (not *why*), split the function. |
| **Docstrings** | Google-style on every public function and class |
| **Errors** | Custom exceptions from `core/errors.py`. No bare `except:`. |
| **Logging** | `structlog` with structured key=value. No `print()` inside `src/`. |
| **Secrets** | Env vars only. Never hardcode. Never commit `.env`. |
| **Composition** | Prefer composition over inheritance. |
| **Dry-run** | All send/write operations must support `--dry-run`. Default to dry-run in dev. |

> **SupportBot Studio note:** `core/errors.py` does not exist in this project. Custom exceptions live in the service file that owns them — e.g., `BrandVoiceAnalysisError` is defined inside `backend/services/brand_voice_analyzer.py`. The "no bare `except:`" rule still stands.

---

## OUTPUT FORMAT (when creating files)

Always lead with this block before showing code:

```
[filepath]
Purpose: [one line]
Depends on: [imports]
Used by: [consumers]
```

Then the code (fully typed, documented). Then:

```
Tests: [what to test and where]
```

For architecture changes:

```
ARCHITECTURE UPDATE
What: [change]
Why: [reason]
Impact: [what breaks or changes downstream]
```

---

## RULES — NEVER / ALWAYS

**NEVER:**
- Modify code outside the explicit request
- Install packages without explaining why
- Create duplicate code — find the existing solution first
- Skip types or error handling
- Generate code without stating target directory first
- Send real emails/data during dev — dry-run by default
- Hardcode secrets
- Assume — ask if unclear

**ALWAYS:**
- Read architecture before writing code
- State filepath and reasoning BEFORE creating files
- Show dependencies and consumers
- Include types, docstrings, and inline comments
- Suggest relevant tests after implementation
- Keep functions small and single-purpose
- Ask before giving a long/elaborate answer

---

## QUICK REFERENCE — KAY'S ACTIVE PROJECTS

| Project | Stack | Status |
|---|---|---|
| Supplier Outreach Bot | Python, Serper.dev, Apollo, Claude API, Zoho SMTP, CSV, Docker | Production (live sends, warmup active) |
| Kilo Picks (football bot) | Python, Telegram, API-Football, Claude API | Active, tuning |
| Social Scheduler SaaS | FastAPI, React/Vite, Claude API, Cloudinary, Meta Graph API, SQLite | MVP built, deploying |
| SupportBot Studio | FastAPI, React, SQLite, Anthropic API | Deployed on Render |

---

---

## SupportBot Studio — Project-Specific Conventions

These rules document what the SupportBot Studio v2 codebase *actually does* today. They override the generic standards above where they conflict, and capture conventions the generic standards don't mention. Audit date: 2026-05-04.

### Logging

- **structlog is the target, not the current state.** Only `backend/routers/brand_voice.py` and `backend/services/brand_voice_analyzer.py` use it. Every other module has zero logging. New modules should add structlog at request entry and on error exit.
- **`print()` is allowed in two places only:** `backend/config.py` (boot-guard messages that must run before any logger is configured) and APScheduler jobs in `backend/main.py`. Anywhere else, use structlog.

### Error Handling

- **Silent `except Exception: pass` requires an inline comment justifying it.** Allowed only in infrastructure-level guard code where bubbling the error would crash the app. Examples: `database.py:372` (column-already-exists shim), `safe_executor.py:88` (retry exhaustion), `error_handler.py:89` (don't crash the error handler), `chat.py:190` (final fallback).
- **Fan-out operations wrap each channel independently.** When sending to multiple targets (Telegram, email, every webhook), each gets its own try/except and writes to `ErrorLog` on failure. Partial success is the correct outcome — one channel failing must not abort the others. Pattern lives in `backend/routers/escalate.py:31-44` (`_log_notification_error`).
- **Custom exceptions live in the service file that owns them.** No central `core/errors.py`. Example: `BrandVoiceAnalysisError` in `backend/services/brand_voice_analyzer.py:35`.

### Migrations

- **Hand-written, additive-only.** Every migration after the baseline includes a top-of-file comment saying "Hand-written rather than autogenerated" with the reason — autogenerate produces drift noise (orphan backup tables, type churn, FK shuffle). Autogenerate output is reviewed for drift, but never used verbatim.
- **One concern per migration.** No drops, renames, or data movement bundled into a single-purpose additive migration.
- **Don't add columns in `database.py:_migrate_columns()`.** That shim exists only for columns added before Alembic was introduced. New columns get a proper Alembic migration.

### API Endpoint Patterns

- **Rate limits are tiered by downstream cost:**
  - `5/15 minutes` — auth endpoints (login, super login). Source: `auth_api.py:42,61`.
  - `5/minute` — escalation (fans out to Telegram + email + every webhook). Source: `escalate.py:177`.
  - `10/minute` — endpoints that trigger paid Claude calls. Source: `chat.py:438`.
  - `20/minute` — public chat. Source: `chat.py:365`.
- **Auth dependency naming signals intent:**
  - `_: dict = Depends(get_super_admin)` — pure gate, payload unused.
  - `tenant: Tenant = Depends(get_current_client)` — `tenant.bot_id` is used downstream for tenant isolation.
- **Public widget endpoints share the router with a `/public` path suffix.** `POST /api/chat/public` (no auth) lives in the same router as `POST /api/chat` (auth). Never split into separate router files for public vs private.
- **Pydantic schemas live at the top of the router file** under a `# ── Request/Response schemas ──` divider. There is no central `schemas.py`. Keep schemas next to the endpoint that uses them.

### Database Sessions

- **Two patterns, picked by context:**
  - Request handlers: `db: Session = Depends(get_db)`.
  - Background jobs, scheduler tasks, middleware: `SessionLocal()` directly, with `try/finally: db.close()`. FastAPI DI is unavailable in those contexts.
- **`backend/database.py:_migrate_columns()` is a legacy startup shim** for columns added before Alembic. Additive-only, swallows "column already exists" errors, runs on every `init_db()`. **Do not add new columns here** — write an Alembic migration instead.

### Security

- **Boot guard.** `backend/config.py:52-64` calls `sys.exit(1)` if `JWT_SECRET_KEY` or `SUPER_ADMIN_PASSWORD` are missing or still set to defaults — unless `ENV=dev`. The `print("Boot guard passed.")` line is intentional startup output.
- **Tiered CORS** via `TieredCORSMiddleware` in `backend/main.py:217-264`:
  - Widget endpoints (`_PUBLIC_EXACT` set + `_PUBLIC_PREFIXES`): `allow_origins=["*"]`, no credentials.
  - Everything else: locked to `APP_URL`, `credentials=True`.
  - Adding a new public endpoint? Register its path in the middleware sets.
- **HttpOnly cookie auth.** Tokens live in `sb_client_token` / `sb_super_token`. `Secure=True` unless `ENV=dev`, `SameSite=lax`, `HttpOnly=True`. Source: `auth_api.py:25-26`. Both `get_current_client` and `get_super_admin` also accept `Authorization: Bearer <token>` as a fallback for programmatic API-key access.
- **HMAC-SHA256 webhook signing** in `backend/services/webhook_sender.py:17-67`. Custom HTTPS webhooks are signed over the raw body bytes; signature header is `X-SupportBot-Signature: sha256=<hex>` (Stripe/GitHub style). Body is encoded once and reused for both signing and the POST — never encode twice or signatures drift.

### Frontend

- **`credentials: 'include'` on every fetch to authenticated endpoints.** Cookies are HttpOnly + SameSite=lax, so omitting credentials happens to work on same-site by accident — but cross-site setups and stricter cookie modes break silently. This rule was added after `AdminPanel.jsx` and `WebhookSettings.jsx` were found missing it; both have been patched (16 fetch sites updated).
- **Async feedback uses `addToast(msg, type)` from `ToastContext`.** Never `alert()`. `setError` is reserved for inline form-level validation, not for surfacing the result of an async call.
- **Two-layer CSS.** Reusable elements use global utility classes from `globals.css` (`.card`, `.btn`, `.btn-primary`, `.input`, `.label`). Component-specific layout uses inline `style={{...}}` referencing CSS variables (`var(--body-bg)`, `var(--text-secondary)`, etc.). No CSS Modules, no Tailwind, no per-component stylesheets.

### Code Style

- **Section dividers inside files** use `# ── Section name ──────────` (em-dashes, trailing dashes to roughly column 79). Used in every router, service, and `main.py` — 75+ occurrences across 15 files. New files should follow it.
- **Docstrings: terse is the actual norm.** Most public functions have no docstring or just a single sentence. True Google-style with `Args:`/`Returns:` is reserved for functions with non-obvious params or return shapes — currently only `webhook_sender.py` and `brand_voice_analyzer.py`. The "Google-style on every public function" rule above is aspirational; current practice is "one-liner minimum, full Google-style when the shape isn't obvious."
- **No `core/` folder in this project.** Backend layout is `routers/` + `services/` + `utils/` + `alembic/` under `backend/`.

---

*Last updated from: `CLAUDE.md` — Supplier Outreach Bot (2026-04-25)*
