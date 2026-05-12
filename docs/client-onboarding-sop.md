---
title: Client Onboarding SOP
version: 1.0
owner: Kay — SupportBot Studio
last_updated: 2026-05-08
---

# Client Onboarding SOP

## Section 1 — Overview

This SOP is the single source of truth for onboarding a new SupportBot Studio client. It covers everything from the moment a contract is signed to the moment the client is marked LIVE in the registry. Follow this document in order for every new client, no exceptions. Skipping steps causes support debt.

---

## Section 2 — Pre-Onboarding (Before touching the dashboard)

Confirm every item below before you create a tenant.

- [ ] Signed service agreement received (or verbal confirmed and noted)
- [ ] Setup fee payment confirmed
- [ ] Client filled onboarding form with:
  - [ ] Business name
  - [ ] Website URL
  - [ ] Brand color (hex code)
  - [ ] Agent name (what they want the bot called)
  - [ ] Welcome message
  - [ ] Escalation email address
  - [ ] Telegram chat ID (if they want escalation alerts)
- [ ] List of FAQs collected (minimum 5 before going live)
- [ ] Client's webhook tool confirmed (Activepieces / n8n / Zapier / Make / none)
- [ ] Webhook destination URL collected (if applicable)

Do not create the tenant until ALL items above are checked. A half-configured bot is worse than no bot.

---

## Section 3 — Tenant Creation (Super Admin Dashboard)

1. Log into the super admin dashboard.
2. Navigate to **Tenants → Create New Tenant**.
3. Fill in:
   - **Business name:** `{{CLIENT_BUSINESS_NAME}}`
   - **Subdomain / bot_id:** lowercase-hyphenated version of business name (e.g. `Acme Corp` → `acme-corp`).
   - **Plan:** select the agreed tier.
   - **Monthly message limit:** set per agreement.
4. Click **Save** → copy the `bot_id` that is generated.
5. Log in as the new tenant (use **Impersonate** or the temp credentials).
6. Verify the dashboard loads correctly with no errors.

⚠️ **WARNING — bot_id is permanent.** Once a tenant is created, the `bot_id` cannot be safely changed without breaking every embed and webhook tied to it. Confirm the slug is correct before saving.

**Section 3 checklist:**

- [ ] Tenant created
- [ ] `bot_id` noted: ________________
- [ ] Dashboard accessible
- [ ] No console errors on load

---

## Section 4 — Bot Configuration

1. Go to the **Configure** tab in the client dashboard.
2. Set:
   - **Business name**
   - **Agent name**
   - **Brand color** (paste hex code)
   - **Welcome message**
3. Click **Save Config**.
4. Go to the **Knowledge Base** tab.
5. Add all FAQs from the onboarding form one by one (or use **Bulk Upload** if the client provided a CSV/PDF/DOCX).
6. Verify each FAQ appears in the list after saving.
7. Go to the **Chat Demo** tab.
8. Test 3–5 of the client's FAQs manually.
9. Verify auto-replies fire correctly (the **⚡ Instant reply** badge shows).
10. Test one question the bot doesn't know → verify it escalates correctly.

**Section 4 checklist:**

- [ ] Brand config saved
- [ ] All FAQs added (count: ___)
- [ ] Auto-reply working for known questions
- [ ] Escalation working for unknown questions
- [ ] Welcome message correct in demo

---

## Section 5 — Escalation Setup

1. Go to **Configure → Escalation Settings**.
2. Set escalation email: `{{CLIENT_ESCALATION_EMAIL}}`.
3. If the client wants Telegram alerts:
   - Ask the client to start a chat with the SupportBot Telegram bot.
   - Get their Telegram chat ID.
   - Enter the chat ID in the dashboard.
   - Send a test Telegram message → confirm the client receives it.
4. Click **Save Escalation Settings**.
5. Trigger a test escalation from the **Chat Demo** tab.
6. Verify the email arrives at the escalation address.
7. Verify the Telegram message arrives (if configured).

⚠️ **WARNING — wrong email = silent failure.** If the escalation email is mistyped, the bot will keep escalating and nothing will arrive. Always send a test escalation and watch it land before moving on.

**Section 5 checklist:**

- [ ] Escalation email set and tested
- [ ] Telegram alert set and tested (or N/A noted)
- [ ] Client confirmed receipt of test alert

---

## Section 6 — Webhook Setup

> Skip this entire section if the client has no automation tool.

1. Go to the **Webhooks** tab in the client dashboard.
2. Click **+ Add Webhook**.
3. Set **Platform:** `custom_https`.
4. Paste the client's webhook URL (from their Activepieces / n8n / Zapier / Make).
5. Select events to **Subscribe to**:
   - `lead_captured` (always recommend)
   - `escalation_triggered` (always recommend)
   - `conversation_ended` (optional)
6. Click **+ Add Webhook** → secret auto-generates.
7. **ONE-TIME MODAL APPEARS** — do the following immediately:
   1. Copy the secret.
   2. Paste it into a secure note / password manager.
   3. Send Email 2 (webhook secret delivery) to client.
   4. Click **Done** to close the modal.
8. Send a test event via the **Test** button.
9. Confirm the event arrives in the client's automation tool.
10. Confirm signature verification passes (no error in their tool).

⚠️ **WARNING — modal is single-shot.** If you close the modal without copying the secret, you must regenerate it. The old secret is gone. Any integration using it will break immediately.

**Section 6 checklist:**

- [ ] Webhook URL entered
- [ ] Events selected
- [ ] Secret copied and stored safely
- [ ] Email 2 sent to client
- [ ] Test event sent and received
- [ ] Signature verification confirmed passing
- [ ] Client's automation flow published/active (not just saved)

---

## Section 7 — Widget Embed

1. Copy the embed code from the dashboard:

   ```html
   <script src="{{BOT_URL}}/widget.js" data-bot-id="{{BOT_ID}}"></script>
   ```

2. Send the embed code to the client (or install it yourself if agreed).
3. Ask the client to paste it before `</body>` on their website.
4. Visit the client's website after they install it.
5. Confirm the chat bubble appears bottom-right.
6. Send one message through the live widget.
7. Verify the response is correct.
8. Verify the escalation path works from the live widget.

**Section 7 checklist:**

- [ ] Embed code sent to client
- [ ] Widget visible on client's live website
- [ ] Live chat test passed
- [ ] Live escalation test passed

---

## Section 8 — Send Onboarding Emails

| Email | Template | When to Send | Trigger |
|---|---|---|---|
| Email 1 | Welcome + Login | Immediately after Section 4 complete | Tenant created + bot configured |
| Email 2 | Webhook Secret | Immediately after Section 6 step 7 | Secret generated |
| Email 3 | 7-Day Check-In | 7 days after Email 1 | Calendar reminder |

Instructions:

- Use the templates in `docs/client-onboarding-email.md`.
- Fill every `{{PLACEHOLDER}}` before sending.
- Set a calendar reminder for Email 3 immediately after sending Email 1.
- Log the send date in the Client Registry (Section 10).

**Section 8 checklist:**

- [ ] Email 1 sent (date: _________)
- [ ] Email 2 sent (date: _________)
- [ ] Calendar reminder set for Email 3

---

## Section 9 — Final QA Before Handoff

This is the last check before telling the client they are live. Run every item.

- [ ] Widget loads on client's website with no console errors
- [ ] Brand color matches client's brand
- [ ] Agent name correct in chat header
- [ ] Welcome message correct
- [ ] 5 FAQ auto-replies tested and passing
- [ ] Escalation email tested and arriving
- [ ] Telegram alert tested (or N/A)
- [ ] Webhook test event received (or N/A)
- [ ] Webhook signature verification passing (or N/A)
- [ ] Client has logged into their dashboard at least once
- [ ] Client knows how to add FAQs themselves
- [ ] Client knows where to find analytics

Only mark a client as LIVE after all items are checked.

---

## Section 10 — Client Registry

Maintain the table below (or a separate `docs/client-registry.md`) with one row per client. Update it after every onboarding.

| # | Client Name | bot_id | Live Date | Plan | Webhook | Notes |
|---|---|---|---|---|---|---|
| 1 |  |  |  |  | Yes/No |  |
| 2 |  |  |  |  | Yes/No |  |
| 3 |  |  |  |  | Yes/No |  |

**Section 10 checklist:**

- [ ] New client row added to registry
- [ ] Live Date filled in
- [ ] Webhook column marked Yes or No
- [ ] Notes captured (any custom config, edge cases, future asks)

---

## Section 11 — Ongoing Responsibilities

| Task | When | How |
|---|---|---|
| Check all tenants active | 1st of month | Super admin dashboard |
| Confirm Render deployment healthy | Weekly | Render dashboard + `/api/health` |
| Review escalation logs for issues | Weekly | Analytics tab per tenant |
| Send monthly report summary | 1st of month | **Reports** tab or manual email |
| Rotate secrets if any client requests | As needed | **Webhooks → Regenerate Secret** |
| Offboard inactive tenants | As needed | See offboarding SOP (TBD) |

⚠️ **WARNING — Regenerate Secret breaks live integrations.** Only rotate when the client has explicitly asked for it or you have evidence the secret is compromised. Confirm the client is ready to update their receiver before clicking.

**Section 11 checklist:**

- [ ] Monthly tenant audit done (date: _________)
- [ ] Weekly health check done (date: _________)
- [ ] Weekly escalation review done (date: _________)
- [ ] Monthly report sent (date: _________)

---

## Section 12 — Troubleshooting Quick Reference

| Problem | Cause | Fix |
|---|---|---|
| Widget not showing on client site | Wrong `bot_id` in embed code | Check `bot_id` in super admin |
| Auto-replies not firing | FAQ not saved correctly | Re-add FAQ, check spelling |
| Escalation email not arriving | Wrong email in config | Verify email field, check spam |
| Telegram alert not sending | Wrong chat ID | Client must `/start` the bot first |
| Webhook secret modal closed too fast | Human error | Regenerate secret in dashboard |
| Webhook test passes but live events don't arrive | Flow not published | Client must publish, not just save |
| Signature mismatch in Activepieces | Whitespace in secret | Re-paste secret without spaces |
| Bot responding in wrong language | Auto-detect working correctly | Expected behaviour — tell client |

**Section 12 checklist:**

- [ ] Issue diagnosed against this table before escalating
- [ ] Fix verified in client's environment
- [ ] If new issue type: added to this table in next SOP version

---

## Section 13 — SOP Maintenance

Update this document whenever:

- A new feature is added to SupportBot Studio
- A step is found to be missing or wrong during an onboarding
- A new automation platform is supported

**Version history:**

| Version | Date | Change |
|---|---|---|
| 1.0 | 2026-05-08 | Initial SOP created |

**Section 13 checklist:**

- [ ] Version number bumped on every change
- [ ] Date updated
- [ ] Change row added to the version history table
- [ ] `last_updated` field in header block updated
