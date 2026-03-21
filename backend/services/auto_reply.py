from typing import Optional
from backend.utils.text_similarity import similarity


def find_auto_reply(user_message: str, faqs: list, threshold: float = 0.65) -> Optional[str]:
    """
    Compare user_message against all FAQ questions.
    Uses combined fuzzy + keyword + stem matching.
    If similarity >= threshold, return the FAQ answer.
    Otherwise return None (falls through to Claude).
    """
    best_score = 0.0
    best_answer = None

    for faq in faqs:
        score = similarity(user_message, faq.question)
        if score > best_score:
            best_score = score
            best_answer = faq.answer

    if best_score >= threshold:
        return best_answer

    return None