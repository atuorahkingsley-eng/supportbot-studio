# SupportBot Studio — Multi-Tenant Spec

## Overview

This spec transforms SupportBot from a single-instance app into a multi-tenant SaaS platform. One server, unlimited clients. Each client gets their own isolated chatbot, admin panel, data, and embeddable widget.

Think of it like Shopify: one platform, many stores, each completely independent.

---

## ARCHITECTURE

```
┌─────────────────────────────────────────────────────┐
│                  YOUR RENDER SERVER                   │
│                                                       │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  │
│  │  Client A    │  │  Client B    │  │  Client C    │  │
│  │  bot_abc123  │  │  bot_def456  │  │  bot_ghi789  │  │
│  │              │  │              │  │              │  │
│  │  FAQs: 25    │  │  FAQs: 12    │  │  FAQs: 40    │  │
│  │  Convos: 150 │  │  Convos: 80  │  │  Convos: 300 │  │
│  │  Leads: 20   │  │  Leads: 5    │  │  Leads: 45   │  │
│  └─────────────┘  └─────────────┘  └─────────────┘  │
│                                                       │
│  ┌─────────────────────────────────────────────────┐  │
│  │              SQLite Database                      │  │
│  │  All data tagged with bot_id                      │  │
│  │  Client A only sees bot_id = "bot_abc123"        │  │
│  └─────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────┘

Client A's website                Client B's website
┌──────────────────┐              ┌──────────────────┐
│  shopafrica.com  │              │  techstartup.io  │
│                  │              │                  │
│  <script src=    │              │  <script src=    │
│  ".../widget.js" │              │  ".../widget.js" │
│  data-bot-id=    │              │  data-bot-id=    │
│  "bot_abc123">   │              │  "bot_def456">   │
│                  │              │                  │
│  ┌────────────┐  │              │  ┌────────────┐  │
│  │ Chat Widget │  │              │  │ Chat Widget │  │
│  │ (iframe)    │  │              │  │ (iframe)    │  │
│  └────────────┘  │              │  └────────────┘  │
└──────────────────┘              └──────────────────┘
```

---

## BUILD ORDER

Build in this exact sequence:

1. Database migration — add bot_id to all models
2. Tenant (client) management — create/edit/delete tenants
3. Authentication — login system for admin panel
4. bot_id isolation — all API queries filter by bot_id
5. Super admin panel — your master dashboard to manage all clients
6. Client admin panel — each client's isolated dashboard
7. Embed widget system — widget.js + iframe + /embed/:bot_id route
8. API key system — each client gets an API key for their bot
9. Usage tracking & billing helpers
10. Deployment updates

---

## PHASE 1: DATABASE MIGRATION

### New Model — `Tenant`

This is the core model. One tenant = one client = one chatbot.

```python
class Tenant(Base):
    __tablename__ = "tenants"
    
    id = Column(Integer, primary_key=True)
    bot_id = Column(String, unique=True, nullable=False, index=True)  # e.g. "bot_abc123"
    
    # Client info
    owner_name = Column(String, nullable=False)              # "John Doe"
    owner_email = Column(String, nullable=False, unique=True) # "john@shopafrica.com"
    company_name = Column(String, nullable=False)             # "ShopAfrica"
    
    # Auth
    password_hash = Column(String, nullable=False)            # bcrypt hash
    api_key = Column(String, unique=True, nullable=False)     # "sk_live_xxxxxxxxxxxx"
    
    # Plan & billing
    plan = Column(String, default="basic")                    # "basic" | "pro" | "enterprise"
    is_active = Column(Boolean, default=True)
    monthly_message_limit = Column(Integer, default=1000)     # messages per month
    messages_used_this_month = Column(Integer, default=0)
    
    # Timestamps
    created_at = Column(DateTime, default=func.now())
    last_login_at = Column(DateTime, nullable=True)
    
    # Relationships
    config = relationship("BotConfig", back_populates="tenant", uselist=False)
```

### New Model — `SuperAdmin`

Your master account to manage everything.

```python
class SuperAdmin(Base):
    __tablename__ = "super_admins"
    
    id = Column(Integer, primary_key=True)
    username = Column(String, unique=True, nullable=False)
    password_hash = Column(String, nullable=False)
    created_at = Column(DateTime, default=func.now())
```

### Add `bot_id` to ALL Existing Models

Every existing model gets a `bot_id` column:

```python
# BotConfig
bot_id = Column(String, ForeignKey("tenants.bot_id"), nullable=False, index=True)

# FAQEntry
bot_id = Column(String, ForeignKey("tenants.bot_id"), nullable=False, index=True)

# Conversation
bot_id = Column(String, ForeignKey("tenants.bot_id"), nullable=False, index=True)

# Message
bot_id = Column(String, ForeignKey("tenants.bot_id"), nullable=False, index=True)

# Visitor
bot_id = Column(String, ForeignKey("tenants.bot_id"), nullable=False, index=True)

# VisitorConversation
bot_id = Column(String, ForeignKey("tenants.bot_id"), nullable=False, index=True)

# Lead
bot_id = Column(String, ForeignKey("tenants.bot_id"), nullable=False, index=True)

# WebhookConfig
bot_id = Column(String, ForeignKey("tenants.bot_id"), nullable=False, index=True)

# ReportSchedule
bot_id = Column(String, ForeignKey("tenants.bot_id"), nullable=False, index=True)

# SalesConfig
bot_id = Column(String, ForeignKey("tenants.bot_id"), nullable=False, index=True)
```

### Migration Strategy

Since we use SQLite, the simplest approach:

1. Add columns with `nullable=True` first
2. Set default bot_id for existing data: `"default"`
3. Then change to `nullable=False`

Or use Alembic for proper migrations:

```bash
pip install alembic
alembic init alembic
alembic revision --autogenerate -m "add multi-tenancy"
alembic upgrade head
```

Add `alembic` to requirements.txt.

---

## PHASE 2: TENANT MANAGEMENT

### API Endpoints — `/api/admin/tenants` (Super Admin Only)

**`POST /api/admin/tenants`** — Create new tenant (when you onboard a client)
```json
Request: {
    "owner_name": "John Doe",
    "owner_email": "john@shopafrica.com",
    "company_name": "ShopAfrica",
    "password": "clientpassword123",
    "plan": "pro"
}

Response: {
    "bot_id": "bot_a1b2c3d4",
    "api_key": "sk_live_xxxxxxxxxxxxxxxx",
    "admin_url": "https://your-app.onrender.com/admin/bot_a1b2c3d4",
    "embed_code": "<script src=\"https://your-app.onrender.com/widget.js\" data-bot-id=\"bot_a1b2c3d4\"></script>"
}
```

**`GET /api/admin/tenants`** — List all tenants
```json
Response: [
    {
        "bot_id": "bot_a1b2c3d4",
        "company_name": "ShopAfrica",
        "owner_email": "john@shopafrica.com",
        "plan": "pro",
        "is_active": true,
        "messages_used_this_month": 342,
        "monthly_message_limit": 5000,
        "faq_count": 25,
        "conversation_count": 150,
        "lead_count": 20,
        "created_at": "2026-03-21T10:00:00Z",
        "last_login_at": "2026-03-21T14:30:00Z"
    }
]
```

**`GET /api/admin/tenants/{bot_id}`** — Get single tenant details

**`PUT /api/admin/tenants/{bot_id}`** — Update tenant (change plan, limits, active status)
```json
Request: {
    "plan": "enterprise",
    "monthly_message_limit": 10000,
    "is_active": true
}
```

**`DELETE /api/admin/tenants/{bot_id}`** — Deactivate tenant (soft delete — set is_active=false, don't delete data)

**`POST /api/admin/tenants/{bot_id}/reset-password`** — Reset client password
```json
Request: { "new_password": "newpassword456" }
```

**`POST /api/admin/tenants/{bot_id}/reset-api-key`** — Regenerate API key

### bot_id Generation

```python
import secrets
import string

def generate_bot_id():
    """Generate unique bot ID like 'bot_a1b2c3d4'"""
    chars = string.ascii_lowercase + string.digits
    random_part = ''.join(secrets.choice(chars) for _ in range(8))
    return f"bot_{random_part}"

def generate_api_key():
    """Generate API key like 'sk_live_xxxxxxxxxxxxxxxxxxxxxxxx'"""
    return f"sk_live_{secrets.token_hex(24)}"
```

---

## PHASE 3: AUTHENTICATION

### Two Auth Systems

1. **Super Admin auth** — You (the platform owner) manage all tenants
2. **Client auth** — Each client manages their own chatbot

### Auth Implementation

Use JWT tokens stored in httpOnly cookies.

```
pip install python-jose[cryptography] passlib[bcrypt]
```

Add to requirements.txt: `python-jose[cryptography]`, `passlib[bcrypt]`

### Auth Utilities — `backend/services/auth.py`

```python
from datetime import datetime, timedelta
from jose import jwt, JWTError
from passlib.context import CryptContext
from backend.config import settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

SECRET_KEY = settings.jwt_secret_key  # Add to .env
ALGORITHM = "HS256"

def hash_password(password: str) -> str:
    return pwd_context.hash(password)

def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)

def create_token(data: dict, expires_hours: int = 24) -> str:
    expire = datetime.utcnow() + timedelta(hours=expires_hours)
    return jwt.encode({**data, "exp": expire}, SECRET_KEY, algorithm=ALGORITHM)

def decode_token(token: str) -> dict:
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except JWTError:
        return None
```

### Auth Endpoints — `/api/auth`

**`POST /api/auth/super/login`** — Super admin login
```json
Request: { "username": "admin", "password": "your_master_password" }
Response: { "token": "eyJ...", "role": "super_admin" }
```
Sets httpOnly cookie: `sb_super_token`

**`POST /api/auth/login`** — Client login
```json
Request: { "email": "john@shopafrica.com", "password": "clientpassword123" }
Response: { "token": "eyJ...", "bot_id": "bot_a1b2c3d4", "role": "client" }
```
Sets httpOnly cookie: `sb_client_token`

**`POST /api/auth/logout`** — Clear cookies

**`GET /api/auth/me`** — Get current user from token
```json
Response: {
    "role": "client",
    "bot_id": "bot_a1b2c3d4",
    "company_name": "ShopAfrica",
    "plan": "pro"
}
```

### Auth Middleware — FastAPI Dependencies

```python
from fastapi import Depends, HTTPException, Request

async def get_current_client(request: Request, db: Session = Depends(get_db)) -> Tenant:
    """Extract bot_id from JWT token in cookie. Returns Tenant object."""
    token = request.cookies.get("sb_client_token")
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    payload = decode_token(token)
    if not payload or payload.get("role") != "client":
        raise HTTPException(status_code=401, detail="Invalid token")
    
    tenant = db.query(Tenant).filter(Tenant.bot_id == payload["bot_id"]).first()
    if not tenant or not tenant.is_active:
        raise HTTPException(status_code=403, detail="Account inactive")
    
    return tenant

async def get_super_admin(request: Request, db: Session = Depends(get_db)):
    """Verify super admin token."""
    token = request.cookies.get("sb_super_token")
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    payload = decode_token(token)
    if not payload or payload.get("role") != "super_admin":
        raise HTTPException(status_code=401, detail="Not authorized")
    
    return payload
```

### Protect ALL Existing Endpoints

Every existing API endpoint must be updated to:
1. Require authentication
2. Filter by the authenticated client's `bot_id`

Example — update `/api/knowledge`:

```python
# BEFORE (single tenant)
@router.get("")
def list_faqs(db: Session = Depends(get_db)):
    return db.query(FAQEntry).all()

# AFTER (multi-tenant)
@router.get("")
def list_faqs(
    db: Session = Depends(get_db),
    tenant: Tenant = Depends(get_current_client)
):
    return db.query(FAQEntry).filter(FAQEntry.bot_id == tenant.bot_id).all()
```

Apply this pattern to EVERY endpoint:
- `/api/knowledge` — filter by bot_id
- `/api/chat` — filter by bot_id, increment messages_used_this_month
- `/api/analytics` — filter by bot_id
- `/api/escalate` — filter by bot_id
- `/api/webhooks` — filter by bot_id
- `/api/reports` — filter by bot_id
- `/api/sales/config` — filter by bot_id
- `/api/sales/leads` — filter by bot_id
- `/api/config` — filter by bot_id
- `/api/visitors` — filter by bot_id

### Message Limit Enforcement

In `/api/chat`, check message limits before processing:

```python
@router.post("")
async def chat(
    request: ChatRequest,
    db: Session = Depends(get_db),
    tenant: Tenant = Depends(get_current_client)
):
    # Check message limit
    if tenant.messages_used_this_month >= tenant.monthly_message_limit:
        return {"reply": "This chatbot has reached its monthly message limit. Please contact the site administrator.", "was_auto_reply": True}
    
    # ... process message ...
    
    # Increment counter (only for AI replies, not auto-replies)
    if not was_auto_reply:
        tenant.messages_used_this_month += 1
        db.commit()
```

### Monthly Reset Cron

Add to APScheduler — reset all tenants' message counts on the 1st of each month:

```python
def reset_monthly_counts():
    db = SessionLocal()
    try:
        db.query(Tenant).update({Tenant.messages_used_this_month: 0})
        db.commit()
    finally:
        db.close()

# Schedule: 1st of every month at midnight UTC
scheduler.add_job(reset_monthly_counts, 'cron', day=1, hour=0, minute=0)
```

---

## PHASE 4: BOT_ID ISOLATION

### Chat API — Public Endpoint (No Auth Required)

The chat endpoint used by the embeddable widget must be public (customers aren't logged in) but must identify which bot they're talking to.

**New route:** `POST /api/chat/public`

```python
@router.post("/public")
async def public_chat(
    request: PublicChatRequest,  # includes bot_id
    db: Session = Depends(get_db)
):
    # Validate bot_id exists and is active
    tenant = db.query(Tenant).filter(
        Tenant.bot_id == request.bot_id,
        Tenant.is_active == True
    ).first()
    
    if not tenant:
        return {"reply": "This chatbot is not available.", "was_auto_reply": True}
    
    # Check message limit
    if tenant.messages_used_this_month >= tenant.monthly_message_limit:
        return {"reply": "This chatbot has reached its monthly limit.", "was_auto_reply": True}
    
    # Load this tenant's config
    config = db.query(BotConfig).filter(BotConfig.bot_id == request.bot_id).first()
    
    # Load this tenant's FAQs
    faqs = db.query(FAQEntry).filter(FAQEntry.bot_id == request.bot_id).all()
    
    # Process message (auto-reply or Claude)
    # ... same logic but using tenant-specific data ...
    
    # Save with bot_id
    message = Message(
        conversation_id=conversation.id,
        bot_id=request.bot_id,
        role="user",
        content=request.message,
    )
    db.add(message)
    
    # Increment usage
    if not was_auto_reply:
        tenant.messages_used_this_month += 1
    
    db.commit()
```

**PublicChatRequest schema:**
```python
class PublicChatRequest(BaseModel):
    bot_id: str
    session_id: Optional[str] = None
    visitor_id: Optional[str] = None
    message: str
    browser_language: Optional[str] = "en"
    input_method: Optional[str] = "text"
```

### Public Config Endpoint

The embed widget needs to load the bot's config (brand color, agent name, etc.) without authentication.

**`GET /api/config/public/{bot_id}`**

```python
@router.get("/public/{bot_id}")
def get_public_config(bot_id: str, db: Session = Depends(get_db)):
    tenant = db.query(Tenant).filter(
        Tenant.bot_id == bot_id,
        Tenant.is_active == True
    ).first()
    if not tenant:
        raise HTTPException(status_code=404, detail="Bot not found")
    
    config = db.query(BotConfig).filter(BotConfig.bot_id == bot_id).first()
    
    # Only return public-safe fields
    return {
        "bot_id": bot_id,
        "business_name": config.business_name if config else tenant.company_name,
        "agent_name": config.agent_name if config else "SupportBot",
        "brand_color": config.brand_color if config else "#6366F1",
        "welcome_message": config.welcome_message if config else "Hi! How can I help?",
        "voice_enabled": config.voice_enabled if config else False,
        "sales_enabled": False,  # Don't expose sales config publicly
    }
```

### Public Escalation Endpoint

```python
@router.post("/public")
async def public_escalate(request: PublicEscalateRequest, db: Session = Depends(get_db)):
    tenant = db.query(Tenant).filter(Tenant.bot_id == request.bot_id, Tenant.is_active == True).first()
    if not tenant:
        raise HTTPException(status_code=404)
    
    # ... same escalation logic but loads tenant's webhook/email config ...
```

---

## PHASE 5: SUPER ADMIN PANEL

Your master dashboard to manage all clients. Accessible at `/super-admin`.

### Frontend Route: `/super-admin`

**Login page** — username + password → sets `sb_super_token` cookie

**Dashboard after login:**

#### Overview Tab
- Total tenants (active/inactive)
- Total messages this month (across all clients)
- Total conversations today
- Total leads captured
- Revenue estimate: `active_tenants × average_plan_price`
- API cost estimate: `total_ai_messages × $0.003` (approximate per message)

#### Tenants Tab
- Table of all clients:
  | Company | Plan | Messages Used | Limit | FAQs | Convos | Leads | Status | Actions |
  |---------|------|--------------|-------|------|--------|-------|--------|---------|
  | ShopAfrica | Pro | 342/5000 | 5000 | 25 | 150 | 20 | ✅ Active | Edit / Disable |

- **Create Tenant button** → form: name, email, company, password, plan
- **Click a tenant** → detail view with their analytics (read-only)
- **Actions:** Edit plan, reset password, regenerate API key, toggle active/inactive
- **Search + filter** by company name, plan, status

#### Billing Tab
- Monthly summary per client
- Total revenue breakdown by plan
- API usage cost estimate
- Export billing data as CSV

#### System Tab
- Server health: uptime, database size, total records
- Your environment variables status (which are configured)
- Scheduler status (reports running)
- Quick actions: reset all monthly counters, export full database backup

### Super Admin Auto-Setup

On first startup, if no SuperAdmin exists, auto-create one:

```python
# In main.py on startup
@app.on_event("startup")
def create_default_super_admin():
    db = SessionLocal()
    existing = db.query(SuperAdmin).first()
    if not existing:
        admin = SuperAdmin(
            username=settings.super_admin_username or "admin",
            password_hash=hash_password(settings.super_admin_password or "changeme123"),
        )
        db.add(admin)
        db.commit()
        print("⚡ Default super admin created: admin / changeme123")
        print("⚠️  CHANGE THIS PASSWORD IMMEDIATELY via the Super Admin panel!")
    db.close()
```

Add to `.env`:
```
SUPER_ADMIN_USERNAME=admin
SUPER_ADMIN_PASSWORD=your_secure_password_here
JWT_SECRET_KEY=your_random_secret_key_here
```

---

## PHASE 6: CLIENT ADMIN PANEL

Each client gets their own admin panel at `/admin/{bot_id}` (or after login, redirect to their bot).

### Login Flow

1. Client goes to `https://your-app.onrender.com/login`
2. Enters email + password
3. Backend validates, creates JWT with `bot_id` embedded
4. Redirects to admin panel — they only see their own data
5. All API calls include the JWT cookie → backend extracts `bot_id` → filters all queries

### What Clients See

The exact same admin panel you already built (Configure, Chat Demo, Analytics, Integrations, Sales) — but:

- Data is filtered to their `bot_id` only
- They can't see other clients
- They can't access super admin
- They see their usage: "342 / 5,000 messages used this month"
- They see their plan with upgrade CTA

### Client Self-Service Features

- Change password
- View their API key (masked, with reveal button)
- View their embed code
- See their plan + usage
- Contact you (link to your email/Telegram)

---

## PHASE 7: EMBEDDABLE WIDGET

This is the key product feature — one line of code on any website loads the chatbot.

### How It Works

```
Client's website                    Your server
─────────────────                   ──────────────
1. Page loads widget.js  ───────►  2. Serves widget.js
3. widget.js creates    ───────►  4. Serves /embed/bot_abc123
   an iframe                          (standalone chat page)
5. iframe loads config  ───────►  6. Returns bot config
7. Customer chats       ───────►  8. /api/chat/public processes
```

### File 1: `widget.js` — Served at `/widget.js`

This is a standalone JavaScript file that clients paste on their website. It creates a floating chat bubble.

```javascript
(function() {
  // Read config from script tag
  var script = document.currentScript;
  var botId = script.getAttribute('data-bot-id');
  var position = script.getAttribute('data-position') || 'right'; // "left" or "right"
  var baseUrl = script.src.replace('/widget.js', '');
  
  if (!botId) {
    console.error('SupportBot: data-bot-id attribute is required');
    return;
  }
  
  // Prevent double-loading
  if (document.getElementById('supportbot-widget')) return;
  
  // Create container
  var container = document.createElement('div');
  container.id = 'supportbot-widget';
  container.style.cssText = 'position:fixed;bottom:20px;' + position + ':20px;z-index:99999;font-family:sans-serif;';
  
  // Chat bubble button
  var bubble = document.createElement('div');
  bubble.id = 'supportbot-bubble';
  bubble.innerHTML = '<svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="white" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>';
  bubble.style.cssText = 'width:60px;height:60px;border-radius:50%;display:flex;align-items:center;justify-content:center;cursor:pointer;box-shadow:0 4px 20px rgba(0,0,0,0.2);transition:transform 0.2s;';
  
  // Chat iframe (hidden initially)
  var frame = document.createElement('iframe');
  frame.id = 'supportbot-frame';
  frame.src = baseUrl + '/embed/' + botId;
  frame.style.cssText = 'width:400px;height:600px;max-height:80vh;border:none;border-radius:16px;box-shadow:0 20px 60px rgba(0,0,0,0.15);display:none;margin-bottom:12px;background:white;';
  frame.setAttribute('allow', 'microphone');  // For voice input
  
  // Notification badge
  var badge = document.createElement('div');
  badge.id = 'supportbot-badge';
  badge.textContent = '1';
  badge.style.cssText = 'position:absolute;top:-4px;right:-4px;width:20px;height:20px;border-radius:50%;background:#EF4444;color:white;font-size:11px;font-weight:700;display:flex;align-items:center;justify-content:center;display:none;';
  
  // Toggle chat
  var isOpen = false;
  bubble.onclick = function() {
    isOpen = !isOpen;
    frame.style.display = isOpen ? 'block' : 'none';
    badge.style.display = 'none';
    bubble.innerHTML = isOpen
      ? '<svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="white" stroke-width="2.5"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>'
      : '<svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="white" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>';
  };
  
  // Hover effect
  bubble.onmouseover = function() { bubble.style.transform = 'scale(1.08)'; };
  bubble.onmouseout = function() { bubble.style.transform = 'scale(1)'; };
  
  // Fetch brand color and apply
  fetch(baseUrl + '/api/config/public/' + botId)
    .then(function(r) { return r.json(); })
    .then(function(config) {
      bubble.style.background = config.brand_color || '#6366F1';
    })
    .catch(function() {
      bubble.style.background = '#6366F1';
    });
  
  // Assemble
  var wrapper = document.createElement('div');
  wrapper.style.cssText = 'display:flex;flex-direction:column;align-items:' + (position === 'left' ? 'flex-start' : 'flex-end') + ';';
  wrapper.appendChild(frame);
  
  var bubbleWrapper = document.createElement('div');
  bubbleWrapper.style.cssText = 'position:relative;';
  bubbleWrapper.appendChild(bubble);
  bubbleWrapper.appendChild(badge);
  wrapper.appendChild(bubbleWrapper);
  
  container.appendChild(wrapper);
  document.body.appendChild(container);
  
  // Listen for messages from iframe (for proactive popups)
  window.addEventListener('message', function(event) {
    if (event.data === 'supportbot:notify') {
      if (!isOpen) {
        badge.style.display = 'flex';
      }
    }
    if (event.data === 'supportbot:close') {
      isOpen = false;
      frame.style.display = 'none';
      bubble.innerHTML = '<svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="white" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>';
    }
  });
})();
```

### File 2: Embed Page — `/embed/{bot_id}`

A standalone lightweight chat page rendered inside the iframe. This is a separate React component (or plain HTML) that:

1. Reads `bot_id` from the URL
2. Fetches config from `/api/config/public/{bot_id}`
3. Renders ONLY the chat widget (no admin panel, no info panel)
4. Uses `/api/chat/public` for messages
5. Uses `/api/escalate/public` for escalations

**Frontend route:** Add to React router:
```jsx
<Route path="/embed/:botId" element={<EmbedChat />} />
```

**EmbedChat component:**
```jsx
// frontend/src/components/EmbedChat.jsx
function EmbedChat() {
  const { botId } = useParams()
  const [config, setConfig] = useState(null)
  
  useEffect(() => {
    fetch(`/api/config/public/${botId}`)
      .then(r => r.json())
      .then(setConfig)
      .catch(() => {})
  }, [botId])
  
  if (!config) return <div>Loading...</div>
  
  // Render a minimal version of ChatWidget that uses public endpoints
  // and passes bot_id with every request
  return <EmbedChatWidget config={config} botId={botId} />
}
```

**EmbedChatWidget** is a stripped-down version of ChatWidget that:
- Has no info panel (just the chat)
- Uses `/api/chat/public` instead of `/api/chat`
- Passes `bot_id` in every request
- Full height, no padding (fills the iframe)
- Has "Powered by SupportBot" footer with link to your site
- Supports all features: voice, memory, multilingual, sales

### Serving widget.js from FastAPI

```python
from fastapi.responses import FileResponse

@app.get("/widget.js")
async def serve_widget():
    return FileResponse(
        "static/widget.js",
        media_type="application/javascript",
        headers={
            "Cache-Control": "public, max-age=3600",
            "Access-Control-Allow-Origin": "*",  # Allow any website to load it
        }
    )
```

### CORS Configuration

The embed needs to work from ANY domain. Update CORS:

```python
from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Any website can embed
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["*"],
    allow_credentials=True,
)
```

For the admin panel endpoints, add stricter CORS (only your domain).

---

## PHASE 8: API KEY SYSTEM

Some clients may want to use the API directly (headless chatbot integration). Each tenant gets an API key.

### API Key Authentication (Alternative to Cookie Auth)

```python
async def get_tenant_from_api_key(
    request: Request,
    db: Session = Depends(get_db)
) -> Tenant:
    """Authenticate via API key in header."""
    api_key = request.headers.get("X-API-Key") or request.headers.get("Authorization", "").replace("Bearer ", "")
    
    if not api_key:
        raise HTTPException(status_code=401, detail="API key required")
    
    tenant = db.query(Tenant).filter(
        Tenant.api_key == api_key,
        Tenant.is_active == True
    ).first()
    
    if not tenant:
        raise HTTPException(status_code=401, detail="Invalid API key")
    
    return tenant
```

### API Usage Example (for clients)

Clients can call the chat API programmatically:

```bash
curl -X POST https://your-app.onrender.com/api/chat/public \
  -H "Content-Type: application/json" \
  -H "X-API-Key: sk_live_xxxxxxxxxxxx" \
  -d '{"bot_id": "bot_a1b2c3d4", "message": "What are your prices?"}'
```

---

## PHASE 9: USAGE TRACKING & BILLING HELPERS

### Usage Model

```python
class UsageLog(Base):
    __tablename__ = "usage_logs"
    
    id = Column(Integer, primary_key=True)
    bot_id = Column(String, ForeignKey("tenants.bot_id"), nullable=False, index=True)
    date = Column(Date, nullable=False)
    
    total_messages = Column(Integer, default=0)
    ai_messages = Column(Integer, default=0)          # Cost you money
    auto_reply_messages = Column(Integer, default=0)   # Free
    escalations = Column(Integer, default=0)
    leads_captured = Column(Integer, default=0)
    voice_messages = Column(Integer, default=0)
    
    # Cost tracking
    estimated_api_cost = Column(Float, default=0.0)    # ai_messages × $0.003
```

### Daily Usage Logger

Run nightly via APScheduler — aggregates daily stats per tenant:

```python
def log_daily_usage():
    db = SessionLocal()
    today = date.today()
    
    for tenant in db.query(Tenant).filter(Tenant.is_active == True).all():
        # Count today's messages for this tenant
        total = db.query(Message).filter(
            Message.bot_id == tenant.bot_id,
            func.date(Message.created_at) == today
        ).count()
        
        auto = db.query(Message).filter(
            Message.bot_id == tenant.bot_id,
            Message.was_auto_reply == True,
            func.date(Message.created_at) == today
        ).count()
        
        ai = total - auto
        
        log = UsageLog(
            bot_id=tenant.bot_id,
            date=today,
            total_messages=total,
            ai_messages=ai,
            auto_reply_messages=auto,
            estimated_api_cost=ai * 0.003,
        )
        db.add(log)
    
    db.commit()
    db.close()

scheduler.add_job(log_daily_usage, 'cron', hour=23, minute=55)
```

### Billing Summary Endpoint (Super Admin)

```
GET /api/admin/billing?month=2026-03
```

Returns:
```json
{
    "month": "2026-03",
    "tenants": [
        {
            "bot_id": "bot_a1b2c3d4",
            "company_name": "ShopAfrica",
            "plan": "pro",
            "plan_price": 150,
            "total_messages": 3420,
            "ai_messages": 1200,
            "auto_reply_messages": 2220,
            "estimated_api_cost": 3.60,
            "profit": 146.40
        }
    ],
    "totals": {
        "revenue": 1500,
        "api_costs": 25.50,
        "profit": 1474.50
    }
}
```

---

## PHASE 10: DEPLOYMENT UPDATES

### Updated .env.example

```
# Core
ANTHROPIC_API_KEY=

# Auth
JWT_SECRET_KEY=your_random_secret_here
SUPER_ADMIN_USERNAME=admin
SUPER_ADMIN_PASSWORD=changeme123

# Telegram (escalation + reports)
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=

# EmailJS (escalation + reports)
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

### Updated render.yaml

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
      - key: JWT_SECRET_KEY
        sync: false
      - key: SUPER_ADMIN_USERNAME
        sync: false
      - key: SUPER_ADMIN_PASSWORD
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

### Updated requirements.txt

Add:
```
python-jose[cryptography]>=3.3.0
passlib[bcrypt]>=1.7.0
alembic>=1.13.0
```

---

## FRONTEND ROUTING

Update React router to handle all routes:

```jsx
<Routes>
  {/* Public */}
  <Route path="/login" element={<ClientLogin />} />
  <Route path="/embed/:botId" element={<EmbedChat />} />
  
  {/* Client Admin (requires client auth) */}
  <Route path="/admin/*" element={<ClientAdminLayout />}>
    <Route index element={<ConfigureTab />} />
    <Route path="chat" element={<ChatDemoTab />} />
    <Route path="analytics" element={<AnalyticsTab />} />
    <Route path="integrations" element={<IntegrationsTab />} />
    <Route path="sales" element={<SalesTab />} />
    <Route path="settings" element={<AccountSettings />} />
  </Route>
  
  {/* Super Admin (requires super auth) */}
  <Route path="/super-admin/login" element={<SuperAdminLogin />} />
  <Route path="/super-admin/*" element={<SuperAdminLayout />}>
    <Route index element={<SuperDashboard />} />
    <Route path="tenants" element={<TenantsManager />} />
    <Route path="tenants/:botId" element={<TenantDetail />} />
    <Route path="billing" element={<BillingDashboard />} />
    <Route path="system" element={<SystemHealth />} />
  </Route>
  
  {/* Default redirect */}
  <Route path="/" element={<Navigate to="/login" />} />
</Routes>
```

---

## CLIENT ONBOARDING FLOW (How You Add a New Client)

1. Log into Super Admin panel at `/super-admin`
2. Click "Create Tenant"
3. Fill in: company name, owner name, email, password, plan
4. System generates `bot_id` and `api_key`
5. Copy the embed code
6. Send client an email with:
   - Their login URL: `https://your-app.onrender.com/login`
   - Their email + temporary password
   - Their embed code: `<script src="..." data-bot-id="bot_xxx"></script>`
   - Quick start guide: "Paste this before </body> on your website"
7. Client logs in, configures their FAQs, brand colors, etc.
8. Client pastes embed code on their website
9. Done — chatbot is live on their site

---

## SECURITY CHECKLIST

- [ ] All admin endpoints require JWT auth
- [ ] All queries filter by bot_id — no cross-tenant data access
- [ ] Passwords hashed with bcrypt (never stored plain)
- [ ] JWT tokens expire after 24 hours
- [ ] API keys are unique per tenant
- [ ] Super admin panel has separate auth from client panel
- [ ] Public endpoints (chat, config, escalate) validate bot_id exists
- [ ] Rate limiting on public chat endpoint (prevent abuse)
- [ ] CORS set to allow embed from any domain
- [ ] widget.js served with proper caching headers
- [ ] .env file never committed to git
- [ ] Sensitive data (API keys, passwords) never returned in API responses

---

## PRICING CHEAT SHEET (For Selling to Clients)

| Plan | Messages/mo | Features | Your Price | Your API Cost | Profit |
|------|------------|----------|------------|---------------|--------|
| Basic | 1,000 | FAQ bot + analytics | $100/mo | ~$3 | $97 |
| Pro | 5,000 | + memory + multilingual + voice | $200/mo | ~$15 | $185 |
| Enterprise | 20,000 | + sales agent + webhooks + priority | $400/mo | ~$60 | $340 |

**Setup fees (one-time):**
- Basic: $300
- Pro: $800
- Enterprise: $2,000

**10 Pro clients = $2,000/mo recurring with ~$150 in costs = $1,850 profit/mo**
