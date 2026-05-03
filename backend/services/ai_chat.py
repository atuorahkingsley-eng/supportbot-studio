import json
import re
from typing import List, Optional
import anthropic
from backend.config import settings
from backend.services.brand_voice_analyzer import render_voice_block


def build_system_prompt(
    bot_config,
    faqs: list,
    visitor_context: Optional[dict] = None,   # Phase 1
    sales_config=None,                         # Phase 3
    brand_voice=None,                          # Brand Voice DNA
) -> str:
    # ── Knowledge Base ────────────────────────────────────────────────────────
    faq_text = ""
    if faqs:
        faq_text = "\n\nKnowledge Base:\n"
        for faq in faqs:
            faq_text += f"Q: {faq.question}\nA: {faq.answer}\n\n"

    # ── Phase 1: Returning Visitor Context ───────────────────────────────────
    visitor_block = ""
    if visitor_context and visitor_context.get("visit_count", 1) > 1:
        tags = visitor_context.get("tags", [])
        topics = visitor_context.get("notes") or (", ".join(tags) if tags else "general support")
        visitor_block = f"""
RETURNING VISITOR CONTEXT:
- This customer has visited {visitor_context['visit_count']} times before
- First visit: {visitor_context.get('first_seen', 'unknown')}
- Email: {visitor_context.get('email') or 'not provided'}
- Previous topics they asked about: {topics}
- Tags: {', '.join(tags) if tags else 'none'}

Use this context to personalize your greeting and responses:
- Welcome them back warmly
- Reference their previous interests naturally
- If they previously asked about pricing, gently guide toward conversion
- Do NOT be creepy or over-reference their history — keep it subtle and helpful
"""

    # ── Phase 2: Language Rules ───────────────────────────────────────────────
    language_block = """
LANGUAGE RULES:
- ALWAYS detect the language of the customer's message
- ALWAYS respond in the SAME language the customer used
- If the customer writes in Nigerian Pidgin, respond in Nigerian Pidgin
- If the customer writes in French, respond in French
- If the customer switches languages mid-conversation, switch with them
- Translate knowledge base answers naturally — don't machine-translate, adapt culturally
- After your response, on a new line add: LANG:<detected_language_code> (e.g. LANG:en, LANG:fr, LANG:pcm)
"""

    # ── Phase 3: Sales Agent Rules ────────────────────────────────────────────
    sales_block = ""
    if sales_config and getattr(sales_config, "enabled", False):
        discount_info = ""
        if getattr(sales_config, "discount_code", None):
            discount_info = f"Current promotion: use code {sales_config.discount_code} — {sales_config.discount_message or ''}"
        demo_info = ""
        if getattr(sales_config, "demo_booking_url", None):
            demo_info = f"Demo booking URL: {sales_config.demo_booking_url}"

        sales_block = f"""
SALES AGENT RULES:
- Watch for buying signals: pricing questions, comparisons, "how much", trial mentions, plan questions
- When you detect buying intent, naturally guide toward conversion
- {discount_info}
- {demo_info}
- Offer to book a demo if available
- Ask for their email to send more info when appropriate
- Be helpful first, salesy second — never be pushy
- After your response text, include on a new line: SALES_META:{{"buying_signal": <1-5>, "intent": "<pricing_inquiry|general|demo_interest|comparison>", "action": "<none|offer_discount|offer_demo|capture_lead>"}}
"""

    # ── Brand Voice DNA (rendered first — sets tone for all rules below) ────
    voice_block = render_voice_block(brand_voice)

    prompt = f"""You are {bot_config.agent_name}, a helpful customer support assistant for {bot_config.business_name}.

Always be friendly, concise, and helpful. Answer questions based on the knowledge base below when relevant.

If you cannot answer the question or the customer seems frustrated, suggest escalation by including the phrase "ESCALATE" in your response.
{voice_block}{visitor_block}{language_block}{sales_block}{faq_text}"""

    return prompt


def parse_metadata(raw_reply: str) -> dict:
    """Extract LANG and SALES_META tags from Claude's response, return clean reply + metadata."""
    reply = raw_reply
    detected_language = None
    sales_meta = None

    # Extract LANG tag (last occurrence, any line)
    lang_match = re.search(r'LANG:([a-z\-]{2,10})', reply, re.IGNORECASE)
    if lang_match:
        detected_language = lang_match.group(1).lower()
        # Remove the LANG line
        reply = re.sub(r'\nLANG:[a-z\-]{2,10}\s*', '', reply, flags=re.IGNORECASE)

    # Extract SALES_META tag
    sales_match = re.search(r'SALES_META:(\{[^}]+\})', reply, re.DOTALL)
    if sales_match:
        try:
            sales_meta = json.loads(sales_match.group(1))
        except Exception:
            sales_meta = None
        reply = re.sub(r'\nSALES_META:\{[^}]+\}\s*', '', reply, flags=re.DOTALL)

    return {
        "reply": reply.strip(),
        "detected_language": detected_language,
        "sales_meta": sales_meta,
    }


async def get_ai_reply(
    messages: List[dict],
    bot_config,
    faqs: list,
    visitor_context: Optional[dict] = None,
    sales_config=None,
    brand_voice=None,
) -> dict:
    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)

    system_prompt = build_system_prompt(
        bot_config, faqs,
        visitor_context=visitor_context,
        sales_config=sales_config,
        brand_voice=brand_voice,
    )

    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=1024,
        system=system_prompt,
        messages=messages,
    )

    raw = response.content[0].text
    return parse_metadata(raw)


async def generate_visitor_summary(messages: list) -> dict:
    """Generate a brief summary of a conversation for visitor memory (Phase 1)."""
    if not settings.anthropic_api_key or not messages:
        return {"summary": "", "tags": [], "buying_signal": False}

    transcript = "\n".join(
        f"{'Customer' if m['role'] == 'user' else 'Bot'}: {m['content']}"
        for m in messages
    )

    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
    prompt = (
        'Summarize this customer support conversation in 1-2 sentences. '
        'What were they interested in? Any buying signals? '
        'Return ONLY valid JSON: {"summary": "...", "tags": ["..."], "buying_signal": true}\n\n'
        f"Conversation:\n{transcript}"
    )

    try:
        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=256,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = response.content[0].text.strip()
        match = re.search(r'\{.*\}', raw, re.DOTALL)
        if match:
            return json.loads(match.group())
    except Exception:
        pass

    return {"summary": "", "tags": [], "buying_signal": False}
