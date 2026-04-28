# SupportBot Webhooks — Integration Guide

For developers wiring up a `custom_https` webhook receiver to SupportBot Studio.

---

## 1. Overview

SupportBot fires webhooks at your server when something happens in a chat — for example, a customer asks to speak to a human. Your server gets a signed HTTPS POST containing the event details. You decide what to do with it: ping Slack, open a ticket, page someone, whatever.

Right now there's one event:

- **`escalation`** — fired when a customer requests human support (clicks "talk to a human", types something the bot escalates, etc.)

More event types are planned. The format below is locked-in — your receiver code won't break when new events are added; you'll just start getting more `event` values.

---

## 2. Setup

### Register a webhook

1. Open the admin panel
2. Go to **Webhook Settings**
3. Click **Add webhook**
4. Choose platform: **Custom HTTPS**
5. Paste your endpoint URL (must be `https://`)
6. Generate a **secret** — any random string of 32+ characters. Treat it like a password
7. Pick which events you want (currently just `escalation`)
8. Save

### What the secret is for

The secret is shared between SupportBot and your server. Only the two of you know it. SupportBot uses it to "sign" each webhook — your server uses the same secret to verify the signature is valid.

Without it, an attacker who knew your endpoint URL could fire fake escalation events at it. With it, only requests carrying the right signature are accepted.

**Generate it once. Store it somewhere your server can read** (env var, secrets manager — not in code). If it leaks, regenerate it in the admin panel.

---

## 3. Request format

Every webhook is sent as:

- **Method:** `POST`
- **URL:** whatever you registered
- **Headers:**
  - `Content-Type: application/json`
  - `X-SupportBot-Signature: sha256=<hex digest>`
- **Body:** JSON

### Example body — `escalation` event

```json
{
  "event": "escalation",
  "text": "SupportBot Escalation\nCustomer: alice@example.com\nMessages: 4\n\n[transcript here]",
  "timestamp": "2026-04-28T14:23:51Z"
}
```

| Field | Type | Notes |
|---|---|---|
| `event` | string | Event type — currently always `"escalation"` for managed events. May be `null` for manual test pings. |
| `text` | string | Pre-formatted human-readable summary. Includes customer email, message count, transcript. |
| `timestamp` | string | RFC 3339 UTC. Use this for replay protection (reject anything more than ~5 minutes old). |

The body is sent with **compact JSON** (no spaces between keys/values: `{"a":1}`, not `{"a": 1}`). This matters for signature verification — see the warning in section 4.

---

## 4. Signature verification

### What HMAC-SHA256 is, in plain English

You and SupportBot share a secret. SupportBot runs a math function that takes the raw bytes of the request body plus the secret and produces a fixed-length fingerprint. That fingerprint goes in the `X-SupportBot-Signature` header.

When the request arrives, your server runs the **exact same math** on the body it received. If the fingerprint matches the header, the request is genuine. If not, drop it on the floor — someone tampered with it, or it didn't come from SupportBot.

The fingerprint can't be forged without the secret, so as long as your secret stays secret, you can trust signed requests.

### ⚠️ The one rule that catches everyone

**Verify over the raw body bytes you received off the wire — not over a re-serialized version of the parsed JSON.**

Why this matters: most web frameworks parse the body into a dict/object for you. If you then `JSON.stringify(body)` to verify, you'll get different bytes than what SupportBot signed — different key order, different whitespace, different escape sequences. The signature won't match. You'll think your secret is wrong. It isn't. You're hashing different bytes.

Every example below shows how to grab the raw bytes *before* parsing.

### Python (Flask)

```python
import hmac
import hashlib
import json
import os
from flask import Flask, request, abort

app = Flask(__name__)
SECRET = os.environ["SUPPORTBOT_WEBHOOK_SECRET"].encode("utf-8")


@app.route("/webhook", methods=["POST"])
def webhook():
    # Grab raw bytes BEFORE Flask parses them.
    raw_body = request.get_data()  # bytes, not str

    received = request.headers.get("X-SupportBot-Signature", "")
    # hmac.new takes (key, msg, digest) — secret first, body second.
    expected = "sha256=" + hmac.new(SECRET, raw_body, hashlib.sha256).hexdigest()

    if not hmac.compare_digest(expected, received):
        abort(401)

    # Safe to parse and process now.
    payload = json.loads(raw_body)
    if payload["event"] == "escalation":
        handle_escalation(payload)

    return "", 200
```

`hmac.compare_digest` is constant-time — protects against timing attacks. Don't use `==`.

### Python (FastAPI)

```python
import hmac
import hashlib
import os
from fastapi import FastAPI, Request, HTTPException

app = FastAPI()
SECRET = os.environ["SUPPORTBOT_WEBHOOK_SECRET"].encode("utf-8")


@app.post("/webhook")
async def webhook(request: Request):
    raw_body = await request.body()  # bytes

    received = request.headers.get("X-SupportBot-Signature", "")
    expected = "sha256=" + hmac.new(SECRET, raw_body, hashlib.sha256).hexdigest()

    if not hmac.compare_digest(expected, received):
        raise HTTPException(status_code=401, detail="bad signature")

    import json
    payload = json.loads(raw_body)
    # ... handle event
    return {"ok": True}
```

### Node.js (Express)

```javascript
const express = require("express");
const crypto = require("crypto");

const app = express();
const SECRET = process.env.SUPPORTBOT_WEBHOOK_SECRET;

// IMPORTANT: tell express to keep the raw body around. The default
// JSON parser throws away the bytes once it has the parsed object.
app.use(express.json({
  verify: (req, _res, buf) => { req.rawBody = buf; }
}));

app.post("/webhook", (req, res) => {
  const received = req.header("X-SupportBot-Signature") || "";
  const expected = "sha256=" + crypto
    .createHmac("sha256", SECRET)
    .update(req.rawBody)        // raw bytes, NOT JSON.stringify(req.body)
    .digest("hex");

  // timingSafeEqual requires equal-length buffers.
  const a = Buffer.from(received);
  const b = Buffer.from(expected);
  if (a.length !== b.length || !crypto.timingSafeEqual(a, b)) {
    return res.status(401).end();
  }

  // Now safe to use req.body (already parsed)
  if (req.body.event === "escalation") {
    handleEscalation(req.body);
  }

  res.status(200).end();
});
```

### PHP

```php
<?php
$secret = getenv('SUPPORTBOT_WEBHOOK_SECRET');

// Grab raw input — file_get_contents('php://input') gives you the
// untouched bytes. $_POST won't work for JSON bodies anyway.
$rawBody = file_get_contents('php://input');

$received = $_SERVER['HTTP_X_SUPPORTBOT_SIGNATURE'] ?? '';
$expected = 'sha256=' . hash_hmac('sha256', $rawBody, $secret);

if (!hash_equals($expected, $received)) {
    http_response_code(401);
    exit;
}

$payload = json_decode($rawBody, true);
if ($payload['event'] === 'escalation') {
    handleEscalation($payload);
}

http_response_code(200);
```

`hash_equals` is the constant-time comparison.

---

## 5. Event types

| Event | Triggered when | Body fields |
|---|---|---|
| `escalation` | Customer requests human support, or SupportBot decides the conversation needs a human | `event`, `text`, `timestamp` |

More events are planned (e.g. `lead.captured`, `conversation.rated`). When they ship:

- The body shape stays the same — `event`, `text`, `timestamp` are always there
- New events may add fields (e.g. `lead_email`)
- Your `events` subscription list controls which ones you receive — webhooks not subscribed to a new event type are simply not called

So your receiver code only needs to handle the events you opt into. Unknown event types → ignore safely.

---

## 6. Best practices

### Always verify the signature before processing

Don't read or act on the body until you've confirmed the signature matches. An attacker who finds your URL can fire arbitrary JSON at it; the signature is what proves it came from SupportBot.

### Return 200 fast, process async

SupportBot has a 10-second timeout on the request. If your handler takes longer (sending emails, calling APIs, writing to slow databases), return 200 immediately and do the work in a background job.

```python
# Anti-pattern — blocks the webhook
@app.post("/webhook")
async def webhook(request):
    verify(...)
    payload = await request.json()
    await send_email(...)        # 8 seconds
    await create_ticket(...)     # 4 seconds → timeout
    return 200

# Better
@app.post("/webhook")
async def webhook(request, background_tasks: BackgroundTasks):
    verify(...)
    payload = await request.json()
    background_tasks.add_task(process_escalation, payload)
    return 200
```

### Be idempotent

If your endpoint times out or returns 5xx, SupportBot may retry the same event. Don't create duplicate tickets or send duplicate emails on retry.

Cheapest pattern: use `(event, timestamp, customer_email)` as a dedup key in a short-lived cache (Redis with 10-minute TTL, or just a DB table with a unique constraint). If you've already seen it, ack and ignore.

### Reject old timestamps (replay protection)

The signature proves the request came from SupportBot — it doesn't prove it came from SupportBot *just now*. If someone captures a valid request and replays it later, the signature still matches.

Reject anything with a `timestamp` more than 5 minutes old:

```python
from datetime import datetime, timezone, timedelta

ts = datetime.fromisoformat(payload["timestamp"].replace("Z", "+00:00"))
if datetime.now(timezone.utc) - ts > timedelta(minutes=5):
    abort(400)  # too old
```

### Keep the secret in environment variables, never in code

If your repo leaks, your secret leaks. Use `process.env`, `os.environ`, or your platform's secrets manager.

---

## 7. Troubleshooting

### "Signature mismatch" — every request fails verification

The single most common cause: you're hashing a re-serialized version of the body, not the raw bytes.

**Symptoms:** verification fails 100% of the time, even with a brand-new webhook and a fresh secret.

**Diagnosis:** add temporary logging:

```python
print("RECEIVED:", request.headers.get("X-SupportBot-Signature"))
print("RAW BYTES:", raw_body[:200])
print("EXPECTED:", "sha256=" + hmac.new(SECRET, raw_body, hashlib.sha256).hexdigest())
```

If `RAW BYTES` shows JSON with spaces (`{"event": "escalation"`) but you computed your `EXPECTED` from a re-serialized object that has different spacing — that's the bug.

**Fix:** In every framework, there's a way to access the untouched body bytes. Use that, not the parsed object. See section 4 for framework-specific examples.

### "Signature mismatch" — only sometimes

Less common. Causes:

- Secret rotated in admin panel but the new value not deployed to your server yet
- A reverse proxy (nginx, Cloudflare) re-encoding the body. Disable any body transforms on the webhook route
- You're computing HMAC over a string that was decoded from UTF-8 then re-encoded — round-tripping through Unicode can mangle non-ASCII characters

### Missing `X-SupportBot-Signature` header

Either:

- The webhook in the admin panel doesn't have a secret set. Edit it, add a secret, save. Re-register if needed.
- The webhook's platform isn't `custom_https`. Slack/Discord/Twilio/WhatsApp webhooks aren't signed — those platforms have their own auth.

### `400 Bad Request` when saving the webhook

Most likely error messages:

| Error | Cause | Fix |
|---|---|---|
| `secret is only supported for custom_https webhooks` | You set a secret on a Slack/Discord/Twilio/WhatsApp webhook — they ignore it | Either change platform to `custom_https`, or remove the secret |
| `custom_https webhooks require a non-empty 'secret' for HMAC signing` | You picked `custom_https` but didn't fill in the secret field | Fill in the secret. Generate a random 32+ character string |
| `Webhook URL must use https` | URL starts with `http://` | Use `https://` — webhooks over plaintext aren't allowed |

### `401` from your server but request looks valid in logs

You have a working signature check that's rejecting everything. Walk through this checklist:

1. Is the secret on your server **exactly** the same as the one in the admin panel? No trailing newline, no leading whitespace, same case.
2. Are you reading the raw body, not the parsed object? See section 4.
3. Are you stripping or adding the `sha256=` prefix consistently on both sides?
4. Are you using the constant-time comparison (`hmac.compare_digest`, `crypto.timingSafeEqual`, `hash_equals`)? A regular `==` will sometimes work and sometimes not depending on string interning quirks in some languages — but the real reason to use it is timing-attack resistance.

### Webhook never fires

- Check the webhook is `enabled` (toggle in admin panel)
- Check the `events` list includes the event you're expecting (`escalation`)
- Check the **Test webhook** button in the admin panel — that bypasses the events filter and sends a manual ping. If the test fires but real escalations don't, the events list is the problem.
