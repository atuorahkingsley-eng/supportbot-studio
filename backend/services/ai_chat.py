from typing import List, Optional
import anthropic
from backend.config import settings


def build_system_prompt(bot_config, faqs: list) -> str:
    faq_text = ""
    if faqs:
        faq_text = "\n\nKnowledge Base:\n"
        for faq in faqs:
            faq_text += f"Q: {faq.question}\nA: {faq.answer}\n\n"

    return f"""You are {bot_config.agent_name}, a helpful customer support assistant for {bot_config.business_name}.

Always be friendly, concise, and helpful. Answer questions based on the knowledge base below when relevant.

If you cannot answer the question or the customer seems frustrated, suggest escalation by including the phrase "ESCALATE" in your response.
{faq_text}"""


async def get_ai_reply(
    messages: List[dict],
    bot_config,
    faqs: list,
) -> str:
    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)

    system_prompt = build_system_prompt(bot_config, faqs)

    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=1024,
        system=system_prompt,
        messages=messages,
    )

    return response.content[0].text
