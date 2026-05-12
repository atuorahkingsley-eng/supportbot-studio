from difflib import SequenceMatcher
import re


def similarity(a: str, b: str) -> float:
    """Combined similarity: best of sequence match and keyword overlap."""
    a_clean = a.lower().strip()
    b_clean = b.lower().strip()

    # 1. Original sequence matching
    seq_score = SequenceMatcher(None, a_clean, b_clean).ratio()

    # 2. Keyword overlap (ignores word order)
    a_words = set(_extract_keywords(a_clean))
    b_words = set(_extract_keywords(b_clean))

    if not a_words or not b_words:
        return seq_score

    overlap = a_words & b_words
    keyword_score = len(overlap) / max(len(a_words), len(b_words))

    # 3. Stem-aware overlap (catches "secure" vs "secured")
    a_stems = set(_simple_stem(w) for w in a_words)
    b_stems = set(_simple_stem(w) for w in b_words)
    stem_overlap = a_stems & b_stems
    stem_score = len(stem_overlap) / max(len(a_stems), len(b_stems))

    # Return the best score
    return max(seq_score, keyword_score, stem_score)


STOP_WORDS = {
    "i", "me", "my", "we", "our", "you", "your", "the", "a", "an",
    "is", "are", "was", "were", "be", "been", "being", "do", "does",
    "did", "have", "has", "had", "can", "could", "will", "would",
    "should", "may", "might", "shall", "to", "of", "in", "for",
    "on", "at", "by", "with", "from", "about", "into", "how",
    "what", "when", "where", "which", "who", "that", "this",
    "it", "if", "or", "and", "but", "not", "no", "so", "up",
    "out", "just", "get", "got", "please", "thanks", "thank",
}


def _extract_keywords(text: str) -> list:
    """Extract meaningful words, removing stop words."""
    words = re.findall(r"[\w']+", text.lower())
    return [w for w in words if w not in STOP_WORDS and len(w) > 1]


def _simple_stem(word: str) -> str:
    """Basic suffix stripping — catches secured/secure, files/file, etc."""
    for suffix in ["ing", "tion", "ed", "es", "ly", "er", "est", "ment", "ness", "ful", "less", "able", "ible", "al", "ous", "ive", "s"]:
        if word.endswith(suffix) and len(word) - len(suffix) >= 3:
            return word[:-len(suffix)]
    return word