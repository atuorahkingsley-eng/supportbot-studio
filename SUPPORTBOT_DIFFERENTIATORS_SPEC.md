# SupportBot Studio — Differentiator Features Spec

## Overview

These 4 features transform SupportBot from "another chatbot" into a unique product that competitors don't offer. Each feature is designed to either make money (proactive sales), save money (auto-reply + memory), or unlock new markets (multi-language, voice).

Build in this order: 1 → 2 → 3 → 4

---

## FEATURE 1: Conversation Memory (Remembers Returning Customers)

### Why It's Different
Most chatbots treat every visit as a stranger. Ours remembers. "Welcome back! Last time you asked about pricing — ready to get started?" This alone converts more visitors into customers.

### How It Works

**Customer identification:** Browser fingerprint + optional email. When a customer first chats, generate a unique `visitor_id` stored in the browser's cookie. If they provide an email during escalation or conversation, link it to their visitor_id.

### Database Changes

Add new model — `Visitor`:
```
id: int (PK)
visitor_id: str (uuid, stored in browser cookie)
email: str (nullable, linked when provided)
first_seen: datetime
last_seen: datetime
visit_count: int (default 1)
name: str (nullable, extracted from conversation if mentioned)
tags: str (JSON array, e.g. ["interested_in_pricing", "enterprise", "returning"])
notes: str (nullable, AI-generated summary of past interactions)
```

Add new model — `VisitorConversation` (links visitors to conversations):
```
id: int (PK)
visitor_id: str (FK → Visitor.visitor_id)
conversation_id: int (FK → Conversation.id)
```

### API Changes

**`POST /api/chat`** — updated request:
```json
{
  "session_id": "uuid",
  "visitor_id": "uuid-from-cookie",
  "message": "Hi there"
}
```

**`GET /api/visitors/{visitor_id}/history`** — returns past conversations summary

### AI Chat Integration

When a returning visitor sends their first message, inject their history into Claude's system prompt:

```
RETURNING VISITOR CONTEXT:
- This customer has visited 3 times before
- First visit: March 1, 2026
- Email: john@example.com
- Previous topics they asked about: pricing, integrations, refund policy
- Tags: interested_in_pricing, returning

Use this context to personalize your greeting and responses:
- Welcome them back warmly
- Reference their previous interests naturally
- If they previously asked about pricing, gently guide toward conversion
- Do NOT be creepy or over-reference their history — keep it subtle and helpful
```

### After Each Conversation Ends

Use Claude to generate a brief visitor summary:

```
Prompt: "Summarize this customer conversation in 1-2 sentences. What were they interested in? Any buying signals? Return JSON: {\"summary\": \"...\", \"tags\": [\"...\"], \"buying_signal\": true/false}"
```

Store the summary in `Visitor.notes` and update `Visitor.tags`.

### Frontend Changes

**Chat Widget:**
- On load, check for `supportbot_visitor_id` cookie
- If exists → send with first message → backend returns personalized greeting
- If not exists → generate new UUID, store in cookie (expires 365 days)
- Show subtle "Welcome back!" badge on returning visitors

**Admin Panel — New "Customers" section in Analytics tab:**
- List of visitors with visit count, last seen, email, tags
- Click a visitor → see all their past conversations
- Filter by: returning, has email, specific tags

---

## FEATURE 2: Multi-Language Auto-Detect

### Why It's Different
Most chatbots only work in English or require manual language selection. Ours auto-detects and responds in the customer's language. A Nigerian business can serve Yoruba, Pidgin, French, and English customers from one bot.

### How It Works

Let Claude handle it naturally. Add language instructions to the system prompt:

```
LANGUAGE RULES:
- ALWAYS detect the language of the customer's message
- ALWAYS respond in the SAME language the customer used
- If the customer writes in Nigerian Pidgin, respond in Nigerian Pidgin
- If the customer writes in French, respond in French
- If the customer switches languages mid-conversation, switch with them
- Translate knowledge base answers naturally — don't machine-translate, adapt culturally
```

### Database Changes

Add to `Message` model:
```
detected_language: str (nullable, e.g. "en", "fr", "pcm", "yo", "es")
```

Add to `Conversation` model:
```
primary_language: str (nullable, most-used language in conversation)
```

### Auto-Reply Enhancement

Non-English messages naturally fall through to Claude (auto-reply only matches English FAQs). This is correct behavior — auto-reply handles English cheaply, Claude handles translation.

### Analytics Enhancement

**New metric:** Language distribution chart
- Pie chart: English 60%, Pidgin 20%, French 10%, etc.
- Filter conversations by language
- This data is valuable for clients — shows actual customer demographics

### Frontend Changes

- Detect browser language (`navigator.language`) and send as hint
- Show language indicator in chat header
- Placeholder text adapts to detected language

### Supported Languages (via Claude — 50+)
English, French, Spanish, Portuguese, German, Italian, Dutch, Nigerian Pidgin, Yoruba, Igbo, Hausa, Arabic, Swahili, Chinese, Japanese, Korean, Hindi, and many more.

Marketing line: "One chatbot. Every language. Automatically."

---

## FEATURE 3: Proactive Sales Agent

### Why It's Different
Most chatbots wait for questions. Ours actively sells. It detects buying intent, offers deals, captures leads, and books demos. Turns support cost into profit center.

### Three Triggers

1. **Timed trigger** — After X seconds on page with no interaction, bot pops up with offer
2. **Intent detection** — Claude detects buying signals and pivots to sales
3. **Exit intent** — When user moves mouse toward closing, offer a discount

### Database Changes

Add new model — `SalesConfig`:
```
id: int (PK)
enabled: bool (default true)
greeting_delay_seconds: int (default 30)
greeting_message: str ("Looking for something? I can help you find the perfect plan!")
discount_code: str (nullable, e.g. "SAVE10")
discount_message: str (nullable, "Use code SAVE10 for 10% off!")
demo_booking_url: str (nullable, e.g. "https://calendly.com/company/demo")
exit_intent_enabled: bool (default true)
exit_intent_message: str ("Wait! Before you go — here's 10% off.")
```

Add new model — `Lead`:
```
id: int (PK)
visitor_id: str (nullable, FK → Visitor.visitor_id)
email: str
name: str (nullable)
interest: str (what they were asking about)
source: str ("chat_capture" | "exit_intent" | "proactive" | "escalation")
buying_signal_score: int (1-5, AI-rated)
conversation_id: int (nullable, FK → Conversation.id)
created_at: datetime
followed_up: bool (default false)
```

### AI Integration

Add to Claude system prompt when sales mode is enabled:

```
SALES AGENT RULES:
- Watch for buying signals: pricing questions, comparisons, "how much", trial mentions
- When you detect buying intent, naturally guide toward conversion
- Mention current promotion if one exists: {discount_code}
- Offer to book a demo if available: {demo_booking_url}
- Ask for their email to send more info
- Be helpful first, salesy second — never be pushy
- After your response text, include on a new line: SALES_META:{"buying_signal": 3, "intent": "pricing_inquiry", "action": "offer_discount"}
```

Backend parses the SALES_META from Claude's response:
- If buying_signal >= 3 → trigger sales action card in widget
- If intent = "pricing" → show pricing comparison card
- If action = "offer_discount" → display discount code card
- Strip SALES_META from the response shown to customer

### API Changes

**`POST /api/chat`** — response now includes:
```json
{
  "reply": "Great question about pricing!...",
  "was_auto_reply": false,
  "sales_action": {
    "type": "discount",
    "code": "SAVE10",
    "message": "Use code SAVE10 for 10% off!"
  }
}
```

**`GET /api/leads`** — list captured leads
**`POST /api/leads/capture`** — capture lead from chat
**`PUT /api/leads/{id}/follow-up`** — mark as followed up

### Frontend Changes

**Sales Action Cards in Chat Widget:**

1. **Discount Card** — gold/amber background, shows code with copy button
2. **Demo Booking Card** — calendar icon, button links to booking URL
3. **Lead Capture Card** — "Want a detailed comparison?" + email input + submit
4. **Pricing Comparison Card** — mini pricing table with recommended plan highlighted

**Proactive Popup:**
- After `greeting_delay_seconds` with no interaction, chat bubble bounces
- Small notification badge: "1 new message"

**Exit Intent:**
- Detect `mouseleave` event on document
- Show overlay with exit_intent_message + discount code + email capture

**Admin Panel — New "Sales" tab:**
- Toggle sales mode on/off
- Configure: greeting delay, messages, discount code, booking URL
- Lead board: table with email, interest, score, date, follow-up status
- Export leads as CSV
- Stats: leads captured this week/month, conversion funnel

### Sales Analytics (in Analytics dashboard)

- **Lead Funnel:** Visitors → Conversations → Leads
- **Revenue Attribution:** "X leads captured worth ~$Y"
- **Top Converting Topics:** Which questions lead to sales captures
- **Proactive vs Reactive:** Leads from popup vs organic chat

---

## FEATURE 4: Voice Input Support

### Why It's Different
90% of chatbots are text-only. Voice makes the bot accessible to everyone — mobile users, people who can't type fast, people with disabilities. It's the "wow factor" in client demos.

### How It Works

Uses the browser's built-in **Web Speech API** — completely free, no external service needed. Speech-to-text happens in the browser, then text is sent to chat API normally.

### Frontend Implementation

**Mic Button** next to send button:

```jsx
const [isListening, setIsListening] = useState(false);
const recognitionRef = useRef(null);

useEffect(() => {
  const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (SpeechRecognition) {
    const recognition = new SpeechRecognition();
    recognition.continuous = false;
    recognition.interimResults = true;
    recognition.lang = navigator.language || 'en-US';
    
    recognition.onresult = (event) => {
      const transcript = Array.from(event.results)
        .map(result => result[0].transcript)
        .join('');
      setInput(transcript);
      
      if (event.results[0].isFinal) {
        sendMessage(transcript);
        setIsListening(false);
      }
    };
    
    recognition.onerror = () => setIsListening(false);
    recognition.onend = () => setIsListening(false);
    recognitionRef.current = recognition;
  }
}, []);
```

**UI States:**
- Default: gray mic icon
- Listening: pulsing red/brand-color mic with sound wave animation
- Not supported: hide mic button entirely

**Animations:**
```css
@keyframes pulse {
  0%, 100% { opacity: 1; transform: scale(1); }
  50% { opacity: 0.7; transform: scale(1.1); }
}
@keyframes soundWave {
  0%, 100% { height: 8px; }
  50% { height: 20px; }
}
```

### Multi-Language Voice (combines with Feature 2)

```javascript
recognition.lang = detectedLanguage || navigator.language || 'en-US';
```

### Backend Changes

Minimal — add to `Message` model:
```
input_method: str (default "text", can be "voice")
```

Add voice vs text metric to Analytics.

### Admin Panel
- Toggle: "Enable voice input" in Configure tab
- Controls whether mic button appears

---

## BUILD ORDER FOR CLAUDE CODE

### Phase 1: Conversation Memory
1. Add Visitor and VisitorConversation models
2. Add visitor_id cookie logic to frontend
3. Update /api/chat to accept visitor_id
4. Add visitor history to Claude system prompt
5. Add post-conversation summary generation
6. Add Customers section to Analytics
7. Test: Chat → close → reopen → personalized greeting

### Phase 2: Multi-Language
8. Update Claude system prompt with language rules
9. Add detected_language to Message model
10. Add primary_language to Conversation model
11. Update /api/chat to store detected language
12. Add language distribution chart to Analytics
13. Add browser language detection to frontend
14. Test: Type in French/Pidgin → bot responds in same language

### Phase 3: Proactive Sales Agent
15. Add SalesConfig and Lead models
16. Create /api/sales/config endpoint
17. Create /api/leads endpoints
18. Update Claude system prompt with sales rules
19. Update /api/chat response parsing for sales metadata
20. Add Sales Action Cards to ChatWidget
21. Add proactive greeting popup
22. Add exit intent detection
23. Add Sales tab to admin panel
24. Add sales metrics to Analytics
25. Test: Ask about pricing → discount card → capture lead

### Phase 4: Voice Input
26. Add Speech Recognition to ChatWidget
27. Add mic button with animation
28. Add input_method to Message model
29. Add voice toggle to Configure tab
30. Add voice vs text metric to Analytics
31. Test: Click mic → speak → auto-sends → gets reply

### Phase 5: Integration Testing
32. Test all 4 together: Voice in French → auto-detect → remember visitor → detect buying intent → offer discount
33. Push to GitHub and deploy to Render

---

## PRICING WITH THESE FEATURES

| Tier | Features | Price |
|------|----------|-------|
| Basic | FAQ bot + analytics | $500-$800 |
| Pro | + memory + multilingual | $1,500-$2,500 |
| Enterprise | + sales agent + voice + webhooks | $3,000-$5,000 |
| Monthly | Maintenance + API costs | $100-$300/month |

## MARKETING TAGLINE

"The chatbot that remembers, speaks every language, and closes deals."
