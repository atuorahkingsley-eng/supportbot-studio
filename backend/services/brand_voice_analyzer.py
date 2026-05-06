"""Brand Voice DNA analyzer.

Sends sample copy (marketing pages, support emails, blog posts) to Claude
and asks for a structured JSON profile of the brand's voice. The result
is later injected into the chat system prompt so the bot writes in the
same voice the customer's existing materials use.

Failure modes handled here:
  - Claude returns text that isn't JSON (parse error)
  - Claude returns JSON missing one of the four facets (partial OK)
  - Anthropic API itself fails (network, auth, rate limit)

All three raise BrandVoiceAnalysisError so the router can return a clean
4xx/5xx without leaking internals.
"""
import json
import re
from typing import Optional

import anthropic
import structlog

from backend.config import settings


log = structlog.get_logger(__name__)


# ── Anthropic client (module-level, reused) ───────────────────────────────────
# One client per process. timeout=30.0 caps any single call so a hung Anthropic
# request can't pin a worker — important here because brand-voice analysis is
# triggered from a user-facing route, not a background job.
_client = anthropic.Anthropic(api_key=settings.anthropic_api_key, timeout=30.0)


# Hard cap on sample text — protects token budget and DB row size.
# 8000 chars is roughly 2k tokens, which gives Claude plenty to work
# with while staying well under the 200k context window.
MAX_SAMPLE_CHARS = 8000


class BrandVoiceAnalysisError(Exception):
    """Raised when Claude can't be reached or returns unusable output."""
    pass


_EXTRACTION_PROMPT = """Analyse the brand-voice samples below and extract a structured profile.

Return ONLY valid JSON in exactly this shape — no preamble, no commentary:

{
  "tone": "<one short phrase, e.g. 'warm and professional', 'playful and irreverent'>",
  "vocabulary": "<one to two sentences describing the word choices, sentence length, formality level>",
  "personality_traits": ["<trait>", "<trait>", "<trait>"],
  "avoid": "<one sentence on what NOT to do — phrases, tones, or styles that would feel off-brand>"
}

Rules:
- "tone" must be a single short phrase (under 60 chars).
- "personality_traits" must be a list of 3-5 single-word or short-phrase items.
- "avoid" describes what the brand explicitly does NOT sound like.
- If the samples are too short or contradictory, do your best — partial output is fine, but every key must still be present.

Samples:
"""


def _truncate_samples(raw: str) -> str:
    """Trim samples to MAX_SAMPLE_CHARS at a word boundary if possible."""
    if len(raw) <= MAX_SAMPLE_CHARS:
        return raw
    cut = raw[:MAX_SAMPLE_CHARS]
    # Walk back to last whitespace so we don't slice mid-word.
    last_space = cut.rfind(" ")
    if last_space > MAX_SAMPLE_CHARS - 200:  # only if we found one nearby
        cut = cut[:last_space]
    return cut + "\n\n[... truncated]"


def _parse_voice_json(raw_reply: str) -> dict:
    """Extract the first JSON object from Claude's response and validate shape."""
    match = re.search(r"\{.*\}", raw_reply, re.DOTALL)
    if not match:
        raise BrandVoiceAnalysisError("Claude response contained no JSON object")
    try:
        data = json.loads(match.group())
    except json.JSONDecodeError as e:
        raise BrandVoiceAnalysisError(f"Claude returned malformed JSON: {e}")

    # Coerce expected shape — be lenient with missing keys (per the
    # nullable-columns design) but reject totally wrong types so a
    # garbage response doesn't sneak into the DB.
    tone = data.get("tone")
    vocabulary = data.get("vocabulary")
    traits = data.get("personality_traits") or []
    avoid = data.get("avoid")

    if traits and not isinstance(traits, list):
        raise BrandVoiceAnalysisError("personality_traits must be a list")

    return {
        "tone": tone if isinstance(tone, str) else None,
        "vocabulary": vocabulary if isinstance(vocabulary, str) else None,
        "personality_traits": [str(t) for t in traits] if isinstance(traits, list) else [],
        "avoid": avoid if isinstance(avoid, str) else None,
    }


async def analyze_brand_voice(samples: str, bot_id: str) -> dict:
    """Run Claude over `samples` and return the structured voice profile.

    Returns dict shaped:
        {
          "tone": str | None,
          "vocabulary": str | None,
          "personality_traits": list[str],
          "avoid": str | None,
          "raw_samples": str,   # truncated copy of input — caller persists this
        }

    Raises BrandVoiceAnalysisError on any failure path.
    """
    if not settings.anthropic_api_key:
        raise BrandVoiceAnalysisError("ANTHROPIC_API_KEY is not configured")

    sample_text = (samples or "").strip()
    if not sample_text:
        raise BrandVoiceAnalysisError("No samples provided")

    truncated = _truncate_samples(sample_text)

    try:
        response = _client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=512,
            messages=[
                {"role": "user", "content": _EXTRACTION_PROMPT + truncated},
            ],
        )
    except anthropic.APIError as e:
        log.error("brand_voice.api_error", bot_id=bot_id, error=str(e))
        raise BrandVoiceAnalysisError(f"Claude API call failed: {e}")
    except Exception as e:
        log.error("brand_voice.unexpected_api_error", bot_id=bot_id, error=str(e))
        raise BrandVoiceAnalysisError(f"Unexpected error calling Claude: {e}")

    raw = response.content[0].text if response.content else ""
    if not raw.strip():
        raise BrandVoiceAnalysisError("Claude returned an empty response")

    profile = _parse_voice_json(raw)
    profile["raw_samples"] = truncated

    log.info(
        "brand_voice.analyzed",
        bot_id=bot_id,
        sample_chars=len(truncated),
        tone=profile["tone"],
        trait_count=len(profile["personality_traits"]),
    )
    return profile


def render_voice_block(brand_voice) -> str:
    """Render a BrandVoice ORM row as a system-prompt block.

    Returns "" when the row is missing, inactive, or has nothing useful to
    say — caller can concatenate the result unconditionally.
    """
    if not brand_voice or not getattr(brand_voice, "is_active", False):
        return ""

    tone = getattr(brand_voice, "tone", None)
    vocabulary = getattr(brand_voice, "vocabulary", None)
    avoid = getattr(brand_voice, "avoid", None)

    traits_raw = getattr(brand_voice, "personality_traits", None)
    traits_list: list = []
    if traits_raw:
        try:
            parsed = json.loads(traits_raw)
            if isinstance(parsed, list):
                traits_list = [str(t) for t in parsed]
        except (json.JSONDecodeError, TypeError):
            # Fail open — bad JSON on disk shouldn't crash the chat path.
            traits_list = []

    # If every facet is missing, don't pollute the prompt with an empty header.
    if not any([tone, vocabulary, traits_list, avoid]):
        return ""

    lines = ["", "BRAND VOICE:"]
    if tone:
        lines.append(f"- Tone: {tone}")
    if vocabulary:
        lines.append(f"- Vocabulary: {vocabulary}")
    if traits_list:
        lines.append(f"- Personality: {', '.join(traits_list)}")
    if avoid:
        lines.append(f"- Avoid: {avoid}")
    lines.append("")  # trailing blank to separate from next block
    return "\n".join(lines)
