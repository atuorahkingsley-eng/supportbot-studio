# Webhook Setup Guide

Connect your SupportBot chat to the rest of your business — Slack, Gmail, your CRM, Google Sheets — so the right people hear about the right conversations, automatically.

---

## 1. What Is a Webhook

A webhook is like a notification bell — every time something happens in your SupportBot chat, it rings a bell in your other tools automatically. Instead of you checking your dashboard, your dashboard checks itself and tells everyone else what's going on.

---

## 2. What You Need Before Starting

Before you begin, have these three things ready:

- **Your SupportBot Webhook URL** — copied from your SupportBot admin dashboard, under **Webhooks**.
- **Your Webhook Secret** — the long string shown to you **only once** at the moment your webhook was created. If you didn't save it, click **Regenerate** in the dashboard to get a fresh one (this will break any existing connections — see Section 7).
- **An account on one of**: Activepieces, n8n, Zapier, or Make.

⚠️ Treat your webhook secret like a password. Anyone who has it can send fake events to your automations.

---

## 3. Setup Guide

Pick the platform you're using. Each section is self-contained — you only need to follow one.

### Activepieces

1. Log in to Activepieces and click **+ New Flow**. Name it `SupportBot - [Your Business Name]`.
2. Click **Select Trigger** → search for **Webhook** → select **Catch Webhook**.
3. Activepieces shows you a webhook URL. Click the **Copy** icon next to it.
4. Open your **SupportBot admin dashboard** → **Webhooks** → paste the URL into the **Webhook URL** field, choose **Custom (n8n / Make / Activepieces)** as the Platform, and click **+ Add Webhook**.
5. Back in Activepieces, click **+ Add Step** → choose **Code**. Paste this exact code into the editor:

```javascript
const crypto = require('crypto');
const secret = 'PASTE_YOUR_SECRET_HERE';
const signature = input.headers['x-supportbot-signature'];
const body = JSON.stringify(input.body, null, 0);
const expected = 'sha256=' + crypto
  .createHmac('sha256', secret)
  .update(body)
  .digest('hex');
if (signature !== expected) throw new Error('Invalid signature');
return { event: input.body.event_type, data: input.body.data };
```

⚠️ Replace `PASTE_YOUR_SECRET_HERE` with the actual secret from your SupportBot dashboard. Keep the quotes around it.

6. Click **+ Add Step** again → choose **Router**. Add one branch per event type you care about (e.g. `lead_captured`, `escalation_triggered`, `conversation_ended`).
7. Inside each branch, click **+ Add Step** and connect to your tool of choice — **Slack** to post a message, **Gmail** to send an email, **Google Sheets** to add a row, etc.
8. Click **Publish** at the top right. **Save alone is not enough** — an unpublished flow does not run.

✅ A working integration looks like this: when you click **Test** in your SupportBot dashboard, the flow shows a green "Run succeeded" entry in the Activepieces **Runs** tab within a few seconds, and a message lands in your downstream tool (e.g. Slack).

### n8n (self-hosted or cloud)

1. Log in to n8n and click **+ Add workflow**. Name it `SupportBot - [Your Business Name]`.
2. Click **+ Add first step** → search for **Webhook** → select the **Webhook** node. Set **HTTP Method** to **POST**. Leave **Path** as the default or pick something memorable.
3. Click **Listen for Test Event**, then copy the **Test URL** shown by n8n.
4. Open your **SupportBot admin dashboard** → **Webhooks** → paste the URL into the **Webhook URL** field, set Platform to **Custom (n8n / Make / Activepieces)**, and click **+ Add Webhook**.
5. Back in n8n, click the **+** after the Webhook node → choose **Code**. Paste the same JavaScript block from the Activepieces section above, replacing `PASTE_YOUR_SECRET_HERE` with your real secret.

⚠️ The Code node in n8n uses the same Node.js `crypto` module — the snippet works as-is. Don't change the variable names.

6. Add a **Switch** node next. Set its expression to `{{ $json.body.event_type }}` and create one rule per event you want to route (e.g. equals `lead_captured`).
7. Connect each Switch output to your downstream nodes — **Slack**, **Gmail**, **Google Sheets**, **HTTP Request** to your CRM, etc.
8. Toggle the workflow **Active** using the switch at the top right. **Test URLs only fire while you're actively listening; the Production URL fires whenever the workflow is Active.** Make sure your SupportBot dashboard holds the **Production URL**, not the Test URL.

✅ A working integration looks like this: in the **Executions** tab you see a green checkmark for each event, and your downstream tool receives the data within a second or two of clicking **Test** in SupportBot.

### Zapier

⚠️ Zapier does **not** support signature verification on free plans — there is no Code step on the Free or Starter tier. Use Zapier only if you trust the source environment or are on a paid plan that includes **Code by Zapier**.

1. Log in to Zapier and click **+ Create Zap**.
2. For the trigger, choose **Webhooks by Zapier** → event type **Catch Hook** → click **Continue**.
3. Zapier shows you a **Custom Webhook URL**. Click **Copy**.
4. Open your **SupportBot admin dashboard** → **Webhooks** → paste the URL into the **Webhook URL** field, set Platform to **Custom (n8n / Make / Activepieces)**, and click **+ Add Webhook**.
5. Back in Zapier, click **Test trigger** to confirm the connection. You'll see a sample payload appear.
6. Click **+** to add a step → choose **Filter by Zapier**. Set the rule to **`event_type` (Text) Exactly matches** the event you care about (e.g. `lead_captured`).
7. Add an action step and connect it to your destination app — **Slack**, **Gmail**, **Notion**, **HubSpot**, etc.
8. Click **Publish** to turn the Zap on.

✅ A working integration looks like this: clicking **Test** in your SupportBot dashboard creates a new run in the Zapier **Zap History** within a few seconds, and the action app receives the payload.

### Make (formerly Integromat)

1. Log in to Make and click **+ Create a new scenario**.
2. Click the large **+** in the canvas → search for **Webhooks** → choose **Custom webhook**.
3. Click **Add** to create a new webhook hook → give it a name → click **Save**. Make shows you a webhook URL.
4. Open your **SupportBot admin dashboard** → **Webhooks** → paste the URL into the **Webhook URL** field, set Platform to **Custom (n8n / Make / Activepieces)**, and click **+ Add Webhook**.
5. Back in Make, click the next **+** → choose **Flow Control** → **Router**. Add one route per event type you want to handle.
6. On each route, click the route's filter icon and set the condition to **`event_type` Equal to** your target value (e.g. `escalation_triggered`).
7. To verify the signature, add an **HTTP** → **Make a request (advanced)** module before the Router that re-computes the HMAC and compares against the `X-SupportBot-Signature` header. If you're not comfortable doing this, restrict the webhook URL to your IP allowlist in your network rules instead.

⚠️ Skipping signature verification means anyone who guesses your webhook URL can fire fake events at your automation. Either verify the signature or restrict the URL.

8. Connect each Router branch to your destination modules — **Slack**, **Email**, **Google Sheets**, your CRM, etc. Click the toggle at the bottom-left to set the scenario from **OFF** to **ON**.

✅ A working integration looks like this: clicking **Test** in your SupportBot dashboard produces a new entry in the scenario's **History** tab with a green "Success" status, and downstream modules light up in sequence.

---

## 4. Event Types Reference Table

| Event | When It Fires | What to Do With It |
|---|---|---|
| `lead_captured` | A visitor expresses buying interest — leaves an email, asks about pricing, requests a demo. | Log to CRM (HubSpot, Pipedrive), alert sales team in Slack/Telegram, add row to Google Sheets. |
| `escalation_triggered` | The bot decides it needs a human — visitor frustrated, complex question, or asked for a person. | Alert on-call agent via Slack/Telegram/SMS, create a ticket in your helpdesk. |
| `conversation_ended` | A chat session closes — visitor closes the widget, conversation is rated, or session times out. | Archive transcript to Notion/Sheets, trigger a satisfaction survey, update CRM activity log. |

---

## 5. Sample Payload

Every event SupportBot sends has the same outer shape. The `data` block changes per event type. Here are all three:

```json
{
  "event_type": "lead_captured",          // which event fired — use this to route
  "bot_id": "abc123xyz",                  // your SupportBot tenant ID
  "timestamp": "2026-05-08T14:32:11Z",    // ISO-8601 UTC, when the event happened
  "data": {
    "lead_id": 482,                       // SupportBot's internal lead ID
    "email": "jane@example.com",          // visitor's email (always present for this event)
    "name": "Jane Doe",                   // visitor's name, may be null
    "interest": "pricing for 50 seats",   // free-text snippet of what they asked, may be null
    "source": "chat_capture",             // where the lead was captured: chat_capture | demo_form | exit_intent
    "buying_signal_score": 4,             // 1 = curiosity, 5 = ready-to-buy
    "visitor_id": "v_a1b2c3d4",           // stable visitor cookie ID — same across sessions
    "conversation_id": 1284               // ID of the chat where this lead came from
  }
}
```

```json
{
  "event_type": "escalation_triggered",
  "bot_id": "abc123xyz",
  "timestamp": "2026-05-08T14:35:02Z",
  "data": {
    "conversation_id": 1284,              // the live conversation that needs a human
    "visitor_id": "v_a1b2c3d4",           // visitor cookie ID
    "reason": "complex_billing_question", // why the bot escalated
    "last_message": "I was charged twice this month and the refund link doesn't work.",
    "transcript_url": "https://app.supportbot.studio/conversations/1284"  // direct link for your agent
  }
}
```

```json
{
  "event_type": "conversation_ended",
  "bot_id": "abc123xyz",
  "timestamp": "2026-05-08T14:41:55Z",
  "data": {
    "conversation_id": 1284,              // the conversation that just closed
    "visitor_id": "v_a1b2c3d4",           // visitor cookie ID
    "rating": 5,                          // visitor's star rating (1-5), or null if not rated
    "message_count": 12,                  // total messages exchanged
    "duration_seconds": 624,              // how long the chat lasted
    "ended_at": "2026-05-08T14:41:55Z"    // ISO-8601 UTC, when the chat closed
  }
}
```

⚠️ Field names are lowercase with underscores (`event_type`, not `eventType`). Match them exactly in your filter and routing rules — JavaScript and most automation tools are case-sensitive.

---

## 6. Testing Your Webhook

You don't need to wait for a real customer to test. SupportBot has a built-in test button.

1. Open your **SupportBot admin dashboard** → **Webhooks**.
2. Find your webhook in the list and click **Test**.
3. Watch your automation tool — within a few seconds you should see the test event arrive.

What success looks like in each tool:

- **Activepieces**: A new entry appears in the **Runs** tab with a green checkmark. Each step shows a green tick.
- **n8n**: A new execution appears in the **Executions** tab with green ticks across every node.
- **Zapier**: A new task appears in **Zap History** with status **Success**.
- **Make**: A new bundle appears in the scenario's **History** tab with all modules lit up green.

If the **Test** button shows a green "Connected" badge in the SupportBot dashboard but nothing arrives in your tool, the URL is reachable but your flow isn't activated yet — see Section 7.

---

## 7. Troubleshooting

| Problem | Likely Cause | Fix |
|---|---|---|
| Signature mismatch error | The secret in your Code/HTTP step doesn't match the one stored in SupportBot — usually a typo, an extra space, or you pasted the masked version (the one with bullets) instead of the real secret. | Click **Regenerate** in the SupportBot dashboard → copy the new secret from the one-time popup → paste it into your Code step → save and re-test. |
| No events arriving | Your flow/scenario is saved but not activated. Saving alone does not turn it on. | **Activepieces**: click **Publish**. **n8n**: toggle **Active** at top right. **Zapier**: click **Publish**. **Make**: flip the scenario switch to **ON**. |
| Events arriving but routing to the wrong branch | Your filter/Switch/Router is comparing the wrong field, or the value is misspelled. | Check that you're routing on `event_type` (not `event` or `type`) and that the value matches exactly — lowercase, underscores, no spaces. See Section 4 for the exact strings. |
| Flow not triggering at all (Activepieces) | You copied the **Test URL** instead of the **Live URL** — the Test URL only listens while the flow editor is open. | In Activepieces, after **Publish**, copy the live URL shown in the Webhook trigger details. Update SupportBot → **Webhooks** → edit the entry → paste the live URL → save. |
| Secret lost / need a new one | Webhook secrets are shown only once at creation. There is no way to recover the original. | In the SupportBot dashboard → **Webhooks** → click **Regenerate** on that webhook → confirm. Copy the new secret from the popup, update every place it's used (your Code step), and re-test. The old secret stops working immediately. |

---

## 8. Security Rules

- **Never share your webhook secret publicly** — not in screenshots, not in support tickets, not in shared documents.
- **If the secret is exposed, regenerate it immediately** from the SupportBot dashboard. The old one stops working the moment you click Regenerate.
- **Always verify the signature** in your automation tool. The `X-SupportBot-Signature` header is what proves the event really came from SupportBot and not from someone who guessed your URL.

---

## 9. Need Help?

Contact your SupportBot Studio administrator.
