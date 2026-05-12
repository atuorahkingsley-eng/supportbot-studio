# Client Onboarding Email Templates

Three templates Kay sends across the SupportBot Studio onboarding lifecycle. Copy the body of each, fill in the `{{PLACEHOLDERS}}` from the reference table at the bottom, and send. Each email is built to be read in under 60 seconds.

---

## EMAIL 1 — Welcome + Login Details

**Trigger:** Send immediately after the tenant is created in the super admin dashboard.

**Subject:** Your SupportBot is live 🚀

**Body:**

Hi {{CLIENT_FIRST_NAME}},

Welcome aboard — your SupportBot is up and running.

I've set up **{{BOT_NAME}}** for **{{CLIENT_WEBSITE}}**, and your admin dashboard is ready whenever you are.

**Login details**

- Dashboard: {{DASHBOARD_URL}}
- Email: {{EMAIL}}
- Temporary password: `{{TEMP_PASSWORD}}`

**3-step quickstart**

1. **Log in and change your password** — top-right menu → Account → Change Password.
2. **Add your FAQs** in the Knowledge Base tab — paste in your common customer questions and answers, and your bot will use them right away.
3. **Copy the embed code** and paste it just before the closing `</body>` tag on your website:

```html
<script src="{{BOT_URL}}/widget.js" data-bot-id="{{BOT_ID}}"></script>
```

That's it — once the script is live, the chat widget appears on every page.

Reply to this email if you need help with anything.

— {{YOUR_NAME}}, SupportBot Studio

---

## EMAIL 2 — Webhook Secret Delivery

**Trigger:** Send immediately after a webhook is created in the dashboard and a fresh secret is generated.

**Subject:** Your SupportBot webhook secret (save this now)

**Body:**

Hi {{CLIENT_FIRST_NAME}},

You just created a webhook in your SupportBot dashboard — this email contains the signing secret you'll need to verify the events on the receiving end.

> ⚠️ This secret will not be shown again. Save it somewhere safe like a password manager before closing this email.

**Your webhook secret:** `{{WEBHOOK_SECRET}}`

**Sending events to:** {{CLIENT_WEBHOOK_URL}}

**Subscribed events:** {{EVENT_LIST}}

**What to do next**

1. Copy the secret above.
2. Open your automation tool (Activepieces / n8n / Zapier / Make).
3. Paste it into the signature verification step (see full guide: {{GUIDE_URL}}).

If you lose this secret, log into your dashboard and regenerate it under **Webhooks → Regenerate Secret**.

— {{YOUR_NAME}}, SupportBot Studio

---

## EMAIL 3 — 7-Day Check-In

**Trigger:** Send 7 days after onboarding.

**Subject:** How is your SupportBot performing?

**Body:**

Hi {{CLIENT_FIRST_NAME}},

It's been a week since {{BOT_NAME}} went live — checking in to see how things are going.

A quick review of your dashboard usually surfaces the easy wins:

- **Conversations tab** — see what customers are actually asking.
- **Analytics tab** — check your auto-reply rate (higher = more support hours saved).
- **Knowledge Base tab** — add FAQs for any questions the bot couldn't answer.

If you'd like to connect your SupportBot to Slack, email, or your CRM automatically, reply and I'll set that up for you.

Happy to jump on a 15-minute call if you have questions or want a walk-through — just reply with a couple of times that work.

— {{YOUR_NAME}}, SupportBot Studio

---

## Placeholder Reference Table

Every `{{PLACEHOLDER}}` used in the three emails above, what it means, and where to find the value.

| Placeholder | Meaning | Where to find it |
|---|---|---|
| `{{CLIENT_FIRST_NAME}}` | The recipient's first name. | Super admin dashboard → Tenants → row contact name (first word). |
| `{{BOT_NAME}}` | The display name of the bot you provisioned. | Super admin → Tenants → `bot_name` column. |
| `{{CLIENT_WEBSITE}}` | The website the bot is being embedded on. | Super admin → Tenants → `website_url` column (or the URL the client gave you on signup). |
| `{{DASHBOARD_URL}}` | Client's admin login URL. | Render deployment URL + `/admin` (e.g. `https://supportbot-studio.onrender.com/admin`). |
| `{{EMAIL}}` | The login email for the client's tenant account. | Super admin → Tenants → `email` column. The same one you used when creating the tenant. |
| `{{TEMP_PASSWORD}}` | One-time password generated at tenant creation. | Shown in the Tenant Created confirmation modal in the super admin dashboard. Note it before closing the modal — it's not stored anywhere afterwards. |
| `{{BOT_URL}}` | Public origin where the widget script is hosted. | Render deployment URL (e.g. `https://supportbot-studio.onrender.com`). |
| `{{BOT_ID}}` | The unique tenant ID for the embed `data-bot-id` attribute. | Super admin → Tenants → `bot_id` column. Click the row to copy. |
| `{{WEBHOOK_SECRET}}` | One-time HMAC signing secret. | Shown ONCE in the webhook-created modal in the client's admin dashboard. If lost, click **Regenerate Secret** in **Webhooks**. |
| `{{CLIENT_WEBHOOK_URL}}` | The URL the client wants SupportBot to POST events to (their Activepieces / n8n / Zapier / Make endpoint). | Client's admin dashboard → Webhooks → `Webhook URL` field for the webhook in question. |
| `{{EVENT_LIST}}` | Comma-separated list of events the webhook is subscribed to (e.g. `lead_captured, escalation_triggered`). | Client's admin dashboard → Webhooks → "Subscribe to events" checkboxes for the webhook. If none are checked, write `all events`. |
| `{{GUIDE_URL}}` | Public link to the webhook setup guide. | The `docs/webhook-setup-guide.md` file, hosted wherever you publish docs (e.g. `https://supportbot-studio.onrender.com/docs/webhook-setup-guide` or your GitHub Pages URL). |
| `{{YOUR_NAME}}` | The sender's name (Kay's name or whoever's onboarding the client). | Your own name — replace once when you save your personal copy of the template. |

---

## Sending Checklist

Run through these before hitting send. Each email has its own list.

### Email 1 — Welcome + Login Details

- [ ] Tenant created in super admin
- [ ] Embed code tested locally (widget loads, no console errors)
- [ ] Temp password noted (it's not retrievable after the modal closes)
- [ ] Dashboard URL confirmed live (loads the login screen)
- [ ] Widget visible on client's website

### Email 2 — Webhook Secret Delivery

- [ ] Webhook secret copied before closing the one-time modal
- [ ] Client's webhook URL confirmed reachable (responds to the dashboard's **Test** button)
- [ ] Test event sent and received successfully on the client's side
- [ ] Guide URL working and accessible (open in an incognito window to confirm it's public)

### Email 3 — 7-Day Check-In

- [ ] 7 days since onboarding date (check the tenant's `created_at`)
- [ ] Client has logged in at least once (verify in Analytics → recent sessions)
- [ ] Any unanswered questions flagged for follow-up (Conversations tab → filter by "no FAQ match")
