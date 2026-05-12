---
title: Client Registry
version: 1.0
owner: Kay — SupportBot Studio
last_updated: 2026-05-08
instructions: Add one row per client. Update after every onboarding, change, or offboarding event. Never delete rows — mark status as Churned instead.
---

# Client Registry

## Section 1 — Active Clients

One row per active client. Keep sorted by Live Date (oldest first).

| # | Client Name | bot_id | Industry | Live Date | Plan | MRR (USD) | Webhook | Telegram | Status | Notes |
|---|---|---|---|---|---|---|---|---|---|---|
| 1 |  |  |  |  |  |  |  |  | Onboarding |  |
| 2 |  |  |  |  |  |  |  |  | Onboarding |  |
| 3 |  |  |  |  |  |  |  |  | Onboarding |  |

Column definitions:

| Column | What to enter |
|---|---|
| **#** | Sequential number — never reuse |
| **Client Name** | Business trading name |
| **bot_id** | Exact bot_id from super admin e.g. `acme-corp` |
| **Industry** | e.g. Ecommerce, SaaS, Real Estate, Restaurant |
| **Live Date** | Date widget went live on client's website (YYYY-MM-DD) |
| **Plan** | Starter / Growth / Pro (or custom label) |
| **MRR (USD)** | Monthly recurring revenue from this client |
| **Webhook** | Yes / No / Pending |
| **Telegram** | Yes / No |
| **Status** | Active / Paused / Churned / Onboarding |
| **Notes** | Any important context — one line max |

---

## Section 2 — Revenue Summary

Update this section on the 1st of every month.

| Month | Active Clients | Total MRR (USD) | New Clients | Churned | Notes |
|---|---|---|---|---|---|
| 2026-05 | 0 | $0 | 0 | 0 | Launch month |

```
MRR Growth    = This Month MRR - Last Month MRR
Churn Rate    = Churned This Month / Active Last Month × 100
Target MRR    = Active Clients × Average Plan Value
```

---

## Section 3 — Setup Fee Tracker

Log every setup fee payment here. One row per client.

| # | Client Name | Setup Fee (USD) | Payment Method | Payment Date | Invoice Sent | Invoice Paid |
|---|---|---|---|---|---|---|
| 1 |  |  |  |  | No | No |

Payment methods accepted: Bank Transfer, Payoneer, Wise, PayPal, Cash.

---

## Section 4 — Credentials & Access Log

Log all credentials Kay holds or has sent to clients. Never store actual passwords here — use a password manager. Log only that credentials exist and were sent.

| # | Client Name | Dashboard URL | Login Email Sent | Temp Password Reset | Embed Code Sent | Embed Installed |
|---|---|---|---|---|---|---|
| 1 |  |  | Yes/No (date) | Yes/No (date) | Yes/No (date) | Yes/No (date) |

⚠️ **WARNING — never write actual passwords in this file.** This file may be stored in a git repo. Use Bitwarden, 1Password, or similar for credential storage.

---

## Section 5 — Webhook Registry

Track webhook configuration per client. One row per client that has webhooks enabled.

| # | Client Name | bot_id | Webhook URL (domain only) | Platform | Events Subscribed | Secret Stored | Last Test | Status |
|---|---|---|---|---|---|---|---|---|
| 1 |  |  |  |  |  |  |  |  |

Column definitions:

| Column | What to enter |
|---|---|
| **Webhook URL** | Domain only for security e.g. `cloud.activepieces.com` |
| **Platform** | Activepieces / n8n / Zapier / Make / Custom |
| **Events Subscribed** | `lead_captured`, `escalation_triggered`, `conversation_ended` |
| **Secret Stored** | Yes (in password manager) / No |
| **Last Test** | Date last test event was sent and confirmed (YYYY-MM-DD) |
| **Status** | Active / Broken / Paused |

⚠️ **WARNING — never write webhook secrets in this file.** Store secrets in your password manager only. If a secret is lost, regenerate it from the SupportBot dashboard.

---

## Section 6 — Onboarding Status Tracker

Use this to track exactly where each client is in the onboarding process. Update in real time.

| # | Client Name | Pre-Onboard | Tenant Created | Bot Configured | FAQs Added | Escalation Tested | Webhook Live | Widget Live | Email 1 Sent | Email 2 Sent | Email 3 Sent | LIVE ✓ |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 |  |  |  |  |  |  |  |  |  |  |  |  |
| 2 |  |  |  |  |  |  |  |  |  |  |  |  |
| 3 |  |  |  |  |  |  |  |  |  |  |  |  |

All columns after Client Name are Yes / No / N/A / date fields.

A client is only marked LIVE ✓ after every applicable column is Yes or N/A. No exceptions.

---

## Section 7 — Support & Issue Log

Log every support request or issue raised by any client. One row per incident. Never delete rows.

| # | Date | Client Name | Issue Description | Severity | Status | Resolution | Time to Fix |
|---|---|---|---|---|---|---|---|
| 1 | 2026-05-08 | Example Corp | Widget not loading after DNS change | High | Resolved | Updated CORS settings in config | 2 hours |

Severity: Critical (bot down) / High (major feature broken) / Medium (minor issue) / Low (question or feedback).

Status: Open / In Progress / Resolved / Won't Fix.

---

## Section 8 — Churned Clients

Move clients here when they cancel. Never delete. Understanding why clients leave improves the product.

| # | Client Name | bot_id | Live Date | Churn Date | MRR Lost (USD) | Churn Reason | Salvageable |
|---|---|---|---|---|---|---|---|
| 1 |  |  |  |  |  |  |  |

Common churn reasons: Price, No longer needed, Switched tool, Poor fit, Non-payment, Business closed, Unresponsive.

Salvageable: Yes (follow up in 90 days) / No / Maybe.

---

## Section 9 — Pipeline (Prospects)

Track potential clients before they sign. Move to Section 1 when they go live.

| # | Business Name | Industry | Contact Name | Contact Email | Stage | Est. MRR (USD) | Follow-up Date | Notes |
|---|---|---|---|---|---|---|---|---|
| 1 |  |  |  |  |  |  |  |  |
| 2 |  |  |  |  |  |  |  |  |
| 3 |  |  |  |  |  |  |  |  |
| 4 |  |  |  |  |  |  |  |  |
| 5 |  |  |  |  |  |  |  |  |

Stages: Lead → Contacted → Demo Done → Proposal Sent → Negotiating → Won → Lost.

---

## Section 10 — Key Metrics Dashboard

Update monthly. These are the numbers that matter.

| Metric | Value | Target | Last Updated |
|---|---|---|---|
| Total Active Clients | 0 | 10 | 2026-05-08 |
| Total MRR | $0 | $1,500 | 2026-05-08 |
| Average MRR per Client | $0 | $150 | 2026-05-08 |
| Churn Rate | 0% | <5% | 2026-05-08 |
| Setup Fees Collected (All Time) | $0 | $5,000 | 2026-05-08 |
| Clients with Webhooks | 0 | 80% | 2026-05-08 |
| Avg FAQs per Client | 0 | 20 | 2026-05-08 |
| Open Support Issues | 0 | 0 | 2026-05-08 |

Targets are Kay's 90-day goals as of launch. Revise targets every quarter.

---

## Section 11 — Registry Maintenance Rules

1. Update this file within 24 hours of any client event.
2. Never delete any row — use Status = Churned instead.
3. Never store passwords, secrets, or API keys in this file.
4. Back up this file to Google Drive on the 1st of every month.
5. If a client's `bot_id` changes for any reason, log the old one in Notes and update the row.
6. Keep pipeline prospects in Section 9 only — move to Section 1 the moment they go live.
7. Review Section 8 (Churned) every quarter — follow up with Salvageable = Yes clients.
