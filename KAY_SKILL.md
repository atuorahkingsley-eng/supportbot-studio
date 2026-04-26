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

*Last updated from: `CLAUDE.md` — Supplier Outreach Bot (2026-04-25)*
